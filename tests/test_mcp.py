""" The actions offered to the sessions as MCP tools, their calls crossing the link between the app's two processes. """
# Imports
import json
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication
from stouputils.typing import JsonDict

from clairechan import tools
from clairechan.actions import ACTIONS, find
from clairechan.link import Link
from clairechan.mcp import ActionServer
from clairechan.report import Picture


# Functions
@pytest.fixture
def links(app: QApplication) -> tuple[Link, Link]:
	""" The two ends of a line: the core's, which a face connects to, and that face's. """
	server = QLocalServer(app)
	server.listen(f"ClaireChan-test-{id(server)}")
	face_socket = QLocalSocket(app)
	face_socket.connectToServer(server.serverName())
	face_socket.waitForConnected()
	server.waitForNewConnection(1000)
	core, face = Link(), Link()
	core.attach(server.nextPendingConnection())
	face.attach(face_socket)
	return core, face


def post(url: str, method: str, params: JsonDict) -> JsonDict:
	body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
	with urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"})) as response:
		return json.load(response)


def wait_for[T](app: QApplication, pending: Future[T]) -> T:
	while not pending.done():
		app.processEvents()
	return pending.result()


def test_a_tool_call_crosses_the_link_and_each_role_reaches_only_its_tools(app: QApplication, links: tuple[Link, Link]) -> None:
	core, face = links
	def run(kind: str, call: JsonDict) -> None:
		face.reply(call["ask"], content=[{"type": "text", "text": f"{kind} {call['name']} {call['arguments']}"}], isError=False)
	face.received.connect(run)
	server = ActionServer(core)
	server.offer({"main": tools.listed(child=False), "child": tools.listed(child=True)})

	with ThreadPoolExecutor() as pool:
		listed = wait_for(app, pool.submit(post, server.urls["child"], "tools/list", {}))
		called = wait_for(app, pool.submit(post, server.urls["main"], "tools/call", {"name": "timer", "arguments": {"amount": 2}}))
		refused = wait_for(app, pool.submit(post, server.urls["child"], "tools/call", {"name": "timer", "arguments": {}}))

	assert [tool["name"] for tool in listed["result"]["tools"]] == [action.name for action in ACTIONS if action.child]
	assert called["result"]["content"] == [{"type": "text", "text": "tool timer {'amount': 2}"}]
	assert refused["error"]["message"] == "Unknown tool timer"
	with pytest.raises(urllib.error.HTTPError):
		post(server.urls["main"] + "x", "tools/list", {})


def test_a_tool_tells_the_types_of_its_arguments_and_shows_the_picture_it_made(tmp_path: Path) -> None:
	schema = tools.tool(find("timer"))["inputSchema"]
	assert schema["required"] == ["amount"]
	unit = {"type": "string", "description": "minutes by default.", "enum": ("seconds", "minutes", "hours")}
	assert schema["properties"]["unit"] == unit

	image = QImage(4000, 1000, QImage.Format.Format_RGB32)
	image.fill(0)
	image.save(str(tmp_path / "screen.png"))
	text, shown = tools.content(Picture(said="Captured.", path=tmp_path / "screen.png"))
	assert text == {"type": "text", "text": "Captured."}
	assert shown["mimeType"] == "image/jpeg"
	assert tools.content(Picture(said="Captured.", path=tmp_path / "missing.png")) == [text]

