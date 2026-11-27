""" The test Minecraft clients of tools/minecraft, game instances of their own, each driven through the HTTP bridge its mod opens. """
# Imports
import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

from stouputils.typing import JsonDict

from clairechan.config import APP_DATA, ROOT
from clairechan.i18n import tr
from clairechan.report import Answer, Picture
from clairechan.services import hidden_desktop

# Constants
CLIENTS: int = 3
""" How many test clients may run at once, as many as the client runs of build.gradle. """
BRIDGE_PORT: int = 47620
""" Client n's bridge listens on BRIDGE_PORT + n, the `clairechan.bridge.port` its run of build.gradle sets. """
CLIENT: Path = ROOT / "tools" / "minecraft"
""" The Gradle project of the bridge mod, whose runClient tasks start the test clients. """
SETUP: tuple[str, ...] = ("options.txt", "servers.dat", "config", "mods", "resourcepacks", "shaderpacks")
""" What a new client's folder copies from client 1's, so its packs and settings follow. """
LEASES: Path = APP_DATA / "minecraft"
""" One file per client being started, so that two sessions starting at once get different clients. """
LOADING_S: int = 180
""" How long a lease holds a client that does not answer yet: past it, its start is taken as failed. """


# Functions
def start() -> str:
	""" Starts the first test client neither running nor starting, on a hidden desktop at idle priority. """
	client = next((n for n in range(1, CLIENTS + 1) if not taken(n)), None)
	if client is None:
		return tr(f"All {CLIENTS} test clients are in use.", f"Les {CLIENTS} clients de test sont pris.")

	LEASES.mkdir(parents=True, exist_ok=True)
	(LEASES / f"client{client}").touch()
	folder = CLIENT / ("run" if client == 1 else f"run{client}")
	if not folder.exists():
		for name in SETUP:
			source = CLIENT / "run" / name
			if source.is_dir():
				shutil.copytree(source, folder / name)
			elif source.exists():
				folder.mkdir(parents=True, exist_ok=True)
				shutil.copy2(source, folder / name)
	task = "runClient" if client == 1 else f"runClient{client}"
	# A daemon started from the user's desktop would open the game there, outside the idle job.
	hidden_desktop.run(f'"{CLIENT}\\gradlew.bat" {task} --no-daemon --console=plain', str(CLIENT))
	return tr(
		f"Test client {client} is starting: pass client {client} to the other minecraft tools. "
		"Ready once its state says loading: false.",
		f"Le client de test {client} démarre : passe client {client} aux autres outils minecraft. "
		"Prêt quand son état dit loading: false.",
	)


def taken(client: int) -> bool:
	lease = LEASES / f"client{client}"
	starting = lease.exists() and time.time() - lease.stat().st_mtime < LOADING_S
	return starting or call(client, "/state").startswith("{")


def screenshot(client: int) -> Answer:
	""" What the test client shows, which the bridge saves into a picture file. """
	answer = call(client, "/screenshot")
	path = json.loads(answer).get("path") if answer.startswith("{") else None
	return Picture(said=answer, path=Path(path)) if path else answer


def call(client: int, route: str, body: JsonDict | None = None) -> str:
	""" The bridge's JSON answer to a route, or why the client cannot answer. """
	url = f"http://127.0.0.1:{BRIDGE_PORT + client}{route}"
	request = urllib.request.Request(url, data=json.dumps(body or {}).encode(), method="POST")
	try:
		with urllib.request.urlopen(request, timeout=15) as response:
			return response.read().decode()
	except (urllib.error.URLError, TimeoutError):
		return tr(
			f"Test client {client} is not running: start one with minecraft_start.",
			f"Le client de test {client} ne tourne pas : lance-en un avec minecraft_start.",
		)

