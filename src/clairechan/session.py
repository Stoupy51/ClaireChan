""" The hidden Claude Code session: `claude --remote-control` in a pseudo terminal, and the hook events it posts to the app. """
# Imports
import json
import re
import subprocess
import threading
import time
import uuid
import webbrowser
from collections.abc import Callable
from concurrent.futures import CancelledError, Future
from email.message import Message
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

import pyte
from PySide6.QtCore import QObject, QTimer, Signal, SignalInstance
from stouputils.typing import JsonDict
from winpty import PtyProcess

from clairechan.claude_code import HOME, SESSION_ID, environment
from clairechan.config import APP_DATA, CAPTURES, ROOT, SCREENSHOTS, USER_CONFIG, Config

# Constants
SYSTEM_PROMPT: str = (
	f"You are Claire, the voice of ClaireChan, a voice assistant app installed in {ROOT} that keeps its settings in {USER_CONFIG}.\n"
	"ClaireChan started this Claude Code session hidden in a pseudo-terminal, with Remote Control and the auto permission mode, "
	"resumes it each time the app starts, and follows it through hooks to animate your avatar on the screen.\n"
	f"The session works in {HOME}, a folder of your own. To change ClaireChan's code, work in {ROOT} and read its CLAUDE.md first.\n"
	"Prompts come from the user's voice, transcribed by Whisper, which can mishear words, "
	"or from the Remote Control on claude.ai or in the Claude app on their iPhone.\n"
	"Your replies appear in a speech bubble next to your avatar, which scrolls through long ones at reading pace.\n"
	"Your clairechan tools act on the user's computer, such as screenshots and transcribing meetings: "
	"use them rather than writing scripts.\n"
)
""" What the app tells the session about itself, before the user's additions from the config. """
REVIEW_CHANGES: str = "Never commit your changes to ClaireChan's own code: the user reviews and commits them.\n"
""" What the session does with its changes to the app's code while `commit_changes` is off. """
COMMIT_CHANGES: str = (
	"Commit each change you make to ClaireChan's own code, on the branch checked out, with a short conventional commit message: "
	"the user allows it here, whatever their CLAUDE.md says.\n"
)
WORKER_DESCRIPTION: str = (
	"Handles complicated requests in the background: writing or changing code, research, and tasks with several steps. "
	"Hand such requests to it so that you stay free for quick ones, and tell the user when it has started."
)
""" When the session delegates to the worker. Like `WORKER_PROMPT`, it goes through cmd.exe, which mangles & | < > ^ % ( ). """
WORKER_PROMPT: str = (
	"You carry out a complicated request for Claire, the user's voice assistant, in the background. "
	"Finish it on your own, then report the result in a few sentences: they are shown in a small speech bubble."
)
HOOK_EVENTS: tuple[str, ...] = (
	"UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Notification", "MessageDisplay",
	"SubagentStart", "SubagentStop", "Stop", "StopFailure", "PreCompact", "PostCompact",
)
RESUME_DIALOG: str = "Resume full session as-is"
""" Option of the dialog Claude Code shows when it resumes a large session after a long pause. """
COMPACT_ABOVE_TOKENS: int = 100_000
""" Context size worth a `/compact`: a fresh session already holds about 50k tokens of system prompt and tools. """
SESSION_URL: re.Pattern[str] = re.compile(r"https://claude\.ai/code/session_\w+")
ANSWER_WAIT_S: float = 60.0
""" How long a permission request waits for the user's spoken answer before the dialog is left to them. """
PASTE_DELAY_MS: int = 400
""" Pause between the text and Enter, so the TUI takes the text as one paste before submitting it. """


