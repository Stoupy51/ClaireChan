""" What she does on the computer: said aloud as the phrases of an action, or called by the session as an MCP tool. """
# Imports
import re
from collections.abc import Callable, Mapping
from ctypes import windll
from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtGui import QGuiApplication

from clairechan.config import SCREENSHOTS
from clairechan.i18n import tr
from clairechan.link import PEER
from clairechan.phrases import match_phrase
from clairechan.report import Answer, Picture
from clairechan.services import agents, claude, desktop, dream, minecraft, programs, weather
from clairechan.services.alarms import ALARMS
from clairechan.services.children import CHILDREN


# Classes
@dataclass(frozen=True)
class Parameter:
	""" An argument of an action, as the session reads it in the tool's schema. The action gets it as text, JSON for an array. """
	description: str
	kind: str = "string"
	""" Its JSON type. """
	required: bool = False
	choices: tuple[str, ...] = ()
	""" The values it takes, any when empty. """


@dataclass(frozen=True)
class Action:
	""" Something she does on the computer: the whole request matches `phrases`, or the session calls the tool `name`. """
	name: str
	description: str
	""" What the session reads to choose the tool. """
	run: Callable[[Mapping[str, str | None]], Answer]
	""" Carries the action out and returns what she says about it. """
	phrases: str = ""
	""" Its named groups are the arguments the request gives. Empty for a tool only the session calls. """
	parameters: Mapping[str, Parameter] = field(default_factory=dict[str, Parameter])
	threaded: bool = False
	""" Whether it runs on a thread of its own, taking seconds that would freeze the Qt thread. """
	spoken_only: bool = False
	""" Whether only the user's request can do it, never the session as a tool. """
	child: bool = False
	""" Whether the child sessions she starts may call it too. """


