
# 🎙️ ClaireChan

<div align="center">

*Say "Hey Claire": Claire pops up on your screen while a hidden Claude Code session, running on your Claude subscription, does the work.*

</div>

https://github.com/user-attachments/assets/362c7b06-fcf6-4984-8b7d-4766ba969d6c

> [!NOTE]
> Work in progress: the roadmap is in [PLAN.md](PLAN.md), in French.

## ✨ Features

- 🎙️ **Voice**: say *"Hey Claire, ..."* and Whisper transcribes you on your own GPU, or on the CPU after a wake phrase spotter.
- ✅ **Permissions by voice**: answer her permission requests with *"yes"* or *"no"*, without touching the keyboard.
- 🧵 **Background work**: long tasks go to an Opus agent while she waits as a small pill, and she tells you when they are done.
- 🌐 **Any language**: the session answers in the language you speak, and she says her replies aloud in Japanese, her bubble being their subtitles.
- 🖼️ **Overlay and tray menu**: drag her or her pill anywhere, open the links of her bubble, and set her voice and options from her menu.
- 🖥️ **Actions on the computer**: screenshots, meeting transcripts, timers, weather, programs, other apps' windows and ShadowPlay clips, see [Actions](#-actions).
- ⛏️ **Minecraft test client**: a Minecraft client of its own, never your game, that the session drives on a server: commands, chat, keys and screenshots.
- ♻️ **She changes her own code**: ask for a new action and she writes it, restarts her face on it in 1.5 s without losing the conversation, and puts a change that breaks her aside in git.

## 📋 Requirements

