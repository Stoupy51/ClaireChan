""" The dream's tools, on a git repository made like the one of the shared memory. """
# Imports
import json
from pathlib import Path

import pytest
from stouputils.typing import JsonDict

from clairechan.actions import find, route
from clairechan.report import Answer
from clairechan.services import dream

# Constants
INDEX: str = "- [Cache](cache.md) - where the cache lives\n"
TESTS_MEMORY: list[JsonDict] = [
	{"path": "memory/tests.md", "content": "Run the tests with uv.\n"},
	{"path": "memory/MEMORY.md", "content": INDEX + "- [Tests](tests.md) - how to run them\n"},
]
""" The files of a proposal that adds a memory and its line of the index. """


# Functions
@pytest.fixture
def memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
	""" The `memory` folder of a repository the dream's tools take for the shared one, with one memory committed on `main`. """
	folders = {
		"REPO": tmp_path / "claude", "HOME": tmp_path / "dream", "DIGESTS": tmp_path / "dream" / "digests",
		"PROPOSALS": tmp_path / "dream_memory", "STATE": tmp_path / "dream.json", "PROJECTS": tmp_path / "projects",
	}
	for name, folder in folders.items():
		monkeypatch.setattr(dream, name, folder)

	(dream.REPO / "memory").mkdir(parents=True)
	(dream.REPO / ".gitattributes").write_text("* text=auto eol=lf\nmemory/MEMORY.md merge=union\n", encoding="utf-8", newline="\n")
	dream.git(dream.REPO, "init", "-b", "main")
	dream.git(dream.REPO, "config", "user.name", "Claire")
	dream.git(dream.REPO, "config", "user.email", "claire@example.com")
	dream.git(dream.REPO, "add", ".gitattributes")
	write_memory(dream.REPO / "memory", {"MEMORY.md": INDEX, "cache.md": "The cache lives on D:.\n"})
	return dream.REPO / "memory"


def write_memory(memory: Path, files: dict[str, str]) -> None:
	""" Writes memories and commits them on `main`, as a session and its Stop hook do. """
	for name, text in files.items():
		(memory / name).write_text(text, encoding="utf-8", newline="\n")
	dream.git(memory, "add", "--all", ".")
	dream.git(memory, "commit", "-m", "Update memory")


def propose(summary: str, files: list[JsonDict]) -> Answer:
	arguments = {"summary": summary, "reason": "Asked in 2 sessions", "sessions": "abc, def", "files": json.dumps(files)}
	return find("dream_propose").run(arguments)


