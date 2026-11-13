
# ClaireChan

A voice assistant with an anime overlay (PySide6), driving a hidden Claude Code session. `README.md` says how to run it, `PLAN.md` what is done and planned.

## Layout

- `src/clairechan/app.py`: the core process, which lasts as long as the app: the session, the hook and MCP servers, her ears and her voice. It starts her face and relays what each side tells the other.
- `src/clairechan/face.py`: the face process: her windows (`windows.py`), `Assistant` (`assistant.py`, which turns hook events and heard requests into what Claire shows) and the actions.
- `src/clairechan/link.py`: `PEER`, the other process, one JSON message per line over a local socket.
- `src/clairechan/changes.py`: what the session changed since the code was loaded, and whether it reaches the core.
- `src/clairechan/session.py`: the hidden `claude` process in a pseudo-terminal, working in `%APPDATA%\ClaireChan\home` (`claude_code.HOME`), and the hook server.
- `src/clairechan/launcher.py`: runs the app, starts it again after a change to the core, and puts the change aside in git when the app then fails to start. It imports nothing of the app.
- `src/clairechan/actions.py`: `ACTIONS`, what she does on the computer. `mcp.py` offers the same list to the session as tools.
- `src/clairechan/services/`: what the actions call (weather, programs, timers, other applications' windows in `desktop.py`, the dream of the shared memory in `dream.py`). Put the code of a new action there when it is more than a few lines.
- `src/clairechan/voice/`: microphone, Whisper, wake and end phrases, meeting transcription, and her Japanese voice (`speech.py`). `overlay/`: avatar, bubble, tray.
- `tools/sprites/`: a separate uv project that draws `assets/claude/`. Leave it alone unless asked about sprites.
- `tools/minecraft/`: a Fabric mod (Gradle, Java) for the test client the `minecraft_*` actions drive over HTTP (`services/minecraft.py`). `gradlew.bat runClient` starts it, its game folder is `run/`; `runClient2` starts a second player, ClaireChan2, whose bridge listens on 47622, for tests that need two.

## Adding an action

1. Add one `Action(...)` to `ACTIONS` in `actions.py`, with `name`, `description` (what the session reads to choose the tool), `phrases` (a regex matched against the whole request, its named groups being the arguments), `run` (returns what she says, as `tr(english, french)` from `i18n.py`, or a `Report` or a `Picture` from `report.py`, the picture reaching the session as an image), `parameters` when it takes arguments, and `child=True` to offer it to child sessions too.
2. The same entry is then a voice phrase and the MCP tool `mcp__clairechan__<name>`. Never list an action anywhere else.
3. Add a `>>>` example to `route` or a test in `tests/` for the behaviour that could break. Mock only I/O (network, key presses), as `tests/test_services.py` does.
4. Add a row to the table in `README.md`.

Actions run on the Qt thread: keep them quick, and start a thread for anything long, as `meeting.py` does, or set `threaded=True` on a tool that answers after seconds. An effect on the session itself (typing `/model`, restarting it) goes in `Assistant.run_action`, not in the action.

Once the session has nothing running, a change applies by itself. A change to a module only the face loads (actions, services, overlay, sprites) starts the face again alone in 1.5 s and the session goes on. A change to a module the core loads restarts the whole app on the same conversation, cutting the session's work: keep what the face can do in the face. The face keeps nothing in memory across a restart, so state that must survive one goes in a file of `APP_DATA`, as `ALARMS` and `CHILDREN` do. A new action reaches the hidden session as a tool without a restart, the MCP server telling it the list changed (`notifications/tools/list_changed`).

## Checks

All must pass before you report: `uv run ruff check`, `uv run pyright`, `uv run pytest --doctest-modules src tests`, `uv run stouputils check`, `uvx complexipy src --failed --max-complexity-allowed 15`.

Code style: tabs, pyright strict, a `.py` file ends with two newlines, no comments that restate the code. Never write long dashes, arrows, curly quotes or an ellipsis character.

Do not commit or push: suggest a short conventional commit message with a gitmoji, and the user commits.

