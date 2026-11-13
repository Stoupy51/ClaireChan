""" Claude Code as the app reaches it: the only package that knows the formats it writes and reads. """
# Imports
import os
import subprocess
from pathlib import Path

from clairechan.config import APP_DATA

# Constants
PROJECTS: Path = Path.home() / ".claude" / "projects"
""" Where Claude Code keeps the transcripts of every session, under a folder per project. """
SESSION_ID: Path = APP_DATA / "session_id"
""" The conversation the app resumes, saved once a hook reports it, so a session that never got a prompt is not resumed. """
HOME: Path = APP_DATA / "home"
""" The folder the hidden session works in. """
NESTED_SESSION_VARS: tuple[str, ...] = (
	"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
	"CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_PID",
)
""" Set when the app runs inside another Claude Code session; a `claude` started with them refuses to start nested. """

PROBE_FLAGS: int = subprocess.CREATE_NO_WINDOW | subprocess.IDLE_PRIORITY_CLASS
""" How the probes start `claude`: low priority, so that checking an update never slows the app or the user's games. """


# Functions
def environment() -> dict[str, str]:
	""" The environment of a `claude` the app starts, without `NESTED_SESSION_VARS`. """
	return {name: value for name, value in os.environ.items() if name not in NESTED_SESSION_VARS}


def run(
	*arguments: str, cwd: str | Path | None = None, timeout: int = 60, creationflags: int = subprocess.CREATE_NO_WINDOW,
) -> subprocess.CompletedProcess[str]:
	""" Runs `claude` to its end with the arguments, never waiting for input. """
	return subprocess.run(
		["claude", *arguments], cwd=cwd, env=environment(), stdin=subprocess.DEVNULL, capture_output=True, text=True,
		encoding="utf-8", timeout=timeout, creationflags=creationflags,
	)

