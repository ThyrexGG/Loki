# Loki — Project State

*Last Updated: 2026-11-16 (through Task 32)*

## 1. Current Milestone & Status

* **Completed**:
  * **Stage 1 (Milestone 1)** — Local App Shell, Hardware Health View & Ollama Chat.
  * **Handoff System** — Repository-based documentation & model-to-model continuation system (`docs/*`).
  * **Stage 2 (Milestone 2 / Task 2.1)** — Inspectable Workflow Engine, Run History (`app/workflows.py`), and Read-Only PC Analyst & Log Summarizer (`app/diagnostics.py`).
  * **Stage 3 (Milestone 3 / Task 3.1)** — Local Document Indexer (`app/indexer.py`), Folder Allowlist Controls, Cited Q&A, and the `folder_research_digest` Workflow.
  * **Task 5 (UX/UI Overhaul)** — Fluid ChatGPT/Claude/Gemini hybrid interface with borderless editorial assistant prose, safe Markdown + code-block copy renderer, floating omni-composer dock, and frosted-glass workspace views.
  * **Stage 4 (Task 4.1)** — Preview-and-Approval Gate for Safe New-Copy File Outputs (`app/approvals.py`) and the `clean_csv_to_new_copy` and `export_research_report` workflows.
  * **Stage 5 (Task 5.1)** — User-Controlled Personal/Project Memory Store (`app/memory.py`) & Local Push-to-Talk Voice + Offline TTS (`app/voice.py`).
  * **Stage 6 (Task 6.1)** — Three-Switch Cloud Provider Gateway Adapters & Outbound Activity/Cost Visibility Ledger (`app/cloud_gateway.py`).
  * **Stage 7 (Task 7.1)** — Explicit Opt-In Scheduled Workflow Automation & Foreground-Priority Resource Guardrails (`app/scheduler.py`).
  * **Stage 8 (Task 8.1 & Model Upgrade)** — Upgraded local model to **`gemma2:9b`** (`9.2B` parameters, `5.4 GB`), implemented the **Natural-Language Job-to-Workflow Planner** (`app/project_tools.py`), and added three domain workflows (`game_dev_project_audit`, `folder_organization_plan`, `content_publishing_kit`).
  * **Task 32 (Coding Agent)** - Agent switch: Loki works in the project folder itself (read, write, run, fix), smart-auto approvals, Undo all (ADR-016).
  * **Task 31 (Build & Preview)** - Website/app requests use the coder model; HTML answers get sandboxed Preview and Download (ADR-015).
  * **Task 30 (Model Menu Sections)** - Coloured section headings, dividers and speed dots.
  * **Task 29 (PC Help)** - Reviewed PowerShell commands: Run button, risk rating (read / change / admin / blocked), never elevated, 60 s limit, logged; troubleshooting route to qwen2.5:7b (`app/commands.py`, ADR-014).
  * **Task 28 (Screen Help)** - On-demand screenshot (3 s countdown) analysed by local `qwen3-vl:8b`; never saved (`app/screen.py`, ADR-013).
  * **Task 27 (Coding in Project Folders)** - Attach a project; Loki reads relevant files and proposes `file:` changes with diff review, backup and undo (`app/projects.py`, ADR-012).
  * **Task 26 (Model Menu)** - Styled model picker with plain names, strengths and speed groups; friendly names in replies.
  * **Task 25 (UI/UX Polish)** - Plain professional copy, no emoji, accurate privacy wording, narrow-window layout fixes, fade-in re-render bug fixed.
  * **Task 24 (Web Search & Link Reading)** - Automatic DuckDuckGo search and pasted-link reading with cited sources; sharper system prompt (`app/web_tools.py`, `app/web_decider.py`, ADR-011).
  * **Task 23 (In-App Dialogs)** - Styled confirm/rename dialogs replace browser pop-ups.
  * **Task 22 (Test Isolation)** - `LOKI_DATA_DIR` override + `tests/run_tests.py` isolated runner; tests can no longer touch real data.
  * **Task 21 (Auto Model)** - Per-task routing to coder / reasoning specialists with visible pill and collapsible reasoning (ADR-010).
  * **Task 20 (Model Fit)** - VRAM-aware model ratings, safe default selection, grouped picker with warnings (ADR-009).
  * **Task 18 (Repo, Tests, Multi-Chat)** - Git repo initialised; verify_m1-m8 re-run; saved chats list in sidebar with open/rename/delete (`/api/chats`).
  * **Task 14 (Brand)** - Serpent logo/icon (two-headed S serpent) across icon, favicon, sidebar, chat avatar, and welcome screen.
  * **Task 13 (Desktop App)** — Edge app-mode desktop app (`desktop/Loki.ps1`), Desktop + Start Menu shortcuts, Loki icon/favicon (ADR-008).
