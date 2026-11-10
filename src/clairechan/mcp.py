""" The MCP server of the hidden session and of its child sessions, relaying their tool calls to the process holding the actions. """
# Imports
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, override

from stouputils.typing import JsonDict

from clairechan.link import Link
from clairechan.session import is_local_request

# Constants
CALL_TIMEOUT_S: float = 90.0
""" How long a tool call waits for its answer, longer than the slowest action takes. """
TOOLS_WAIT_S: float = 30.0
""" How long a session listing its tools waits for the process that holds the actions to have given them. """


# Classes
class ActionServer:
	""" Serves each role its tools at an address no other program knows, and relays its calls over the link. """

	def __init__(self, link: Link) -> None:
		self.link = link
		self.tools: dict[str, list[JsonDict]] = {}
		""" The tools of each role: "main" for the hidden session, "child" for the sessions it starts. """
		self.offered = threading.Event()
		roles = {secrets.token_urlsafe(16): "main", secrets.token_urlsafe(16): "child"}
		answer = self.answer

		class Handler(BaseHTTPRequestHandler):
			def do_POST(self) -> None:
				role = roles.get(self.path.strip("/"))
				if not role or not is_local_request(self.headers):
					self.send_error(403)
					return
				response = answer(json.loads(self.rfile.read(int(self.headers["Content-Length"]))), role)
				body = b"" if response is None else json.dumps(response).encode()
				self.send_response(202 if response is None else 200)
				self.send_header("Content-Type", "application/json")
				self.send_header("Content-Length", str(len(body)))
				self.end_headers()
				self.wfile.write(body)

			def do_GET(self) -> None:
				self.send_error(405)

			@override
			def log_message(self, format: str, *args: Any) -> None:
				pass

		server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		self.urls = {role: f"http://127.0.0.1:{server.server_port}/{token}" for token, role in roles.items()}
		""" The address of each role. """
		threading.Thread(target=server.serve_forever, daemon=True).start()

	def offer(self, tools: dict[str, list[JsonDict]]) -> bool:
		""" Takes the tools of each role, and says whether they replace others, which a running session has already read. """
		replaced = self.offered.is_set() and tools != self.tools
		self.tools = tools
		self.offered.set()
		return replaced

	def answer(self, request: JsonDict, role: str) -> JsonDict | None:
		""" The JSON-RPC response to a request, None for a notification. """
		if "id" not in request:
			return None

		result: JsonDict
		match request["method"]:
			case "initialize":
				result = {
					"protocolVersion": request["params"]["protocolVersion"],
					"capabilities": {"tools": {}},
					"serverInfo": {"name": "clairechan", "version": "1"},
				}
			case "tools/list":
				self.offered.wait(TOOLS_WAIT_S)
				result = {"tools": self.tools.get(role, [])}
			case "tools/call" if any(tool["name"] == request["params"]["name"] for tool in self.tools.get(role, [])):
				result = self.call(request["params"])
			case "tools/call":
				return error(request, -32602, f"Unknown tool {request['params']['name']}")
			case "ping":
				result = {}
			case method:
				return error(request, -32601, f"Unknown method {method}")
		return {"jsonrpc": "2.0", "id": request["id"], "result": result}

	def call(self, params: JsonDict) -> JsonDict:
		""" What the action answers, as the process that holds it writes it: its `content`, and `isError`. """
		try:
			return self.link.ask("tool", name=params["name"], arguments=params.get("arguments", {})).result(CALL_TIMEOUT_S)
		except TimeoutError:
			return {"content": [{"type": "text", "text": f"{params['name']} did not answer"}], "isError": True}


# Functions
def error(request: JsonDict, code: int, message: str) -> JsonDict:
	return {"jsonrpc": "2.0", "id": request["id"], "error": {"code": code, "message": message}}

