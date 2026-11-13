""" What Claude Code reports about the hidden session and the plan, laid out for the bubble. """
# Imports
import re

from clairechan.claude_code import SESSION_ID, panels
from clairechan.i18n import tr
from clairechan.report import Report, Slice

# Constants
CATEGORIES: dict[str, str] = {
	"System prompt": "Prompt", "System tools": "Outils", "MCP tools": "Outils MCP",
	"MCP server instructions": "Consignes MCP", "Memory files": "Mémoire", "Skills": "Skills", "Messages": "Messages",
	"Autocompact buffer": "Compactage", "Free space": "Libre",
}
""" The categories of `/context` in French, which English shows as `/context` names them. """


# Functions
def plan_usage() -> Report:
	""" How much of the 5-hour window and of the week the subscription has used, each on its own bar with its reset date. """
	usage = panels.plan_usage()
	if not usage:
		return Report(tr("I couldn't read your usage.", "Je n'ai pas réussi à lire ton usage."), ())
	limits = (
		("Window", tr("5-hour window", "Fenêtre de 5 h"), usage.window),
		("Week", tr("Week", "Semaine"), usage.week),
	)
	slices = tuple(
		Slice(
			key=key, label=label, amount=tr("resets ", "renouvelée ") + without_zone(limit.resets),
			share=tr(f"{limit.percent}%", french(f"{limit.percent}%")), fraction=limit.percent / 100,
		)
		for key, label, limit in limits
	)
	return Report(tr("Claude plan", "Forfait Claude"), slices, stacked=False)


def context() -> Report:
	""" How full the context of the hidden session is, then what fills it from the largest to the smallest, the free space last. """
	if not SESSION_ID.exists():
		return Report(tr("There is no conversation yet.", "Il n'y a pas encore de conversation."), ())
	usage = panels.context(SESSION_ID.read_text())
	if not usage:
		return Report(tr("I couldn't read the context.", "Je n'ai pas réussi à lire le contexte."), ())
	slices = tuple(
		Slice(
			key=share.name, label=tr(share.name, CATEGORIES.get(share.name, share.name)),
			amount=tr(share.tokens, french(share.tokens)), share=tr(share.percent, french(share.percent)),
			fraction=float(share.percent.rstrip("%")) / 100,
		)
		for share in usage.shares
	)
	english = f"Context: {usage.tokens}\nModel: {usage.model}"
	return Report(tr(english, french(f"Contexte : {usage.tokens}\nModèle : {usage.model}")), slices)


def french(text: str) -> str:
	""" The decimal commas and the unbreakable space before the percent sign of French.

	>>> french("29.1%") == "29,1" + chr(0xA0) + "%"
	True
	"""
	return re.sub(r"(\d)%", r"\1" + chr(0xA0) + "%", text.replace(".", ","))


def without_zone(date: str) -> str:
	""" A reset date without its time zone.

	>>> without_zone("Oct 19, 12am (Europe/Paris)")
	'Oct 19, 12am'
	"""
	return re.sub(r" \([^)]*\)$", "", date)

