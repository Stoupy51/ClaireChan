""" The `/usage` and `/context` panels, which a fresh `claude -p` prints in about 3 s without a model call. """
# Imports
import re
import subprocess
from dataclasses import dataclass

from clairechan.claude_code import HOME, run

# Constants
PLAN_USAGE: re.Pattern[str] = re.compile(
	r"Current session: (?P<window>\d+)% used\W+resets (?P<window_reset>[^\n]*)\n"
	r"Current week \(all models\): (?P<week>\d+)% used\W+resets (?P<week_reset>[^\n]*)",
)
""" The two limits `/usage` prints, each followed by when it resets, such as "Oct 19, 12am (Europe/Paris)". """
CONTEXT: re.Pattern[str] = re.compile(r"\*\*Model:\*\* (?P<model>\S+)\s+\*\*Tokens:\*\* (?P<tokens>[^\n]*?)\s*\n")
""" The model and the size of the conversation `/context` prints, such as "107.6k / 1m (11%)". """
SHARES: re.Pattern[str] = re.compile(r"^\| (?P<name>[^|]+?) \| (?P<tokens>\d\S*) \| (?P<share>\S+) \|$", re.MULTILINE)
""" A row of the table of what fills the context, such as "| Messages | 290.6k | 29.1% |". """
SHARES_TITLE: str = "### Estimated usage by category"
MAGNITUDES: dict[str, int] = {"k": 1000, "m": 1_000_000}
""" What the suffix of a number of tokens multiplies it by. """


# Classes
@dataclass(frozen=True)
class Limit:
	percent: int
	resets: str
	""" When it resets, with its time zone, such as "Oct 19, 12am (Europe/Paris)". """


@dataclass(frozen=True)
class PlanUsage:
	window: Limit
	""" The 5-hour window. """
	week: Limit


@dataclass(frozen=True)
class Share:
	name: str
	tokens: str
	""" As `/context` writes it, such as "2.4k". """
	percent: str
	""" As `/context` writes it, such as "29.1%". """


@dataclass(frozen=True)
class ContextUsage:
	model: str
	tokens: str
	""" The size of the conversation as `/context` writes it, such as "107.6k / 1m (11%)". """
	shares: tuple[Share, ...]
	""" What fills the context, from the largest to the smallest, the free space last. """


# Functions
def read_plan_usage(panel_text: str) -> PlanUsage | None:
	""" The limits of a `/usage` panel, None when it does not show them the way it did.

	>>> read_plan_usage("Current session: 22% used, resets Oct 14\\nCurrent week (all models): 27% used, resets Oct 19")
	PlanUsage(window=Limit(percent=22, resets='Oct 14'), week=Limit(percent=27, resets='Oct 19'))
	>>> read_plan_usage("Usage is now shown on the web") is None
	True
	"""
	if not (match := PLAN_USAGE.search(panel_text)):
		return None
	return PlanUsage(Limit(int(match["window"]), match["window_reset"]), Limit(int(match["week"]), match["week_reset"]))


def read_context(panel_text: str) -> ContextUsage | None:
	""" The model, size and shares of a `/context` panel, None when it does not show them the way it did. """
	if not (match := CONTEXT.search(panel_text)):
		return None
	table = panel_text.split(SHARES_TITLE)[-1].split("###")[0]
	shares = sorted(
		(Share(row["name"], row["tokens"], row["share"]) for row in SHARES.finditer(table) if "deferred" not in row["name"]),
		key=lambda share: (share.name == "Free space", -tokens(share.tokens)),
	)
	return ContextUsage(match["model"], match["tokens"], tuple(shares)) if shares else None


def tokens(amount: str) -> float:
	""" A number of tokens as `/context` writes it.

	>>> tokens("2.4k"), tokens("671"), tokens("1m")
	(2400.0, 671.0, 1000000.0)
	"""
	return float(amount.rstrip("km")) * MAGNITUDES.get(amount[-1], 1)


def plan_usage(creationflags: int = subprocess.CREATE_NO_WINDOW) -> PlanUsage | None:
	return read_plan_usage(panel("/usage", creationflags=creationflags))


def context(session_id: str, creationflags: int = subprocess.CREATE_NO_WINDOW) -> ContextUsage | None:
	""" The `/context` of a conversation. """
	return read_context(panel("/context", "--resume", session_id, "--fork-session", creationflags=creationflags))


def panel(command: str, *options: str, creationflags: int = subprocess.CREATE_NO_WINDOW) -> str:
	""" What `claude` prints for the slash command. """
	return run("-p", command, "--no-session-persistence", *options, cwd=HOME, timeout=30, creationflags=creationflags).stdout