# Constants
VK_MENU, VK_F10 = 0x12, 0x79
VK_MUTE = 0xAD
KEY_UP: int = 0x0002
""" `KEYEVENTF_KEYUP`, the flag of a key release for `keybd_event`. """
UNITS: dict[str, int] = {"s": 1, "m": 60, "h": 3600}
""" Seconds in a unit of time, by its first letter. """
SCREENS: dict[str, int] = {"1": 1, "un": 1, "one": 1, "2": 2, "deux": 2, "two": 2, "3": 3, "trois": 3, "three": 3}
""" Screen numbers as Whisper may write them. """
MODELS: tuple[str, ...] = ("opus", "sonnet", "haiku")
""" The models of `/model` she switches to by name. """
CORE_WAIT_S: float = 10.0
""" How long an action waits for the app's other process to do its part. """
WINDOW: Parameter = Parameter(
	"Its program's file name, such as firefox.exe, for its frontmost window, or its id from list_windows.", required=True,
)
ELEMENT: Parameter = Parameter("Its number from the last read_window.", kind="integer", required=True)
ACTIONS: list[Action] = [
	Action(
		name="screenshot",
		description="Saves a screenshot of one screen in the Screenshots folder of the user's pictures, and shows it to you.",
		phrases=r"(?:fais une |prends une |take a )?(?:capture|screenshot)(?: d'écran)?"
		r"(?: (?:de |of )?(?:l' ?écran|screen|monitor)(?: (?P<screen>[1-3]|un|deux|trois|one|two|three))?)?",
		run=lambda arguments: screenshot(SCREENS[(arguments.get("screen") or "1").lower()]),
		parameters={"screen": Parameter("Screen number from 1, 1 by default.", kind="integer")},
		child=True,
	),
	Action(
		name="meeting_start",
		description="Writes what the PC plays and the microphone hears into a file of the Transcriptions folder, until meeting_stop.",
		phrases=r"(?:lance|démarre|commence) (?:la |une )?(?:re)?transcription(?: de la réunion)?|transcris(?: la réunion)?"
		r"|(?:start )?(?:transcribing|transcribe)(?: the meeting)?|start (?:a |the )?transcription",
		run=lambda _: PEER.ask("meeting", on=True).result(CORE_WAIT_S)["text"],
		threaded=True,
	),
	Action(
		name="meeting_stop",
		description="Stops the transcription started by meeting_start and says where its file is.",
		phrases=r"(?:arrête|stoppe|termine|coupe) (?:la )?(?:re)?transcription|stop (?:the )?(?:transcription|transcribing)",
		run=lambda _: PEER.ask("meeting", on=False).result(CORE_WAIT_S)["text"],
		threaded=True,
	),
	Action(
		name="stop_all",
		description="Stops the running request, its agents and the queued ones, and restarts this session. Only if the user asks.",
		phrases=r"(?:stop|arrête|stoppe|annule)(?: (?:tout|ça|everything|it))?(?: (?:maintenant|now))?",
		run=lambda _: tr("Stopping everything, starting over.", "J'arrête tout, je repars de zéro."),
	),
	Action(
		name="restart_app",
		description="Quits and starts the whole app again on the same conversation, as it does by itself for a change to the code "
		"of its session or its voice. Only when a change did not apply, or the app is stuck.",
		phrases=r"(?:redémarre|relance)(?:-toi| (?:l'appli|l'application|claire-?chan))|restart (?:yourself|the app)",
		run=lambda _: tr("Restarting myself.", "Je me redémarre."),
	),
	Action(
		name="agent_progress",
		description="Where the background agents of this session stand: task, running time, tool calls and the last one.",
		phrases=r"(?:il |elle )?(?:en est|est en) où(?: là)?|où en (?:est|sont)(?: l'agent| les agents| le travail)?"
		r"|(?:agent )?progress|how(?:'s| is) the agent(?: doing)?",
		run=lambda _: agents.progress(),
		threaded=True,
	),
	Action(
		name="child_session",
		description=(
			"Starts a child Claude session in the background (claude --bg) that the user can read in their Code list on claude.ai, "
			"for a long job instead of a subagent. The brief must hold the rules a subagent brief holds and the path of a rapport.md "
			"the session writes when done, outside any git repository. You are told when it has finished. Never run claude stop on it."
		),
		run=lambda arguments: CHILDREN.start(
			arguments["name"] or "", arguments["brief"] or "", arguments["folder"] or "",
			arguments.get("model") or "", arguments.get("effort") or "",
		),
		parameters={
			"name": Parameter("Short name of the session, shown in the user's list.", required=True),
			"brief": Parameter("What the session must do, with the rules and the report path.", required=True),
			"folder": Parameter("Project folder the session works in.", required=True),
			"model": Parameter("opus, sonnet, haiku, or a full id such as claude-fable-5-2. The user's default when left out."),
			"effort": Parameter("The user's default when left out.", choices=("low", "medium", "high", "xhigh", "max")),
		},
		threaded=True,
	),
	Action(
		name="agent_usage",
		description="What the background agents and the child sessions used over the last day, by model: "
		"tokens written and read, largest context.",
		phrases=r"(?:usage|consommation|coûts?) (?:des |de l')?agents?|agents? (?:usage|costs?)",
		run=lambda _: agents.usage_today(),
	),
	Action(
		name="dream",
		description="Starts the dream: a child session that reads what every session did since the last dream and proposes changes "
		r"to the shared memory, numbered in the rapport.md of %APPDATA%\ClaireChan\dream. Only if the user asks.",
		phrases=r"(?:lance|démarre|commence|start|run) (?:le |un |the |a )?(?:rêve|dream)",
		run=lambda _: dream.launch(),
		threaded=True,
	),
	Action(
		name="dream_digest",
		description="For the dream session only: writes the digest files of what the sessions did since the last dream, and answers "
		"with their paths, the size of MEMORY.md and the proposals the user refused before.",
		run=lambda _: dream.digest(),
		threaded=True,
		child=True,
	),
	Action(
		name="dream_propose",
		description="For the dream session only: records one change to the shared memory, as a proposal the user accepts or refuses.",
		run=lambda arguments: dream.propose(
			arguments["summary"] or "", arguments["reason"] or "", arguments["sessions"] or "", arguments["files"] or "[]",
		),
		parameters={
			"summary": Parameter("The change in one line, as the user reads it first.", required=True),
			"reason": Parameter("Why it is worth making, and how often what calls for it was seen.", required=True),
			"sessions": Parameter("Ids of the sessions that show it, separated by commas.", required=True),
			"files": Parameter(
				'One {"path": "memory/name.md", "content": "its whole new text"} per file written, '
				'one {"path": "memory/name.md"} per file deleted.', kind="array", required=True,
			),
		},
		threaded=True,
		child=True,
	),
	Action(
		name="dream_review",
		description="Lists the proposals of the last dream that wait for the user's word, each with its number, reason and diff.",
		phrases=r"(?:(?:montre(?:-moi)?|affiche|liste|show(?: me)?|list) )?(?:les |the )?"
		r"(?:propositions(?: du rêve)?|(?:dream )?proposals)",
		run=lambda _: dream.review(),
		threaded=True,
	),
	Action(
		name="dream_apply",
		description="Puts a proposal of the dream into the shared memory, and pushes it. Only when the user accepts that proposal.",
		phrases=r"(?:applique|accepte|apply|accept) (?:la |the )?(?:proposition|proposal) (?:numéro |number )?(?P<number>\d+)",
		run=lambda arguments: dream.apply(arguments["number"] or "0"),
		parameters={"number": Parameter("Its number in dream_review.", kind="integer", required=True)},
		threaded=True,
	),
	Action(
		name="dream_reject",
		description="Refuses a proposal of the dream, with a reason the next dream reads. Only when the user refuses that proposal.",
		phrases=r"(?:refuse|rejette|reject) (?:la |the )?(?:proposition|proposal) (?:numéro |number )?(?P<number>\d+)"
		r"(?:\W+(?:parce que |parce qu'|car |because )?(?P<reason>.+))?",
		run=lambda arguments: dream.reject(arguments["number"] or "0", arguments.get("reason") or ""),
		parameters={
			"number": Parameter("Its number in dream_review.", kind="integer", required=True),
			"reason": Parameter("Why the user refuses it, in their words."),
		},
		threaded=True,
	),
	Action(
		name="clip",
		description="Saves the last minutes of the game with ShadowPlay, by pressing Alt+F10.",
		phrases=r"(?:enregistre|clippe|clip|save)(?: (?:ça|ca|ce moment|les dernières minutes|that|it|the replay))?",
		run=lambda _: press(VK_MENU, VK_F10, said=tr("I pressed Alt+F10 for ShadowPlay.", "J'ai appuyé sur Alt+F10 pour ShadowPlay.")),
	),
	Action(
		name="model",
		description="Switches the model this session answers with, once the current request is done.",
		phrases=r"(?:passe|bascule|switch|mets-toi)(?: en| sur| to)?(?: mode)? (?P<model>" + "|".join(MODELS) + ")",
		run=lambda arguments: tr(f"Switching to {model}.", f"Je passe en {model}.") if (model := chosen_model(arguments))
		else tr(f"Pick {', '.join(MODELS)}.", f"Choisis {', '.join(MODELS)}."),
		parameters={"model": Parameter("The model to switch to.", required=True, choices=MODELS)},
	),
	Action(
		name="compact",
		description="Types /compact into this session once its current request is done, to free its context.",
		phrases=r"(?:compacte|compact)(?: (?:la conversation|le contexte|la session|toi|the conversation|the session))?",
		run=lambda _: tr("Compacting the conversation.", "Je compacte la conversation."),
	),
	Action(
		name="context",
		description="How full the context window of this session is: its model and its tokens.",
		phrases=r"(?:(?:quel est|montre-moi|donne-moi|affiche|what's|show me) )?(?:le |the )?contexte?(?: de la session| usage)?",
		run=lambda _: claude.context(),
		threaded=True,
	),
	Action(
		name="plan_usage",
		description="How much of the Claude subscription's 5-hour window and weekly limit is used, and when they reset.",
		phrases=r"(?:(?:quel est|montre-moi|donne-moi|affiche|what's|show me) )?(?:mon |l'|my |the )?(?:plan )?usage(?: du forfait)?",
		run=lambda _: claude.plan_usage(),
		threaded=True,
	),
	Action(
		name="timer",
		description="Rings after a while, with a sound and a message, and says what the timer is for when given.",
		phrases=r"(?:(?:mets|lance|démarre|règle|programme|set|start) )?(?:un |a )?(?:minuteur|timer)(?: de| pour| of| for)?"
		r" (?P<amount>\d+(?:[.,]\d+)?) ?(?P<unit>secondes?|seconds?|sec|s|minutes?|min|heures?|hours?|h)?",
		run=lambda arguments: set_timer(arguments.get("amount") or "0", arguments.get("unit") or "m", arguments.get("label") or ""),
		parameters={
			"amount": Parameter("How long.", kind="number", required=True),
			"unit": Parameter("minutes by default.", choices=("seconds", "minutes", "hours")),
			"label": Parameter("What it is for."),
		},
	),
	Action(
		name="weather",
		description="The weather now and for the day in a city.",
		phrases=r"(?:(?:quelle est|donne-moi|dis-moi|what's|what is|tell me) )?(?:la météo|the weather|quel temps (?:fait-il|il fait))"
		r"(?: (?:à|a|de|pour|sur|in|at) (?P<city>.+))?",
		run=lambda arguments: forecast(arguments.get("city") or ""),
		parameters={"city": Parameter("Name of the city.", required=True)},
	),
	Action(
		name="allow_acting",
		description="Lets her press and fill in an application the config only lets her read.",
		phrases=r"(?:tu peux|vous pouvez|you can) (?:agir|utiliser|act|use|press|appuyer)(?: (?:dans|sur|in|on))? (?P<application>.+)",
		run=lambda arguments: desktop.allow_acting(arguments["application"] or ""),
		parameters={"application": Parameter("File name of its program.", required=True)},
		spoken_only=True,
	),
	Action(
		name="launch_program",
		description="Opens a program installed on the computer, found by part of its name as the Start menu shows it.",
		run=lambda arguments: programs.launch(arguments["name"] or ""),
		parameters={"name": Parameter("Part of the program's name, such as Spotify or Discord.", required=True)},
	),
	Action(
		name="list_windows",
		description="Lists the open windows of the applications the user lets you read or act in, by the id read_window takes. "
		"Needed only to pick a window other than the frontmost one of its program.",
		run=lambda _: desktop.list_windows(),
	),
	Action(
		name="read_window",
		description="Lists what a window shows, as numbered elements with their type, name and value, without disturbing the user. "
		"Cheaper than look_window, so read first.",
		run=lambda arguments: desktop.read_window(arguments["window"] or ""),
		parameters={"window": WINDOW},
		threaded=True,
	),
	Action(
		name="look_window",
		description="Shows you a window as a picture, even behind others, when read_window does not tell enough.",
		run=lambda arguments: desktop.look_window(arguments["window"] or ""),
		parameters={"window": WINDOW},
		threaded=True,
	),
	Action(
		name="press",
		description="Presses a button, link, tab or check box of a window, without a mouse.",
		run=lambda arguments: desktop.press(arguments["element"] or ""),
		parameters={"element": ELEMENT},
		threaded=True,
	),
	Action(
		name="fill",
		description="Writes text into a field of a window, in place of what it holds, without a keyboard.",
		run=lambda arguments: desktop.fill(arguments["element"] or "", arguments["text"] or ""),
		parameters={"element": ELEMENT, "text": Parameter("What to write.", required=True)},
		threaded=True,
	),
	Action(
		name="minecraft_start",
		description="Starts the test Minecraft client, a game instance of its own, never the user's. "
		"Ready once minecraft_state says loading: false.",
		run=lambda _: minecraft.start(),
		child=True,
	),
	Action(
		name="minecraft_state",
		description="The test client's screen, and in a world the player's position, rotation, health, gamemode and hotbar, as JSON.",
		run=lambda _: minecraft.call("/state"),
		threaded=True,
		child=True,
	),
	Action(
		name="minecraft_connect",
		description="Joins a server with the test client, whose player is ClaireChan, so the server needs online-mode=false.",
		run=lambda arguments: minecraft.call("/connect", {"address": arguments.get("address") or "localhost"}),
		parameters={"address": Parameter("host:port, localhost by default.")},
		threaded=True,
		child=True,
	),
	Action(
		name="minecraft_disconnect",
		description="Leaves the world or server of the test client, back to the title screen.",
		run=lambda _: minecraft.call("/disconnect"),
		threaded=True,
		child=True,
	),
	Action(
		name="minecraft_command",
		description="Runs a command as the test client's player. Its feedback arrives in minecraft_chat.",
		run=lambda arguments: minecraft.call("/command", {"command": arguments["command"] or ""}),
		parameters={"command": Parameter("The command, with or without its slash.", required=True)},
		threaded=True,
		child=True,
	),
	Action(
		name="minecraft_chat",
		description="The chat, system and action bar lines the test client received from an index on, and the next index.",
		run=lambda arguments: minecraft.call("/chat", {"after": arguments.get("after") or "0"}),
		parameters={"after": Parameter("Index of the first line, 0 by default.", kind="integer")},
		threaded=True,
		child=True,
	),
	Action(
		name="minecraft_hold",
		description="Holds a key of the test client for some ticks, after one click: forward, back, left, right, jump, sneak, sprint, "
		"use, attack, drop, swapOffhand, inventory or hotbar.1 to hotbar.9.",
		run=lambda arguments: minecraft.call("/hold", {"key": arguments["key"] or "", "ticks": arguments.get("ticks") or "1"}),
		parameters={
			"key": Parameter("The key's name.", required=True),
			"ticks": Parameter("How long, in ticks of 1/20 s, 1 by default.", kind="integer"),
		},
		threaded=True,
		child=True,
	),
	Action(
		name="minecraft_look",
		description="Turns the test client's player to a rotation.",
		run=lambda arguments: minecraft.call("/look", {"yaw": arguments.get("yaw") or "0", "pitch": arguments.get("pitch") or "0"}),
		parameters={
			"yaw": Parameter("Degrees, 0 south, 90 west.", kind="number"),
			"pitch": Parameter("Degrees, -90 up, 90 down.", kind="number"),
		},
		threaded=True,
		child=True,
	),
	Action(
		name="minecraft_screenshot",
		description="Shows you what the test client shows, saved into a picture file.",
		run=lambda _: minecraft.screenshot(),
		threaded=True,
		child=True,
	),
	Action(
		name="minecraft_quit",
		description="Closes the test client.",
		run=lambda _: minecraft.call("/quit"),
		threaded=True,
		child=True,
	),
	Action(
		name="mute",
		description="Mutes the PC's sound, or unmutes it when it is muted.",
		phrases=r"coupe le son|(?:re)?mets le son|mute|unmute",
		run=lambda _: press(VK_MUTE, said=tr("Done.", "C'est fait.")),
	),
]
""" Every action, tried in order. The lambdas call functions defined below. """
PHRASES: dict[str, re.Pattern[str]] = {
	action.name: re.compile(action.phrases, re.IGNORECASE) for action in ACTIONS if action.phrases
}
""" The phrase of each action that can be said aloud, by its name. """


