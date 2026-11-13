""" The hook server that relays the session's events and permission requests. """
# Imports
import json
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor

from PySide6.QtWidgets import QApplication

from clairechan.session import HookServer


# Functions
def test_a_permission_request_waits_for_the_spoken_answer_and_returns_it(app: QApplication) -> None:
	server = HookServer(lambda _tool, _tool_input: None)
	def answer(verdict: Future[bool]) -> None:
		verdict.set_result(False)
	server.asked.connect(answer)

	def post(event: str) -> bytes:
		body = json.dumps({"hook_event_name": event}).encode()
		with urllib.request.urlopen(urllib.request.Request(server.url, body)) as response:
			return response.read()

	with ThreadPoolExecutor() as pool:
		asked, other = pool.submit(post, "PermissionRequest"), pool.submit(post, "Stop")
		while not (asked.done() and other.done()):
			app.processEvents()

	assert json.loads(asked.result())["hookSpecificOutput"]["decision"]["behavior"] == "deny"
	assert other.result() == b""