def test_a_digest_holds_what_was_said_since_the_last_dream_and_nothing_claude_code_keeps_for_itself(memory: Path) -> None:
	said = {"cwd": "D:/repo", "timestamp": "2026-11-12T10:00:00Z"}
	session = dream.PROJECTS / "project" / "abc.jsonl"
	agent = dream.PROJECTS / "project" / "abc" / "subagents" / "agent-a1.jsonl"
	own = dream.PROJECTS / "dream" / "own.jsonl"
	for folder in (agent.parent, own.parent):
		folder.mkdir(parents=True)
	session.write_text(json.dumps({"type": "user", "message": {"content": "Hier"}, **said}) + "\n", encoding="utf-8", newline="\n")

	assert str(find("dream_digest").run({})).startswith("No digest file: 0.0 MB of transcripts read")

	rows: list[JsonDict] = [
		{"type": "user", "message": {"content": "Lance les tests"}, **said},
		{"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "Exit code 1"}]}, **said},
		{"type": "api-request-blob", "message": {"content": "Lance les tests"}},
		{"type": "a-type-of-next-year", "text": "Lance les tests"},
		{"type": "ai-title", "aiTitle": "Tests"},
	]
	with session.open("a", encoding="utf-8", newline="\n") as file:
		file.write("".join(json.dumps(row) + "\n" for row in rows) + '{"type": "user", "mess')
	agent.write_text(json.dumps({"type": "user", "message": {"content": "Run pytest"}, **said}) + "\n", encoding="utf-8", newline="\n")
	agent.with_suffix(".meta.json").write_text(json.dumps({"description": "Run the tests"}), encoding="utf-8")
	asked = {"type": "user", "message": {"content": "Call dream_digest"}, "cwd": str(dream.HOME), "timestamp": "2026-11-12T11:00:00Z"}
	own.write_text(json.dumps(asked) + "\n", encoding="utf-8", newline="\n")

	assert f"Digest file: {dream.DIGESTS / '1.md'}" in str(find("dream_digest").run({}))
	assert (dream.DIGESTS / "1.md").read_text(encoding="utf-8") == (
		"## Session abc: Tests\nProject: D:/repo\nFrom 2026-11-12T10:00:00Z to 2026-11-12T10:00:00Z\n"
		"USER: Lance les tests\nERROR: Exit code 1\n"
		"## Agent of session abc: Run the tests\nProject: D:/repo\nFrom 2026-11-12T10:00:00Z to 2026-11-12T10:00:00Z\n"
		"USER: Run pytest"
	)

	with session.open("a", encoding="utf-8", newline="\n") as file:
		file.write('age": {"content": "Et maintenant ?"}, "cwd": "D:/repo", "timestamp": "2026-11-12T12:00:00Z"}\n')
	find("dream_digest").run({})
	assert (dream.DIGESTS / "1.md").read_text(encoding="utf-8").endswith("to 2026-11-12T12:00:00Z\nUSER: Et maintenant ?")


def test_a_proposal_is_a_commit_naming_its_sessions_and_never_leaves_the_memory_folder(memory: Path) -> None:
	find("dream_digest").run({})

	assert propose("Say how to run the tests", TESTS_MEMORY) == "Proposal 1 recorded."
	message = dream.git(dream.REPO, "log", "-1", "--format=%B", "dream").stdout.strip()
	assert message == "Say how to run the tests\n\nAsked in 2 sessions\n\nSessions: abc, def"
	assert not (memory / "tests.md").exists()

	hook: JsonDict = {"path": "hooks/commit_memory.py", "content": "import os\n"}
	assert propose("Speed up the hook", [hook]) == "Refused: a proposal only changes files of memory/, not hooks/commit_memory.py."
	assert str(propose("Speed up the hook", [hook | {"path": "memory/../hooks/commit_memory.py"}])).startswith("Refused")
	assert len(dream.proposals()) == 1


def test_an_accepted_proposal_joins_what_sessions_wrote_meanwhile_and_one_the_memory_outgrew_is_set_aside(memory: Path) -> None:
	find("dream_digest").run({})
	propose("Say how to run the tests", TESTS_MEMORY)
	propose("Move the cache", [{"path": "memory/cache.md", "content": "The cache lives on E:.\n"}])
	junction = "The cache lives on D:, behind a junction.\n"
	write_memory(memory, {"MEMORY.md": INDEX + "- [Ward](ward.md) - what 26.3 lacks\n", "cache.md": junction})

	action, arguments = route("Applique la proposition 1.") or (None, {})
	assert action
	assert action.run(arguments) == "Proposal 1 is in the memory."
	assert (memory / "tests.md").read_text(encoding="utf-8") == "Run the tests with uv.\n"
	assert set((memory / "MEMORY.md").read_text(encoding="utf-8").splitlines()) == {
		"- [Cache](cache.md) - where the cache lives", "- [Ward](ward.md) - what 26.3 lacks", "- [Tests](tests.md) - how to run them",
	}

	applied = dream.git(dream.REPO, "rev-parse", "HEAD").stdout
	assert str(find("dream_apply").run({"number": "2"})).startswith("The memory changed since proposal 2 was made")
	assert dream.git(dream.REPO, "rev-parse", "HEAD").stdout == applied
	assert dream.git(dream.REPO, "status", "--porcelain").stdout == ""
	assert (memory / "cache.md").read_text(encoding="utf-8") == junction
	assert find("dream_review").run({}) == "No proposal is waiting."


def test_a_refused_proposal_leaves_the_review_and_its_reason_reaches_the_next_dream(memory: Path) -> None:
	find("dream_digest").run({})
	propose("Say how to run the tests", TESTS_MEMORY)
	review = str(find("dream_review").run({}))
	assert review.startswith("Proposal 1: Say how to run the tests\n\nAsked in 2 sessions")
	assert "+Run the tests with uv." in review
	assert "still wait" in str(find("dream").run({}))
	assert "still wait" in str(find("dream_digest").run({}))

	action, arguments = route("Refuse la proposition 1, parce que c'est déjà dans le README.") or (None, {})
	assert action
	action.run(arguments)

	assert find("dream_review").run({}) == "No proposal is waiting."
	assert "- Say how to run the tests: c'est déjà dans le README" in str(find("dream_digest").run({}))
	assert not dream.proposals()