* **Current Stage**: All 8 platform stages plus Tasks 12-29 complete and verified (`tests/run_tests.py`: 9/9 pass). Loki now also searches the web, helps with code in project folders, looks at the screen on request, and runs reviewed PowerShell commands. Version label in code is still `v0.8.0`.

---

## 2. What Currently Works (Verified)

1. **Localhost FastAPI Backend (`app/main.py`)**:
   * Runs on `http://127.0.0.1:8420` via `%LOCALAPPDATA%\Python\bin\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8420`.
   * Rejects non-localhost clients (`HTTP 403`) and serves strict `Content-Security-Policy` headers (`default-src 'self'; connect-src 'self'`).
2. **Local Ollama Service & Resource Controls (`app/ollama_service.py`)**:
   * Connects to local Ollama daemon (`v0.40.13`) at `http://127.0.0.1:11434` (with models stored on Disk `D:` at `D:\OllamaModels`, linked via NTFS junction from `%USERPROFILE%\.ollama\models`).
   * **8 Installed Local Models in `D:\OllamaModels`**:
     1. **`qwen2.5:14b`** (`14.8B`, `8.37 GB`, `Q4_K_M`)
     2. **`phi4:14b`** (`14.7B`, `8.43 GB`, `Q4_K_M`)
     3. **`mistral-nemo:12b`** (`12.2B`, `6.59 GB`, `Q4_0`)
     4. **`gemma2:9b`** (`9.2B`, `5.07 GB`, `Q4_0` — Default)
     5. **`deepseek-r1:8b`** (`8.2B`, `4.87 GB`, `Q4_K_M`)
     6. **`llama3:latest`** (`8.0B`, `4.34 GB`, `Q4_0`)
     7. **`qwen2.5:7b`** (`7.6B`, `4.36 GB`, `Q4_K_M`)
     8. **`qwen2.5-coder:7b`** (`7.6B`, `4.36 GB`, `Q4_K_M`)
   * Provides `run_workflow_ai_step(...)` for workflow & Q&A AI steps with `<untrusted_data source="...">` prompt-injection isolation, sharing the same foreground `asyncio.Lock` (`inference_lock`).
   * Supports immediate generation cancellation (`POST /api/chat/stop`) and explicit GPU VRAM unloading (`POST /api/ollama/unload` using `keep_alive: 0`).
   * Enforces the Cloud Provider Privacy Gate.
3. **Read-Only Hardware Health & PC Analyst Collectors (`app/diagnostics.py`)**:
   * CPU load % via Win32 `kernel32.GetSystemTimes`.
   * System RAM usage (`used_gb`, `available_gb`, `total_gb = 15.23 GB`) via Win32 `kernel32.GlobalMemoryStatusEx`.
   * NVIDIA GeForce RTX 5050 Laptop GPU utilization %, VRAM usage (`8151 MiB` total), and temperature via read-only `nvidia-smi --query-gpu`.
   * Top 10 processes by working-set memory (MB) and CPU time (s) via read-only `Get-Process`.
   * Bounded user-selected `.log`/`.txt` tail reader (`<= 120 lines / 16 KB`) and opt-in Windows `Application`/`System` Warning & Error event reader (`Get-WinEvent -MaxEvents 12`).
4. **Inspectable Workflow Engine & Run History (`app/workflows.py`)**:
   * Exposes eight workflow blueprints (`pc_health_audit`, `log_file_explainer`, `folder_research_digest`, `clean_csv_to_new_copy`, `export_research_report`, `game_dev_project_audit`, `folder_organization_plan`, and `content_publishing_kit`).
   * Executes steps sequentially, halts safely if any step fails, supports Pause/Resume/Cancel/Retry, pauses at `approval_gate` steps (`status="awaiting_approval"`), and persists step-by-step history in `data/workflow_runs.json`.
