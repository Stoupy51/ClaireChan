""" The phrases of the actions as Whisper writes them, which the listener matches without loading the actions themselves. """
# Imports
import re
from collections.abc import Mapping

# Constants
CURLY_APOSTROPHE: str = chr(0x2019)
""" The apostrophe Whisper sometimes writes, turned into a straight one before matching phrases. """


# Functions
def match_phrase(phrases: Mapping[str, re.Pattern[str]], request: str) -> tuple[str, re.Match[str]] | None:
	""" The first action whose phrase is the whole request, with the punctuation around it, and its match.

	>>> phrases = {"mute": re.compile("coupe le son|mute", re.IGNORECASE)}
	>>> match_phrase(phrases, "Coupe le son !")[0]
	'mute'
	>>> match_phrase(phrases, "Coupe le son, puis ouvre Spotify.") is None
	True
	"""
	words = request.strip(" .,;:!?").replace(CURLY_APOSTROPHE, "'")
	matches = ((name, phrase.fullmatch(words)) for name, phrase in phrases.items())
	return next(((name, match) for name, match in matches if match), None)

