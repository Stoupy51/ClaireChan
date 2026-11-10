""" Her avatar, pill and tray icon, wired to what they act on. """
# Imports
import ctypes
from ctypes import windll
from dataclasses import replace

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from clairechan import actions
from clairechan.assistant import Assistant
from clairechan.config import Config, save_setting
from clairechan.link import PEER
from clairechan.overlay import avatar as avatar_module, tray as tray_module
from clairechan.services.desktop import full_screen

# Constants
GWL_EXSTYLE: int = -20
WS_EX_TRANSPARENT: int = 0x20
""" Extended style that lets the clicks on a window go to the one under it. """
FULL_SCREEN_CHECK_MS: int = 500


# Classes
class Windows:
	def __init__(self, config: Config) -> None:
		self.avatar = avatar_module.Avatar(config.avatar_zoom, config.text_zoom)
		self.pill = avatar_module.Pill(config.avatar_zoom)
		self.tray = tray_module.Tray(config.volume, config.fps, config.avatar_zoom)
		self.tray.show()
		self.full_screen_check = QTimer(self.avatar)
		self.full_screen_check.setInterval(FULL_SCREEN_CHECK_MS)
		self.full_screen_check.timeout.connect(self.pass_clicks_through_in_full_screen)
		self.full_screen_check.start()

	def wire(self, assistant: Assistant) -> None:
		""" Connects the windows to her reactions and, through the link, to the session, her ears and her voice. """
		self.assistant = assistant
		self.tray.quit_requested.connect(self.quit)
		self.tray.action_requested.connect(self.announce)
		self.tray.open_session.connect(lambda: PEER.send("open_session"))
		self.tray.volume_changed.connect(self.set_volume)
		self.tray.fps_changed.connect(self.set_fps)
		self.tray.zoom_changed.connect(self.set_zoom)
		self.tray.menu.closed.connect(self.save_settings)
		self.avatar.set_fps(assistant.config.fps)
		self.pill.set_fps(assistant.config.fps)
		self.avatar.clicked.connect(lambda: PEER.send("open_session"))
		self.pill.clicked.connect(lambda: PEER.send("open_session"))
		self.pill.menu_requested.connect(lambda: self.tray.menu.toggle_by(self.pill.geometry()))
		self.avatar.read.connect(assistant.on_read)
		self.avatar.closed.connect(lambda: PEER.send("cancel"))
		for dismissed in (self.avatar.closed, self.avatar.hidden):
			dismissed.connect(assistant.leave)
			dismissed.connect(lambda: PEER.send("hush"))

	def announce(self, action: str) -> None:
		self.assistant.announce(actions.find(action), {})

	def quit(self) -> None:
		self.tray.hide()
		PEER.send("quit")

	def set_volume(self, volume: float) -> None:
		""" Applies a volume picked in the tray to her voice, and to the config she holds so that saving it announces nothing. """
		PEER.send("volume", value=volume)
		self.assistant.config = replace(self.assistant.config, volume=volume)

	def set_fps(self, fps: str) -> None:
		self.assistant.config = replace(self.assistant.config, fps=fps)
		self.avatar.set_fps(fps)
		self.pill.set_fps(fps)

	def set_zoom(self, zoom: float) -> None:
		self.assistant.config = replace(self.assistant.config, avatar_zoom=zoom)
		self.avatar.set_zoom(zoom, self.assistant.config.text_zoom)
		self.pill.set_zoom(zoom)

	def save_settings(self) -> None:
		save_setting("volume", f"{self.assistant.config.volume:.2f}")
		save_setting("fps", f'"{self.assistant.config.fps}"')
		save_setting("avatar_zoom", f"{self.assistant.config.avatar_zoom}")

	def pass_clicks_through_in_full_screen(self) -> None:
		""" Lets the clicks reach a full screen game under her, which her translucent windows would catch. """
		for window in (self.avatar, self.pill):
			set_clicks_through(window, full_screen())


# Functions
def set_clicks_through(window: QWidget, through: bool) -> None:
	hwnd = int(window.winId())
	style: int = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
	wanted = style | WS_EX_TRANSPARENT if through else style & ~WS_EX_TRANSPARENT
	if wanted != style:
		windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ctypes.c_long(wanted))

