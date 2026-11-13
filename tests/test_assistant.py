""" Claire's reactions to the session's hook events, and the queue that keeps commands from being typed during a turn. """
# Imports
from concurrent.futures import Future
from ctypes import windll
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from stouputils.typing import JsonDict

import clairechan.app as app
import clairechan.config
from clairechan.actions import VK_MUTE
from clairechan.assistant import FILLERS, Assistant
from clairechan.config import DEFAULTS, Config
from clairechan.i18n import tr
from clairechan.overlay import avatar as avatar_module
from clairechan.overlay.avatar import Avatar, Pill


# Functions
@pytest.fixture
def assistant(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> Assistant:
	monkeypatch.setattr(avatar_module, "chime", mute)
	monkeypatch.setattr(clairechan.config, "USER_CONFIG", DEFAULTS)
	return Assistant(Avatar(), Pill(), Config.load())


def mute(*_notes: float) -> None:
	""" Stands in for the chimes, which would ring on the speakers during the tests. """


def hook(name: str, **fields: object) -> JsonDict:
	return {"hook_event_name": name, **fields}


def test_she_names_the_surfaces_a_claude_code_update_broke(assistant: Assistant) -> None:
	assistant.on_claude_code_broke("2.1.400", {"usage": "no limits", "hooks": "PreCompact has no trigger"})
	assert assistant.avatar.bubble.text == "Claude Code updated to 2.1.400 and I can no longer read: usage, hooks. The log says why."


def test_commands_wait_for_the_running_turn(assistant: Assistant) -> None:
	sent: list[str] = []
	assistant.send.connect(sent.append)
	assistant.on_command("ouvre Spotify")
	assistant.on_hook(hook("UserPromptSubmit", prompt="ouvre Spotify"))
	assistant.on_command("mets de la musique")
	assert sent == ["ouvre Spotify"]

	assistant.on_hook(hook("Stop", last_assistant_message="Spotify est ouvert."))
	assert sent == ["ouvre Spotify", "mets de la musique"]


def test_commands_wait_for_a_compaction_between_turns(assistant: Assistant) -> None:
	sent: list[str] = []
	assistant.send.connect(sent.append)
	assistant.on_hook(hook("PreCompact", trigger="manual", custom_instructions=None))
	assistant.on_command("ouvre Spotify")
	assert sent == []

	assistant.on_hook(hook("PostCompact", trigger="manual", compact_summary="Résumé"))
	assert sent == ["ouvre Spotify"]


def test_an_automatic_compaction_keeps_the_turn_running(assistant: Assistant) -> None:
	sent: list[str] = []
	assistant.send.connect(sent.append)
	assistant.on_hook(hook("UserPromptSubmit", prompt="range le projet"))
	assistant.on_hook(hook("PreCompact", trigger="auto", custom_instructions=None))
	assistant.on_hook(hook("PostCompact", trigger="auto", compact_summary="Résumé"))
	assistant.on_command("ouvre Spotify")
	assert sent == []


def log_nothing(session_transcript: str, agent_id: str) -> None:
	pass


def test_background_work_keeps_the_pill_until_its_result(assistant: Assistant, monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr("clairechan.assistant.log_usage", log_nothing)
	assistant.on_hook(hook("UserPromptSubmit", prompt="range le projet"))
	assistant.on_hook(hook("SubagentStart", agent_id="a1", agent_type="expert"))
	assistant.on_hook(hook("Stop", last_assistant_message="Je confie ça à l'expert."))
	assistant.leave()
	assert assistant.pill.isVisible()

	assistant.on_hook(hook("SubagentStop", agent_id="a1", agent_type="expert", transcript_path="", last_assistant_message="Rangé."))
	assistant.on_hook(hook("UserPromptSubmit", prompt="L'expert a fini."))
	assistant.on_hook(hook("Stop", last_assistant_message="Le projet est rangé."))
	assert not assistant.pill.isVisible()
	assert assistant.avatar.bubble.text == "Le projet est rangé."


def test_she_says_one_filler_when_the_first_agent_starts(assistant: Assistant) -> None:
	said: list[str] = []
	def record(text: str, _style: int) -> None:
		said.append(text)
	assistant.speak.connect(record)
	assistant.on_hook(hook("SubagentStart", agent_id="a1"))
	assistant.on_hook(hook("SubagentStart", agent_id="a2"))
	assert len(said) == 1
	assert said[0] in [tr(*filler) for filler in FILLERS]


def test_permission_is_asked_then_thanked(assistant: Assistant) -> None:
	command = {"command": "rm -r build", "description": "Supprime build"}
	assistant.on_hook(hook("UserPromptSubmit", prompt="supprime le dossier build"))
	assistant.on_hook(hook("PreToolUse", tool_name="Bash", tool_input=command, tool_use_id="t1"))
	assistant.on_hook(hook("PermissionRequest", tool_name="Bash", tool_input=command))
	assistant.on_hook(hook("PreToolUse", tool_name="ToolSearch", tool_input={}, tool_use_id="t2"))
	assistant.on_hook(hook("PostToolUse", tool_name="ToolSearch", tool_input={}, tool_response={}, tool_use_id="t2"))
	assert assistant.avatar.expression == "please"

	assistant.on_hook(hook("PostToolUse", tool_name="Bash", tool_input=command, tool_response={}, tool_use_id="t1"))
	assert assistant.avatar.expression == "thanks"



def test_local_actions_skip_the_session(assistant: Assistant, monkeypatch: pytest.MonkeyPatch) -> None:
	keys: list[int] = []
	def press(key: int, _scan: int, flags: int, _extra: int) -> None:
		if not flags:
			keys.append(key)
	monkeypatch.setattr(windll.user32, "keybd_event", press)
	sent: list[str] = []
	assistant.send.connect(sent.append)
	assistant.on_command("Coupe le son.")
	assert keys == [VK_MUTE]
	assert sent == []
	assert assistant.avatar.expression == "present"


def test_stopping_everything_restarts_the_session_and_forgets_the_work(assistant: Assistant) -> None:
	restarts: list[bool] = []
	assistant.restart.connect(lambda: restarts.append(True))
	assistant.on_hook(hook("UserPromptSubmit", prompt="range le projet"))
	assistant.on_hook(hook("SubagentStart", agent_id="worker"))
	assistant.on_command("Stop.")
	assert restarts == [True]
	assert not assistant.busy
	assert not assistant.agents
	assert assistant.avatar.expression == "present"


def test_telling_her_to_restart_asks_for_the_whole_app_to_start_again(assistant: Assistant) -> None:
	restarts: list[bool] = []
	assistant.restart_app.connect(lambda: restarts.append(True))
	assistant.on_command("Relance-toi.")
	assert restarts == [True]
	assert assistant.avatar.expression == "present"


def test_switching_model_by_voice_types_it_into_the_session(assistant: Assistant) -> None:
	sent: list[str] = []
	assistant.send.connect(sent.append)
	assistant.on_command("Passe en Opus.")
	assert sent == ["/model opus"]


def test_a_spoken_verdict_answers_the_pending_permission_request(assistant: Assistant) -> None:
	answer: Future[bool] = Future()
	asking: list[str] = []
	assistant.listening_for_answer.connect(lambda: asking.append("asking"))
	assistant.answer_settled.connect(lambda: asking.append("settled"))
	assistant.on_hook(hook("PermissionRequest", tool_name="Bash", tool_input={"command": "git status"}))
	assistant.on_permission_asked(answer)
	assistant.on_verdict(allowed=True)
	assert answer.result() is True
	assert asking == ["asking", "settled"]
	assert assistant.avatar.expression == "thanks"


def test_settings_of_a_new_app_restart_it_once_she_is_free(assistant: Assistant, monkeypatch: pytest.MonkeyPatch) -> None:
	restarts: list[bool] = []
	assistant.restart.connect(lambda: restarts.append(True))
	config = Config.load()
	assistant.on_config(config, ["wake"])
	assistant.leave()
	assert restarts == []

	assistant.on_hook(hook("UserPromptSubmit", prompt="range le projet"))
	assistant.on_config(config, ["prompt"])
	assistant.leave()
	assert restarts == []

	assistant.on_hook(hook("Stop", last_assistant_message="C'est rangé."))
	assistant.leave()
	assert restarts == [True]


def test_she_stays_until_her_voice_has_said_her_reply_but_never_leaves_for_it(assistant: Assistant) -> None:
	said: list[str] = []

	def speak(text: str, _style: int) -> None:
		said.append(text)

	assistant.speak.connect(speak)
	assistant.on_hook(hook("Stop", last_assistant_message="The tests pass."))
	assistant.on_speaking(((0.0, "e"), (30.0, "")))
	assert said == ["The tests pass."]
	assert assistant.dismiss.remainingTime() > 30_000

	assistant.on_hook(hook("UserPromptSubmit", prompt="delete the build folder"))
	assistant.on_hook(hook("PermissionRequest", tool_name="Bash", tool_input={"command": "rm -r build", "description": "Delete it"}))
	assistant.on_speaking(((0.0, "e"), (5.0, "")))
	assert not assistant.dismiss.isActive()


def test_previous_crash_is_logged_once_with_its_stack(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
	crash_file = tmp_path / "crash.log"
	crash = "Windows fatal exception: access violation\n"
	crash_file.write_text(f"=== start 10:00 ===\n{crash}=== start 11:00 ===\n{crash}  File windows.py, line 50\n", encoding="utf-8")
	monkeypatch.setattr(app, "CRASH_FILE", crash_file)
	app.report_previous_crash()
	assert "line 50" in caplog.text
	assert caplog.text.count("access violation") == 1
	caplog.clear()
	crash_file.write_text(f"{crash_file.read_text(encoding='utf-8')}=== start 12:00 ===\n", encoding="utf-8")
	app.report_previous_crash()
	assert not caplog.text