# Classes
class HookServer(QObject):
	""" Local endpoint for the session's `type: "http"` hooks, relaying each payload to the Qt thread. """
	posted = Signal(dict)
	asked = Signal(Future)
	""" A permission request waiting for the user's answer: its future gets True to allow it and False to deny it. """

	def __init__(self, ask_first: Callable[[str, JsonDict], str | None]) -> None:
		""" Starts the endpoint.

		Args:
			ask_first: Why the session must ask the user before a tool call, from its name and input, None when it need not.
		"""
		super().__init__()
		relay, ask = self.posted, self.asked

		class Handler(BaseHTTPRequestHandler):
			def do_POST(self) -> None:
				if not is_local_request(self.headers):
					self.send_error(403)
					return
				event = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
				relay.emit(event)
				match event["hook_event_name"]:
					case "PermissionRequest":
						body = wait_for_answer(ask)
					case "PreToolUse" if reason := ask_first(event["tool_name"], event["tool_input"]):
						decision = {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": reason}
						body = json.dumps({"hookSpecificOutput": decision}).encode()
					case _:
						body = b""
				self.send_response(200)
				self.send_header("Content-Length", str(len(body)))
				self.end_headers()
				self.wfile.write(body)

			@override
			def log_message(self, format: str, *args: Any) -> None:
				pass

		server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		self.url = f"http://127.0.0.1:{server.server_port}"
		threading.Thread(target=server.serve_forever, daemon=True).start()


class Session(QObject):
	""" Claude Code started in its own folder, resuming the saved conversation, with its hooks posting to `hooks_url`. """
	compacted = Signal()
	died = Signal()
	""" Claude Code stopped by itself, with whatever it was running. """

	def __init__(self, hooks_url: str, tools_url: str, config: Config) -> None:
		super().__init__()
		self.settings = APP_DATA / "session_settings.json"
		waits = {"PermissionRequest": ANSWER_WAIT_S + 10}
		hooks = {name: [{"hooks": [{"type": "http", "url": hooks_url, "timeout": waits.get(name, 5)}]}] for name in HOOK_EVENTS}
		self.settings.write_text(json.dumps({"hooks": hooks, "inputNeededNotifEnabled": True}), encoding="utf-8")
		self.id = SESSION_ID.read_text() if SESSION_ID.exists() else ""
		self.transcript = ""
		self.busy = False
		""" Whether a turn or a compaction runs, between the hooks that open and close them. """
		self.screen_lock = threading.Lock()
		self.tools_url = tools_url
		self.url = "https://claude.ai/code"
		self.started = threading.Event()
		""" Set once Remote Control prints the session's URL, when the session is ready for prompts. """
		self.start(config)

	def start(self, config: Config) -> None:
		""" Starts Claude Code with the config's models and prompt, which it reads only then, resuming the conversation if any. """
		prompt = APP_DATA / "session_prompt.md"
		prompt.write_text(system_prompt(config.prompt, commit=config.commit_changes), encoding="utf-8")
		for folder in (HOME, CAPTURES, SCREENSHOTS):
			folder.mkdir(parents=True, exist_ok=True)
		worker = {"description": WORKER_DESCRIPTION, "prompt": WORKER_PROMPT, "model": config.agent_model, "background": True}
		resume = ["--resume", self.id] if self.id else ["--session-id", str(uuid.uuid4())]
		# Deferred behind tool search, her tools would show the session their names only, so it would pick the ones it already loaded
		tools = json.dumps({"mcpServers": {"clairechan": {"type": "http", "url": self.tools_url, "alwaysLoad": True}}})
		claude = [
			"claude", "--remote-control", "ClaireChan", "--permission-mode", "auto", "--model", config.model,
			"--agents", json.dumps({"worker": worker}), "--mcp-config", tools, "--allowedTools", "mcp__clairechan",
			"--settings", str(self.settings), "--append-system-prompt-file", str(prompt), *resume,
			"--add-dir", str(ROOT), str(CAPTURES), str(SCREENSHOTS),
		]
		# chcp 65001: without it the pseudo console feeds Claude Code accented letters in cp850
		argv = ["cmd.exe", "/c", "chcp", "65001", ">nul", "&&", *claude]
		self.alive = True
		self.started_at = time.monotonic()
		self.pty = PtyProcess.spawn(argv, cwd=str(HOME), env=environment(), dimensions=(50, 200))
		self.screen = pyte.Screen(200, 50)
		""" What the terminal shows, rebuilt from its output: Claude Code only redraws the characters that change. """
		threading.Thread(target=self.read_output, args=(self.pty, self.screen), daemon=True).start()

	def restart(self, config: Config) -> None:
		""" Claude Code started again on the same conversation, to apply settings it reads only when it starts. """
		self.close()
		self.start(config)

	def read_output(self, pty: PtyProcess, screen: pyte.Screen) -> None:
		""" Renders the terminal's output, read continuously so the session never blocks on a full pipe. """
		stream = pyte.Stream(screen)
		resume_answered = False
		while pty.isalive():
			try:
				output = pty.read(4096)
			except EOFError:
				break
			with self.screen_lock:
				stream.feed(output)
			shown = self.text()
			# Enter picks its first option, "Resume from summary", which Claude Code recommends
			if not resume_answered and RESUME_DIALOG in shown:
				resume_answered = True
				pty.write("\r")
			if not self.started.is_set() and (match := SESSION_URL.search(shown)):
				self.url = match.group()
				self.started.set()

		# Neither closed by the app nor replaced by the Claude Code a restart started since
		if self.alive and pty is self.pty:
			self.died.emit()

	def text(self) -> str:
		with self.screen_lock:
			return "\n".join(self.screen.display)

	def on_hook(self, event: JsonDict) -> None:
		self.transcript = event["transcript_path"]
		if event["session_id"] != self.id:
			self.id = event["session_id"]
			SESSION_ID.write_text(self.id)
		match event["hook_event_name"]:
			case "UserPromptSubmit":
				self.busy = True
			case "Stop" | "StopFailure":
				self.busy = False
			# Claude Code compacts on its own during a turn, which stays busy
			case "PreCompact" if event["trigger"] != "auto":
				self.busy = True
			case "PostCompact" if event["trigger"] != "auto":
				self.busy = False
				self.compacted.emit()
			case _:
				pass

	def compact(self) -> bool:
		""" Types `/compact` when the conversation is large enough to be worth that request, and says whether it did. """
		if not self.transcript or context_tokens(Path(self.transcript)) < COMPACT_ABOVE_TOKENS:
			return False
		self.send("/compact")
		return True

	def send(self, prompt: str) -> None:
		self.pty.write(prompt)
		QTimer.singleShot(PASTE_DELAY_MS, partial(self.pty.write, "\r"))

	def open(self) -> None:
		webbrowser.open(self.url)

	def close(self) -> None:
		""" Kills Claude Code outright: on a clean exit, Remote Control archives the session, which drops it from claude.ai's list. """
		self.alive = False
		kill = ["taskkill", "/F", "/T", "/PID", str(self.pty.pid)]
		subprocess.run(kill, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)


# Functions
def is_local_request(headers: Message) -> bool:
	""" Whether a request comes from a program of this computer, not a web page (`Origin`, rebound `Host`).

	>>> request = Message()
	>>> request["Host"] = "127.0.0.1:50000"
	>>> is_local_request(request)
	True
	>>> request["Origin"] = "https://example.com"
	>>> is_local_request(request)
	False
	>>> del request["Origin"]
	>>> request.replace_header("Host", "example.com:50000")
	>>> is_local_request(request)
	False
	"""
	return "Origin" not in headers and re.fullmatch(r"127\.0\.0\.1:\d+", headers.get("Host", "")) is not None


def wait_for_answer(ask: SignalInstance) -> bytes:
	""" The hook's reply to a permission request: the user's spoken decision, or nothing so that the dialog stays as it is. """
	answer: Future[bool] = Future()
	ask.emit(answer)
	try:
		allowed = answer.result(ANSWER_WAIT_S)
	except (TimeoutError, CancelledError):
		return b"{}"
	decision = {"behavior": "allow"} if allowed else {"behavior": "deny", "message": "The user refused it by voice."}
	return json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}).encode()


def system_prompt(additions: str, *, commit: bool) -> str:
	""" Text for `--append-system-prompt-file`: `SYSTEM_PROMPT`, the rule on committing, then the user's additions when there are any.

	>>> system_prompt("\\n", commit=False) == SYSTEM_PROMPT + REVIEW_CHANGES
	True
	>>> system_prompt("Mes jeux sont dans E:/Games.\\n", commit=True).removeprefix(SYSTEM_PROMPT + COMMIT_CHANGES)
	'\\nMes jeux sont dans E:/Games.'
	"""
	base = SYSTEM_PROMPT + (COMMIT_CHANGES if commit else REVIEW_CHANGES)
	return f"{base}\n{additions.strip()}" if additions.strip() else base


def context_tokens(transcript: Path) -> int:
	""" Size of a conversation at its last reply, 0 when it was compacted since. """
	for line in reversed(transcript.read_text(encoding="utf-8").splitlines()):
		entry = json.loads(line)
		if entry.get("subtype") == "compact_boundary":
			return 0
		if usage := entry.get("message", {}).get("usage"):
			return usage["input_tokens"] + usage["cache_read_input_tokens"] + usage["cache_creation_input_tokens"]
	return 0

