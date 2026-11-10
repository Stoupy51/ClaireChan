""" The line between the app's two processes: one JSON message per line over a local socket, some of them asking for a reply. """
# Imports
import json
import threading
from concurrent.futures import Future

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalSocket
from stouputils.typing import JsonDict


# Classes
class Link(QObject):
	""" One end of the line. A message may be sent from any thread, and is received on the Qt thread. """
	received = Signal(str, dict)
	""" The kind of a message and its fields. One that asks for a reply holds under `ask` the number `reply` takes. """
	outgoing = Signal(bytes)
	""" A line to write, which brings it to the Qt thread, the only one that may use the socket. """

	def __init__(self) -> None:
		super().__init__()
		self.socket: QLocalSocket | None = None
		self.waiting: list[bytes] = []
		""" Lines sent while the other end is away, written once it is back. """
		self.asked: dict[int, Future[JsonDict]] = {}
		self.lock = threading.Lock()
		self.outgoing.connect(self.write)

	def attach(self, socket: QLocalSocket) -> None:
		""" Takes the socket of the other end, which may have started again, and writes what waited for it. """
		self.socket = socket
		socket.readyRead.connect(self.read)
		for line in self.waiting:
			socket.write(line)
		self.waiting = []

	def send(self, kind: str, **fields: object) -> None:
		self.outgoing.emit(json.dumps({"kind": kind, **fields}).encode() + b"\n")

	def ask(self, kind: str, **fields: object) -> Future[JsonDict]:
		""" Sends a message whose reply is set on the future, which a thread other than the Qt one may wait for. """
		answer: Future[JsonDict] = Future()
		with self.lock:
			number = max(self.asked, default=0) + 1
			self.asked[number] = answer
		self.send(kind, ask=number, **fields)
		return answer

	def reply(self, number: int, **fields: object) -> None:
		self.send("reply", to=number, **fields)

	def write(self, line: bytes) -> None:
		if self.socket and self.socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
			self.socket.write(line)
		else:
			self.waiting.append(line)

	def read(self) -> None:
		while self.socket and self.socket.canReadLine():
			message: JsonDict = json.loads(bytes(self.socket.readLine().data()))
			kind: str = message.pop("kind")
			if kind != "reply":
				self.received.emit(kind, message)
				continue
			# A reply to an end that has started again since it asked finds nothing waiting for it
			with self.lock:
				answer = self.asked.pop(message.pop("to"), None)
			if answer:
				answer.set_result(message)


# Constants
PEER: Link = Link()
""" The app's other process: the face for the core, the core for the face. """

