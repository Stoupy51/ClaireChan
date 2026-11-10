""" The child sessions she starts with `claude --bg`, which the user reads in their Code list, and the end of their work. """
# Imports
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from stouputils.typing import JsonDict

from clairechan.config import Config
from clairechan.i18n import tr
from clairechan.services import agents
from clairechan.session import NESTED_SESSION_VARS

# Constants
POLL_S: int = 15
SHORT_JOB_S: int = 60
""" A child that never shows as working is done once it has been idle this long. """
CHILD_TOOLS: tuple[str, ...] = (
	"screenshot", "minecraft_start", "minecraft_state", "minecraft_connect", "minecraft_disconnect", "minecraft_command",
	"minecraft_chat", "minecraft_hold", "minecraft_look", "minecraft_screenshot", "minecraft_quit",
)
""" Her tools a child may use: the screen and the Minecraft test client. """
STARTED: re.Pattern[str] = re.compile(r"backgrounded\W+(?P<id>[0-9a-f]+)")
""" The line `claude --bg` prints, such as "backgrounded · c63df584 · Name". """


# Classes
class Children(QObject):
	finished = Signal(str, str)
	""" A child's turn ended, with its name and id. """

	def __init__(self) -> None:
		super().__init__()
		self.waiting: dict[str, str] = {}
		""" The children not done yet, by id, with their name. """
		self.tools_url = ""
		""" Where her tools are served, set at startup so that children can test Minecraft and take screenshots. """

	def start(self, name: str, brief: str, folder: str, model: str = "", effort: str = "") -> str:
		""" Starts the child in `folder` and has it watched. Never `claude stop` it: that removes it from the user's list.

		Args:
			model:  As `claude --model` takes it, empty for the default one.
			effort: As `claude --effort` takes it, empty for the default one.
		"""
		trust(folder)
		options = [*(["--model", model] if model else []), *(["--effort", effort] if effort else [])]
		tools = json.dumps({"mcpServers": {"clairechan": {"type": "http", "url": self.tools_url, "alwaysLoad": True}}})
		allowed = [f"mcp__clairechan__{tool}" for tool in CHILD_TOOLS]
		run = claude("--bg", "-n", name, *options, "--mcp-config", tools, "--allowedTools", *allowed, "--", brief, cwd=folder)
		if not (started := STARTED.search(run.stdout)):
			failure = f"{run.stdout} {run.stderr}"
			return tr(f"The child session did not start: {failure}", f"La session fille n'a pas démarré : {failure}")
		self.waiting[started["id"]] = name
		threading.Thread(target=self.watch, args=(started["id"], name), daemon=True).start()
		return tr(
			f"Child session {name} ({started['id']}) started, the user reads it in the Code list. You are told when it has finished.",
			f"Session fille {name} ({started['id']}) lancée, l'utilisateur la lit dans sa liste Code. Tu seras prévenue à la fin.",
		)

	def watch(self, child_id: str, name: str) -> None:
		""" Polls until the child is idle after having worked, or has been idle for `SHORT_JOB_S`, or has left the list. """
		began = time.time()
		worked = False
		session = ""
		while True:
			time.sleep(POLL_S)
			row = sessions().get(child_id)
			status = row["status"] if row else None
			session = row["sessionId"] if row else session
			worked = worked or status == "busy"
			if status is None or (status == "idle" and (worked or time.time() - began > SHORT_JOB_S)):
				break

		self.waiting.pop(child_id, None)
		agents.log_child_usage(session, name)
		self.finished.emit(name, child_id)


# Constants
CHILDREN: Children = Children()
""" The child sessions of this run of the app, kept by a reload as long as this line does not change. """


# Functions
def trust(folder: str) -> None:
	""" Has Claude Code trust `folder` when it sits in the `trusted_folders` setting, as `claude --bg` needs. """
	path = Path(folder).resolve()
	if not any(path.is_relative_to(root) for root in Config.load().trusted_folders):
		return
	file = Path.home() / ".claude.json"
	settings: JsonDict = json.loads(file.read_text(encoding="utf-8"))
	projects: JsonDict = settings.setdefault("projects", {})
	# Claude Code writes the drive letter in either case, and reads the key it wrote
	keys = [key for key in projects if key.lower() == path.as_posix().lower()] or [path.as_posix()]
	if all(projects.get(key, {}).get("hasTrustDialogAccepted") for key in keys):
		return

	for key in keys:
		projects.setdefault(key, {})["hasTrustDialogAccepted"] = True
	# Claude Code rewrites this file too: replacing it in one step never leaves it half written
	draft = file.with_name(".claude.json.clairechan")
	draft.write_text(json.dumps(settings, indent=2), encoding="utf-8")
	draft.replace(file)


def claude(*arguments: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
	env = {name: value for name, value in os.environ.items() if name not in NESTED_SESSION_VARS}
	return subprocess.run(
		["claude", *arguments], cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
		timeout=60, creationflags=subprocess.CREATE_NO_WINDOW,
	)


def sessions() -> dict[str, JsonDict]:
	""" What `claude agents` tells about each background session, its `status` and `sessionId` among it, by id. """
	rows: list[JsonDict] = json.loads(claude("agents", "--json").stdout)
	return {row["id"]: row for row in rows if row["kind"] == "background"}

