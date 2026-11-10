""" The changes the hidden session makes to the app's code, and which process must start again to run them.

Her face (`clairechan.face`: her windows, her reactions and her actions) starts again alone in a second or two, on the same session.
A change to a module the core has loaded (the session, her ears and her voice, the servers) starts the whole app again.
"""
# Imports
import sys
from contextlib import suppress
from pathlib import Path

from clairechan import launcher
from clairechan.config import ROOT

# Constants
PACKAGE: Path = Path(__file__).parent
ASSETS: Path = ROOT / "assets"
""" Images her windows load when they are built. """


# Classes
class Changes:
	""" The app's files as the running processes loaded them, compared with what they hold now. """

	def __init__(self) -> None:
		self.loaded = watched_files()
		self.since = launcher.git(ROOT, "rev-parse", "HEAD")
		""" The commit the running code was loaded from, after which the session's commits belong to its change. """

	def edited(self) -> list[str]:
		""" The files changed, added or deleted since they were loaded. """
		files = watched_files()
		return sorted(str(path) for path in self.loaded.keys() | files.keys() if self.loaded.get(path) != files.get(path))

	def applied(self) -> None:
		""" Takes the files as they are for what runs, once the process a change was for has started on them. """
		self.loaded = watched_files()
		self.since = launcher.git(ROOT, "rev-parse", "HEAD")


# Functions
def watched_files() -> dict[Path, bytes]:
	""" The app's code and images, without one the session deletes while they are read. """
	files: dict[Path, bytes] = {}
	for path in [*PACKAGE.rglob("*.py"), *ASSETS.rglob("*.png")]:
		with suppress(FileNotFoundError):
			files[path] = path.read_bytes()
	return files


def reach_this_process(edited: list[str]) -> bool:
	""" Whether one of the files is a module the process that asks has loaded. """
	loaded = {Path(file).resolve() for module in list(sys.modules.values()) if (file := getattr(module, "__file__", None))}
	return any(Path(path).resolve() in loaded for path in edited)

