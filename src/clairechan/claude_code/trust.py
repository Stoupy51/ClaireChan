""" The folders Claude Code trusts, recorded as `hasTrustDialogAccepted` per project in `~/.claude.json`. """
# Imports
import json
from pathlib import Path

from stouputils.typing import JsonDict, is_generic_instance

# Constants
FILE: Path = Path.home() / ".claude.json"
KEY: str = "hasTrustDialogAccepted"


# Functions
def is_trusted(folder: Path) -> bool:
	""" Whether the user told Claude Code it may work in the folder. """
	return any(settings.get(KEY) for settings in matching(read().get("projects", {}), folder).values())


def trust(folder: Path) -> None:
	""" Has Claude Code trust the folder, as `claude --bg` needs. """
	settings = read()
	projects: JsonDict = settings.setdefault("projects", {})
	keys = list(matching(projects, folder)) or [folder.as_posix()]
	if all(projects.get(key, {}).get(KEY) for key in keys):
		return

	for key in keys:
		projects.setdefault(key, {})[KEY] = True
	# Claude Code rewrites this file too: replacing it in one step never leaves it half written
	draft = FILE.with_name(".claude.json.clairechan")
	draft.write_text(json.dumps(settings, indent=2), encoding="utf-8")
	draft.replace(FILE)


def matching(projects: JsonDict, folder: Path) -> JsonDict:
	""" The entries of `projects` for the folder, as Claude Code writes the drive letter in either case.

	>>> matching({"d:/a": {}, "D:/b": {}}, Path("D:/a"))
	{'d:/a': {}}
	"""
	return {key: settings for key, settings in projects.items() if key.lower() == folder.as_posix().lower()}


def read() -> JsonDict:
	return json.loads(FILE.read_text(encoding="utf-8"))


def broken_file(settings: JsonDict) -> str | None:
	""" What the app reads of the file that it does not have, None when it has it all. """
	projects = settings.get("projects")
	if not is_generic_instance(projects, dict[str, JsonDict]):
		return "there is no projects table"
	if projects and not any(KEY in entry for entry in projects.values()):
		return f"no project has {KEY}"
	return None