# Functions
def find(name: str) -> Action:
	return next(action for action in ACTIONS if action.name == name)


def route(request: str) -> tuple[Action, dict[str, str | None]] | None:
	""" The action whose phrases are the whole request, with the punctuation around it, and the arguments it gives.

	>>> route("Capture l'écran 2.")[0].name, route("Capture l'écran 2.")[1]["screen"]
	('screenshot', '2')
	>>> route("Passe en Opus !")[0].name, route("Passe en Opus !")[1]["model"]
	('model', 'Opus')
	>>> route("Arrête la transcription.")[0].name
	'meeting_stop'
	>>> route("Il en est où ?")[0].name
	'agent_progress'
	>>> route("Mets pause, puis ouvre Spotify.") is None
	True
	"""
	found = match_phrase(PHRASES, request)
	return (find(found[0]), found[1].groupdict()) if found else None


def chosen_model(arguments: Mapping[str, str | None]) -> str | None:
	""" The model the arguments name, None when it is not one of `MODELS`.

	>>> chosen_model({"model": "Opus"}), chosen_model({"model": "gpt"})
	('opus', None)
	"""
	model = (arguments["model"] or "").lower()
	return model if model in MODELS else None


def set_timer(amount: str, unit: str, label: str) -> str:
	""" Starts a timer of `amount` of the unit starting with the letter of `unit`, and says how long it runs. """
	seconds = round(float(amount.replace(",", ".")) * UNITS[unit[0].lower()])
	ALARMS.start(seconds, label)
	hours, rest = divmod(seconds, 3600)
	minutes, secs = divmod(rest, 60)
	duration = " ".join(f"{value} {name}" for value, name in ((hours, "h"), (minutes, "min"), (secs, "s")) if value) or "0 s"
	return tr(f"{duration} timer started.", f"Minuteur de {duration} lancé.")


def forecast(city: str) -> str:
	if not city:
		return tr("Tell me the city.", "Dis-moi la ville.")
	return weather.forecast(city)


def screenshot(screen: int) -> Answer:
	""" Saves the screen, counted from 1 as Qt orders them, in the Screenshots folder of the user's pictures. """
	screens = QGuiApplication.screens()
	if screen > len(screens):
		plural = "s" * (len(screens) > 1)
		return tr(f"I only see {len(screens)} screen{plural}.", f"Je ne vois que {len(screens)} écran{plural}.")
	SCREENSHOTS.mkdir(parents=True, exist_ok=True)
	path = SCREENSHOTS / f"Capture {datetime.now():%Y-%m-%d %H-%M-%S}.png"
	screens[screen - 1].grabWindow(0).save(str(path))
	return Picture(said=tr(f"Screen {screen} captured in {path}.", f"Capture de l'écran {screen} enregistrée dans {path}."), path=path)


def press(*keys: int, said: str) -> str:
	""" Presses the keys together and returns `said`. """
	for key in keys:
		windll.user32.keybd_event(key, 0, 0, 0)
	for key in reversed(keys):
		windll.user32.keybd_event(key, 0, KEY_UP, 0)
	return said

