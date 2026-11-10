""" What an action tells when a bar and colors say it better than a sentence. """
# Imports
from dataclasses import dataclass
from pathlib import Path

from clairechan.i18n import tr


# Classes
@dataclass(frozen=True)
class Slice:
	""" One part of a whole, such as what fills the context. """
	key: str
	""" Names the part for its color. """
	label: str
	amount: str
	share: str
	""" As written for the user, such as "29,1 %". """
	fraction: float
	""" Of the whole, from 0 to 1, for the width of its slice of the bar. """


@dataclass(frozen=True)
class Report:
	""" A title and the parts of a whole, which the bubble draws as a bar and a colored table and anything else reads as text. """
	title: str
	slices: tuple[Slice, ...]
	stacked: bool = True
	""" Whether the slices share one bar, or each is a fraction of its own bar. """

	def __str__(self) -> str:
		rows = (f"{part.label}{tr(': ', ' : ')}{part.amount} ({part.share})" for part in self.slices)
		return "\n".join([self.title, *rows])


@dataclass(frozen=True)
class Picture:
	""" A picture file an action made, which the session is shown along with what she says about it. """
	said: str
	path: Path

	def __str__(self) -> str:
		return self.said


# Constants
type Answer = str | Report | Picture
""" What an action answers: a sentence, or what shows better as a bar or a picture, each reading as text with `str`. """

