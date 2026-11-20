# Loki — Private, Local-First Personal Assistant & Workflow Platform

Loki is a private, local-first AI assistant and inspectable workflow automation platform for a Windows PC with **16 GB system RAM**, an **AMD Ryzen 7 H 260 CPU**, and an **NVIDIA GeForce RTX 5050 Laptop GPU (8 GB VRAM)** running **Ollama**.

---

## Project Documentation & Model-to-Model Handoff

The repository documentation is the shared source of truth across coding sessions and AI models:

* **[docs/HANDOFF.md](docs/HANDOFF.md)** — **Start here** when resuming work or switching models. Contains mandatory agent continuation instructions, current repository state, constraints, and the single concrete next action.
* **[docs/PROJECT_STATE.md](docs/PROJECT_STATE.md)** — Current milestone, verified working features, planned slices, environment notes, and next task.
* **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — Component design, data flow, Model Gateway, Workflow Engine, Tool Layer, storage, and security/permission boundaries.
* **[docs/DECISIONS.md](docs/DECISIONS.md)** — Dated Architectural Decision Records (ADRs) with context, alternatives, and consequences.
* **[docs/WORK_LOG.md](docs/WORK_LOG.md)** — Chronological log of completed tasks, files changed, and exact verification commands/results run.

---

## 1. Current Working Capabilities (Verified)

* **Local Ollama Chat (`app/ollama_service.py`)**:
  * Connects to local Ollama (`127.0.0.1:11434`, default `gemma2:9b`; 8 local models installed in `D:\OllamaModels`).
  * Streams answers with explicit model/provider attribution (`LOCAL • ollama / gemma2:9b • ctx 4096`), token counts, and `tok/s`.
  * Enforces a foreground single-inference lock (`asyncio.Lock`) so only one model generation runs at a time on your 8 GB GPU.
  * Includes immediate **Stop Generation** and **Unload Model (Free VRAM)** (`keep_alive: 0`) controls.
* **Home screen, command palette and Tools page (`static/tools.js`, `static/ui2.css`)**:
  * The home screen greets you, shows your next reminder, how busy the PC is and how much Loki knows about you, and offers one-click actions (build something, check my PC, set a reminder, talk hands-free, news, game project check).
  * **Ctrl+K** opens a command palette for everything (new chat, agent on/off, hands-free, tools, switch model); typing a question there asks Loki.
  * **Tools** page: reminders, what the PC is doing right now (memory, GPU, drives, top apps, startup apps), files (largest, duplicates, organise with plan / apply / undo) and Godot / Unity project checks. Narrow windows get a slide-in menu.
* **Local tools in chat (`app/local_tools.py`)**:
  * "Remind me Friday at 5 to ...", "in 20 minutes ...", "what reminders do I have" are answered instantly without a model; a Windows notification appears when a reminder is due (while Loki runs).
  * "Why is my PC slow?", "biggest files in my downloads", "duplicates in D:\Photos", "organise my downloads", "check my Godot project" run the tool on this PC, show a result card, and the model explains it. Organising only moves files after you click the button, and can be undone. Windows and program folders are never scanned.
