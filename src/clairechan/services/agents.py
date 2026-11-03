""" What the session's tool calls and its background agents do, the agents read from the transcripts Claude Code keeps. """
# Imports
import json
import time
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from stouputils.typing import JsonDict

from clairechan.config import APP_DATA
from clairechan.i18n import tr
from clairechan.report import Report, Slice
from clairechan.services import desktop
from clairechan.session import SESSION_ID

# Constants
PROJECTS: Path = Path.home() / ".claude" / "projects"
""" Where Claude Code keeps the transcripts of every session, under a folder per project. """
RECENT_S: int = 6 * 3600
""" The agents that did nothing for longer than this are left out. """
ACTIVE_S: int = 180
""" An agent that did nothing for this long is not running any more, or stuck. """
MAX_AGENTS: int = 3
HANDBACK: str = "SubagentHandback"
""" The tool an agent ends with, to hand its report back. """
USAGE_LOG: Path = APP_DATA / "usage.jsonl"
""" One line per time an agent stopped, holding what it used since it started: the last line of an agent is its total. """
CONTEXT_KINDS: tuple[str, ...] = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
""" The usage fields adding up to what the model read on a turn. """


# Functions
def progress() -> str:
	""" Where the background agents of the session stand: what each is, how long it runs, how many tool calls it made and the last. """
	folders = PROJECTS.glob(f"*/{SESSION_ID.read_text()}/subagents")
	now = time.time()
	transcripts = sorted(
		(path for folder in folders for path in folder.glob("agent-*.jsonl") if now - path.stat().st_mtime < RECENT_S),
		key=lambda path: path.stat().st_mtime, reverse=True,
	)[:MAX_AGENTS]
	if not transcripts:
		return tr("No agent worked on this session lately.", "Aucun agent n'a travaillé récemment sur cette session.")
	return "\n".join(describe_agent(path, now) for path in transcripts)


def describe_agent(transcript: Path, now: float) -> str:
	""" One line about an agent: its task, running or finished, its age, its tool calls and what it did last. """
	meta: JsonDict = json.loads(transcript.with_suffix(".meta.json").read_text(encoding="utf-8"))
	rows = read_rows(transcript)
	answers = [row["message"] for row in rows if row["type"] == "assistant"]
	if not answers:
		return tr(f"{meta['description']}: starting.", f"{meta['description']} : démarrage.")
	calls = [block for answer in answers for block in answer["content"] if block["type"] == "tool_use"]
	finished = answers[-1].get("stop_reason") == "end_turn" or (bool(calls) and calls[-1]["name"] == HANDBACK)
	idle_s = now - transcript.stat().st_mtime
	started = datetime.fromisoformat(next(row["timestamp"] for row in rows if "timestamp" in row))
	age_min = round((now - started.timestamp()) / 60)
	silent = tr("silent for ", "silencieux depuis ") + f"{round(idle_s / 60)} min"
	state = tr("finished", "terminé") if finished else tr("running", "en cours") if idle_s < ACTIVE_S else silent
	last = describe_tool(calls[-1]["name"], calls[-1]["input"]) if calls else "-"
	return tr(
		f"{meta['description']}: {state}, {age_min} min, {len(calls)} tool calls, last: {last}.",
		f"{meta['description']} : {state}, {age_min} min, {len(calls)} appels d'outils, dernier : {last}.",
	)


def log_usage(session_transcript: str, agent_id: str) -> None:
	""" Appends to `USAGE_LOG` what an agent used so far: its model, tokens, turns and the largest context it read. """
	transcript = Path(session_transcript).with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl"
	usages = [row["message"]["usage"] for row in read_rows(transcript) if row["type"] == "assistant" and "usage" in row["message"]]
	meta: JsonDict = json.loads(transcript.with_suffix(".meta.json").read_text(encoding="utf-8"))
	line = {
		"time": datetime.now().isoformat(timespec="seconds"), "agent": agent_id, "description": meta["description"],
		"model": meta.get("model", ""), "turns": len(usages),
		"peak_context": max((sum(usage.get(kind, 0) for kind in CONTEXT_KINDS) for usage in usages), default=0),
		**{kind: sum(usage.get(kind, 0) for usage in usages) for kind in (*CONTEXT_KINDS, "output_tokens")},
	}
	with USAGE_LOG.open("a", encoding="utf-8") as log:
		log.write(json.dumps(line) + "\n")


