""" ClaireChan's core: the hidden Claude Code session, her ears and her voice, in the process that lasts as long as the app runs.

Her face (`clairechan.face`: her windows, her reactions and her actions) is a process of its own, which the core starts,
talks to over a local socket, and starts again alone to apply a change to its code.
"""
# Imports
import faulthandler
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import Future
from datetime import datetime
from functools import partial
from logging.handlers import RotatingFileHandler
from pathlib import Path

import stouputils as stp
from PySide6.QtCore import QCoreApplication, QFileSystemWatcher, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from stouputils.typing import JsonDict

from clairechan import i18n, launcher
from clairechan.changes import Changes, reach_this_process
from clairechan.claude_code import probes
from clairechan.config import APP_DATA, CRASH_FILE, LOG_FILE, USER_CONFIG, Config
from clairechan.console import enable_colors
from clairechan.launcher import CHANGED, READY, RESTART, SET_ASIDE
from clairechan.link import PEER
from clairechan.mcp import ActionServer
from clairechan.services import claude
from clairechan.session import HookServer, Session
from clairechan.voice.audio import GPU, microphone
from clairechan.voice.listener import Listener
from clairechan.voice.meeting import MEETING
from clairechan.voice.speech import Voice, Vowels

# Constants
LOG: logging.Logger = logging.getLogger("clairechan")
""" The app's own log, kept at INFO while the libraries stay at WARNING. """
LOG_BYTES: int = 5_000_000
LOG_BACKUPS: int = 20
""" The log is cut every `LOG_BYTES`, and these many older files are kept besides the current one (about 100 MB, weeks of use). """
CRASH_MARKER: str = "=== start "
""" Written to the crash file at each start, so that what follows the last one is what the last run left. """
STARTUP_S: float = 60.0
""" How long the session, Whisper and her face may take to start before the app reports them as failed. """
FACE_START_S: float = 20.0
""" How long her face may take to say hello before the change it starts on is put aside, or it is started once more. """
FACE_SETTLED_S: float = 60.0
""" A face that ran this long before stopping by itself is not counted with the ones that stopped before it. """
ASK_FIRST_S: float = 4.0
""" How long a tool call waits for her face to say whether the user must be asked first, within the 5 s its hook has. """
SESSION_RETRY_S: float = 60.0
""" A Claude Code that stops sooner than this after it started is not started again, as it would stop again. """
COMPACT_TIMEOUT_MS: int = 180_000
""" How long quitting waits for the session's compaction. """
RESTART_DELAY_MS: int = 2500
""" How long she keeps to say she restarts before the app quits. """
FULL_RESTART: str = '{"files": [], "since": ""}'
""" The change line of a restart that applies no change to the code, so the launcher puts nothing aside. """
INSTANCE_NAME: str = "ClaireChan"
""" Local server of the running app: a new one connects to it to have it quit. """
PIPES: str = "\\\\.\\pipe\\"
""" Where Windows lists the named pipes, the local server among them, without connecting to them. """
SAVED_MS: int = 300
""" Quiet time after the config file changed before it is read, as editors write it in several steps. """


