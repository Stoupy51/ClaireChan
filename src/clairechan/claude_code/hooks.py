""" The events Claude Code posts to the app's `type: "http"` hooks, and the fields of their payloads that the app reads. """
# Imports
import json
from pathlib import Path

from stouputils.typing import JsonDict

from clairechan.config import APP_DATA

# Constants
SEEN: Path = APP_DATA / "hook_payloads.json"
""" The field names of the last payload of each kind of event, which no `claude` command can produce without a model call. """
EVENTS: tuple[str, ...] = (
	"UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Notification", "MessageDisplay",
	"SubagentStart", "SubagentStop", "Stop", "StopFailure", "PreCompact", "PostCompact",
)
COMMON: tuple[str, ...] = ("hook_event_name", "session_id", "transcript_path")
FIELDS: dict[str, tuple[str, ...]] = {
	"UserPromptSubmit": ("prompt",),
	"PreToolUse": ("tool_name", "tool_input"),
	"PostToolUse": ("tool_name", "tool_input"),
	"PermissionRequest": ("tool_name", "tool_input"),
	"Notification": ("notification_type", "message"),
	"MessageDisplay": ("message_id", "delta", "final"),
	"SubagentStart": ("agent_id",),
	"SubagentStop": ("agent_id",),
	"Stop": ("last_assistant_message",),
	"StopFailure": ("error",),
	"PreCompact": ("trigger",),
	"PostCompact": ("trigger",),
}
""" What each event's payload holds on top of `COMMON`, as the app reads it. """


# Functions
def record(event: JsonDict) -> None:
	""" Keeps the field names of the last payload of each kind, which `broken_payloads` checks. """
	seen: dict[str, list[str]] = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {}
	if seen.get(event["hook_event_name"]) != list(event):
		seen[event["hook_event_name"]] = list(event)
		SEEN.write_text(json.dumps(seen), encoding="utf-8")


def broken_payloads() -> str | None:
	""" What the app reads of the payloads recorded that one does not have, None when they have it all. """
	seen: dict[str, list[str]] = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {}
	for name, fields in seen.items():
		if missing := missing_fields(dict.fromkeys(fields) | {"hook_event_name": name}):
			return f"{name} has no {missing[0]}"
	return None


def missing_fields(event: JsonDict) -> list[str]:
	""" The fields the app reads that a payload does not have.

	>>> missing_fields({"hook_event_name": "PreCompact", "session_id": "a", "transcript_path": "b"})
	['trigger']
	"""
	return [field for field in COMMON + FIELDS.get(event.get("hook_event_name", ""), ()) if field not in event]

