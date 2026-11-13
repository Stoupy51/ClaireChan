""" The formats of Claude Code the app reads, and the probes that name the ones a new version changed. """
# Imports
import json
import subprocess
from pathlib import Path

import pytest
from stouputils.typing import JsonDict

from clairechan.claude_code import background, hooks, panels, probes, transcripts, trust

# Constants
USAGE_PANEL: str = (
	"Current session: 22% used · resets Oct 14, 1:30am (Europe/Paris)\n"
	"Current week (all models): 27% used · resets Oct 19, 12am (Europe/Paris)\n"
)
HELP: str = " ".join(probes.terminal.FLAGS + background.FLAGS)


# Functions
def test_context_size_is_read_from_the_last_reply_until_a_compaction(tmp_path: Path) -> None:
	usage = {"input_tokens": 2, "cache_read_input_tokens": 120_000, "cache_creation_input_tokens": 3000}
	reply = {"type": "assistant", "message": {"role": "assistant", "usage": usage}}
	transcript = tmp_path / "session.jsonl"
	transcript.write_text("\n".join(json.dumps(entry) for entry in [reply, {"type": "last-prompt"}]), encoding="utf-8")
	assert transcripts.context_tokens(transcript) == 123_002

	boundary = {"type": "system", "subtype": "compact_boundary"}
	transcript.write_text("\n".join(json.dumps(entry) for entry in [reply, boundary, {"type": "user"}]), encoding="utf-8")
	assert transcripts.context_tokens(transcript) == 0


@pytest.fixture
def claude_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
	""" A Claude Code whose surfaces all have the shape the app expects, and the version it reports as the only item of the list. """
	version = ["2.1.322"]
	def run(*arguments: str, **_options: object) -> subprocess.CompletedProcess[str]:
		return subprocess.CompletedProcess(arguments, 0, stdout=version[0] if arguments == ("--version",) else HELP)
	def panel(*_arguments: str, **_options: object) -> str:
		return USAGE_PANEL
	def rows(_creationflags: int) -> list[JsonDict]:
		return [{"kind": "background", "status": "idle", "id": "c63df584", "sessionId": "abc"}]

	reply = {"type": "assistant", "message": {"usage": dict.fromkeys(transcripts.CONTEXT_KINDS, 1)}}
	project = tmp_path / "projects" / "D--repo"
	project.mkdir(parents=True)
	(project / "abc.jsonl").write_text(json.dumps(reply), encoding="utf-8")
	(tmp_path / "claude.json").write_text(json.dumps({"projects": {"d:/repo": {trust.KEY: True}}}), encoding="utf-8")
	monkeypatch.setattr(probes, "run", run)
	monkeypatch.setattr(panels, "panel", panel)
	monkeypatch.setattr(background, "rows", rows)
	monkeypatch.setattr(probes, "PROJECTS", tmp_path / "projects")
	monkeypatch.setattr(probes, "SESSION_ID", tmp_path / "no_session")
	monkeypatch.setattr(probes, "VERSION_FILE", tmp_path / "claude_version")
	monkeypatch.setattr(trust, "FILE", tmp_path / "claude.json")
	monkeypatch.setattr(hooks, "SEEN", tmp_path / "hook_payloads.json")
	return version


def test_probes_stay_quiet_on_a_version_whose_formats_have_not_changed(claude_code: list[str]) -> None:
	update = probes.after_update()
	assert update == probes.Update("2.1.322", {})
	assert probes.after_update() is None

	claude_code[0] = "2.1.323"
	assert probes.after_update() == probes.Update("2.1.323", {})


def test_a_version_that_changes_a_format_is_announced_with_the_surface_it_broke(
	claude_code: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
	probes.after_update()
	claude_code[0] = "2.1.400"
	def usage_moved(*_arguments: str, **_options: int) -> str:
		return "Usage moved to claude.ai/usage"
	def rows_without_status(_creationflags: int) -> list[JsonDict]:
		return [{"kind": "background", "state": "idle", "id": "c63df584"}]
	monkeypatch.setattr(panels, "panel", usage_moved)
	monkeypatch.setattr(background, "rows", rows_without_status)
	(tmp_path / "projects" / "D--repo" / "abc.jsonl").write_text(
		json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 1}}}), encoding="utf-8",
	)
	hooks.record({"hook_event_name": "PreCompact", "session_id": "a", "transcript_path": "b", "reason": "auto"})

	update = probes.after_update()
	assert update
	assert update.version == "2.1.400"
	assert update.broken == {
		"usage": "the /usage panel does not show the two limits",
		"background": "a background row has no status",
		"transcripts": "usage has no cache_read_input_tokens",
		"hooks": "PreCompact has no trigger",
	}