# Classes
class Face(QObject):
	""" Her face, a process started again when it stops by itself or to apply a change to its code. """
	stopped = Signal(object)
	""" The process that ended, told by the thread that read its log. """
	gave_up = Signal()
	""" Her face keeps stopping, on code that is not a change to put aside. """

	def __init__(self) -> None:
		super().__init__()
		self.changes = Changes()
		self.edited: list[str] = []
		""" The files of the change her starting face applies, put aside if it does not start. """
		self.aside = os.environ.get(SET_ASIDE, "")
		""" The files of a change that broke the app and was put aside, which she tells the user once. """
		self.stops = 0
		self.closing = False
		self.ready = threading.Event()
		""" Set once a face has said hello. """
		self.server = QLocalServer(self)
		self.server.listen(f"{INSTANCE_NAME}-{os.getpid()}")
		self.server.newConnection.connect(lambda: PEER.attach(self.server.nextPendingConnection()))
		self.late = QTimer(self, singleShot=True, interval=round(1000 * FACE_START_S))
		self.late.timeout.connect(self.on_failed)
		self.stopped.connect(self.on_stopped)
		self.start()

	def start(self) -> None:
		self.started_at = time.monotonic()
		self.process = subprocess.Popen(
			[sys.executable, "-m", "clairechan.face", self.server.serverName()], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
		)
		threading.Thread(target=self.relay_log, args=(self.process,), daemon=True).start()
		self.late.start()

	def relay_log(self, process: subprocess.Popen[str]) -> None:
		""" Writes what the face logs, and the errors it prints, in the app's log until it ends. """
		assert process.stderr
		for line in process.stderr:
			LOG.info("Face: %s", line.rstrip())
		self.stopped.emit(process)

	def apply_changes(self) -> None:
		""" Starts again what runs the code the session changed, if it did: her face alone, or the whole app. """
		edited = self.changes.edited()
		if not edited:
			return
		if reach_this_process(edited):
			LOG.info("Restarting the app for: %s", ", ".join(edited))
			restart(json.dumps({"files": edited, "since": self.changes.since}))
			return

		LOG.info("Restarting her face for: %s", ", ".join(edited))
		self.edited = edited
		self.replace()

	def replace(self) -> None:
		old = self.process
		self.start()
		old.kill()

	def on_hello(self) -> None:
		LOG.info("Her face is there, %.1f s after it started", time.monotonic() - self.started_at)
		self.late.stop()
		self.ready.set()
		self.changes.applied()
		self.edited = []
		if self.aside:
			PEER.send("set_aside", reason=self.aside)
			self.aside = ""

	def on_stopped(self, process: subprocess.Popen[str]) -> None:
		if process is self.process and not self.closing:
			self.on_failed()

	def on_failed(self) -> None:
		""" Her face stopped by itself or did not say hello in time: its change is put aside, or it starts again a few times. """
		if self.edited:
			LOG.error("Her face does not start on this change, put aside: %s", ", ".join(self.edited))
			launcher.set_aside(self.edited, self.changes.since)
			self.aside = ", ".join(Path(file).name for file in self.edited)
			self.edited = []
		else:
			self.stops = self.stops + 1 if time.monotonic() - self.started_at < FACE_SETTLED_S else 1
			LOG.error("Her face stopped by itself, %s time in a row", self.stops)
			if self.stops >= launcher.MAX_CRASHES:
				self.gave_up.emit()
				return
		self.replace()

	def close(self) -> None:
		self.closing = True
		self.process.kill()


class Core(QObject):
	""" Carries out what her face asks of the session, her ears and her voice. """

	def __init__(self, face: Face, session: Session, tools: ActionServer, listener: Listener, voice: Voice) -> None:
		super().__init__()
		self.face, self.session, self.tools, self.listener, self.voice = face, session, tools, listener, voice
		self.permissions: dict[int, Future[bool]] = {}
		""" The permission requests waiting for the user's answer, by the number her face was given. """
		PEER.received.connect(self.on_message)

	def on_message(self, kind: str, fields: JsonDict) -> None:
		match kind:
			case "hello":
				self.listener.phrases = {name: re.compile(phrase, re.IGNORECASE) for name, phrase in fields["phrases"].items()}
				# Claude Code reads the tools of a server only when it starts
				if self.tools.offer(fields["tools"]):
					self.session.restart(self.listener.config)
				PEER.send("welcome", tools_url=self.tools.urls["child"])
				self.face.on_hello()
			case "type":
				self.session.send(fields["text"])
			case "restart_session":
				self.session.restart(self.listener.config)
			case "compact":
				self.session.compact()
			case "open_session":
				self.session.open()
			case "say":
				self.voice.say(fields["text"], fields["style"])
			case "hush":
				self.voice.hush()
			case "volume":
				self.voice.volume = fields["value"]
			case "asking":
				self.listener.asking = fields["on"]
			case "cancel":
				self.listener.cancel()
			case "verdict":
				self.on_verdict(fields["request"], fields["allowed"])
			case "meeting":
				PEER.reply(fields["ask"], text=MEETING.start() if fields["on"] else MEETING.stop())
			case "free":
				self.face.apply_changes()
			case "quit":
				shut_down(self.session)
			case "restart_app":
				QTimer.singleShot(RESTART_DELAY_MS, partial(restart, FULL_RESTART))
			case _:
				LOG.warning("Unknown message from her face: %s", kind)

	def on_permission_asked(self, answer: Future[bool]) -> None:
		number = max(self.permissions, default=0) + 1
		self.permissions[number] = answer
		PEER.send("permission", request=number)

	def on_verdict(self, number: int, allowed: bool | None) -> None:
		""" Gives the hook that waits the user's answer, or None to leave the dialog to them. """
		answer = self.permissions.pop(number)
		if allowed is None:
			answer.cancel()
		else:
			answer.set_result(allowed)

	def on_session_died(self) -> None:
		if time.monotonic() - self.session.started_at < SESSION_RETRY_S:
			LOG.error("Claude Code stopped right after it started: it is not started again")
			return
		LOG.warning("Claude Code stopped by itself: starting it again on the same conversation")
		self.session.start(self.listener.config)
		PEER.send("session_lost")

	def reload_config(self, watcher: QFileSystemWatcher) -> None:
		""" Gives her ears and her voice the saved config. Her face tells the user about it, or that it cannot be read. """
		# Editors save by replacing the file, which drops it from the watch
		watcher.addPath(str(USER_CONFIG))
		try:
			config = Config.load()
		except Exception:
			return
		self.listener.config = config
		self.voice.volume = config.volume