- Windows 10 or 11 and a microphone.
- Preferably an NVIDIA GPU with the CUDA 12 runtime, which the [CUDA Toolkit 12](https://developer.nvidia.com/cuda-downloads) installs, for Whisper. Without one, it runs on the CPU: see [Without an NVIDIA GPU](#without-an-nvidia-gpu).
- [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs Python 3.14 by itself.
- [Claude Code](https://code.claude.com/docs/en/setup), signed in with a Claude Pro or Max subscription.

## 🔧 Installation

```powershell
git clone https://github.com/Stoupy51/ClaireChan
cd ClaireChan
uv run clairechan-setup
```

The setup installs the dependencies, downloads Whisper (1.6 GB, or 0.5 GB without an NVIDIA GPU) and runs it once, downloads the wake phrase spotter (18 MB),
then downloads [AivisSpeech](https://aivis-project.com/), her voice (0.5 GB, unless `voice = false` in the config).
Then, only when needed, it opens Claude Code's sign-in page, and Claude Code itself in her folder, `%APPDATA%\ClaireChan\home`, so that you trust it:
pick *Yes, I trust this folder*, then type `/exit`. This dialog is Claude Code's safety check before it works in a folder, so the app never answers it for you.

Optional, once:

- Windows hides new tray icons behind the `^` arrow: drag Claire's next to the clock to keep it in sight.
- Turn on *Start with Windows* in her tray menu to start her at logon.

## ▶️ Usage

```powershell
uv run clairechan
```

The app starts in the background with a hidden Claude Code session in her folder, prints the session's link and your plan usage once ready, and keeps running until you quit it from her tray icon.
The session stays in claude.ai's list after you quit, and the app resumes it on its next start.
Say *"Hey Claire, ..."*: she shows up as soon as she hears it, shows the sentence she understood, then what the session does and its answer.
Her own lines are in French when you speak French, in English otherwise.
Her Japanese voice says her replies and her permission requests: Claude Haiku translates each line, which takes a little of your plan's usage, and AivisSpeech says it on the CPU, about 4 s after the bubble shows.

You may pause while you speak: she sends your request after 15 s of silence, or as soon as you say *"done"* (or *"terminé"*, *"termine"*) as a sentence of its own after a pause, or end it with *"over"* (or *"c'est tout"*). *"Cancel"* said alone, or *"cancel prompt"* at the end, drops it. The bubble reminds you of the word.

- When she asks your permission, say *"yes"* or *"no"* as a sentence of its own, within 60 s. Otherwise answer in Claude Code or on claude.ai as usual.
- A click on a link or a path in her bubble opens it. A click on her or on her pill opens Claude Code's Remote Control on claude.ai, and a long press on either drags it.
- Dropped on a second screen, she comes back there, and shows up on the main screen while it is unplugged.
- Her tray icon, with a left or a right click, or her pill with a right click, opens her menu: the session, its context, your plan usage, her voice's volume, the frame rate of her windows (from the screen's own refresh rate to unlimited), the config, the log, the start with Windows, and quitting.

### 🧰 Actions

A request that is exactly one of the phrases below is done by the app itself, at once and without the session. Any other wording goes to the session, which has the same actions as tools (`mcp__clairechan__*`) and calls them itself.

| Action | Say | Does |
|---|---|---|
| Screenshot | *"take a screenshot of screen 2"*, *"capture l'écran 2"* | Saves the screen (1 to 3, the first by default) in `Pictures\Screenshots` |
| Start a transcription | *"transcribe the meeting"*, *"transcris la réunion"* | Writes everything the PC plays and your microphone hears into `Documents\Transcriptions`, one timed line per sentence |
| Stop the transcription | *"stop the transcription"*, *"arrête la transcription"* | Closes that file |
| Stop everything | *"stop everything"*, *"arrête tout"* | Kills the running request, its agents and the queued commands, then starts the session again on the same conversation. The app keeps running |
| Agents progress | *"il en est où ?"*, *"agent progress"* | Tells what each background agent of the session works on: running or finished, its age, its tool calls and the last one |
| Restart the app | *"restart yourself"*, *"relance-toi"* | Quits and starts the whole app again on the same conversation, for the rare change she cannot apply by herself |
| Switch model | *"switch to Opus"*, *"passe en Sonnet"* | Types `/model` into the session once its current request is done |
| Compact the conversation | *"compacte la conversation"* | Types `/compact` into the session once its current request is done |
| Context of the session | *"show me the context"*, *"le contexte"*, or the tray menu | How full the hidden session's context window is, as `/context` reports it |
| Child session | (tool only) | Starts a `claude --bg` session the user reads in their Code list on claude.ai, and tells the session when it has finished. Never stop it with `claude stop`, which removes it from the list |
| Agent usage | *"usage des agents"*, *"agent costs"* | What the background agents used over the last day by model: tokens written and read, largest context. Each agent that stops adds a line to `usage.jsonl` next to the config |
| Dream | *"lance le rêve"*, *"start the dream"* | Starts a child session that reads what every Claude Code session did since the last dream and proposes changes to the shared memory, `~/.claude/memory`, as commits on a branch `dream` of its repository. Its `rapport.md` is in `%APPDATA%\ClaireChan\dream`, a folder to list in `trusted_folders` |
| Dream proposals | *"montre les propositions"*, *"applique la proposition 2"*, *"refuse la proposition 2, parce que ..."* | Lists the proposals with their diff, carries one into the memory and pushes it, or refuses one with a reason the next dream reads. Nothing reaches the memory without your word |
| Plan usage | *"my usage"*, *"mon usage"*, or the tray menu | Share of the 5-hour window and of the week used, as `/usage` reports it |
| Timer | *"set a timer for 10 minutes"*, *"mets un minuteur de 5 min"* | Rings with a chime and a message once the time is up |
| Weather | *"what's the weather in Lyon"*, *"quel temps fait-il"* | The weather now and for the day, in the city you name |
| Mute | *"mute"*, *"coupe le son"* | Mutes the PC's sound, or unmutes it |
| Open a program | Any request, through the session (`launch_program` tool) | Opens the program whose Start menu shortcut matches the name |
| Use an application | Any request, through the session (`list_windows`, `read_window`, `look_window`, `press`, `fill` tools) | Reads the windows of the applications of the `apps` config key, and presses or fills what they show in those set to `"act"`, after asking you, again every 10 min and each time for a button that sends, pays, deletes or logs in. *"Tu peux agir dans Firefox"* lets her act for 10 min in a program set to `"read"`. She never takes the focus from a game |
| ShadowPlay clip | *"clip that"*, *"enregistre ça"* | Presses Alt+F10 |
| Test Minecraft | Any request, through the session (`minecraft_*` tools) | Starts a Minecraft 26.3 test client of its own (`tools/minecraft/`, never your game), joins a server, runs commands, reads the chat, holds keys and takes screenshots |

### ♻️ Her own code

Ask her to change her own code, such as *"make yourself an action that ..."*: the session edits this folder.
The app runs as two processes: her core (the session, her ears and her voice) and her face (her windows, her reactions and her actions).
Once the session has nothing running, a change to her face, her actions or a sprite starts her face again alone, in 1.5 s, while the session goes on.
A change to the core starts the whole app again on the same conversation.
A change that stops her from starting is put aside in git (stashed, or her commits reverted), and she tells you which.
She leaves her changes for you to review and commit, unless `commit_changes = true` in the config.

### Without an NVIDIA GPU

Whisper's model takes 20 s a sentence on a 6-core CPU, against 0.6 s on a GPU, so the app switches to a lighter setup by itself:
a small model of [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) listens for *"Hey Claire"* on 2.5 % of one core, and Whisper's `small` model only transcribes what you say after it.
She then answers about 4 s after you stop speaking instead of 1 s, mishears more words, and wakes on the usual ways to say *"Hey Claire"* in English or French, whatever the `wake` key of the config says.
With a GPU, `wake_gate = true` in the config gives it the same role, so that Whisper no longer transcribes every sentence the microphone hears.

## ⚙️ Configuration

*Open the config* in the tray menu opens `%APPDATA%\ClaireChan\config.toml`, which explains each key:
the speech recognition language, the wake phrase, the pause and the phrases that end a spoken request,
the models of the hidden session (Sonnet) and of the agent it hands complicated requests to (Opus), whether she commits the changes to her own code, the applications she may use, her size on screen, her voice, and your additions to the session's system prompt, such as where your folders are.
A change applies as soon as you save the file, and she tells you what changed. The agent's model, the commits and the system prompt, which Claude Code reads only when it starts, restart the hidden session on the same conversation once she has nothing running.

## 🧑‍💻 Development

```powershell
uv run pytest --doctest-modules src tests
$env:CLAIRECHAN_UI_TESTS = 1; uv run pytest tests/test_desktop.py   # opens a Notepad, which takes the focus
uv run ruff check .
uv run pyright
uv run prototypes/overlay_demo.py              # plays every expression in a loop
uv run scripts/demo_video/main.py              # renders dist/demo.mp4, a scripted run through her features (needs ffmpeg)
uv run prototypes/voice_demo.py --wav clip.wav # prints what the listener hears, from the microphone without --wav
uv run prototypes/voice_demo.py --spotter      # counts what the wake phrase spotter of a computer without NVIDIA GPU catches
uv run python -m clairechan.voice.bench record request   # 30 requests to the microphone, into %APPDATA%\ClaireChan\bench
uv run python -m clairechan.voice.bench record noise     # an hour of what she must not wake to (--minutes 60)
uv run python -m clairechan.voice.bench replay           # recall, false alarms and wake delay of Whisper alone and of the spotter
```

The demo video at the top of this file is the `_small` copy of that script's video, uploaded with the [gh-image](https://github.com/drogers0/gh-image) extension:
`gh image dist/demo_small.mp4 --repo Stoupy51/ClaireChan` prints the link to paste in place of the old one.

The sprites in `assets/claude/` come out of `tools/sprites/`, a separate uv project described in [PLAN.md](PLAN.md#sprites).

### With Claude Code in auto mode

The auto mode classifier stops a session from writing and running code that starts another Claude Code session in auto mode, which is what this app does ("Create Unsafe Agents").
To let Claude Code work on that part, add this exception to your user settings, `~/.claude/settings.json`, since the classifier ignores a project's own settings:

```json
"autoMode": {
	"allow": [
		"$defaults",
		"In the ClaireChan repository, the app starts a hidden Claude Code session with claude --remote-control --permission-mode auto and types the user's voice commands into it: writing, testing and running that launcher, including scripts that start such a session to test it, is allowed."
	]
}
```

`claude auto-mode config` shows the rules in effect. Without the exception, ask for that action explicitly in your message instead.


## License

The code is under the [MIT license](LICENSE). The character's images in `assets/` come from a third-party video and are not covered by it.