5. **Preview-and-Approval Gate & Safe New-Copy Writer (`app/approvals.py`)**:
   * Stores pending write requests in `data/pending_approvals.json`.
   * Requires explicit user approval (`POST /api/approvals/{approval_id}/decide`) before writing any output file.
   * Writes exclusively to new copies inside `loki/data/exports/`, never overwriting existing files or modifying/deleting original source files.
6. **Local Document Indexer & Cited Q&A (`app/indexer.py`)**:
   * Indexes only explicitly approved folders into `data/index.db` (SQLite + `scikit-learn` TF-IDF cosine similarity + keyword boost, 0 MB GPU VRAM overhead).
   * Tracks exact `file_name`, `relative_path`, `start_line`, and `end_line` (`[relative_path:Lstart-Lend]`).
   * Supports **Add & Index Folder**, **Pause/Resume Index Access**, **Remove Folder**, **Remove Individual File**, **Re-Index**, and **Clear Entire Index**.
7. **User-Controlled Personal & Project Memory Store (`app/memory.py`)**:
   * Stores explicit memories (`personal`, `project`, `preference`, `workflow`) in `data/memories.json`.
   * Supports adding, per-memory pause/enable, global composer toggle (`use_memories_in_chat`), single deletion, and clearing all memories.
   * Injects active memories into local Ollama chat system context and emits `memories_used` metadata on every response.
8. **Local Push-to-Talk Voice & Offline TTS (`app/voice.py`)**:
   * Uses built-in Windows `.NET System.Speech` (`MS-1033-80-DESK` offline recognizer + `Microsoft Zira Desktop` / `Microsoft David Desktop` offline SAPI voices).
   * Strictly push-to-talk with a high-visibility red active-microphone banner, zero continuous recording, and zero audio uploads.