# Functions
def main() -> None:
	""" Starts the app in the background and returns once it reports it is ready, so no console window stays open. """
	enable_colors()
	if INSTANCE_NAME in os.listdir(PIPES):
		stp.progress("ClaireChan is already running: shutting it down first, after it compacts its session when that is large...")
	stp.progress("Starting ClaireChan, which takes about 15 s...")
	# A gui-script would not do: uv makes the venv's pythonw.exe a copy of the console python.exe, which opens a window
	app = subprocess.Popen(
		[sys.executable, "-m", "clairechan.launcher"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
		text=True, creationflags=subprocess.CREATE_NO_WINDOW,
	)
	assert app.stdout
	for line in app.stdout:
		if line == READY:
			stp.info('Say "Hey Claire, ..." to ask her something, and quit her from her tray icon.')
			return
		print(line, end="", flush=True)
	stp.error(f"ClaireChan stopped while starting, see {stp.CYAN}{LOG_FILE}")


def tell_face(kind: str, value: object = None) -> None:
	""" Tells her face what her ears heard, with its language, which her own lines follow. """
	PEER.send(kind, value=value, language=i18n.heard)


def tell_hook(event: JsonDict) -> None:
	PEER.send("hook", event=event)


def tell_speaking(vowels: Vowels) -> None:
	PEER.send("speaking", vowels=vowels)


def ask_first(tool: str, tool_input: JsonDict) -> str | None:
	""" Why the session must ask the user before one of her tools acts, which her face knows, None when it need not. """
	if not tool.startswith("mcp__clairechan__"):
		return None
	try:
		return PEER.ask("reason", tool=tool, input=tool_input).result(ASK_FIRST_S)["reason"]
	except TimeoutError:
		return None


def report_ready(session: Session, listener: Listener, face: Face) -> None:
	""" Tells `main`, through stdout, how the session and Whisper started, once her face is there. """
	if not face.ready.wait(STARTUP_S):
		return
	if session.started.wait(STARTUP_S):
		stp.info(f"Claude Code session {'resumed' if session.id else 'started'}: {stp.CYAN}{session.url}")
		stp.info(f"Plan usage: {claude.plan_usage()}")
	else:
		stp.warning("Claude Code did not start Remote Control: run uv run clairechan-setup, then start the app again", file=sys.stdout)
	if listener.loaded.wait(STARTUP_S):
		stp.info("Whisper runs on the GPU" if GPU else "Whisper runs on the CPU, after the wake phrase only")
	else:
		stp.warning("Whisper did not load", file=sys.stdout)
	stp.info(f"Log: {stp.CYAN}{LOG_FILE}")
	print(READY, end="", flush=True)


def report_update(session: Session, face: Face) -> None:
	""" Tells her face which surfaces of Claude Code broke, when the session starts on a version the probes did not check yet. """
	if not (face.ready.wait(STARTUP_S) and session.started.wait(STARTUP_S)):
		return
	if (update := probes.after_update()) and update.broken:
		PEER.send("claude_code_broke", version=update.version, broken=update.broken)


def restart(change: str) -> None:
	""" Quits for the launcher to start the app again on its changed code. """
	print(CHANGED + change, flush=True)
	QCoreApplication.exit(RESTART)


def shut_down(session: Session) -> None:
	""" Quits, after compacting a large session so that the next start does not reread it all once the prompt cache has expired. """
	PEER.send("quitting")
	if session.busy or not session.compact():
		QCoreApplication.quit()
		return
	session.compacted.connect(QCoreApplication.quit)
	QTimer.singleShot(COMPACT_TIMEOUT_MS, QCoreApplication.quit)


def replace_running_app() -> None:
	""" Has the app already running quit, and waits until it has, so that starting the app again applies new code and settings. """
	running = QLocalSocket()
	running.connectToServer(INSTANCE_NAME)
	if running.waitForConnected(1000):
		running.waitForDisconnected(COMPACT_TIMEOUT_MS + 10_000)


def report_previous_crash() -> None:
	""" Writes in the log what the last run left in the crash file, so that a crash shows next to the lines before it. """
	if not CRASH_FILE.exists():
		return
	_, marker, last_run = CRASH_FILE.read_text(encoding="utf-8").rpartition(CRASH_MARKER)
	if marker and (crash := last_run.partition("\n")[2].strip()):
		LOG.critical("The previous run crashed:\n%s", crash)


def run() -> None:
	APP_DATA.mkdir(parents=True, exist_ok=True)
	logging.basicConfig(
		handlers=[RotatingFileHandler(LOG_FILE, maxBytes=LOG_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")],
		level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s",
	)
	LOG.setLevel(logging.INFO)
	# Without a console the default hooks print tracebacks nowhere
	sys.excepthook = lambda _kind, exception, _trace: logging.critical("Uncaught error", exc_info=exception)
	# A crash in native code, which no Python hook sees, dumps the stack of every thread here
	report_previous_crash()
	crash_log = CRASH_FILE.open("a", encoding="utf-8")
	crash_log.write(f"{CRASH_MARKER}{datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
	crash_log.flush()
	faulthandler.enable(crash_log)
	threading.excepthook = lambda hook: logging.critical("Uncaught error in %s", hook.thread, exc_info=hook.exc_value)
	# Qt's event loop never hands control back to Python's KeyboardInterrupt, so let Ctrl+C end the process directly
	signal.signal(signal.SIGINT, signal.SIG_DFL)

	app = QCoreApplication(sys.argv)
	replace_running_app()
	instance = QLocalServer()
	instance.listen(INSTANCE_NAME)
	config = Config.load()
	face = Face()
	hooks = HookServer(ask_first)
	tools = ActionServer(PEER)
	session = Session(hooks.url, tools.urls["main"], config)
	voice = Voice(config.voice_style if config.voice else None, config.volume)
	listener = Listener(config)
	core = Core(face, session, tools, listener, voice)
	instance.newConnection.connect(partial(shut_down, session))
	face.gave_up.connect(partial(app.exit, 1))
	hooks.posted.connect(session.on_hook)
	hooks.posted.connect(tell_hook)
	hooks.asked.connect(core.on_permission_asked)
	session.died.connect(core.on_session_died)
	voice.started.connect(tell_speaking)
	for heard, kind in (
		(listener.woke, "woke"), (listener.dictated, "dictated"), (listener.heard, "heard"),
		(listener.cancelled, "cancelled"), (listener.answered, "answered"),
	):
		heard.connect(partial(tell_face, kind))
	for close in (session.close, voice.close, face.close):
		app.aboutToQuit.connect(close)

	watcher = QFileSystemWatcher([str(USER_CONFIG)])
	saved = QTimer(singleShot=True, interval=SAVED_MS)
	saved.timeout.connect(partial(core.reload_config, watcher))
	watcher.fileChanged.connect(lambda: saved.start())
	threading.Thread(target=listener.run, args=(microphone(),), daemon=True).start()
	# Its waits for the session and Whisper would otherwise freeze the app until they are done
	threading.Thread(target=report_ready, args=(session, listener, face), daemon=True).start()
	threading.Thread(target=report_update, args=(session, face), daemon=True).start()
	code = app.exec()
	LOG.info("Exiting with code %s, threads alive: %s", code, ", ".join(thread.name for thread in threading.enumerate()))
	logging.shutdown()
	# Closing the interpreter while her voice or the microphone uses the audio library corrupts the heap
	os._exit(code)


if __name__ == "__main__":
	run()

