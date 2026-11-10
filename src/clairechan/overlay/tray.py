""" The tray icon: its menu, and starting the app with Windows. """
# Imports
import os
import sys
import winreg
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Signal
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from clairechan.config import APP_DATA, FPS_CHOICES, LOG_FILE, USER_CONFIG, ZOOM_CHOICES
from clairechan.overlay.avatar import face
from clairechan.overlay.menu import Entry, Menu, Slider, Switch

# Constants
SIZES: tuple[str, ...] = tuple(f"{choice:.0%}" for choice in ZOOM_CHOICES)
""" The texts of the size slider. """
RUN_KEY: str = r"Software\Microsoft\Windows\CurrentVersion\Run"
""" Registry key, under HKEY_CURRENT_USER, of the programs Windows starts at logon. """
LAUNCHER: Path = Path(sys.prefix) / "Scripts" / "clairechan.exe"
""" Entry point that `uv sync` installs in the project environment, which starts the app in the background. """


# Classes
class Tray(QSystemTrayIcon):
	open_session = Signal()
	action_requested = Signal(str)
	""" The name of an action picked in the menu. """
	quit_requested = Signal()
	volume_changed = Signal(float)
	""" The volume of her voice the slider was moved to, from 0 to 1. """

	fps_changed = Signal(str)
	""" The frame rate, one of `FPS_CHOICES`, the slider was moved to. """

	zoom_changed = Signal(float)
	""" The size of her avatar, one of `ZOOM_CHOICES`, the slider was moved to. """

	def __init__(self, volume: float, fps: str, zoom: float) -> None:
		super().__init__(QIcon(face(64)))
		self.setToolTip("Claire")
		self.menu = Menu([
			[
				Entry("Open the session", "\ue8a7", self.open_session.emit),
				Entry("Session context", "\ue9d2", lambda: self.action_requested.emit("context")),
				Entry("Plan usage", "\uec4a", lambda: self.action_requested.emit("plan_usage")),
			],
			[
				Slider("Volume", "\ue767", volume, self.volume_changed.emit),
				Slider("Frame rate", "\ue916", FPS_CHOICES.index(fps) / (len(FPS_CHOICES) - 1), self.pick_fps, FPS_CHOICES),
				Slider("Size", "\ue799", nearest(zoom) / (len(ZOOM_CHOICES) - 1), self.pick_zoom, SIZES),
			],
			[
				Entry("Open the config", "\ue713", lambda: os.startfile(USER_CONFIG)),
				Entry("View the log", "\ue8a5", lambda: os.startfile(LOG_FILE)),
				Entry("Open the folder", "\ue838", lambda: os.startfile(APP_DATA)),
				Switch("Start with Windows", "\ue770", starts_with_windows(), start_with_windows),
			],
			[Entry("Quit", "\ue7e8", self.quit_requested.emit)],
		])
		self.activated.connect(self.on_activated)

	def pick_fps(self, value: float) -> None:
		self.fps_changed.emit(FPS_CHOICES[round(value * (len(FPS_CHOICES) - 1))])

	def pick_zoom(self, value: float) -> None:
		self.zoom_changed.emit(ZOOM_CHOICES[round(value * (len(ZOOM_CHOICES) - 1))])

	def on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
		""" Opens the menu by the icon on a left or a right click, or by the cursor where the system tells no place for the icon. """
		if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.Context):
			icon = self.geometry()
			self.menu.toggle_by(icon if icon.isValid() else QRect(QCursor.pos(), QSize(1, 1)))


# Functions
def nearest(zoom: float) -> int:
	""" Index in `ZOOM_CHOICES` of the size closest to `zoom`, which the config may hold between two of them. """
	return min(range(len(ZOOM_CHOICES)), key=lambda index: abs(ZOOM_CHOICES[index] - zoom))


def starts_with_windows() -> bool:
	with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
		try:
			winreg.QueryValueEx(key, "ClaireChan")
		except FileNotFoundError:
			return False
		return True


def start_with_windows(enabled: bool) -> None:
	with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, access=winreg.KEY_SET_VALUE) as key:
		if enabled:
			winreg.SetValueEx(key, "ClaireChan", 0, winreg.REG_SZ, f'"{LAUNCHER}"')
		else:
			winreg.DeleteValue(key, "ClaireChan")

