""" Claude Code as the app reaches it: where it keeps its files, and how to start it outside the session the app may run in. """
# Imports
import os
from pathlib import Path

from clairechan.config import APP_DATA

# Constants
PROJECTS: Path = Path.home() / ".claude" / "projects"
""" Where Claude Code keeps the transcripts of every session, under a folder per project. """
SESSION_ID: Path = APP_DATA / "session_id"
""" The conversation the app resumes, saved once a hook reports it, so a session that never got a prompt is not resumed. """
HOME: Path = APP_DATA / "home"
""" The folder the hidden session works in, whose memory stays apart from the one of the sessions that develop the app. """
NESTED_SESSION_VARS: tuple[str, ...] = (
	"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
	"CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_PID",
)
""" Set when the app runs inside another Claude Code session; a `claude` started with them refuses to start nested. """


# Functions
def environment() -> dict[str, str]:
	""" The environment of a `claude` the app starts, without `NESTED_SESSION_VARS`. """
	return {name: value for name, value in os.environ.items() if name not in NESTED_SESSION_VARS}