* **Memory that learns (`app/memory.py`)**: with **Learn from chats** on (Privacy page), facts you state about yourself (setup, projects, preferences) are saved with a "Remembered: ... / Forget" note under the reply. Only your own messages are used; duplicates merge; memories can be edited; with many memories only the relevant ones go into the prompt.
* **Hands-free voice (`app/voice.py`, `app/voice_handsfree.ps1`)**: the Hands-free button listens for "Hey Loki" with the offline Windows speech engine, takes your request and speaks the answer. Off by default and after every restart; nothing is recorded or uploaded; it pauses while Loki speaks.
* **Bigger brain**: an optional button under replies re-asks a cloud model, only when cloud AI, a provider and its API key (environment variable) are all set up, after a confirmation that says what leaves the PC.
* **Coding Agent (`app/agent.py`)**:
  * With **Agent** on (composer switch, on by default) and a project attached, or when you ask Loki to build something new, Loki does the work itself instead of only printing code: it reads the project, writes and edits files, runs the code or tests, reads the errors and fixes them, then summarises. New projects get their own folder under `D:\LokiProjects` (attached automatically).
  * Every step shows live under the reply (files read, diffs of each change, command output). Safe steps run by themselves; installs, deletions, git history changes, downloads and paths outside the project wait for **Run it / Skip**. Servers and admin commands are never run. **Undo all** puts every file back; **Preview** opens a project's `index.html`; **Open folder** shows it in Explorer.
  * New websites start from Loki's own designed starter (`app/web_starter/`: dark/light theme, hero, cards, stats, contact panel, scroll reveal; a colour scheme picked per project); the model writes the page content.
  * **Plan, do, check**: for a real build or change request Loki first writes a short plan (shown as a checklist), works through it, then a reviewer pass reads the changed files and sends real problems (missing features, broken references, code that would crash) back to fix before it reports done.
  * **Code map** (`app/code_map.py`): bigger projects get a map of which file defines which classes and functions (Python via `ast`, JS/TS, C#, GDScript by pattern), and the files matching the task are read first.
  * **Runs the apps it builds** (`app/app_runner.py`): web apps and servers (Flask, FastAPI, Node, `npm start`) start in the background on a free localhost port; Loki requests pages, reads the response and fixes errors. **Open app** / **Stop app** in the chat; an app stops after 30 minutes, when the next one starts, or when Loki closes.
  * Uses `qwen2.5:7b` (benchmarked best for tool use on 8 GB, see ADR-016). Small local models still make mistakes: when the code's own checks fail at the end, Loki says so plainly and shows the error.
* **Build Websites and Small Apps**:
  * Ask for a website, landing page, small app or browser game: Loki (Qwen 2.5 Coder) writes one self-contained HTML file. **Preview** runs it inside Loki in a sandbox (its own code runs, but it cannot reach the internet, your files or Loki); **Download** saves it as an `.html` file.
* **PC Help (`app/commands.py`)**:
  * Troubleshooting questions ("my PC is slow", "Wi-Fi keeps dropping", errors) use PC help: Loki starts with 2-4 read-only PowerShell checks and waits for the results before suggesting changes.
  * Every PowerShell block in a reply has a **Run** button. Nothing runs until you review it: **Read-only** (Run), **Changes your PC** (red "Run anyway"), **Needs administrator** (copy only; Loki never elevates) or **Not allowed** (destructive or security-weakening commands are refused; copy only).
  * Commands run as your normal account with a 60-second limit; output appears in the dialog with **Ask Loki about this output**. Every run is logged in `data/command_log.json` and the Activity log.
* **Screen Help (`app/screen.py`, vision model `qwen3-vl:8b`)**:
  * Click the monitor button next to the microphone: after a 3-second countdown (switch to the window you need help with) Loki takes ONE screenshot of the main monitor. Add a question or just press Send; the screenshot goes only to the local vision model.
  * Screenshots are never saved: saved chats keep a "Screenshot (not saved)" note. Each capture is listed in the Activity log as local.
  * Expect roughly 45-60 s per answer: the model reasons first (shown under Reasoning) and only just fits the 8 GB GPU.
* **Coding in Project Folders (`app/projects.py`)**:
  * Attach a project folder from the **No project** chip in the composer (Add a project folder...). Loki sees the file list plus the files most relevant to your question (secrets such as `.env` and folders like `.git`, `node_modules`, build output are never read) and uses Qwen 2.5 Coder with an 8k context when it fits.
  * Proposed changes appear as `file:path` blocks with **Review change**: a diff with warnings (for example when a change would delete most of a file). Nothing is written until you click Apply; the old version is backed up in `data/backups/`, the change is logged in `data/project_changes.json`, and **Undo** restores it (refused if you edited the file afterwards).
* **Web Search & Links (`app/web_tools.py`, `app/web_decider.py`)**:
  * Loki decides automatically when to go online: pasted links are read; time-sensitive questions (latest, news, prices, dates, scores, releases), explicit requests ("search ...", "look up ...") and who/when/where questions about named things are searched. Code, maths, creative writing and small talk stay offline.
  * Uses DuckDuckGo, or Yahoo when DuckDuckGo is busy (no account or API key), reads the top 3 pages, and answers with inline citations [1], [2] plus a **Sources** list under the reply. Web-backed answers use `qwen2.5:7b` when Auto model is on.
  * Turn it off under **Privacy & Data > Web search & links**.
* **Auto Model (per-task routing, `app/model_router.py`)**:
  * With **Auto model** on (composer chip, default on), code questions go to `qwen2.5-coder:7b`, maths / logic / step-by-step questions to `deepseek-r1:8b`, and everything else to the model you picked. Only models that fit the 8 GB GPU are used; otherwise your picked model answers.
  * Each reply shows an **Auto • Code / Reasoning** pill (hover for why). `deepseek-r1`'s thinking appears in a collapsible **Reasoning** section and is not sent back as history.
  * Switching models takes ~20-30 s the first time (loading from disk); turn **Auto model** off to always use one model.
* **Read-Only System Health & Telemetry (`app/diagnostics.py`)**:
  * Live read-only CPU load (`Win32 GetSystemTimes`), System RAM load (`Win32 GlobalMemoryStatusEx`), and RTX 5050 GPU load/VRAM/temperature (`nvidia-smi --query-gpu`).
  * Top 10 processes by WorkingSet RAM and CPU seconds (`PowerShell Get-Process`, read-only).
  * Bounded log file tail reader (`<= 120 lines / 16 KB` for explicitly selected `.log`/`.txt` files) and opt-in Windows `Application`/`System` Warning & Error event reader (`Get-WinEvent -MaxEvents 12`).
* **Inspectable Workflow Engine, Natural-Language Job Planner & PC Analyst (`app/workflows.py`, `app/project_tools.py`)**:
  * **Describe a Job in Plain English (`POST /api/workflows/plan`)**: Maps everyday language to an inspectable workflow blueprint and pre-fills inputs.
  * Displays workflow blueprints (trigger, inputs, allowed sources, ordered deterministic vs. AI vs. approval-gate steps, expected outputs, and approval points) before running.
  * Includes eight verified workflows:
    * **`pc_health_audit`** (*PC Resource & Log Diagnostic Report* — Read-Only)
    * **`log_file_explainer`** (*Selected Log File Summarizer* — Read-Only)
    * **`folder_research_digest`** (*Research Digest from Approved Indexed Folders* — Read-Only)
    * **`clean_csv_to_new_copy`** (*Clean Spreadsheet / CSV to New Copy* — Pauses at Preview & Approval Gate)
    * **`export_research_report`** (*Export Cited Research Report to Markdown* — Pauses at Preview & Approval Gate)
    * **`game_dev_project_audit`** (*Game & Code Project Build Report* — Pauses at Preview & Approval Gate)
    * **`folder_organization_plan`** (*Selected Folder Organization Plan & Manifest* — Pauses at Preview & Approval Gate)
    * **`content_publishing_kit`** (*Video & Content Publishing Kit Drafter* — Pauses at Preview & Approval Gate)
  * Supports **Pause/Resume**, **Cancel**, **Retry**, safe halting on step failure, and persistent step-by-step run history in `data/workflow_runs.json` with full tool/model attribution (`data_left_pc: false`).
* **Preview-and-Approval Gate for Safe New-Copy Writes (`app/approvals.py`)**:
  * Any workflow that writes an output file pauses in state `awaiting_approval` and shows the destination path, byte size, before/after diff summary, and file content preview.
  * Writes are restricted to new copies inside `loki/data/exports/` only after explicit user approval; original files are never modified or deleted.
* **Local Document Indexer & Cited Q&A (`app/indexer.py`)**:
  * Indexes only folders you explicitly add (`.md`, `.txt`, `.py`, `.json`, `.csv`, `.log`, `.html`, `.ps1`) into `data/index.db` using SQLite + `scikit-learn` TF-IDF hybrid search (0 MB GPU VRAM overhead).
  * Cites exact file names, relative paths, and line ranges (`[relative_path:Lstart-Lend]`) and isolates all document chunks inside `<untrusted_data>` tags.
  * Provides UI & API controls to **Pause/Resume Index Access**, **Remove Individual Folders/Files**, **Re-Index**, and **Clear Entire Index**.
* **Personal & Project Memory Store (`app/memory.py`)**:
  * Lets you explicitly choose what Loki remembers across chats (`personal`, `project`, `preference`, `workflow` memories stored in `data/memories.json`).
  * Memories are never extracted silently; you can add, pause/enable per entry, toggle global memory injection in the composer (`Memories (N)`), or delete individual/all memories anytime.
  * Every chat response shows how many explicit memories were injected (`memories_used`).
* **Local Push-to-Talk Voice & Offline TTS (`app/voice.py`)**:
  * Uses built-in Windows `.NET System.Speech` (`MS-1033-80-DESK` offline recognizer + `Microsoft Zira Desktop` / `Microsoft David Desktop` offline SAPI voices).
  * Strictly push-to-talk with a high-visibility red active-microphone banner (`MICROPHONE ACTIVE — Local Windows Push-to-Talk Listening (No Cloud Upload)`), immediate Stop Recording button, zero continuous recording, and zero audio uploads.
  * Every assistant reply includes a **Speak** button for local offline TTS playback.
* **Three-Switch Cloud Provider Gateway & Activity/Cost Visibility Ledger (`app/cloud_gateway.py`)**:
  * Enforces the Three-Switch Cloud Privacy Gate (`cloud_global_opt_in`, per-provider `enabled`, and per-request `cloud_request_opt_in`) keeping external providers (`openai`, `anthropic`, `gemini`) **hard-disabled by default**.
  * Reads API keys exclusively from Windows environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`)—never storing secrets in source code, `settings.json`, or logs.
  * Persists an inspectable **Activity & Cost Visibility Ledger** (`data/activity_ledger.json`) recording every local Ollama inference (`0 B` external, `$0.0000`), blocked cloud attempt (`0 B` external), and any opted-in cloud API usage/cost.
* **Opt-In Scheduled Automation & Foreground-Priority Guardrails (`app/scheduler.py`)**:
  * Off by default (`scheduler_enabled: false`) with both a global master switch and per-schedule enable/pause controls.
  * Automatically yields to foreground chat (`inference_lock`) and skips/defers (`skipped_foreground_busy`) if a chat or workflow is active or CPU load exceeds 92%, logging every trigger and deferral in `data/schedules.json`.
* **Privacy Gate & Local Data Inspector (`app/config.py`, `app/main.py`)**:
  * Bound strictly to `127.0.0.1:8420` with browser `Content-Security-Policy: default-src 'self'; connect-src 'self'`.
  * Full inspection and one-click wipe of all files stored in `loki/data/`, plus an Ephemeral Chat toggle.

---

## 2. Setup

No new packages or model downloads are required. Loki uses the Python 3.14 runtime and the local Ollama models already installed in `D:\OllamaModels` (default `gemma2:9b`) on your PC.

* **Project Folder**: `D:\Loki` (also reachable via the Desktop junction `%USERPROFILE%\Desktop\Loki`)
* **Ollama Binary**: `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`
* **Python Runtime**: `%LOCALAPPDATA%\Python\bin\python.exe` (Python 3.14.7 with `fastapi`, `uvicorn`, `httpx`, `pydantic`, `scikit-learn`, `pandas`)

---

## 3. Start & Stop

### Desktop App (recommended)
Double-click **Loki** on your Desktop (or search "Loki" in the Start Menu). It opens Loki in its own app window (Microsoft Edge app mode — no tabs or address bar, separate profile in `D:\Loki\desktop\profile`), starting Ollama and the Loki server in the background if needed. Closing the window unloads the model from GPU VRAM and stops the server it started.

* Launcher: `desktop\Loki.ps1` · server log: `desktop\server.log(.err)`
* Recreate shortcuts: `powershell -ExecutionPolicy Bypass -File D:\Loki\desktop\Install_Shortcuts.ps1`
* Logo & icon: a two-headed Norse serpent coiled into an S (Urnes-style knotwork; Jörmungandr, Loki's child). Regenerate all assets (`static/loki-logo.svg`, `static/loki-mark.svg`, `static/loki.png`, `desktop/loki.ico`) with `& "$env:LOCALAPPDATA\Python\bin\python.exe" desktop\make_icon.py`

### Start Loki (PowerShell)
From inside `D:\Loki` (or double-click `Start_Loki.bat`):

```powershell
.\run_loki.ps1
```

Or run the server directly:

```powershell
# 1. Ensure Ollama is serving locally on 127.0.0.1:11434
$env:OLLAMA_HOST = "127.0.0.1:11434"
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden

# 2. Start Loki bound strictly to localhost
& "$env:LOCALAPPDATA\Python\bin\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8420
```

Then open **`http://127.0.0.1:8420`** in your browser.

### Stop Loki & Unload GPU VRAM
1. **Stop an in-flight answer**: Click the red **Stop Generation** button in the chat composer.
2. **Free GPU VRAM immediately**: Click **Unload Model (Free VRAM)** in the top bar (sends `keep_alive: 0` to Ollama so the model is immediately evicted from your RTX 5050's 8 GB VRAM).
3. **Stop the Loki web server**: Press `Ctrl+C` in the PowerShell window running `uvicorn`.

---

## 4. Model Selection & Resource Limits (16 GB RAM / 8 GB VRAM)

* **Single Active Model Lock**: Loki enforces an `asyncio.Lock` on inference requests so only one model generation runs at a time, preventing background contention.
* **Visible Model Attribution**: Every assistant response displays a badge showing the exact provider, model name, context window (`num_ctx`), token counts, and generation speed (`tok/s`).
* **Context Window (`num_ctx`)**:
  * `2048` tokens — Lowest VRAM usage.
  * `4096` tokens *(Default)* — Recommended for 8 GB VRAM (`gemma2:9b` uses ~5.4 GB VRAM, leaving ~2.5 GB headroom; 14B models such as `phi4:14b` / `qwen2.5:14b` exceed 8 GB and partially offload to CPU).
  * `8192` tokens — Higher VRAM usage for longer conversations/documents.

---

## 5. Data Storage Locations

Loki keeps all persistent state inside a single inspectable folder inside the project directory:

* **`D:\Loki\data\`**
  * `settings.json` — Selected model, context length, temperature, cloud gate flags, memory injection flag, TTS voice selection, and folder allowlist.
  * `conversations.json` — Local chat history: every saved chat (listed under **Chats** in the sidebar — click to reopen, double-click to rename, trash icon to delete; **New chat** starts a fresh one without deleting anything). Only saved when **Save history locally** is checked; unchecking it switches to Ephemeral Mode and deletes `conversations.json`.
  * `workflow_runs.json` — Inspectable step-by-step workflow run history (Stage 2).
  * `index.db` — Local SQLite + TF-IDF document search index (Stage 3).
  * `exports/` — Approved new-copy workflow output files (Stage 4; written only after explicit user preview & approval).
  * `memories.json` — User-controlled personal & project memories (Stage 5).
  * `activity_ledger.json` — Inspectable Model Gateway Activity & Cost Visibility Ledger (Stage 6).
  * `schedules.json` — Opt-in scheduled workflow definitions and scheduler guardrail audit log (Stage 7).

Loki **never** stores files in `%APPDATA%`, the Windows Registry, or outside the project folder.

---

## 6. Privacy Behavior & Security Boundaries

* **Localhost Server**: Loki binds exclusively to `127.0.0.1:8420`; AI runs on the local Ollama at `http://127.0.0.1:11434`.
* **Web Access (on by default, switch on Privacy & Data)**: when a question needs current information, or you paste a link, the Loki server searches DuckDuckGo (Yahoo when DuckDuckGo is busy) and/or reads the page. Only the search text or link leaves this PC; chats, files, memories and the AI itself stay local. Pages on this PC or your home network are never fetched, page text is treated as untrusted, and every lookup is listed in the Activity Ledger.
* **Strict Browser CSP**: HTTP headers enforce `Content-Security-Policy: default-src 'self'; connect-src 'self'`, preventing the browser UI from making any external network requests.
* **Cloud Provider Gate**: Cloud providers (ChatGPT, Claude, Gemini) are **hard-disabled** by default in both configuration and the backend router.
* **Untrusted Data Framing**: Document contents and logs are treated as passive, untrusted data. System prompts instruct the model never to follow instructions found inside files or logs.
* **Read-Only Telemetry**: Hardware status uses read-only Windows API calls (`GetSystemTimes`, `GlobalMemoryStatusEx`) and `nvidia-smi --query-gpu`. Loki does not execute arbitrary shell commands or modify system settings.

---

## 7. How to Remove All Loki Data

You can remove all stored Loki data at any time without affecting your PC or your Ollama installation:

1. **From the Loki UI**: Open the **Privacy & Data** tab and click **Wipe All Stored Loki Data**.
2. **From PowerShell / File Explorer**: Delete the `data` subfolder:
   ```powershell
   Remove-Item -Recurse -Force "D:\Loki\data"
   ```
3. **To remove Loki completely**: Delete the folder `D:\Loki` (and the Desktop junction).

---

## 8. Running the Verification Tests

```powershell
& "$env:LOCALAPPDATA\Python\bin\python.exe" tests\run_tests.py         # all 10 suites
& "$env:LOCALAPPDATA\Python\bin\python.exe" tests\run_tests.py m3 m8   # selected suites
& "$env:LOCALAPPDATA\Python\bin\python.exe" tests\run_tests.py --fast   # full speed (only when you are away from the PC)
```

The runner starts a separate Loki server with a throwaway data folder, so your chats, memories, settings and index are never touched (it checks this and reports it). Your normal Loki can stay open.

It is **gentle by default**: before each AI suite it waits until at least 4 GB of RAM and 5 GB of GPU memory are free (and says so while it waits), unloads the model and pauses after each suite, runs at below-normal priority and caps Ollama's CPU threads, so the PC stays usable. The coding-agent suites (`m9`, `m10`) need no model and run in seconds.

## 9. Troubleshooting

* **`ollama list` fails in terminal with `Unable to init instance: Unspecified error`**:
  * On Windows, running `ollama list` when the daemon is stopped attempts to launch the desktop tray GUI (`ollama app.exe`), which can fail in non-interactive shells. Start the headless server with `& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve` or click **Start Local Ollama** in the Loki top bar.
* **`python` or `py` command cannot find `uvicorn`**:
  * Windows has the Microsoft Store alias enabled for `python.exe`, and `py.exe` points to a secondary Python installation. Always use `& "$env:LOCALAPPDATA\Python\bin\python.exe"` (which `run_loki.ps1` uses automatically).
