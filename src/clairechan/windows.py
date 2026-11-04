""" Her avatar, pill and tray icon, built again from the code of `clairechan.overlay` and of this module once a reload changes it. """
# Imports
import ctypes
import logging
from ctypes import windll
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

from clairechan.config import Config, save_setting
from clairechan.overlay import avatar as avatar_module, tray as tray_module
from clairechan.services.desktop import full_screen
from clairechan.session import Session
from clairechan.voice.listener import Listener
from clairechan.voice.speech import Voice

if TYPE_CHECKING:
	from clairechan.app import Assistant

# Constants
LOG: logging.Logger = logging.getLogger("clairechan")
OVERLAY: str = "clairechan.overlay"
""" The package whose reloaded modules, or images, make the windows be built again. """
GWL_EXSTYLE: int = -20
WS_EX_TRANSPARENT: int = 0x20
""" Extended style that lets the clicks on a window go to the one under it. """
FULL_SCREEN_CHECK_MS: int = 500


# Classes
class Windows(QObject):
	quit_requested = Signal()
	""" Quit was picked in the tray. """

	def __init__(self, config: Config) -> None:
		super().__init__()
		self.build(config)

	def connect_to(self, assistant: Assistant, session: Session, listener: Listener, voice: Voice) -> None:
		""" Wires the windows to what they act on, which they keep to wire the windows built after a reload. """
		self.assistant, self.session, self.listener, self.voice = assistant, session, listener, voice
		self.wire()

	def on_reloaded(self, modules: list[str]) -> None:
		""" Replaces the windows by new ones, wired again, when their classes or this module were reloaded, while she has left. """
		if not any(name.startswith((OVERLAY, __name__)) for name in modules):
			return
		for window in (self.avatar, self.pill, self.tray):
			LOG.info("Replacing %s", type(window).__name__)
			window.hide()
			window.deleteLater()
		self.build(self.listener.config)
		self.assistant.avatar, self.assistant.pill = self.avatar, self.pill
		self.wire()
		LOG.info("Her windows are replaced")

	def build(self, config: Config) -> None:
		self.avatar = avatar_module.Avatar(config.avatar_zoom, config.text_zoom)
		self.avatar.bubble.typing_speed = config.typing_speed
		self.pill = avatar_module.Pill(config.avatar_zoom)
		self.tray = tray_module.Tray(config.volume, config.fps)
		self.tray.show()
		self.full_screen_check = QTimer(self.avatar)
		self.full_screen_check.setInterval(FULL_SCREEN_CHECK_MS)
		self.full_screen_check.timeout.connect(self.pass_clicks_through_in_full_screen)
		self.full_screen_check.start()

	def save_settings(self) -> None:
		save_setting("volume", f"{self.listener.config.volume:.2f}")
		save_setting("fps", f'"{self.listener.config.fps}"')

	def pass_clicks_through_in_full_screen(self) -> None:
		""" Lets the clicks reach a full screen game under her, which her translucent windows would catch. """
		for window in (self.avatar, self.pill):
			set_clicks_through(window, full_screen())

	def wire(self) -> None:
		self.tray.quit_requested.connect(self.quit_requested)
		self.tray.action_requested.connect(self.assistant.announce)
		self.tray.open_session.connect(self.session.open)
		self.tray.volume_changed.connect(partial(set_volume, self.voice, self.listener))
		self.tray.fps_changed.connect(partial(set_fps, self.listener, self.avatar, self.pill))
		self.tray.menu.closed.connect(self.save_settings)
		self.avatar.set_fps(self.listener.config.fps)
		self.pill.set_fps(self.listener.config.fps)
		self.avatar.clicked.connect(self.session.open)
		self.pill.clicked.connect(self.session.open)
		self.pill.menu_requested.connect(lambda: self.tray.menu.toggle_by(self.pill.geometry()))
		self.avatar.read.connect(self.assistant.on_read)
		self.avatar.closed.connect(self.listener.cancel)
		self.avatar.closed.connect(self.assistant.leave)
		self.avatar.hidden.connect(self.assistant.leave)
		self.avatar.closed.connect(self.voice.hush)
		self.avatar.hidden.connect(self.voice.hush)
		self.voice.started.connect(self.avatar.speak)


# Functions
def set_clicks_through(window: QWidget, through: bool) -> None:
	hwnd = int(window.winId())
	style: int = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
	wanted = style | WS_EX_TRANSPARENT if through else style & ~WS_EX_TRANSPARENT
	if wanted != style:
		windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ctypes.c_long(wanted))


def set_fps(listener: Listener, avatar: avatar_module.Avatar, pill: avatar_module.Pill, fps: str) -> None:
	""" Applies a frame rate picked in the tray to her windows and to the listener's config, so that saving it announces nothing. """
	listener.config = replace(listener.config, fps=fps)
	avatar.set_fps(fps)
	pill.set_fps(fps)


def set_volume(voice: Voice, listener: Listener, volume: float) -> None:
	""" Applies a volume picked in the tray to her voice, and to the config the listener holds so that saving it announces nothing. """
	voice.volume = volume
	listener.config = replace(listener.config, volume=volume)

