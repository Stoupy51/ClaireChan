""" Claire reacting to what she hears and to the hidden Claude Code session, through its hook events. """
# Imports
import logging
import random
import threading
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from functools import partial

from PySide6.QtCore import QObject, QPoint, QTimer, Signal
from stouputils.typing import JsonDict

from clairechan import actions
from clairechan.config import FOLLOW_UP_S, Config
from clairechan.i18n import tr
from clairechan.overlay import avatar as avatar_module, bubble as bubble_module
from clairechan.report import Answer, Report
from clairechan.services.agents import describe_tool, log_usage
from clairechan.voice.speech import Vowels

# Constants
LOG: logging.Logger = logging.getLogger("clairechan")
WAKE_NOTES: tuple[float, ...] = (880.0, 1318.5)
DONE_NOTES: tuple[float, ...] = (1046.5, 1318.5, 1568.0)
LONG_TASK_MS: int = 20_000
""" How long a turn runs before she shrinks to the pill. """
HEARD_MS: int = 4000
""" How long the sentence she understood stays up when the session does not start on it right away. """
SPOKEN_MS: int = 1500
""" How long she stays once her voice has said a line. """
CONFIG_NOTICE_MS: int = 6000
""" How long she stays up to say what she applied from the saved config. """
COMPACT_IDLE_MS: int = 55 * 60_000
""" Quiet time after which a large session is compacted, while its prompt cache (1 h on a subscription) still makes that cheap. """
SESSION_KEYS: frozenset[str] = frozenset({"agent_model", "prompt", "commit_changes"})
""" Settings Claude Code reads only when it starts, applied by restarting the session on the same conversation. """
FILLERS: tuple[tuple[str, str], ...] = (
	("I'm on it, I'll tell you when it's done.", "Je m'en occupe, je te préviens."),
	("Here we go, I'm looking into it.", "C'est parti, je regarde ça."),
	("Okay, I'm running it in the background.", "Ok, je lance ça en arrière-plan."),
)
""" What she says when she hands work to an agent: always these lines, so that their translation and sound are kept. """


