""" The child sessions she starts with `claude --bg`, which the user reads in their Code list, and the end of their work. """
# Imports
import json
import os
import re
import subprocess
import threading
import time

from PySide6.QtCore import QObject, Signal
from stouputils.typing import JsonDict

from clairechan.i18n import tr
from clairechan.session import NESTED_SESSION_VARS

# Constants
POLL_S: int = 15
SHORT_JOB_S: int = 60
""" A child that never shows as working is done once it has been idle this long. """
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

	def start(self, name: str, brief: str, folder: str) -> str:
		""" Starts the child in `folder` and has it watched. Never `claude stop` it: that removes it from the user's list. """
		run = claude("--bg", "-n", name, brief, cwd=folder)
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
		while True:
			time.sleep(POLL_S)
			status = states().get(child_id)
			worked = worked or status == "busy"
			if status is None or (status == "idle" and (worked or time.time() - began > SHORT_JOB_S)):
				break
		self.waiting.pop(child_id, None)
		self.finished.emit(name, child_id)


# Constants
CHILDREN: Children = Children()
""" The child sessions of this run of the app, kept by a reload as long as this line does not change. """


# Functions
def claude(*arguments: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
	env = {name: value for name, value in os.environ.items() if name not in NESTED_SESSION_VARS}
	return subprocess.run(
		["claude", *arguments], cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
		timeout=60, creationflags=subprocess.CREATE_NO_WINDOW,
	)


def states() -> dict[str, str]:
	""" The status of each background session, by id. """
	rows: list[JsonDict] = json.loads(claude("agents", "--json").stdout)
	return {row["id"]: row["status"] for row in rows if row["kind"] == "background"}

