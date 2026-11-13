""" What the app types into the hidden session's pseudo-terminal, and what it recognises on the screen it draws back. """
# Imports
import re

# Constants
SESSION_URL: re.Pattern[str] = re.compile(r"https://claude\.ai/code/session_\w+")
RESUME_DIALOG: str = "Resume full session as-is"
""" Option of the dialog Claude Code shows when it resumes a large session after a long pause. """
PASTE_DELAY_MS: int = 400
""" Pause between the text and Enter, so the TUI takes the text as one paste before submitting it. """
FLAGS: tuple[str, ...] = (
	"--remote-control", "--permission-mode", "--model", "--agents", "--mcp-config", "--allowedTools", "--settings",
	"--append-system-prompt", "--resume", "--session-id", "--add-dir",
)
""" The options `claude` is started with, which its `--help` must still list. """


# Functions
def session_url(screen: str) -> str | None:
	""" The address Remote Control prints once the session is ready for prompts.

	>>> session_url("Remote Control active https://claude.ai/code/session_01AbC · /exit")
	'https://claude.ai/code/session_01AbC'
	>>> session_url("Starting...") is None
	True
	"""
	return match.group() if (match := SESSION_URL.search(screen)) else None


def asks_to_resume(screen: str) -> bool:
	""" Whether the screen shows the dialog that Enter answers with its first option, "Resume from summary". """
	return RESUME_DIALOG in screen


def missing_flags(help_text: str, flags: tuple[str, ...] = FLAGS) -> list[str]:
	""" The flags `claude --help` does not list.

	>>> missing_flags("  --resume <id>  Continue", ("--resume", "--session-id"))
	['--session-id']
	"""
	return [flag for flag in flags if flag not in help_text]