# Classes
class Assistant(QObject):
	""" What Claire shows at each step of a request, and when the next command may be typed into the session. """
	send = Signal(str)
	""" A command to type, emitted only between turns: keys typed while a dialog is open would answer it. """
	idle = Signal()
	""" No hook for `COMPACT_IDLE_MS` and no turn running. """
	listening_for_answer = Signal()
	""" A permission request waits for a spoken answer. """
	answer_settled = Signal()
	""" The permission request is answered, or no longer waits. """
	announced = Signal(object)
	""" Something to tell the user, from a thread that had to wait for it. """
	restart = Signal()
	""" The session starts again: `SESSION_KEYS` settings changed while she was free, or she was told to stop everything. """
	restart_app = Signal()
	""" She was told to start the whole app again. """
	free = Signal()
	""" Nothing runs any more and she has left: the moment to apply a change to the app's code. """
	speak = Signal(str, int)
	""" A line to say aloud, with the voice style of the config, emitted only while her voice is on. """
	hush = Signal()
	""" She is called while her voice may still be saying something. """

	def __init__(self, avatar: avatar_module.Avatar, pill: avatar_module.Pill, config: Config) -> None:
		super().__init__()
		self.config = config
		self.avatar = avatar
		self.avatar.bubble.typing_speed = config.typing_speed
		self.pill = pill
		self.commands: deque[str] = deque()
		self.busy = False
		self.agents: set[str] = set()
		self.asking = False
		self.asked_tool: tuple[str, JsonDict] | None = None
		""" Name and input of the tool waiting for permission: only its completion answers the request, others run alongside. """
		self.pending: Future[bool] | None = None
		self.worked = False
		""" Whether the turn used a tool, which makes her present the result rather than smile. """
		self.own_turn = False
		""" Whether the running turn started from what the app typed: tool calls of the others stay off the bubble. """
		self.typed: list[str] = []
		""" What the app typed and whose turn has not started: other prompts (keyboard, Remote Control) stay off the bubble. """
		self.restart_pending = False
		self.activity = ""
		self.message_id = ""
		self.message = ""

		self.long_task = QTimer(self)
		self.long_task.setSingleShot(True)
		self.long_task.setInterval(LONG_TASK_MS)
		self.long_task.timeout.connect(self.shrink_unless_showing)
		self.dismiss = QTimer(self)
		self.dismiss.setSingleShot(True)
		self.dismiss.timeout.connect(self.leave)
		self.idle_timer = QTimer(self)
		self.idle_timer.setSingleShot(True)
		self.idle_timer.setInterval(COMPACT_IDLE_MS)
		self.idle_timer.timeout.connect(self.on_idle)
		self.announced.connect(self.on_announce)

	def on_wake(self) -> None:
		self.hush.emit()
		avatar_module.chime(*WAKE_NOTES)
		self.appear("hello", bubble=tr("Yes?", "Oui ?"))
		self.dismiss.start(round(FOLLOW_UP_S * 1000))

	def on_dictation(self, text: str) -> None:
		english_hint, french_hint = self.config.done_hints
		self.appear("idle", bubble=tr(f'"{text}" Say "{english_hint}" to send.', f"« {text} » Dis « {french_hint} » pour envoyer."))
		self.dismiss.stop()

	def on_cancel(self) -> None:
		LOG.info("Request cancelled")
		self.appear("idle", bubble=tr("Okay, forget it.", "D'accord, j'oublie."))
		self.dismiss.start(HEARD_MS)

	def on_config(self, config: Config, changed: list[str]) -> None:
		LOG.info("Config changed: %s", ", ".join(changed))
		self.config = config
		self.avatar.bubble.typing_speed = config.typing_speed
		if "avatar_zoom" in changed or "text_zoom" in changed:
			self.avatar.set_zoom(config.avatar_zoom, config.text_zoom)
			self.pill.set_zoom(config.avatar_zoom)

		if "fps" in changed:
			self.avatar.set_fps(config.fps)
			self.pill.set_fps(config.fps)

		if "model" in changed:
			self.switch_model(config.model)
		self.restart_pending = self.restart_pending or not SESSION_KEYS.isdisjoint(changed)
		later = tr(
			" I'll restart the Claude session to apply it once I have nothing running.",
			" Je relance la session Claude pour l'appliquer dès que je n'ai plus rien en cours.",
		) if self.restart_pending else ""
		names = ", ".join(changed)
		self.appear("happy", bubble=tr(f"I reread your config: {names}.", f"J'ai relu ta config : {names}.") + later)
		self.dismiss.start(CONFIG_NOTICE_MS)

	def on_config_error(self, error: str) -> None:
		LOG.warning("Config not applied: %s", error)
		self.appear("sad", bubble=tr(
			f"I can't read your config, I'm keeping the old one: {error}",
			f"Je n'arrive pas à lire ta config, je garde l'ancienne : {error}",
		))
		self.dismiss.start(CONFIG_NOTICE_MS)

	def on_command(self, text: str) -> None:
		LOG.info("Heard: %s", text)
		if routed := actions.route(text):
			action, arguments = routed
			LOG.info("Local action: %s", action.name)
			if action.threaded:
				self.announce(action, arguments)
				return
			said = self.run_action(action, arguments)
			self.appear("present", bubble=said)
			self.dismiss.start(reading_ms(str(said)))
			return

		later = tr(" I'll get to it right after.", " Je m'en occupe juste après.") if self.busy else ""
		self.appear("idle", bubble=tr(f'"{text}"', f"« {text} »") + later)
		self.dismiss.start(HEARD_MS)
		self.commands.append(text)
		self.flush()

	def run_action(self, action: actions.Action, arguments: Mapping[str, str | None]) -> Answer:
		""" Carries the action out, whoever asked, and returns what it says about it. """
		text = action.run(arguments)
		match action.name:
			case "stop_all":
				self.stop_all()
			case "restart_app":
				self.restart_app.emit()
			case "model" if model := actions.chosen_model(arguments):
				self.switch_model(model)
			case "compact":
				self.commands.append("/compact")
				self.flush()
			case _:
				pass
		return text

	def switch_model(self, model: str) -> None:
		self.commands.append(f"/model {model}")
		self.flush()

	def announce(self, action: actions.Action, arguments: Mapping[str, str | None]) -> None:
		""" Has her tell what the action says, carried out on a thread since the Qt one would freeze while it waits. """
		threading.Thread(target=lambda: self.announced.emit(action.run(arguments)), daemon=True).start()

	def on_announce(self, text: Answer) -> None:
		self.appear("present", bubble=text)
		self.dismiss.start(reading_ms(str(text)))

	def on_child_finished(self, name: str, child_id: str) -> None:
		LOG.info("Child session finished: %s", name)
		self.commands.append(tr(
			f"The child session {name} ({child_id}) has finished its turn: read its rapport.md and sum it up for me.",
			f"La session fille {name} ({child_id}) a fini son tour : lis son rapport.md et résume-le-moi.",
		))
		self.flush()

	def on_alarm(self, label: str) -> None:
		avatar_module.chime(*DONE_NOTES)
		done = tr(f"Your timer is done: {label}.", f"Ton minuteur est terminé : {label}.")
		self.appear("present", bubble=done if label else tr("Your timer is done.", "Ton minuteur est terminé."))
		self.dismiss.start(HEARD_MS)

	def on_tool_call(self, action: actions.Action, arguments: dict[str, str], answer: Future[Answer]) -> None:
		""" The session called the action as a tool: she does it without interrupting what she shows. """
		LOG.info("Tool called: %s", action.name)
		if action.threaded:
			threading.Thread(target=self.settle, args=(action.run, arguments, answer), daemon=True).start()
		else:
			self.settle(partial(self.run_action, action), arguments, answer)

	def settle(self, run: Callable[[Mapping[str, str | None]], Answer], arguments: dict[str, str], answer: Future[Answer]) -> None:
		""" Sets on the future what the action answers, or what it raised, for the session to read either. """
		try:
			answer.set_result(run(arguments))
		except Exception as error:
			answer.set_exception(error)

	def stop_all(self) -> None:
		""" Drops the queued commands and what the session runs, its agents included, by starting it again. """
		self.commands.clear()
		self.agents.clear()
		self.end_turn()
		self.restart_pending = False
		self.restart.emit()

	def on_hook(self, event: JsonDict) -> None:
		self.idle_timer.start()
		match event["hook_event_name"]:
			case "UserPromptSubmit":
				self.on_prompt(event["prompt"])
			case "PreToolUse":
				self.on_tool(describe_tool(event["tool_name"], event["tool_input"]))
			case "PostToolUse" if self.asking and (event["tool_name"], event["tool_input"]) == self.asked_tool:
				self.settle_permission()
				self.appear("thanks", bubble=tr("Thanks!", "Merci !"))
			case "PermissionRequest":
				self.asked_tool = (event["tool_name"], event["tool_input"])
				self.on_permission(describe_tool(event["tool_name"], event["tool_input"]))
			case "Notification" if event["notification_type"] == "permission_prompt":
				self.on_permission(event["message"])
			case "MessageDisplay":
				self.on_text(event["message_id"], event["delta"], streaming=not event["final"])
			case "SubagentStart":
				if not self.agents:
					self.say_aloud(tr(*random.choice(FILLERS)))
				self.agents.add(event["agent_id"])
				self.shrink_unless_showing()
			case "SubagentStop":
				self.agents.discard(event["agent_id"])
				threading.Thread(target=log_usage, args=(event["transcript_path"], event["agent_id"]), daemon=True).start()
			case "Stop":
				self.on_stop(event["last_assistant_message"])
			case "StopFailure":
				self.on_failure(event["error"])
			# Claude Code compacts on its own during a turn, which stays busy
			case "PreCompact" if event["trigger"] != "auto":
				self.busy = True
			case "PostCompact" if event["trigger"] != "auto":
				self.end_turn()
				self.flush()
				self.leave()
			case _:
				pass

	def on_prompt(self, prompt: str) -> None:
		""" A turn starts, typed by the app, sent from the Remote Control, or started by Claude Code itself. """
		LOG.info("Prompt: %s", prompt)
		self.settle_permission()
		self.busy = True
		self.worked = False
		self.activity = ""
		self.dismiss.stop()
		self.long_task.start()
		self.own_turn = prompt in self.typed
		if self.own_turn:
			self.typed.remove(prompt)
			if not self.pill.isVisible():
				self.appear("thinking", bubble=prompt)

	def on_tool(self, activity: str) -> None:
		LOG.info("Action: %s", activity)
		self.worked = True
		if not self.own_turn:
			return
		if activity != self.activity and not self.asking and not self.pill.isVisible() and not self.showing_while_agents_run():
			self.activity = activity
			self.appear("working", bubble=activity)

	def on_permission(self, request: str) -> None:
		if self.asking:
			return
		LOG.info("Permission asked: %s", request)
		self.asking = True
		self.long_task.stop()
		asked = tr(
			f"I need your OK: {request}. Say yes or no, or click on me.",
			f"J'ai besoin de ton accord : {request}. Dis oui ou non, ou clique sur moi.",
		)
		self.appear("please", bubble=asked)
		# The same words each time, so their translation and sound are kept rather than made again
		self.say_aloud(tr("I need your OK: say yes or no.", "J'ai besoin de ton accord : dis oui ou non."))

	def on_permission_asked(self, answer: Future[bool]) -> None:
		self.pending = answer
		self.listening_for_answer.emit()

	def on_verdict(self, allowed: bool) -> None:
		""" The user said yes or no to the pending permission request. """
		LOG.info("Permission answered: %s", "allowed" if allowed else "refused")
		if not self.pending:
			return
		self.pending.set_result(allowed)
		self.pending = None
		self.settle_permission()
		if allowed:
			self.appear("thanks", bubble=tr("Thanks!", "Merci !"))
		else:
			self.appear("idle", bubble=tr("Got it, I'll leave it alone.", "Compris, je n'y touche pas."))
		self.dismiss.start(HEARD_MS)

	def settle_permission(self) -> None:
		""" Closes a pending permission prompt, allowed or not, and restarts the countdown to the pill. """
		if self.pending:
			self.pending.cancel()
			self.pending = None
		if self.asking:
			self.asking = False
			self.long_task.start()
			self.answer_settled.emit()

	def on_text(self, message_id: str, delta: str, *, streaming: bool) -> None:
		self.message = self.message + delta if message_id == self.message_id else delta
		self.message_id = message_id
		if not self.pill.isVisible() and not self.showing_while_agents_run():
			self.appear("idle", bubble=self.message, talking=streaming)

	def on_stop(self, reply: str) -> None:
		LOG.info("Reply: %s", reply)
		self.end_turn()
		if not self.agents:
			avatar_module.chime(*DONE_NOTES)
		self.appear("present" if self.worked else "happy", bubble=reply)
		self.dismiss.start(reading_ms(reply))
		self.say_aloud(reply)
		self.flush()

	def on_failure(self, error: str) -> None:
		LOG.warning("Request failed: %s", error)
		self.end_turn()
		self.appear("sad", bubble=tr(f"Oops, the request failed ({error}).", f"Oups, la requête a échoué ({error})."))
		self.dismiss.start(reading_ms(error))
		self.flush()
		if error == "rate_limit":
			self.announce(actions.find("plan_usage"), {})

	def on_session_lost(self) -> None:
		""" Claude Code stopped by itself and was started again: what it was running is gone. """
		self.agents.clear()
		self.on_failure(tr("my Claude session stopped, I started it again", "ma session Claude s'est arrêtée, je l'ai relancée"))

	def on_set_aside(self, reason: str) -> None:
		""" A change to the app's code broke it, and was put aside in git. """
		said = tr(
			f"A change to my code broke me, so I put it aside in git: {reason}",
			f"Un changement de mon code me cassait, je l'ai mis de côté dans git : {reason}",
		)
		self.appear("sad", bubble=said)
		self.dismiss.start(reading_ms(said))
		self.say_aloud(said)

	def say_aloud(self, text: str) -> None:
		if self.config.voice:
			self.speak.emit(text, self.config.voice_style)

	def on_speaking(self, vowels: Vowels) -> None:
		""" Keeps her up until her voice has said the line, if she was going to leave before. """
		if self.dismiss.isActive():
			self.dismiss.start(max(self.dismiss.remainingTime(), round(1000 * vowels[-1][0]) + SPOKEN_MS))

	def on_read(self) -> None:
		if self.dismiss.isActive():
			self.leave()

	def end_turn(self) -> None:
		self.busy = False
		self.asking = False
		self.long_task.stop()

	def flush(self) -> None:
		if self.commands and not self.busy:
			command = self.commands.popleft()
			self.typed.append(command)
			self.send.emit(command)

	def appear(self, expression: str, bubble: Answer, *, talking: bool = False) -> None:
		self.pill.hide()
		self.avatar.set_expression(expression, talking=talking, bubble=bubble if isinstance(bubble, Report) else str(bubble))
		self.avatar.pop_in()

	def showing_while_agents_run(self) -> bool:
		""" Whether the bubble holds something she was asked for, which the tool calls and texts of the agents must not replace. """
		return bool(self.agents) and self.dismiss.isActive()

	def shrink_unless_showing(self) -> None:
		""" Gives way to the pill, but not while the bubble holds something she was asked for. """
		if not self.dismiss.isActive():
			self.shrink()

	def shrink(self) -> None:
		self.avatar.pop_out()
		self.pill.show_at(self.avatar.home() + QPoint(self.avatar.width(), self.avatar.height()))

	def leave(self) -> None:
		""" Out of the way once nothing needs her: the pill while work goes on, hidden otherwise. """
		if self.busy or self.agents:
			self.shrink()
			return
		self.pill.hide()
		self.avatar.pop_out()
		if self.restart_pending:
			self.restart_pending = False
			self.restart.emit()
		self.free.emit()

	def on_idle(self) -> None:
		if not self.busy:
			self.idle.emit()


# Functions
def reading_ms(text: str) -> int:
	""" How long a text stays up: 4 s, plus 50 ms per character, which the bubble scrolls through at that pace, 60 s at most. """
	return min(4000 + 50 * len(bubble_module.plain(text)), 60_000)

