""" One probe per surface of Claude Code the app reads, run when `claude --version` changes, naming what broke. """
# Imports
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from clairechan.claude_code import PROBE_FLAGS, PROJECTS, SESSION_ID, background, hooks, panels, run, terminal, transcripts, trust
from clairechan.config import APP_DATA

# Constants
VERSION_FILE: Path = APP_DATA / "claude_version"
""" The version of Claude Code the probes last ran on. """


# Classes
@dataclass(frozen=True)
class Update:
	version: str
	broken: dict[str, str]
	""" Why each surface that no longer works is broken, by the surface's name. """


# Functions
def after_update() -> Update | None:
	""" Runs every probe when Claude Code has a version the probes did not run on yet, None when it has not changed. """
	version = run("--version", creationflags=PROBE_FLAGS).stdout.strip()
	if VERSION_FILE.exists() and VERSION_FILE.read_text(encoding="utf-8") == version:
		return None
	broken: dict[str, str] = {}
	for surface, probe in PROBES.items():
		try:
			problem = probe()
		except Exception as error:
			problem = f"{type(error).__name__}: {error}"
		if problem:
			broken[surface] = problem
	VERSION_FILE.write_text(version, encoding="utf-8")
	return Update(version, broken)


def probe_usage() -> str | None:
	return None if panels.plan_usage(PROBE_FLAGS) else "the /usage panel does not show the two limits"


def probe_context() -> str | None:
	if not SESSION_ID.exists():
		return None
	shown = panels.context(SESSION_ID.read_text(), PROBE_FLAGS)
	return None if shown else "the /context panel does not show the model, the size and the table"


def probe_terminal() -> str | None:
	help_text = run("--help", creationflags=PROBE_FLAGS).stdout
	return f"--help does not list {', '.join(missing)}" if (missing := terminal.missing_flags(help_text)) else None


def probe_background() -> str | None:
	help_text = run("--help", creationflags=PROBE_FLAGS).stdout
	if missing := terminal.missing_flags(help_text, background.FLAGS):
		return f"--help does not list {', '.join(missing)}"
	return background.broken_rows(background.rows(PROBE_FLAGS))


def probe_transcripts() -> str | None:
	newest = max(PROJECTS.glob("*/*.jsonl"), key=lambda path: path.stat().st_mtime, default=None)
	return transcripts.broken_rows(transcripts.read_rows(newest)) if newest else None


def probe_config() -> str | None:
	return trust.broken_file(trust.read())


def probe_hooks() -> str | None:
	return hooks.broken_payloads()


PROBES: dict[str, Callable[[], str | None]] = {
	"usage": probe_usage, "context": probe_context, "terminal": probe_terminal, "background": probe_background,
	"transcripts": probe_transcripts, "config": probe_config, "hooks": probe_hooks,
}
""" What each surface's probe returns: why it is broken, None when it works. """