def usage_today() -> Report:
	""" What the agents used over the last day, one slice per model sized by the tokens it wrote. """
	since = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
	totals: dict[str, JsonDict] = {}
	for line in USAGE_LOG.read_text(encoding="utf-8").splitlines() if USAGE_LOG.exists() else []:
		row: JsonDict = json.loads(line)
		if row["time"] >= since:
			totals[row["agent"]] = row

	if not totals:
		return Report(tr("No agent used anything in the last day.", "Aucun agent n'a rien consommé depuis un jour."), ())

	by_model: defaultdict[str, list[JsonDict]] = defaultdict(list)
	for row in totals.values():
		by_model[row["model"]].append(row)
	written = {model: sum(row["output_tokens"] for row in rows) for model, rows in by_model.items()}
	turns = {model: sum(row["turns"] for row in rows) for model, rows in by_model.items()}
	slices = tuple(
		Slice(
			key=model, label=model,
			amount=tr(f"{len(rows)} agents, {turns[model]} turns", f"{len(rows)} agents, {turns[model]} tours"),
			share=tr(f"{written[model] // 1000}k written", f"{written[model] // 1000}k écrits"),
			fraction=written[model] / max(sum(written.values()), 1),
		)
		for model, rows in by_model.items()
	)
	read = sum(row["cache_read_input_tokens"] for row in totals.values()) // 1_000_000
	peak = max(row["peak_context"] for row in totals.values()) // 1000
	title = tr(
		f"Agents, last day\n{read}M read, largest context {peak}k",
		f"Agents, dernier jour\n{read}M relus, plus grand contexte {peak}k",
	)
	return Report(title, slices)


def read_rows(transcript: Path) -> list[JsonDict]:
	""" The entries of a transcript, leaving out a line still being written. """
	rows: list[JsonDict] = []
	for line in transcript.read_text(encoding="utf-8").splitlines():
		with suppress(json.JSONDecodeError):
			rows.append(json.loads(line))
	return rows


def describe_tool(name: str, tool_input: JsonDict) -> str:
	""" What a tool call does, in a few words for the bubble.

	>>> describe_tool("Edit", {"file_path": "D:/repo/clairechan/app.py", "old_string": "a", "new_string": "b"})
	'edits app.py'
	>>> describe_tool("Bash", {"command": "git status", "description": "Show working tree status"})
	'Show working tree status'
	>>> describe_tool("mcp__clairechan__screenshot", {"screen": 2})
	'screenshot'
	"""
	match name:
		case "Read":
			return tr("reads ", "lit ") + Path(tool_input["file_path"]).name
		case "Write":
			return tr("writes ", "écrit ") + Path(tool_input["file_path"]).name
		case "Edit" | "MultiEdit":
			return tr("edits ", "modifie ") + Path(tool_input["file_path"]).name
		case "Bash" | "PowerShell":
			return tool_input.get("description") or tr("runs ", "lance ") + tool_input["command"][:60]
		case "Grep" | "Glob":
			return tr("searches ", "cherche ") + tool_input["pattern"]
		case "WebSearch":
			return tr(f'searches the web for "{tool_input["query"]}"', f"cherche « {tool_input['query']} » sur le web")
		case "WebFetch":
			return tr("reads ", "lit ") + urlparse(str(tool_input["url"])).netloc
		case "Agent" | "Task":
			return tr("hands off a task: ", "confie une tâche : ") + tool_input["description"]
		case "AskUserQuestion":
			return tool_input["questions"][0]["question"]
		case "mcp__clairechan__press" | "mcp__clairechan__fill" if element := desktop.ELEMENTS.get(str(tool_input["element"])):
			verb = tr("presses ", "appuie sur ") if name.endswith("press") else tr("fills ", "remplit ")
			return f"{verb}{element.label} ({Path(element.app).stem})"
		case _:
			return name.rsplit("__", 1)[-1]

