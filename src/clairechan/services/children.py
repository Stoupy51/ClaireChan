""" The child sessions she starts with `claude --bg`, which the user reads in their Code list, and the end of their work. """
# Imports
import json
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from clairechan.claude_code import background, run, trust
from clairechan.config import APP_DATA, Config
from clairechan.i18n import tr
from clairechan.services import agents

# Constants
POLL_S: int = 15
SHORT_JOB_S: int = 60
""" A child that never shows as working is done once it has been idle this long. """
WAITING: Path = APP_DATA / "children.json"
""" The name of each child not done yet, by its id, for the face that starts again to keep watching them. """


# Classes
class Children(QObject):
	finished = Signal(str, str)
	""" A child's turn ended, with its name and id. """

	def __init__(self) -> None:
		super().__init__()
		self.waiting: dict[str, str] = {}
		""" The children not done yet, by id, with their name. """
		self.tools_url = ""
		""" Where the tools a child may use are served, set at startup. """

	def start(self, name: str, brief: str, folder: str, model: str = "", effort: str = "") -> str:
		""" Starts the child in `folder` and has it watched. Never `claude stop` it: that removes it from the user's list.

		Args:
			model:  As `claude --model` takes it, empty for the default one.
			effort: As `claude --effort` takes it, empty for the default one.
		"""
		path = Path(folder).resolve()
		if any(path.is_relative_to(root) for root in Config.load().trusted_folders):
			trust.trust(path)
		options = [*(["--model", model] if model else []), *(["--effort", effort] if effort else [])]
		tools = json.dumps({"mcpServers": {"clairechan": {"type": "http", "url": self.tools_url, "alwaysLoad": True}}})
		result = run("--bg", "-n", name, *options, "--mcp-config", tools, "--allowedTools", "mcp__clairechan", "--", brief, cwd=folder)
		if not (child_id := background.started_id(result.stdout)):
			failure = f"{result.stdout} {result.stderr}"
			return tr(f"The child session did not start: {failure}", f"La session fille n'a pas démarré : {failure}")
		self.follow(child_id, name)
		return tr(
			f"Child session {name} ({child_id}) started, the user reads it in the Code list. You are told when it has finished.",
			f"Session fille {name} ({child_id}) lancée, l'utilisateur la lit dans sa liste Code. Tu seras prévenue à la fin.",
		)

	def resume(self) -> None:
		""" Watches again the children a previous run was waiting for. """
		waiting: dict[str, str] = json.loads(WAITING.read_text(encoding="utf-8")) if WAITING.exists() else {}
		for child_id, name in waiting.items():
			self.follow(child_id, name)

	def follow(self, child_id: str, name: str) -> None:
		self.waiting[child_id] = name
		WAITING.write_text(json.dumps(self.waiting), encoding="utf-8")
		threading.Thread(target=self.watch, args=(child_id, name), daemon=True).start()

	def watch(self, child_id: str, name: str) -> None:
		""" Polls until the child is idle after having worked, or has been idle for `SHORT_JOB_S`, or has left the list. """
		began = time.time()
		worked = False
		session = ""
		while True:
			time.sleep(POLL_S)
			row = background.sessions().get(child_id)
			status = row["status"] if row else None
			session = row["sessionId"] if row else session
			worked = worked or status == "busy"
			if status is None or (status == "idle" and (worked or time.time() - began > SHORT_JOB_S)):
				break

		self.waiting.pop(child_id, None)
		WAITING.write_text(json.dumps(self.waiting), encoding="utf-8")
		agents.log_child_usage(session, name)
		self.finished.emit(name, child_id)


# Constants
CHILDREN: Children = Children()
""" The child sessions she waits for. """