9. **Three-Switch Cloud Provider Gateway & Activity/Cost Visibility Ledger (`app/cloud_gateway.py`)**:
   * Enforces the Three-Switch Cloud Privacy Gate (`cloud_global_opt_in`, per-provider `enabled`, and per-request `cloud_request_opt_in`) keeping external providers (`openai`, `anthropic`, `gemini`) **hard-disabled by default**.
   * Reads API keys exclusively from environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`), never storing secrets in `settings.json`, source code, or logs.
   * Persists an inspectable Activity & Cost Visibility Ledger (`data/activity_ledger.json`) recording every local Ollama inference, blocked cloud attempt, and any opted-in cloud API usage/cost.
10. **Opt-In Scheduled Workflow Automation & Resource Guardrails (`app/scheduler.py`)**:
    * Off by default (`scheduler_enabled: false`) with both a global master switch and per-schedule enable/pause controls.
    * Enforces the Foreground-Priority Resource Guardrail (`check_foreground_and_resources`): automatically skips/defers (`skipped_foreground_busy`) if `ollama_service.inference_lock` is locked, another workflow is running, or CPU load > 92%.
    * Logs every schedule creation, toggle, guardrail deferral, and scheduled run ID in `data/schedules.json`.
11. **Natural-Language Job Planner & Domain Workflows (`app/project_tools.py`, `app/workflows.py`)**:
    * Maps plain-English job descriptions (`POST /api/workflows/plan`) to any of the 8 registered workflows (`pc_health_audit`, `log_file_explainer`, `folder_research_digest`, `clean_csv_to_new_copy`, `export_research_report`, `game_dev_project_audit`, `folder_organization_plan`, `content_publishing_kit`) and pre-fills inputs.
    * Includes `scan_project_directory` and `build_folder_organization_preview` read-only collectors paired with the Preview & Approval Gate.
12. **Multi-Chat History, Model Fit & Auto Model (`app/config.py`, `app/model_fit.py`, `app/model_router.py`)**:
    * Saved chats in the sidebar (open, rename, delete); conversations.json v2.
    * Models rated fits / tight / too big for the 8 GB GPU; safe default selection; styled model menu.
    * Auto model routes code -> `qwen2.5-coder:7b`, maths -> `deepseek-r1:8b`, web answers and PC help -> `qwen2.5:7b`, screenshots -> `qwen3-vl:8b`, everything else -> the picked model.
13. **Web Search & Link Reading (`app/web_tools.py`, `app/web_decider.py`)**: automatic DuckDuckGo search / pasted-link reading with [n] citations and a Sources list; public addresses only; switch on the Privacy page.
14. **Coding in Project Folders (`app/projects.py`)**: project context in chat; `file:` change proposals -> diff review -> apply with backup -> undo; secrets and dependency folders never read.
15. **Screen Help (`app/screen.py`)**: one screenshot on request to the local vision model; never saved.
16. **PC Help (`app/commands.py`)**: Run button on PowerShell blocks; risk-rated review; runs only after the user confirms; logged.
17. **Automated Verification (`tests/verify_m1.py` through `tests/verify_m9.py`, run via `tests/run_tests.py`)**:
    * `tests/run_tests.py` runs them against an isolated server with a throwaway data folder (`LOKI_DATA_DIR`), so the real `data/` is never touched; the scripts refuse to run directly.
    * All eight verification suites pass end-to-end against live local Ollama (`gemma2:9b` and `llama3:latest`).

---

## 3. What Is Planned / Not Yet Implemented

* All 8 stages from the starter and continuation prompts are complete and verified.

---

## 4. Known Issues & Environment Notes

* **Two Python 3.14 Installations on Host**:
  * Always use `%LOCALAPPDATA%\Python\bin\python.exe` (has `fastapi`, `uvicorn`, `httpx`, `ollama`, `scikit-learn`, `pandas`). Do not use `py` or bare `python`.
* **Ollama CLI Headless Behavior on Windows**:
  * Start the daemon via `%LOCALAPPDATA%\Programs\Ollama\ollama.exe serve` with `OLLAMA_HOST=127.0.0.1:11434`.

---

## 5. Important Paths

* Project Root: `D:\Loki` (Desktop junction: `%USERPROFILE%\Desktop\Loki`)
* Desktop App: `Loki` shortcut on Desktop / Start Menu → `desktop/Loki.ps1` (recreate with `desktop/Install_Shortcuts.ps1`)
* Console Launcher: `Start_Loki.bat` / `run_loki.ps1`
* Backend Entry: `app/main.py`
* Configuration & Storage Manager: `app/config.py`
* Ollama & Provider Gate: `app/ollama_service.py`
* Cloud Provider Gateway & Activity/Cost Ledger: `app/cloud_gateway.py`
* Opt-In Workflow Scheduler & Resource Guardrails: `app/scheduler.py`
* Read-Only Project & Folder Tools + NL Planner: `app/project_tools.py`
* Read-Only Diagnostics & Log Collectors: `app/diagnostics.py`
* Workflow Engine & Run History: `app/workflows.py`
* Preview-and-Approval Gate & CSV Cleaner: `app/approvals.py`
* Local Document Indexer & Cited Q&A: `app/indexer.py`
* User-Controlled Memory Store: `app/memory.py`
* Local Push-to-Talk Voice & Offline TTS: `app/voice.py`
* Model fit / routing: `app/model_fit.py`, `app/model_router.py`
* Web search & link reading: `app/web_tools.py`, `app/web_decider.py`
* Project folders & reviewed edits: `app/projects.py`
* Screen help: `app/screen.py` (vision model `qwen3-vl:8b`)
* PC help (reviewed PowerShell): `app/commands.py`
* Frontend UI: `static/index.html`, `static/styles.css`, `static/app.js`
* Persistent Data Folder: `data/` (`settings.json`, `conversations.json`, `workflow_runs.json`, `pending_approvals.json`, `memories.json`, `activity_ledger.json`, `schedules.json`, `index.db`, `exports/`, `project_changes.json`, `backups/`, `command_log.json`)
* Verification: `tests/run_tests.py` (isolated runner) + `tests/verify_m1.py` … `tests/verify_m9.py`, guard in `tests/_isolated.py`

---

## 6. Single Best Next Task

* None queued; see `docs/HANDOFF.md` section 5 for candidates.
