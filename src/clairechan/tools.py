""" The actions as the tools of the MCP server: what the session reads to call one, and what a call answers it. """
# Imports
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QImageWriter
from stouputils.typing import JsonDict

from clairechan.actions import ACTIONS, Action, Parameter
from clairechan.report import Answer, Picture

# Constants
LONGEST_SIDE: int = 1568
""" Pixels of the longest side of a picture shown to the session, beyond which a model reads no more detail. """


# Functions
def listed(*, child: bool) -> list[JsonDict]:
	""" The tools of the session, or those of the child sessions it starts. """
	return [tool(action) for action in ACTIONS if not action.spoken_only and (action.child or not child)]


def tool(action: Action) -> JsonDict:
	properties = {
		name: {"type": parameter.kind, "description": parameter.description} | choices(parameter)
		for name, parameter in action.parameters.items()
	}
	required = [name for name, parameter in action.parameters.items() if parameter.required]
	schema = {"type": "object", "properties": properties, "required": required}
	return {"name": action.name, "description": action.description, "inputSchema": schema}


def choices(parameter: Parameter) -> JsonDict:
	return {"enum": parameter.choices} if parameter.choices else {}


def content(answer: Answer) -> list[JsonDict]:
	""" What a tool call answers: the text of the action's answer, then its picture when it made one. """
	text: JsonDict = {"type": "text", "text": str(answer)}
	return [text, *picture(answer.path)] if isinstance(answer, Picture) else [text]


def picture(path: Path) -> list[JsonDict]:
	""" The picture as an MCP image, scaled down to `LONGEST_SIDE`, or nothing when the file cannot be read. """
	image = QImage(str(path))
	if image.isNull():
		return []
	if max(image.width(), image.height()) > LONGEST_SIDE:
		smooth = Qt.TransformationMode.SmoothTransformation
		image = image.scaled(LONGEST_SIDE, LONGEST_SIDE, Qt.AspectRatioMode.KeepAspectRatio, smooth)

	data = QByteArray()
	buffer = QBuffer(data)
	buffer.open(QIODevice.OpenModeFlag.WriteOnly)
	writer = QImageWriter(buffer, QByteArray(b"jpeg"))
	writer.setQuality(85)
	writer.write(image)
	return [{"type": "image", "data": bytes(data.toBase64().data()).decode(), "mimeType": "image/jpeg"}]

