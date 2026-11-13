""" The listening bench: real requests and noise recorded once, replayed through Whisper alone and through the wake phrase spotter.

Record with `uv run python -m clairechan.voice.bench record request` (about thirty times) and `record noise` (an hour),
then `uv run python -m clairechan.voice.bench replay` prints recall, false alarms and wake delay of each.
"""
# Imports
import argparse
import contextlib
import itertools
import math
import statistics
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from clairechan.config import APP_DATA, FOLLOW_UP_S, Config
from clairechan.voice.audio import FRAME, RATE, Audio, load_whisper, microphone, utterances
from clairechan.voice.listener import SPELLING, transcribe
from clairechan.voice.wake import spot_wake

# Constants
BENCH: Path = APP_DATA / "bench"
""" Holds `request-01.wav`... (each says "Hey Claire, ..." once) and `noise-01.wav`... (nothing said to her), 16 kHz mono. """


# Classes
@dataclass(frozen=True)
class Score:
	delays: Sequence[float]
	""" Seconds from the start of the request's voice to the wake, of each request that woke her. """
	missed: Sequence[str]
	false_alarms: int


# Functions
def recording(path: Path) -> Iterator[Audio]:
	""" The frames of a 16 kHz mono recording, followed by two seconds of silence so that its last sentence ends. """
	yield from sf.blocks(path, blocksize=FRAME, dtype="float32", fill_value=0.0)
	for _ in range(2 * RATE // FRAME):
		yield np.zeros(FRAME, np.float32)


def timed(frames: Iterator[Audio], clock: list[float]) -> Iterator[Audio]:
	""" The frames, writing into `clock[0]` the second of audio each one ends at. """
	for count, frame in enumerate(frames, start=1):
		clock[0] = count * FRAME / RATE
		yield frame


def debounced(times: Sequence[float]) -> list[float]:
	""" The wakes that count: one inside `FOLLOW_UP_S` of the previous one is the same call.

	>>> debounced([1.0, 2.5, 20.0])
	[1.0, 20.0]
	"""
	woken: list[float] = []
	for moment in times:
		if not woken or moment > woken[-1] + FOLLOW_UP_S:
			woken.append(moment)
	return woken


def whisper_pass(path: Path, config: Config) -> tuple[float, list[float]]:
	""" When the voice starts (within half a second) and when Whisper recognised the wake phrase, as the app does without its gate. """
	whisper = load_whisper()
	clock = [0.0]
	onset = math.inf
	wakes: list[float] = []
	for speech in utterances(timed(recording(path), clock), config.pause_s):
		if speech is None:
			continue
		onset = min(onset, clock[0] - len(speech.audio) / RATE)
		started = time.monotonic()
		text, _, _ = transcribe(whisper, speech.audio, config.language)
		if text.casefold() != SPELLING.casefold() and config.wake.match(text):
			wakes.append(clock[0] + time.monotonic() - started)
	return onset, wakes


def spotter_pass(path: Path) -> list[float]:
	clock = [0.0]
	wakes: list[float] = []
	deque(spot_wake(timed(recording(path), clock), lambda: wakes.append(clock[0])), maxlen=0)
	return wakes


def score(wakes: dict[Path, list[float]], onsets: dict[Path, float], false_alarms: int) -> Score:
	woken = {path: debounced(times) for path, times in wakes.items()}
	return Score(
		delays=[max(0.0, times[0] - onsets[path]) for path, times in woken.items() if times],
		missed=[path.stem for path, times in woken.items() if not times],
		false_alarms=false_alarms,
	)


def table(requests: int, noise_hours: float, scores: dict[str, Score]) -> str:
	""" The scores as a markdown table, one column per listener.

	>>> print(table(2, 0.5, {"Whisper": Score([1.5, 2.5], [], 1)}))
	| | Whisper |
	|---|---|
	| Recall | 2/2 (100 %) |
	| False alarms | 1 in 0.5 h (2.0 per hour) |
	| Delay, median / worst | 2.00 s / 2.50 s |
	"""
	def delay(found: Score) -> str:
		return f"{statistics.median(found.delays):.2f} s / {max(found.delays):.2f} s" if found.delays else "none woke"

	columns = list(scores.values())
	rows = [
		("Recall", [f"{len(found.delays)}/{requests} ({100 * len(found.delays) / requests:.0f} %)" for found in columns]),
		("False alarms", [f"{found.false_alarms} in {noise_hours:.1f} h ({found.false_alarms / noise_hours:.1f} per hour)"
			for found in columns]),
		("Delay, median / worst", [delay(found) for found in columns]),
	]
	lines = ["| | " + " | ".join(scores) + " |", "|---" * (len(scores) + 1) + "|"]
	lines += [f"| {label} | " + " | ".join(cells) + " |" for label, cells in rows]
	return "\n".join(lines)


def replay(directory: Path) -> str:
	requests = sorted(directory.glob("request-*.wav"))
	noise = sorted(directory.glob("noise-*.wav"))
	if not requests or not noise:
		raise SystemExit(f"Nothing to replay in {directory}: record with `record request` and `record noise` first.")

	config = Config.load()
	noise_hours = sum(sf.info(path).duration for path in noise) / 3600
	heard = {path: whisper_pass(path, config) for path in requests}
	onsets = {path: onset for path, (onset, _) in heard.items()}
	whisper_noise = sum(len(debounced(whisper_pass(path, config)[1])) for path in noise)
	spotter_noise = sum(len(debounced(spotter_pass(path))) for path in noise)
	scores = {
		"Whisper alone": score({path: wakes for path, (_, wakes) in heard.items()}, onsets, whisper_noise),
		"Wake spotter": score({path: spotter_pass(path) for path in requests}, onsets, spotter_noise),
	}
	missed = "\n".join(f"{name} missed: {', '.join(found.missed)}" for name, found in scores.items() if found.missed)
	return "\n".join([table(len(requests), noise_hours, scores), missed]).strip()


def record(path: Path, stop: Callable[[], bool]) -> None:
	with sf.SoundFile(path, "w", RATE, 1) as file:
		for frame in microphone():
			file.write(frame)
			if stop():
				return


def wait_for_enter(pressed: threading.Event) -> None:
	input()
	pressed.set()


def record_requests(count: int) -> None:
	""" Asks for each request in turn, keeping the ones already recorded so an interrupted session resumes. """
	for number in range(1, count + 1):
		path = BENCH / f"request-{number:02d}.wav"
		if path.exists():
			continue
		input(f"Request {number}/{count}: press Enter, say \"Hey Claire, ...\" as you would, press Enter again. ")
		stopped = threading.Event()
		threading.Thread(target=wait_for_enter, args=(stopped,), daemon=True).start()
		try:
			record(path, stopped.is_set)
		except KeyboardInterrupt:
			path.unlink()
			raise


def record_noise(minutes: float) -> None:
	""" Records the room, with the usual video, music and talk not meant for her, until the time is up or Ctrl+C. """
	path = next(path for number in itertools.count(1) if not (path := BENCH / f"noise-{number:02d}.wav").exists())
	deadline = time.monotonic() + minutes * 60
	print(f"Recording {path.name} for {minutes:g} min, Ctrl+C to stop early.", flush=True)
	with contextlib.suppress(KeyboardInterrupt):
		record(path, lambda: time.monotonic() >= deadline)


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__)
	commands = parser.add_subparsers(dest="command", required=True)
	recording_parser = commands.add_parser("record")
	kinds = recording_parser.add_subparsers(dest="kind", required=True)
	kinds.add_parser("request").add_argument("--count", type=int, default=30)
	kinds.add_parser("noise").add_argument("--minutes", type=float, default=60.0)
	commands.add_parser("replay").add_argument("--dir", type=Path, default=BENCH)
	args = parser.parse_args()

	BENCH.mkdir(parents=True, exist_ok=True)
	if args.command == "replay":
		print(replay(args.dir))
	elif args.kind == "request":
		record_requests(args.count)
	else:
		record_noise(args.minutes)


if __name__ == "__main__":
	main()

