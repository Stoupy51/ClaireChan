""" Child sessions started with `claude --bg`: the line it prints, and the list `claude agents` gives. """
# Imports
import json
import re
import subprocess

from stouputils.typing import JsonDict

from clairechan.claude_code import run

# Constants
STARTED: re.Pattern[str] = re.compile(r"backgrounded\W+(?P<id>[0-9a-f]+)")
""" The line `claude --bg` prints, such as "backgrounded · c63df584 · Name". """
ROW_KEYS: tuple[str, ...] = ("kind", "status")
BACKGROUND_KEYS: tuple[str, ...] = ("id", "sessionId")
""" What a row of a background session has on top of `ROW_KEYS`. """
FLAGS: tuple[str, ...] = ("--bg", "--name", "--model", "--effort")
""" The options of `claude --bg` the app passes, which `claude --help` must still list. """


# Functions
def started_id(output: str) -> str | None:
	""" The id of the child `claude --bg` started, None when its output does not say it did.

	>>> started_id("backgrounded · c63df584 · Name")
	'c63df584'
	>>> started_id("error: unknown option") is None
	True
	"""
	return match["id"] if (match := STARTED.search(output)) else None


def rows(creationflags: int = subprocess.CREATE_NO_WINDOW) -> list[JsonDict]:
	""" Every session `claude agents` lists. """
	return json.loads(run("agents", "--json", creationflags=creationflags).stdout)


def sessions() -> dict[str, JsonDict]:
	""" What `claude agents` tells about each background session, its `status` and `sessionId` among it, by id. """
	return {row["id"]: row for row in rows() if row["kind"] == "background"}


def broken_rows(listed: list[JsonDict]) -> str | None:
	""" What the app reads of the list that a row does not have, None when they have it all. """
	for row in listed:
		wanted = ROW_KEYS + (BACKGROUND_KEYS if row.get("kind") == "background" else ())
		if missing := [key for key in wanted if key not in row]:
			return f"a {row.get('kind')} row has no {missing[0]}"
	return None

