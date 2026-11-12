""" Claire's face: her windows, her reactions and her actions, in a process of its own.

The core (`clairechan.app`) starts it, and starts it again in a second or two to apply a change to its code,
while the session, her ears and her voice go on. What it logs goes to the core, which writes it in the app's log.
"""
# Imports
import faulthandler
import json
import logging
import os
import sys
from concurrent.futures import Future
from dataclasses import fields
from functools import partial

from PySide6.QtCore import QFileSystemWatcher, QMessageLogContext, QTimer, QtMsgType, qInstallMessageHandler
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication
from stouputils.typing import JsonDict

from clairechan import actions, i18n
from clairechan.assistant import Assistant
from clairechan.config import USER_CONFIG, Config
from clairechan.link import PEER
from clairechan.report import Answer
from clairechan.services import desktop
from clairechan.services.alarms import ALARMS
from clairechan.services.children import CHILDREN
from clairechan.tools import content, listed
from clairechan.windows import Windows

# Constants
LOG: logging.Logger = logging.getLogger("clairechan")
CONNECT_MS: int = 5000
""" How long the core may take to answer on its socket. """
SAVED_MS: int = 300
""" Quiet time after the config file changed before it is read, as editors write it in several steps. """


# Functions
def run(core: str) -> None:
	""" Shows her and reacts for her until the core, which listens on the local socket called `core`, goes away. """
	logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(message)s")
	LOG.setLevel(logging.INFO)
	qInstallMessageHandler(log_qt_message)
	faulthandler.enable()
	app = QApplication(sys.argv)
	app.setQuitOnLastWindowClosed(False)
	socket = QLocalSocket()
	socket.connectToServer(core)
	if not socket.waitForConnected(CONNECT_MS):
		sys.exit(f"The core does not answer on {core}")
	socket.disconnected.connect(app.quit)
	PEER.attach(socket)

	config = Config.load()
	windows = Windows(config)
	assistant = Assistant(windows.avatar, windows.pill, config)
	windows.wire(assistant)
	assistant.send.connect(type_prompt)
	assistant.speak.connect(say)
	assistant.listening_for_answer.connect(lambda: PEER.send("asking", on=True))
	assistant.answer_settled.connect(lambda: PEER.send("asking", on=False))
	for signal, kind in (
		(assistant.hush, "hush"), (assistant.idle, "compact"), (assistant.restart, "restart_session"),
		(assistant.restart_app, "restart_app"), (assistant.free, "free"),
	):
		signal.connect(partial(PEER.send, kind))
	PEER.received.connect(partial(on_message, assistant, windows))
	ALARMS.rang.connect(assistant.on_alarm)
	ALARMS.resume()
	CHILDREN.finished.connect(assistant.on_child_finished)
	CHILDREN.resume()

	watcher = QFileSystemWatcher([str(USER_CONFIG)])
	saved = QTimer(singleShot=True, interval=SAVED_MS)
	saved.timeout.connect(partial(reload_config, watcher, assistant))
	watcher.fileChanged.connect(lambda: saved.start())
	phrases = {name: phrase.pattern for name, phrase in actions.PHRASES.items()}
	PEER.send("hello", tools={"main": listed(child=False), "child": listed(child=True)}, phrases=phrases)
	code = app.exec()
	# Closing the interpreter while her chimes use the audio library corrupts the heap
	os._exit(code)


def type_prompt(text: str) -> None:
	PEER.send("type", text=text)


def say(text: str, style: int) -> None:
	PEER.send("say", text=text, style=style)


def on_message(assistant: Assistant, windows: Windows, kind: str, fields: JsonDict) -> None:
	""" Reacts to what the core tells: what the session does, what her ears heard, what her voice says. """
	# Her lines follow the language of what was just said to her, which her ears know
	i18n.heard = fields.get("language", i18n.heard)
	match kind:
		case "welcome":
			CHILDREN.tools_url = fields["tools_url"]
		case "hook":
			assistant.on_hook(fields["event"])
		case "permission":
			assistant.on_permission_asked(verdict(fields["request"]))
		case "woke":
			assistant.on_wake()
		case "dictated":
			assistant.on_dictation(fields["value"])
		case "heard":
			assistant.on_command(fields["value"])
		case "cancelled":
			assistant.on_cancel()
		case "answered":
			assistant.on_verdict(fields["value"])
		case "speaking":
			vowels = tuple((at, vowel) for at, vowel in fields["vowels"])
			assistant.on_speaking(vowels)
			windows.avatar.speak(vowels)
		case "tool":
			call_tool(assistant, fields)
		case "reason":
			PEER.reply(fields["ask"], reason=desktop.permission(fields["tool"], fields["input"]))
		case "set_aside":
			assistant.on_set_aside(fields["reason"])
		case "session_lost":
			assistant.on_session_lost()
		case "quitting":
			windows.tray.hide()
		case _:
			LOG.warning("Unknown message from the core: %s", kind)


def verdict(request: int) -> Future[bool]:
	""" The answer to a permission request the core holds: what it is set to, or its cancellation, goes back to the core. """
	answer: Future[bool] = Future()
	answer.add_done_callback(lambda done: PEER.send("verdict", request=request, allowed=None if done.cancelled() else done.result()))
	return answer


def call_tool(assistant: Assistant, call: JsonDict) -> None:
	""" Runs the action a session called as a tool, and replies with what it answers once it has. """
	answer: Future[Answer] = Future()
	answer.add_done_callback(partial(reply_tool, call["ask"]))
	arguments = {name: value if isinstance(value, str) else json.dumps(value) for name, value in call["arguments"].items()}
	assistant.on_tool_call(actions.find(call["name"]), arguments, answer)


def reply_tool(number: int, answer: Future[Answer]) -> None:
	if error := answer.exception():
		PEER.reply(number, content=[{"type": "text", "text": f"It failed: {error!r}"}], isError=True)
	else:
		PEER.reply(number, content=content(answer.result()), isError=False)


def reload_config(watcher: QFileSystemWatcher, assistant: Assistant) -> None:
	""" Applies the saved config to what her face holds of it. The core gives it to her ears and her voice. """
	# Editors save by replacing the file, which drops it from the watch
	watcher.addPath(str(USER_CONFIG))
	try:
		config = Config.load()
	# Whatever the user wrote there: a broken table, a regex that does not compile, a word where a number goes
	except Exception as error:
		assistant.on_config_error(f"{type(error).__name__}: {error}")
		return

	changed = [field.name for field in fields(Config) if getattr(config, field.name) != getattr(assistant.config, field.name)]
	if changed:
		assistant.on_config(config, changed)


def log_qt_message(kind: QtMsgType, _context: QMessageLogContext, message: str) -> None:
	if kind not in (QtMsgType.QtDebugMsg, QtMsgType.QtInfoMsg):
		logging.warning("Qt %s: %s", kind.name, message)


if __name__ == "__main__":
	run(sys.argv[1])

