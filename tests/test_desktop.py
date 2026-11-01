""" The windows of other applications, read and filled through UI Automation, on a Notepad opened behind the user's window. """
# Imports
import os
import re
import subprocess
import time
from pathlib import Path

import pytest
import uiautomation as auto

from clairechan import config
from clairechan.services import desktop

# Constants
SW_SHOWNOACTIVATE: int = 4


# Functions
@pytest.mark.skipif(not os.environ.get("CLAIRECHAN_UI_TESTS"), reason="Opens a Notepad that takes the focus from the user's window")
def test_she_asks_before_her_first_action_in_an_app_and_only_reads_one_left_to_reading(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
	user_config = tmp_path / "config.toml"
	user_config.write_text('apps = { "Notepad.exe" = "act" }\n', encoding="utf-8")
	monkeypatch.setattr(config, "USER_CONFIG", user_config)
	startup = subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=SW_SHOWNOACTIVATE)
	notepad = subprocess.Popen(["notepad.exe"], startupinfo=startup)
	try:
		time.sleep(1.5)
		window = str(next(w.NativeWindowHandle for w in auto.GetRootControl().GetChildren() if w.ProcessId == notepad.pid))
		assert f"{window}: " in desktop.list_windows()

		field = edit_number(desktop.read_window(window))
		assert desktop.permission("mcp__clairechan__fill", {"element": field})
		desktop.fill(field, "Bonjour")
		assert desktop.permission("mcp__clairechan__fill", {"element": field}) is None
		assert '= "Bonjour"' in (listing := desktop.read_window(window))

		user_config.write_text('apps = { "notepad.exe" = "read" }\n', encoding="utf-8")
		assert desktop.fill(edit_number(listing), "Au revoir") == "The user lets me only read notepad.exe."
	finally:
		notepad.kill()


def edit_number(listing: str) -> str:
	""" The number `read_window` gave Notepad's text field. """
	match = re.search(r"^\[(\d+)\] Edit ", listing, re.MULTILINE)
	assert match
	return match[1]



def test_she_asks_again_after_ten_minutes_and_every_time_for_a_sensitive_element(monkeypatch: pytest.MonkeyPatch) -> None:
	now = 1000.0
	monkeypatch.setattr(time, "monotonic", lambda: now)
	monkeypatch.setattr(desktop, "APPROVED", {"firefox.exe": now + desktop.APPROVAL_S})
	harmless = desktop.Element(auto.Control(), "firefox.exe", "Edit Search")
	sensitive = desktop.Element(auto.Control(), "firefox.exe", "Button Envoyer")
	monkeypatch.setattr(desktop, "ELEMENTS", {"1": harmless, "2": sensitive})

	assert desktop.permission("mcp__clairechan__press", {"element": "1"}) is None
	assert desktop.permission("mcp__clairechan__press", {"element": "2"})
	now += desktop.APPROVAL_S + 1
	assert desktop.permission("mcp__clairechan__press", {"element": "1"})


def test_her_spoken_permission_lets_her_act_where_the_config_only_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	user_config = tmp_path / "config.toml"
	user_config.write_text('apps = { "firefox.exe" = "read" }' + chr(10), encoding="utf-8")
	monkeypatch.setattr(config, "USER_CONFIG", user_config)
	monkeypatch.setattr(desktop, "GRANTED", {})
	assert desktop.level("firefox.exe") == "read"
	desktop.allow_acting("Firefox")
	assert desktop.level("firefox.exe") == "act"

