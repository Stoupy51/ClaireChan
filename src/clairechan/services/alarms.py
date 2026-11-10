""" The timers she keeps, which ring even when her face has started again since they were set. """
# Imports
import json
import time
from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from clairechan.config import APP_DATA

# Constants
PENDING: Path = APP_DATA / "alarms.json"
""" When each timer not rung yet rings, in seconds since the epoch, with what it was set for. """


# Classes
class Alarms(QObject):
	rang = Signal(str)
	""" A timer ended, with what it was set for. """

	def __init__(self) -> None:
		super().__init__()
		self.pending: list[tuple[float, str]] = []

	def start(self, seconds: int, label: str) -> None:
		""" Rings after `seconds`, from the Qt thread. """
		self.arm(time.time() + seconds, label)

	def resume(self) -> None:
		""" Arms again the timers a previous run left pending, those due since ringing at once. """
		pending: list[tuple[float, str]] = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else []
		for due, label in pending:
			self.arm(due, label)

	def arm(self, due: float, label: str) -> None:
		self.pending.append((due, label))
		PENDING.write_text(json.dumps(self.pending), encoding="utf-8")
		QTimer.singleShot(max(0, round(1000 * (due - time.time()))), partial(self.ring, due, label))

	def ring(self, due: float, label: str) -> None:
		self.pending.remove((due, label))
		PENDING.write_text(json.dumps(self.pending), encoding="utf-8")
		self.rang.emit(label)


# Constants
ALARMS: Alarms = Alarms()
""" The timers set by voice or by the session. """

