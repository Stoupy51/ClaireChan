""" The transcripts Claude Code keeps of every session and of each agent it runs, as JSON lines under `PROJECTS`. """
# Imports
import json
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path

from stouputils.typing import JsonDict

from clairechan.claude_code import PROJECTS

# Constants
CONTEXT_KINDS: tuple[str, ...] = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
""" The usage fields adding up to what the model read on a turn. """


# Functions
def read_rows(transcript: Path) -> list[JsonDict]:
	""" The entries of a transcript, leaving out a line still being written. """
	rows: list[JsonDict] = []
	for line in transcript.read_text(encoding="utf-8").splitlines():
		with suppress(json.JSONDecodeError):
			rows.append(json.loads(line))
	return rows


def replies(rows: Iterable[JsonDict]) -> list[JsonDict]:
	""" The model's replies that report their usage, as the `message` of each entry. """
	return [row["message"] for row in rows if row["type"] == "assistant" and "usage" in row["message"]]


def context_size(usage: JsonDict) -> int:
	""" What the model read on a turn, from the `usage` of its reply. """
	return sum(usage.get(kind, 0) for kind in CONTEXT_KINDS)


def context_tokens(transcript: Path) -> int:
	""" Size of a conversation at its last reply, 0 when it was compacted since. """
	for line in reversed(transcript.read_text(encoding="utf-8").splitlines()):
		entry = json.loads(line)
		if entry.get("subtype") == "compact_boundary":
			return 0
		if usage := entry.get("message", {}).get("usage"):
			return context_size(usage)
	return 0


def sessions(session_id: str) -> list[Path]:
	""" The transcripts of a session, one per project it ran in. """
	return list(PROJECTS.glob(f"*/{session_id}.jsonl"))


def agents_of(session_id: str) -> list[Path]:
	""" The transcripts of the agents a session started. """
	return [path for folder in PROJECTS.glob(f"*/{session_id}/subagents") for path in folder.glob("agent-*.jsonl")]


def agent_of(session_transcript: Path, agent_id: str) -> Path:
	""" Where an agent of the session keeps its transcript, which does not exist for Claude Code's own helpers. """
	return session_transcript.with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl"


def agent_ids(session_transcript: Path) -> list[str]:
	return [path.stem.removeprefix("agent-") for path in (session_transcript.with_suffix("") / "subagents").glob("agent-*.jsonl")]


def read_meta(agent_transcript: Path) -> JsonDict:
	""" What an agent is, with its `description` and, when set, its `model`. """
	return json.loads(agent_transcript.with_suffix(".meta.json").read_text(encoding="utf-8"))


def broken_rows(rows: list[JsonDict]) -> str | None:
	""" What the app reads of a transcript that its entries do not have, None when they have it all. """
	assistant = [row for row in rows if row.get("type") == "assistant"]
	if not assistant:
		return None
	if any("message" not in row for row in assistant):
		return "an assistant entry has no message"
	if not (answers := replies(assistant)):
		return "no reply reports its usage"
	return next((f"usage has no {kind}" for answer in answers for kind in CONTEXT_KINDS if kind not in answer["usage"]), None)

