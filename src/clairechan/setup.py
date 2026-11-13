""" One-time setup, run with `uv run clairechan-setup`: prepares Whisper, the CPU's wake phrase spotter, her voice and Claude Code. """
# Imports
import json
import shutil
import subprocess

import numpy as np
import stouputils as stp

from clairechan.claude_code import HOME, trust
from clairechan.config import Config
from clairechan.console import enable_colors
from clairechan.voice.audio import GPU, RATE, load_whisper
from clairechan.voice.speech import MODEL, RUN, install_engine
from clairechan.voice.wake import load_spotter


# Functions
def main() -> None:
	enable_colors()
	device = "GPU" if GPU else "CPU, as no NVIDIA GPU was found"
	stp.progress(f"Downloading Whisper ({'1.6' if GPU else '0.5'} GB the first time) and running it once on the {device}...")
	segments, _ = load_whisper().transcribe(np.zeros(RATE, np.float32), language="en")
	list(segments)
	stp.progress("Downloading the wake phrase spotter (18 MB the first time)...")
	load_spotter()
	stp.info(f"Whisper runs on the {device}")
	if Config.load().voice and not (RUN.exists() and MODEL.exists()):
		stp.progress("Downloading AivisSpeech, her Japanese voice (0.5 GB), which voice = false in the config turns off...")
		install_engine()

	if not shutil.which("claude"):
		stp.warning(f"Install Claude Code, then run this setup again: {stp.CYAN}https://code.claude.com/docs/en/setup")
		return
	if not signed_in():
		stp.progress("Claude Code opens its sign-in page: sign in with your Claude Pro or Max account.")
		subprocess.run(["claude", "auth", "login"])
	# The decision stays with the user: Claude Code shows its own dialog, and records the answer in a file it keeps rewriting
	if not trust.is_trusted(HOME):
		stp.progress('Claude Code opens in her folder and asks if you trust it: pick "Yes, I trust this folder", then type /exit')
		HOME.mkdir(parents=True, exist_ok=True)
		subprocess.run(["claude"], cwd=HOME)

	if signed_in() and trust.is_trusted(HOME):
		stp.info(f"Claude Code is ready. Start the app with: {stp.CYAN}uv run clairechan")
	else:
		stp.warning("Claude Code is not signed in or does not trust this folder yet: run this setup again.")


def signed_in() -> bool:
	""" Whether Claude Code is signed in with a Claude subscription, which the app needs instead of an API key. """
	status = json.loads(subprocess.run(["claude", "auth", "status"], capture_output=True, text=True).stdout)
	return status.get("authMethod") == "claude.ai"

