# Loki — Work Log

Append a concise entry after each completed task or meaningful implementation step. Never claim checks passed unless they were actually run.

---

## 2026-11-15 — Task 1: Machine Inspection & Milestone 1 Implementation (Local App Shell, Health View & Ollama Chat)

* **Goal**: Verify Windows PC hardware, Ollama installation, and Python environment without installing or downloading anything; implement and verify Milestone 1 (local web shell, Ollama chat with model attribution, stop/unload controls, read-only CPU/RAM/GPU status, and privacy/data reset controls).
* **Files Created / Changed**:
  * `app/__init__.py` — Package version (`0.1.0`).
  * `app/config.py` — Localhost configuration, `data/settings.json` and `data/conversations.json` management, storage inspection, and full wipe helper.
  * `app/ollama_service.py` — Async Ollama client (`127.0.0.1:11434`), single-inference `asyncio.Lock`, streaming chat, stop generation abort event, GPU VRAM unload (`keep_alive: 0`), and Cloud Provider Privacy Gate.
  * `app/diagnostics.py` — Read-only collectors for CPU (`Win32 GetSystemTimes`), RAM (`Win32 GlobalMemoryStatusEx`), and GPU/VRAM (`nvidia-smi --query-gpu`).
  * `app/indexer.py` — Initial index boundary summary module.
  * `app/main.py` — FastAPI server bound to `127.0.0.1:8420` with localhost host-check middleware and strict `Content-Security-Policy` headers.
  * `static/index.html`, `static/styles.css`, `static/app.js` — Local dark-mode web UI.
  * `run_loki.ps1` — PowerShell launcher script using `%LOCALAPPDATA%\Python\bin\python.exe`.
  * `README.md` — Initial setup, run/stop, privacy, and data removal guide.
  * `tests/verify_m1.py` — End-to-end automated verification script.
* **Behavior Added**:
  * Local streaming chat with `llama3:latest`, visible model/context badge on every reply, Stop Generation button, Unload Model (Free VRAM) button, Ephemeral chat toggle, live CPU/RAM/GPU telemetry, and one-click Wipe All Stored Loki Data.
* **Commands & Checks Run**:
  1. Started local Ollama daemon: `& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve` with `OLLAMA_HOST=127.0.0.1:11434` → Listening on `127.0.0.1:11434 (version 0.40.13)`.
  2. Started Loki server: `& "$env:LOCALAPPDATA\Python\bin\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8420` → Listening on `http://127.0.0.1:8420`.
  3. Ran `& "$env:LOCALAPPDATA\Python\bin\python.exe" "<original project folder>\tests\verify_m1.py"`:
     * `GET /` returned `HTTP 200` with `CSP: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';`
     * `GET /api/status` confirmed `ollama.connected = True` (`v0.40.13`), `installed_models = ['llama3:latest']`, CPU `18.8%`, RAM `11.09 / 15.23 GB`, and `NVIDIA GeForce RTX 5050 Laptop GPU` (`2017 / 8151 MiB` VRAM).
     * `POST /api/chat/stream` with `provider="openai"` was blocked by the Loki Privacy Gate.
     * `POST /api/chat/stream` with `model="llama3:latest"` loaded the model into GPU VRAM (`4530.0 MiB` on GPU) and returned `'LOKI_LOCAL_OK'`.
     * `POST /api/ollama/unload` unloaded `llama3:latest` and returned `running_models: []`.
* **Remaining Issues / Limitations**:
  * PC Analyst (`#tab-analyst`) and Document Q&A (`#tab-docs`) tabs are currently UI placeholders awaiting Milestone 2 / Stage 2 and Milestone 3 / Stage 3 implementation.
* **Next Step**:
  * Establish the model-to-model documentation and handoff system (`docs/*`), then implement Stage 2 (Workflow Engine core + Read-Only PC Analyst & Log Diagnostic workflow).

---

## 2026-11-15 — Task 2: Expanded Vision Roadmap & Model-to-Model Handoff Documentation System

* **Goal**: Inspect the existing repository, preserve all working Milestone 1 code, establish the repository-based handoff documentation (`docs/PROJECT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/WORK_LOG.md`, `docs/HANDOFF.md`, and updated `README.md`), and define the staged platform roadmap and single concrete next task.
* **Files Created / Changed**:
  * `docs/PROJECT_STATE.md` — Created current milestone state, verified capabilities, environment quirks, and single best next task.
  * `docs/ARCHITECTURE.md` — Created component diagram, Model Gateway, Workflow Engine, Tool Layer, Storage, and Security/Permission boundary documentation.
  * `docs/DECISIONS.md` — Recorded ADR-001 through ADR-005.
  * `docs/WORK_LOG.md` — Created chronological work log with verified test outputs.
  * `docs/HANDOFF.md` — Created model-to-model continuation brief with mandatory agent startup/completion instructions and concrete next task.
  * `README.md` — Updated with expanded platform overview and links to all `docs/*.md` files.
* **Behavior Added**:
  * Full repository-as-source-of-truth documentation and handoff structure so any AI model or human session can inspect and continue work seamlessly.
* **Commands & Checks Run**:
  * Inspected repository file tree and git status via PowerShell (`Get-ChildItem -Recurse -File` in `<original project folder>`). Confirmed all 19 existing files intact and no `.git` repo initialized yet.
* **Remaining Issues / Limitations**:
  * None for documentation; code implementation of Stage 2 (`app/workflows.py` and expanded `app/diagnostics.py`) awaits user approval to proceed.
* **Next Step**:
  * Execute **Task 2.1**: Implement `app/workflows.py` (Workflow Engine & Run History) and expand `app/diagnostics.py` (top processes + bounded user-selected log reader) to deliver the first end-to-end manually triggered read-only workflow (`pc_health_audit`).

---

## 2026-11-15 — Task 3 (Stage 2 / Task 2.1): Workflow Engine Core, Run History & Read-Only PC Analyst

* **Goal**: Implement the inspectable step-by-step Workflow Engine (`app/workflows.py`), expand `app/diagnostics.py` with read-only top-process and bounded `.log`/`.txt` + opt-in Windows Event Log collectors, wire the **PC Analyst & Workflows** tab in the UI, and verify end-to-end with `tests/verify_m2.py`.
* **Files Created / Changed**:
  * `app/config.py` — Added `WORKFLOW_RUNS_FILE = DATA_DIR / "workflow_runs.json"` and `load_workflow_runs()`, `save_workflow_runs()`, `clear_workflow_runs()`.
  * `app/diagnostics.py` — Added `get_top_processes(limit=10)`, `read_log_file_tail(file_path, max_lines=120, max_bytes=16384)`, `get_recent_windows_events(max_events=12)`, and `ensure_sample_diagnostic_log()`.
  * `app/ollama_service.py` — Added `run_workflow_ai_step(...)` enforcing the Cloud Privacy Gate, single-inference `asyncio.Lock`, `<untrusted_data source="...">` prompt-injection isolation, and cancellation.
  * `app/workflows.py` — Created `WorkflowEngine` with `pc_health_audit` and `log_file_explainer` workflow blueprints, step status tracking, safe halt on step failure, Pause/Resume/Cancel/Retry controls, and persistent run history.
  * `app/main.py` — Added `/api/diagnostics/processes`, `/api/diagnostics/sample-log`, `/api/diagnostics/log-preview`, `/api/workflows`, `/api/workflows/run`, `/api/workflows/runs/{run_id}`, `/api/workflows/runs/{run_id}/cancel`, `/api/workflows/runs/{run_id}/pause`, and `DELETE /api/workflows/runs`.
  * `static/index.html`, `static/styles.css`, `static/app.js` — Built the **PC Analyst & Workflows** screen with live top processes, blueprint inspector, log tail preview, manual runner, live step inspector, and run history table.
  * `tests/verify_m2.py` — Created end-to-end verification script for Stage 2.
  * `README.md`, `docs/PROJECT_STATE.md`, `docs/WORK_LOG.md`, `docs/HANDOFF.md` — Updated handoff documentation.
* **Behavior Added**:
  * Inspectable workflow blueprints showing trigger, inputs, allowed sources, ordered deterministic vs. AI steps, expected outputs, and approval points before first run.
  * Safe failure handling: if a deterministic collector fails (e.g., missing log path), the workflow stops immediately at that step and never invokes the downstream AI step.
  * Full end-to-end execution of `pc_health_audit` and `log_file_explainer` with `llama3:latest` and persisted run history in `data/workflow_runs.json`.
* **Commands & Checks Run**:
  1. Restarted Loki server: `& "$env:LOCALAPPDATA\Python\bin\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8420`.
  2. Ran `& "$env:LOCALAPPDATA\Python\bin\python.exe" "<original project folder>\tests\verify_m2.py"`:
     * `GET /api/diagnostics/processes?limit=10`: Returned 10 processes (`vmmemWSL` 2004 MB, `RobloxStudioBeta` 1392.1 MB, `Memory Compression` 1092.5 MB).
     * `POST /api/diagnostics/sample-log` & `POST /api/diagnostics/log-preview`: Created and read `sample_system.log` (`7 lines`, `835 bytes`).
     * `GET /api/workflows`: Verified blueprints `['pc_health_audit', 'log_file_explainer']`.
     * Safe Halt Test (`log_file_path="C:\\nonexistent_folder\\missing_file.log"`): Step `inspect_selected_logs` failed safely and halted the run (`ai_diagnostic_analysis` remained `pending`).
     * Full Workflow Test (`pc_health_audit` with `sample_system.log` + `include_windows_events=True`): Completed all 4 steps (`run-1794727894-6af782`), verified `data_left_pc: False`, persisted run history (`2 runs`), and unloaded `llama3:latest` from VRAM after completion.
* **Remaining Issues / Limitations**:
  * Document Q&A (`#tab-docs` / `app/indexer.py`) is still a placeholder awaiting Stage 3 (Task 3.1).
* **Next Step**:
  * Execute **Task 3.1**: Implement Local Document Indexer (`app/indexer.py`), Folder Allowlist Controls (add, pause, remove, clear), Cited Q&A (`POST /api/docs/ask`), and the `folder_research_digest` workflow.

---

## 2026-11-15 — Task 4 (Stage 3 / Task 3.1): Local Document Indexer, Cited Q&A & Folder Research Workflow

* **Goal**: Implement local document indexing and hybrid search (`app/indexer.py`) over user-selected folders using SQLite (`data/index.db`) and `scikit-learn` `TfidfVectorizer` (0 MB GPU VRAM overhead), add explicit folder allowlist controls (add, pause, remove folder, remove file, re-index, clear), implement cited Q&A (`POST /api/docs/ask`), register the `folder_research_digest` workflow in `app/workflows.py`, build the **Document Q&A (`#tab-docs`)** UI, and verify end-to-end with `tests/verify_m3.py`.
* **Files Created / Changed**:
  * `app/indexer.py` — Implemented `LocalDocumentIndexer` with SQLite tables (`indexed_files`, `document_chunks`), line-numbered chunking (`start_line`–`end_line`), hybrid TF-IDF + keyword search, pause-access enforcement, folder/file removal, index clearing, and `ask_documents()` with `<untrusted_data source="file:Lstart-Lend">` framing.
  * `app/workflows.py` — Added `folder_research_digest` (*Research Digest from Approved Indexed Folders*) workflow blueprint and step runner (`verify_index_state`, `retrieve_relevant_chunks`, `synthesize_cited_report`).
  * `app/main.py` — Added `/api/docs/status`, `/api/docs/folders`, `/api/docs/reindex`, `/api/docs/pause`, `/api/docs/folders/remove`, `/api/docs/files/remove`, `/api/docs/clear`, `/api/docs/search`, and `/api/docs/ask`.
  * `static/index.html`, `static/app.js` — Built the **Document Q&A** screen with approved folder manager, one-click `Index Loki docs/` helper, pause/resume toggle, indexed files table with per-file removal, search-only mode, and cited local Ollama Q&A.
  * `tests/verify_m3.py` — Created end-to-end verification suite for Stage 3.
  * `README.md`, `docs/PROJECT_STATE.md`, `docs/WORK_LOG.md`, `docs/HANDOFF.md` — Updated handoff documentation.
* **Behavior Added**:
  * 100% local indexing and cited Q&A with `[relative_path:Lstart-Lend]` citations, strict pause-access privacy switch blocking both search and workflows when paused, per-folder and per-file index deletion, and reusable `folder_research_digest` workflow.
* **Commands & Checks Run**:
  1. Restarted Loki server: `& "$env:LOCALAPPDATA\Python\bin\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8420`.
  2. Ran `& "$env:LOCALAPPDATA\Python\bin\python.exe" "<original project folder>\tests\verify_m3.py"`:
     * `POST /api/docs/clear` & `GET /api/docs/status`: Verified clean initial state (`0 files, 0 chunks`).
     * `POST /api/docs/folders` (`<original project folder>\docs`): Indexed `5 files` (`36 chunks`).
     * `POST /api/docs/search` (`query="Three-Switch Cloud Provider Gate ADR-004"`): Returned top citations `['DECISIONS.md:L41-L59', 'DECISIONS.md:L28-L45', 'ARCHITECTURE.md:L51-L69']`.
     * `POST /api/docs/pause` (`paused=True`): Verified both `/api/docs/search` and the `folder_research_digest` workflow halted immediately with `"Document index access is PAUSED. Resume access in Document Q&A first."`
     * `POST /api/docs/ask`: Resumed access and verified cited answer from `llama3:latest` with `data_left_pc: False`.
     * `POST /api/workflows/run` (`workflow_id="folder_research_digest"`): Completed all 3 steps (`run-1794728566-39cf79`).
     * `POST /api/docs/files/remove` & `POST /api/docs/reindex`: Verified file count went `5 -> 4 -> 5`, then unloaded `llama3:latest` from GPU VRAM.
* **Remaining Issues / Limitations**:
  * All workflows are currently read-only (`writes_to: none`). Preview-and-approval gates for writing new output files (`loki/data/exports/`) are scheduled for Stage 4 (Task 4.1).
* **Next Step**:
  * Execute **Task 4.1**: Implement `app/approvals.py` (Preview-and-Approval Gate for Safe New-Copy File Outputs) and add the `export_research_report` and `clean_csv_to_new_copy` workflows.

---

## 2026-11-15 — Task 5: Chat & Workspace UX/UI Overhaul (ChatGPT + Claude + Gemini Hybrid Design)

* **Goal**: Replace the boxy dashboard/card layout with a fluid, modern AI interface combining ChatGPT's centered reading column and floating omni-composer pill dock, Claude's borderless editorial assistant turns and Markdown/code-block formatting, and Gemini's gradient welcome hero and glass suggestion cards.
* **Files Created / Changed**:
  * `static/index.html` — Redesigned layout with crisp inline SVG icons, prominent `+ New chat` pill button, minimal floating model selector bar, Gemini-style welcome hero with 4 interactive suggestion cards, centered `chat-stream-column`, and a floating omni-composer dock with inline context/temperature/history pills.
  * `static/styles.css` — Replaced harsh `#30363d` box borders with deep obsidian canvas (`#0f1014`), translucent frosted-glass surfaces (`border-radius: 18px–24px`), right-aligned soft user pills (`border-radius: 22px 22px 6px 22px`), borderless assistant prose rows, editorial Markdown styles, and dark code blocks with header bars.
  * `static/app.js` — Added zero-dependency safe Markdown & code-block renderer (`renderMarkdown`) with one-click `Copy` buttons for code blocks and assistant replies, citation pill formatting (`[file:Lstart-Lend]`), and smooth textarea auto-resize.
  * `docs/WORK_LOG.md`, `docs/PROJECT_STATE.md`, `docs/HANDOFF.md` — Updated handoff records.
* **Behavior Added**:
  * Borderless editorial assistant responses, rich Markdown rendering (headings, lists, blockquotes, fenced code blocks with copy button, inline citation pills), auto-expanding floating composer dock, and unified frosted-glass surfaces across all 5 tabs.
* **Commands & Checks Run**:
  * Verified `GET /`, `GET /static/styles.css`, `GET /static/app.js`, and `GET /api/status` via `httpx.Client` against `http://127.0.0.1:8420` → `UI ASSETS & STATUS VERIFIED: 200 200 200 200`.
* **Remaining Issues / Limitations**:
  * None for the UI polish.
* **Next Step**:
  * Execute **Task 4.1**: Implement `app/approvals.py` (Preview-and-Approval Gate for Safe New-Copy File Outputs) and add the `export_research_report` and `clean_csv_to_new_copy` workflows.

---

## 2026-11-15 — Task 6 (Stage 4 / Task 4.1): Preview-and-Approval Gate for Safe New-Copy File Outputs

* **Goal**: Implement `app/approvals.py` (`ApprovalManager` + deterministic `pandas` CSV cleaner), add `approval_gate` step support in `app/workflows.py`, register two approval-gated workflows (`clean_csv_to_new_copy` and `export_research_report`), wire the Preview & Approval UI in `static/index.html` and `static/app.js`, and verify end-to-end with `tests/verify_m4.py`.
* **Files Created / Changed**:
  * `app/config.py` — Added `PENDING_APPROVALS_FILE` (`data/pending_approvals.json`) and `EXPORTS_DIR` (`data/exports/`).
  * `app/approvals.py` — Created `ApprovalManager`, `clean_csv_deterministic()`, and `ensure_sample_messy_csv()`. Enforces that approved outputs are written exclusively to non-existing paths inside `data/exports/`, never overwriting existing files or touching source files.
  * `app/workflows.py` — Added `clean_csv_to_new_copy` and `export_research_report` workflow blueprints and step handlers, pausing runs in `status="awaiting_approval"` at `approval_gate` steps.
  * `app/main.py` — Added `POST /api/diagnostics/sample-csv`, `GET /api/approvals`, and `POST /api/approvals/{approval_id}/decide`.
  * `static/index.html`, `static/styles.css`, `static/app.js` — Added **Sample CSV** button and interactive **Preview & Approval Gate Card** (`Approve & Save New Copy` / `Reject (Do Not Write)`).
  * `tests/verify_m4.py` — Created end-to-end verification suite for Stage 4.
  * `README.md`, `docs/PROJECT_STATE.md`, `docs/WORK_LOG.md`, `docs/HANDOFF.md` — Updated handoff documentation.
* **Behavior Added**:
  * Deterministic CSV cleaning (`pandas` header normalization, whitespace trimming, empty & duplicate row removal) paired with local AI explanation and mandatory user preview/approval before writing a new copy to `data/exports/`.
  * Cited Markdown research report drafting and validation paired with mandatory user preview/approval before saving to `data/exports/`.
* **Commands & Checks Run**:
  1. Restarted Loki server: `& "$env:LOCALAPPDATA\Python\bin\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8420`.
  2. Ran `& "$env:LOCALAPPDATA\Python\bin\python.exe" "<original project folder>\tests\verify_m4.py"`:
     * `POST /api/diagnostics/sample-csv`: Created `sample_messy_tasks.csv` (`388 bytes`).
     * `POST /api/workflows/run` (`clean_csv_to_new_copy`): Verified run paused in `status="awaiting_approval"` (`apr-1794730166-b0753d`), diff `Rows: 7 -> 4 (removed 2 empty row(s) and 1 duplicate row(s)) | Normalized 5 column header(s)`, and confirmed target file did **not** exist on disk before approval.
     * `POST /api/approvals/apr-1794730166-b0753d/decide` (`decision="approve"`): Verified new copy written to `data/exports/sample_messy_tasks_cleaned.csv` (`244 bytes`), original file untouched (`True`), and workflow run transitioned to `completed`.
     * `POST /api/workflows/run` (`export_research_report`) + `decision="reject"`: Verified rejected file was never written to disk and workflow run transitioned to `cancelled`.
     * Unloaded `llama3:latest` from GPU VRAM after test.
* **Remaining Issues / Limitations**:
  * Personal/project memory store (`app/memory.py`) and optional local push-to-talk voice (`app/voice.py`) are scheduled next in Stage 5 (Task 5.1).
* **Next Step**:
  * Execute **Task 5.1**: Implement User-Controlled Personal/Project Memory Store (`app/memory.py`) and Local Push-to-Talk Voice Interface (`app/voice.py`).

---

## 2026-11-15 — Task 7 (Stage 5 / Task 5.1): Personal/Project Memory Store & Local Push-to-Talk Voice Interface

* **Goal**: Implement `app/memory.py` (`MemoryStore` persisted in `data/memories.json`), `app/voice.py` (`LocalVoiceService` using offline Windows `.NET System.Speech`), integrate user-approved memories into local Ollama chat (`app/ollama_service.py`), expose `/api/memories` and `/api/voice/*` routes in `app/main.py`, wire push-to-talk microphone banner, offline TTS Speak buttons, and the Personal & Project Memories table in `static/index.html`, `static/styles.css`, and `static/app.js`, and verify end-to-end with `tests/verify_m5.py`.
* **Files Created / Changed**:
  * `app/config.py` — Added `MEMORIES_FILE = DATA_DIR / "memories.json"`, `"use_memories_in_chat": True`, and `"selected_tts_voice": "Microsoft Zira Desktop"`.
  * `app/memory.py` — Created `MemoryStore` with `list_memories`, `add_memory`, `toggle_memory`, `delete_memory`, `clear_all`, and `get_active_memory_context`.
  * `app/voice.py` — Created `LocalVoiceService` using Windows `.NET System.Speech` (`SpeechRecognitionEngine` with `MS-1033-80-DESK` for bounded push-to-talk recognition + `SpeechSynthesizer` with `Microsoft Zira Desktop` / `Microsoft David Desktop` for offline TTS). Enforces `local_only=True`, `continuous_recording=False`, and `audio_uploaded=False`.
  * `app/ollama_service.py` — Injected `memory_store.get_active_memory_context()` into `stream_chat` system context and added `"memories_used"` to the stream `"meta"` event.
  * `app/main.py` — Added `GET/POST/DELETE /api/memories`, `POST /api/memories/{memory_id}/toggle`, `DELETE /api/memories/{memory_id}`, `GET /api/voice/status`, `POST /api/voice/listen`, `POST /api/voice/stop-listen`, `POST /api/voice/speak`, and `POST /api/voice/stop-speak`.
  * `static/index.html`, `static/styles.css`, `static/app.js` — Added high-visibility red `#mic-active-banner`, `#btn-ptt-mic`, `#btn-stop-tts`, assistant reply **Speak** buttons, `#chk-use-memories` composer pill (`Memories (N)`), and the Personal & Project Memories manager in the Privacy & Data tab.
  * `tests/verify_m5.py` — Created end-to-end verification suite for Stage 5.
  * `README.md`, `docs/PROJECT_STATE.md`, `docs/WORK_LOG.md`, `docs/HANDOFF.md` — Updated handoff documentation.
* **Behavior Added**:
  * Explicit user-controlled memory store (`data/memories.json`) with per-entry pause/enable and deletion, plus live recall in local Ollama chat.
  * 100% local push-to-talk speech recognition and offline SAPI TTS playback with prominent active-microphone banner and zero audio uploads.
* **Commands & Checks Run**:
  1. Restarted Loki server on `127.0.0.1:8420`.
  2. Ran `& "$env:LOCALAPPDATA\Python\bin\python.exe" tests\verify_m5.py`:
     * `GET /api/voice/status`: Verified `recognizer_engine="Windows System.Speech (MS-1033-80-DESK, Offline Push-to-Talk)"`, `available_tts_voices=['Microsoft Zira Desktop', 'Microsoft David Desktop']`, `local_only=True`, `continuous_recording=False`, `audio_uploaded=False`.
     * `POST /api/memories`: Added project memory `mem-1794731620-e654d5` (`"Project Codename & UI Accent"` -> `"My project codename is Project Bifrost and my preferred UI accent color is Emerald Green."`).
     * `POST /api/chat/stream`: Verified `"memories_used": 1` in `"meta"` event and verified `llama3:latest` replied: `"Your project codename is Project Bifrost, and your preferred UI accent color is Emerald Green."`
     * `POST /api/memories/mem-1794731620-e654d5/toggle` (`enabled=False`): Verified `"memories_used": 0` on subsequent chat stream.
     * `DELETE /api/memories/mem-1794731620-e654d5`: Verified memory count returned to `0`.
     * `POST /api/ollama/unload`: Unloaded `llama3:latest` from RTX 5050 VRAM.
* **Remaining Issues / Limitations**:
  * Optional Cloud Provider Gateway Adapters & Outbound Activity/Cost Ledger are scheduled next in Stage 6 (Task 6.1).
* **Next Step**:
  * Execute **Task 6.1**: Implement Optional Cloud Provider Gateway Adapters & Outbound Activity/Cost Ledger (`app/cloud_gateway.py`).

---

## 2026-11-15 — Task 8 (Stage 6 / Task 6.1): Three-Switch Cloud Provider Gateway & Activity/Cost Visibility Ledger

* **Goal**: Implement `app/cloud_gateway.py` (`CloudProviderGateway` + `ActivityLedger` persisted in `data/activity_ledger.json`), connect `app/ollama_service.py` so every local Ollama inference and any blocked or opted-in cloud request is audited in `data/activity_ledger.json`, expose `/api/cloud/*` and `/api/activity/ledger` routes in `app/main.py`, wire the Three-Switch Cloud Gate & Activity/Cost Ledger UI in `static/index.html` and `static/app.js`, and verify end-to-end with `tests/verify_m6.py`.
* **Files Created / Changed**:
  * `app/config.py` — Added `ACTIVITY_LEDGER_FILE = DATA_DIR / "activity_ledger.json"` and default model + environment variable metadata (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) to `DEFAULT_SETTINGS["cloud_providers"]`.
  * `app/cloud_gateway.py` — Created `ActivityLedger` and `CloudProviderGateway` enforcing Switch 1 (`cloud_global_opt_in`), Switch 2 (`provider.enabled`), Switch 3 (`cloud_request_opt_in`), and environment-variable-only API key checks.
  * `app/ollama_service.py` — Connected `stream_chat` and `run_workflow_ai_step` to `cloud_gateway` and `activity_ledger`.
  * `app/main.py` — Added `GET /api/cloud/status`, `POST /api/cloud/settings`, `GET /api/activity/ledger`, and `DELETE /api/activity/ledger`, plus `cloud_gateway` and `activity_ledger` fields in `GET /api/status`.
  * `static/index.html`, `static/app.js` — Added interactive Three-Switch Cloud Gate controls and the Model Gateway Activity & Cost Visibility Ledger table in `#tab-privacy`.
  * `tests/verify_m6.py` — Created end-to-end verification suite for Stage 6.
  * `README.md`, `docs/PROJECT_STATE.md`, `docs/WORK_LOG.md`, `docs/HANDOFF.md` — Updated handoff documentation.
* **Behavior Added**:
  * Three-Switch Cloud Privacy Gate blocking unapproved OpenAI, Anthropic, and Gemini calls at each switch level (`0 bytes` leaving the PC) and auto-disabling all individual providers whenever Global Cloud Opt-In is turned off.
  * Unified Activity & Cost Visibility Ledger (`data/activity_ledger.json`) tracking local calls (`data_left_pc=False`, `$0.000000`), blocked cloud attempts (`data_left_pc=False`), external bytes sent, and estimated USD cost.
* **Commands & Checks Run**:
  1. Restarted Loki server on `127.0.0.1:8420`.
  2. Ran `& "$env:LOCALAPPDATA\Python\bin\python.exe" tests\verify_m6.py`:
     * Verified default `cloud_global_opt_in=False`, `local_default=True`, and `openai`/`anthropic`/`gemini` all `enabled=False`.
     * Tested Block #1 (all switches off -> OpenAI), Block #2 (Switch 2 off -> Anthropic), Block #3 (Switch 3 off -> Gemini), and Block #4 (all 3 switches on -> missing `OPENAI_API_KEY` env var).
     * Re-locked `cloud_global_opt_in=False` and confirmed all providers auto-disabled.
     * Ran 100% local Ollama chat (`llama3:latest` -> `'LOCAL'`) and verified `GET /api/activity/ledger` (`total_entries=5`, `local_calls=1`, `blocked_cloud=4`, `cloud_calls=0`, `bytes_sent_external=0`, `est_cost=$0.000000`, all entries `data_left_pc=False`).
     * Unloaded `llama3:latest` from RTX 5050 VRAM.
* **Remaining Issues / Limitations**:
  * Explicit Opt-In Scheduled Workflow Automation (`app/scheduler.py`) is scheduled next in Stage 7 (Task 7.1).
* **Next Step**:
  * Execute **Task 7.1**: Implement Explicit Opt-In Scheduled Workflow Automation (`app/scheduler.py`).

---

## 2026-11-15 — Task 9 (Stage 7 / Task 7.1 & Desktop Migration): Opt-In Scheduled Workflow Automation & Foreground-Priority Guardrails

* **Goal**: Move and organize the Loki repository cleanly to `%USERPROFILE%\Desktop\Loki` (with `Start_Loki.bat`), implement `app/scheduler.py` (`WorkflowScheduler` persisted in `data/schedules.json` with foreground-priority resource guardrails), expose `/api/schedules/*` routes in `app/main.py`, wire the Scheduled Automation & Audit Log UI in `static/index.html` and `static/app.js`, and verify end-to-end with `tests/verify_m7.py`.
* **Files Created / Changed**:
  * `Start_Loki.bat` — Created one-click Windows Desktop launcher in `%USERPROFILE%\Desktop\Loki`.
  * `app/config.py` — Added `SCHEDULES_FILE = DATA_DIR / "schedules.json"` and `"scheduler_enabled": False`.
  * `app/scheduler.py` — Created `WorkflowScheduler` enforcing `scheduler_enabled=False` by default, per-schedule `enabled` toggles, `check_foreground_and_resources()` (deferring/skipping whenever `ollama_service.inference_lock` is locked, another workflow is running, or CPU > 92%), and an inspectable `events` audit log in `data/schedules.json`.
  * `app/main.py` — Added `GET /api/schedules`, `POST /api/schedules/global`, `POST /api/schedules`, `POST /api/schedules/{schedule_id}/toggle`, `POST /api/schedules/{schedule_id}/run-now`, `DELETE /api/schedules/{schedule_id}`, and `DELETE /api/schedules`.
  * `static/index.html`, `static/app.js` — Added the **Opt-In Scheduled Automation & Resource Guardrails** card and **Scheduler Audit Log** table in `#tab-workflows`.
  * `tests/verify_m7.py` — Created end-to-end verification suite for Stage 7.
  * `README.md`, `docs/PROJECT_STATE.md`, `docs/WORK_LOG.md`, `docs/HANDOFF.md` — Updated handoff documentation.
* **Behavior Added**:
  * Explicit, off-by-default scheduled workflow automation with Foreground-Priority Resource Guardrails (`skipped_foreground_busy`) and full audit logging.
* **Commands & Checks Run**:
  1. Moved project to `%USERPROFILE%\Desktop\Loki`, started server on `127.0.0.1:8420`, and re-indexed `%USERPROFILE%\Desktop\Loki\docs` (`5 files`, `70 chunks`).
  2. Ran `& "$env:LOCALAPPDATA\Python\bin\python.exe" tests\verify_m7.py`:
     * Verified default `scheduler_enabled=False`, `loop_active=True`, `foreground_busy=False`.
     * Created schedule `sch-1794736327-90deb6` (`Hourly PC Health Check`, `pc_health_audit`, `interval=60m`, `enabled=False`).
     * Tested Foreground-Priority Guardrail deferral (`simulate_foreground_busy=True`): verified `skipped=True`, `skipped_count=1`, `last_status=skipped_foreground_busy`.
     * Triggered live scheduled execution (`simulate_foreground_busy=False`): verified `run_id=run-1794736327-2ea91d`, `status=completed`, `run_count=1`, `skipped_count=1`.
     * Verified scheduler audit events (`['scheduled_run_triggered', 'skipped_foreground_busy', 'schedule_created']`).
     * Unloaded `llama3:latest` from RTX 5050 VRAM.
* **Remaining Issues / Limitations**:
  * All 7 Core Platform Stages are complete and verified.
* **Next Step**:
  * Execute **Task 8.1 (Stage 8)**: Upgrade local Ollama model to `gemma2:9b` (`9.2B`) and implement the Natural-Language Job-to-Workflow Planner (`app/project_tools.py`) and three domain workflows (`game_dev_project_audit`, `folder_organization_plan`, `content_publishing_kit`).

---

## 2026-11-15 — Task 10 (Stage 8 / Task 8.1 & `gemma2:9b` Model Upgrade): Natural-Language Job-to-Workflow Planner & Domain Workflows

* **Goal**: Upgrade the local Ollama model suite with **`gemma2:9b`** (`9.2B` parameters, `5.4 GB`, running on the RTX 5050 GPU), implement `app/project_tools.py` (`scan_project_directory`, `build_folder_organization_preview`, `plan_workflow_from_natural_language`), expand `app/workflows.py` to 8 workflows (`game_dev_project_audit`, `folder_organization_plan`, `content_publishing_kit`), add `POST /api/workflows/plan` to `app/main.py`, wire the Natural-Language Workflow Planner UI in `static/index.html` and `static/app.js`, and verify end-to-end with `tests/verify_m8.py`.
* **Files Created / Changed**:
  * `app/config.py` — Updated `DEFAULT_SETTINGS["selected_model"]` to `"gemma2:9b"`.
  * `app/project_tools.py` — Created read-only project directory auditor (`scan_project_directory`), non-destructive folder organization planner (`build_folder_organization_preview`), and Natural-Language Job-to-Workflow Planner (`plan_workflow_from_natural_language`).
  * `app/workflows.py` — Added `game_dev_project_audit`, `folder_organization_plan`, and `content_publishing_kit` blueprints and execution pipelines (bringing total inspectable workflows to 8).
  * `app/main.py` — Added `POST /api/workflows/plan`.
  * `static/index.html`, `static/app.js` — Added the **Natural-Language Job-to-Workflow Planner** card with one-click example job chips (`Game/Code Build Audit`, `Organize Messy Folder`, `Video Publishing Kit`, `Clean CSV Copy`) that auto-select the blueprint and pre-fill its inputs.
  * `tests/verify_m8.py` — Created end-to-end verification suite for Stage 8 and `gemma2:9b`.
  * `README.md`, `docs/PROJECT_STATE.md`, `docs/WORK_LOG.md`, `docs/HANDOFF.md` — Updated handoff documentation.
* **Behavior Added**:
  * Installed `gemma2:9b` (`9.2B`, `5.4 GB`) alongside `llama3:latest` (`8.0B`, `4.34 GB`) and set `gemma2:9b` as the active default model.
  * Natural-language job descriptions automatically map to the safest matching inspectable workflow blueprint and extract target folder/file paths and parameters for user review before execution.
  * Added 3 domain workflows (`game_dev_project_audit`, `folder_organization_plan`, `content_publishing_kit`) that perform read-only scanning/retrieval and pause at the Preview & Approval Gate before saving reports to `data/exports/`.
* **Commands & Checks Run**:
  1. Downloaded `gemma2:9b`: `& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull gemma2:9b` -> `success` (`5.4 GB`).
  2. Restarted Loki server on `127.0.0.1:8420`.
  3. Ran `& "$env:LOCALAPPDATA\Python\bin\python.exe" tests\verify_m8.py`:
     * Verified installed models `['gemma2:9b', 'llama3:latest']`, active default `gemma2:9b`, live streaming reply (`20.4 tok/s`), and GPU VRAM allocation (`size_vram_mb: 5391.8`, `processor: 'GPU'`).
     * Verified all 8 registered workflows (`['pc_health_audit', 'log_file_explainer', 'folder_research_digest', 'clean_csv_to_new_copy', 'export_research_report', 'game_dev_project_audit', 'folder_organization_plan', 'content_publishing_kit']`).
     * Verified `POST /api/workflows/plan` mapped all 4 natural-language job prompts to `game_dev_project_audit`, `folder_organization_plan`, `content_publishing_kit`, and `clean_csv_to_new_copy`.
     * Ran `game_dev_project_audit` on `%USERPROFILE%\Desktop\Loki` (`run-1794740130-2d153c` paused at `awaiting_approval` after scanning `45 files, 880.1 KB`), approved, and verified `data/exports/project_build_report_1.md` (`3,825 B`).
     * Ran `folder_organization_plan` on `%USERPROFILE%\Desktop\Loki\data` (`run-1794740165-42bcff` paused at `awaiting_approval` with `0 files moved`), approved, and verified `data/exports/folder_organization_plan_1.md` (`2,244 B`).
     * Unloaded `gemma2:9b` from RTX 5050 VRAM.
* **Remaining Issues / Limitations**:
  * All 8 Platform Stages are complete and verified.
* **Next Step**:
  * Ready for daily use from `%USERPROFILE%\Desktop\Loki\Start_Loki.bat` or `http://127.0.0.1:8420`.

---

## 2026-11-15 — Task 11: Disk `D:` Storage Migration (`D:\Loki` & `D:\OllamaModels`) + 8-Model Local Suite

* **Goal**: Move all Ollama models (`D:\OllamaModels`) and the Loki repository (`D:\Loki`) onto Disk `D:` while preserving transparent NTFS Directory Junctions at `%USERPROFILE%\.ollama\models` and `%USERPROFILE%\Desktop\Loki`, and install 6 additional Tier 1 & Tier 2 specialist/heavyweight models (`qwen2.5:14b`, `phi4:14b`, `mistral-nemo:12b`, `deepseek-r1:8b`, `qwen2.5:7b`, `qwen2.5-coder:7b`), stopping after `qwen2.5:14b` completed at the user's request so disk I/O is completely idle.
* **Files Created / Changed**:
  * `D:\Loki\run_loki.ps1` — Set `$env:OLLAMA_MODELS = "D:\OllamaModels"`.
  * `D:\Loki\app\config.py` — Added `"ollama_models_directory": "D:\\OllamaModels"` to `inspect_stored_data()`.
  * `D:\Loki\docs\PROJECT_STATE.md`, `D:\Loki\docs\HANDOFF.md`, `D:\Loki\docs\WORK_LOG.md` — Updated documentation for the Disk `D:` layout and 8 installed models.
* **Commands & Checks Run**:
  1. Moved `%USERPROFILE%\.ollama\models` (`9.41 GB`) to `D:\OllamaModels` and linked NTFS Junction (`C:` free space increased from `42.48 GB` to `51.85 GB`).
  2. Moved `%USERPROFILE%\Desktop\Loki` to `D:\Loki` and linked NTFS Junction on Desktop.
  3. Verified all 8 models in `GET http://127.0.0.1:8420/api/status`: `['qwen2.5:14b', 'phi4:14b', 'qwen2.5:7b', 'mistral-nemo:12b', 'deepseek-r1:8b', 'qwen2.5-coder:7b', 'gemma2:9b', 'llama3:latest']` (`running_models: []`, `is_generating: false`).

---

## 2026-11-15 — Task 12: Default Model Reset & Documentation Consistency Pass

* **Goal**: Restore the 8 GB-VRAM-safe default model and bring README / PROJECT_STATE in line with the current `D:\Loki` layout and 8-workflow platform.
* **Files Changed**:
  * `data/settings.json` — `selected_model` changed from `phi4:14b` (`8.43 GB`, exceeds 8 GB VRAM → partial CPU offload) back to `gemma2:9b` (matches `app/config.py` default).
  * `README.md` — Replaced stale `llama3:latest` default references with `gemma2:9b`, noted the 8 models in `D:\OllamaModels`, added 14B-model VRAM warning, and switched project paths to `D:\Loki` (Desktop junction noted).
  * `docs/PROJECT_STATE.md` — Workflow engine entry now lists all eight blueprints; Project Root updated to `D:\Loki`.
* **Commands & Checks Run**:
  * `python -m py_compile app/*.py` → OK. Loki/Ollama were not running; verification suites not re-run (no code changes).
* **Next Step**:
  * Start via `Start_Loki.bat`; optionally `git init` for change history.

---

## 2026-11-15 — Task 13: Local Hosting Check & Desktop App (ADR-008)

* **Goal**: Host Loki locally and give it a native-feeling desktop app without new dependencies.
* **Files Created / Changed**:
  * `desktop/Loki.ps1` — App launcher (Ollama + hidden server on demand, Edge `--app` window, unload + stop on close).
  * `desktop/Install_Shortcuts.ps1` — Creates `Loki.lnk` on Desktop and in Start Menu Programs.
  * `desktop/make_icon.py`, `desktop/loki.ico`, `static/loki.png` — Icon from UI brand mark (Pillow).
  * `static/index.html` — Added favicon link.
  * `.claude/launch.json` — Dev-server config for Claude Code preview.
  * `README.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (ADR-008), `docs/PROJECT_STATE.md`, `docs/HANDOFF.md`.
* **Commands & Checks Run**:
  1. Started Ollama (`v0.40.13`) and Loki; `GET /api/status` → 200, UI loaded with `gemma2:9b`.
  2. With server stopped, launched `Desktop\Loki.lnk` → server up in ~1.5 s, Edge app window titled "Loki — Private Local AI".
  3. Closed window → `POST /api/ollama/unload` 200 OK, server process exited, port 8420 closed.
* **Next Step**:
  * Optional: `git init` for change history.

---

## 2026-11-15 - Task 14: Serpent Logo & App Icon

* **Goal**: Replace the star mark with a logo inspired by the user's reference image (Norse two-headed serpent forming an S).
* **Files Created / Changed**:
  * `desktop/make_icon.py` - Rewritten: procedural SVG serpent (180-degree rotational symmetry, dorsal spines, scale texture, wolf-dragon heads, gold woven tendrils), simplified variant for <= 32 px, rasterised via headless Edge.
  * `static/loki-logo.svg`, `static/loki-mark.svg`, `static/loki.png`, `desktop/loki.ico` - Generated assets.
  * `static/index.html` - Sidebar brand mark and new welcome-screen `.hero-logo`; `?v=13` cache-busting on CSS/JS.
  * `static/app.js` - Assistant chat avatar uses `loki-mark.svg`.
  * `static/styles.css` - Dark tile for `.brand-mark`; `.hero-logo` style.
* **Commands & Checks Run**:
  1. `python desktop/make_icon.py` -> assets written; previewed 512 px detailed + simplified renders and 16-64 px sizes.
  2. Browser check: sidebar mark, chat avatars, and welcome logo render (served HTML/JS verified via curl).
  3. Re-ran `desktop/Install_Shortcuts.ps1` and `ie4uinit.exe -show`; launched app via Desktop shortcut -> window "Loki - Private Local AI".

---

## 2026-11-15 - Task 15: Detailed Knotwork Serpent Logo (minimal blend)

* **Goal**: Replace the "goofy" v1 serpent with a more serious Norse knotwork mark, then (per user feedback mid-task) pull it back to a cleaner, minimal-leaning style.
* **Files Created / Changed**:
  * `desktop/make_icon.py` - Rewritten art layer: centre-lines sampled into arc-length polylines (`Line`), double-outlined band with a sparse chevron row, sharp back-swept spines on the outer curves, layered wolf-dragon heads (upper/lower jaw, fangs, snout curl, almond eye + brow, swept mane) biting toward the centre, and two gold strands forming a figure-8 knot with computed over/under interlace (butt-capped over-pieces). Richer `ornament()` (triangle/spiral/scale zones) kept in the file but unused. Preview mode also writes a 16-88 px strip (`preview_small.png`).
  * `static/loki-logo.svg`, `static/loki-mark.svg`, `static/loki.png`, `desktop/loki.ico` - Regenerated.
  * `static/index.html` - Cache-busting bumped to `?v=14`.
  * `desktop/reference/v2_preview/` (kept locally, not in the repo) - Final previews (512 px detailed + simplified, small-size strip).
* **Commands & Checks Run**:
  1. Iterated previews with `python desktop/make_icon.py <dir>`; 16-32 px simplified icon reads as an S.
  2. `python desktop/make_icon.py` -> assets written; re-ran `desktop/Install_Shortcuts.ps1` and `ie4uinit.exe -show`.
  3. Browser check at http://127.0.0.1:8420: sidebar mark (30 px), chat avatars (24 px) and `.hero-logo` (88 px, empty state revealed temporarily via JS) all load; CSS/JS served with `?v=14`.
* **Follow-up**: Added `?v=15` to the favicon, `loki-mark.svg`, `loki-logo.svg` (index.html, app.js) and bumped CSS/JS to `?v=15`, so open app windows stop showing cached v1 art. Verified served assets match disk and both `Loki.lnk` shortcuts point to `desktop\loki.ico`.

---

## 2026-11-15 - Task 16: Loki Taskbar Icon (instead of Microsoft Edge)

* **Goal**: The app window showed the Microsoft Edge icon on the taskbar; give it Loki's own icon and name.
* **Files Created / Changed**:
  * `desktop/LokiShell.cs` - Win32/COM helpers: `SetShortcutAppId` (stamps .lnk with AppUserModelID), `SetWindowAppId` (window AUMID + relaunch command/icon/name), `SetWindowIcon` (WM_SETICON).
  * `desktop/Install_Shortcuts.ps1` - Stamps Desktop + Start Menu `Loki.lnk` with AUMID `Loki.LocalAI`.
  * `desktop/Loki.ps1` - After the Edge window appears, applies AUMID `Loki.LocalAI` and the Loki icon to it; failures are logged to `desktop/server.log` as `[desktop]`.
* **Commands & Checks Run**:
  1. Re-ran `desktop/Install_Shortcuts.ps1`; Shell property `System.AppUserModel.ID` on Desktop shortcut -> `Loki.LocalAI`.
  2. Closed and relaunched via Desktop shortcut; taskbar UI Automation lists `Appid: Loki.LocalAI | Loki - 1 running window` (no Edge entry).
  * Note: reading a window's AUMID back via `IPropertyStore.GetValue` returns VT_EMPTY even in-process; verify through taskbar UI Automation instead.

---

## 2026-11-15 - Task 17: Stale Taskbar Icon (Windows Icon Cache)

* **Problem**: Taskbar still showed the old star icon although `desktop/loki.ico` held the new serpent art; Windows caches icons per file path.
* **Fix**: `desktop/Install_Shortcuts.ps1` copies `loki.ico` to `desktop/icons/loki-<sha256[:10]>.ico` (old copies removed) and points both shortcuts at it; `desktop/Loki.ps1` uses the same hashed path for the window's relaunch icon / WM_SETICON. Any future icon change gets a new path automatically. Re-run `Install_Shortcuts.ps1` after regenerating icons.
* **Checks**: Shortcut IconLocation -> `D:\Loki\desktop\icons\loki-913201c578.ico,0`; relaunched via Desktop shortcut; taskbar UI Automation -> `Appid: Loki.LocalAI | Loki - 1 running window`.

---

## 2026-11-16 - Task 18: Git Repo, Full Test Run, Multi-Chat History

* **Goal**: Version the project, re-verify all stages after Tasks 12-17, and stop "New chat" from deleting history.
* **Files Created / Changed**:
  * `.gitignore` + `git init -b main`; initial commit `b77eaa7` (code, docs, assets, sample fixtures only; `data/*`, `desktop/profile/`, logs, icon copies ignored). Secret scan of HEAD: no matches.
  * `app/config.py` - Multi-chat store: `conversations.json` v2 `{"version": 2, "chats": [...]}`; v1 bare list migrated on read with a stable `legacy<sha1>` id; `list_chats`, `get_chat`, `upsert_chat`, `rename_chat`, `delete_chat`, auto titles from the first user message; legacy `load/save_conversations` map to the most recent chat.
  * `app/main.py` - `GET /api/chats`, `GET/PUT/DELETE /api/chats/{id}`, `POST /api/chats/{id}/rename` (ids validated `^[A-Za-z0-9_-]{8,64}$`; PUT respects `save_chat_history`).
  * `static/index.html`, `static/app.js`, `static/styles.css` - Sidebar **Chats** list (open, double-click rename, delete with confirm), **New chat** no longer deletes history, chat id assigned at first send, switching blocked while a reply streams; most recent chat reopens on start; assets bumped to `?v=16`.
  * `tests/verify_m3.py`, `verify_m4.py`, `verify_m8.py` - Replaced stale hard-coded paths (`<original project folder>\docs`, Desktop path) with `REPO_ROOT` derived from the test file.
* **Commands & Checks Run**:
  1. Backed up `data/` (md5 manifest), ran `verify_m1`-`m8` against the live server, restored `data/` byte-for-byte (only the test export `sample_messy_tasks_cleaned_1.csv` had been added).
     * PASS: m1, m5, m6.
     * FAIL (stale test paths, fixed, not yet re-run): m3, m4.
     * FAIL (transient): m2 - `/api/diagnostics/processes` returned ok on a manual retry.
     * FAIL (environment): m7, m8 - `httpx.ReadTimeout`; a full-screen game held most of the 8 GB VRAM (7.8 / 8.1 GB used), so `gemma2:9b` loaded only ~5.6 of 7.1 GB on GPU and ran too slowly. Model unloaded afterwards.
     * **Re-run m2, m3, m4, m7, m8 when the GPU is free** (back up / restore `data/` around them).
  2. Isolated chat-store tests (temp file): v1 migration, ordering, title truncation, rename persistence, delete-all removes file, legacy save -> all passed (first run caught an unstable migration id, fixed).
  3. Browser: existing history migrated as chat "hi" (8 messages); temporary API-created chat listed, most recent auto-opened, switching and New chat work, no console errors; test chat deleted afterwards. Not yet verified: sending a new message into a fresh chat (needs GPU inference).

---

## 2026-11-16 - Task 19: Re-run of Failed Verification Suites (GPU free)

* **Goal**: Re-run m2, m3, m4, m7, m8 after Task 18 (they failed on stale paths / GPU contention).
* **Commands & Checks Run**:
  1. Confirmed no game running, GPU idle (859 MiB used, 0 %); backed up `data/` with md5 manifest.
  2. Ran `verify_m2`, `m3`, `m4`, `m7`, `m8` against the live server -> **all passed** (m3/m4 with the new `REPO_ROOT` paths). Together with m1/m5/m6 from Task 18, **all 8 suites pass**.
  3. Closed the app window (server stop), restored `data/` byte-for-byte (tests had added 3 export files), relaunched; chats intact; no model left in VRAM.

---

## 2026-11-16 - Task 20: VRAM-Aware Model Selection (ADR-009)

* **Goal**: Stop Loki from defaulting to models too big for the 8 GB GPU, and show which models fit.
* **Files Created / Changed**:
  * `app/model_fit.py` (new) - `classify`, `annotate_models`, `pick_default_model`, `overhead_gb`.
  * `app/main.py` - `/api/status` annotates `installed_models` with `vram_fit` / `vram_fit_label`; missing saved model -> `pick_default_model` instead of first-listed model.
  * `static/app.js` - Model picker grouped into "Fits your GPU (fast)" / "Tight fit" / "Too big for GPU" (largest first), warning toast on tight/too-big choice, picker not rebuilt while focused (the 4 s refresh no longer closes an open menu); Hardware & Health table fit tags.
  * `static/styles.css` - `.fit-tag` styles; `static/index.html` - cache-bust `styles.css?v=17`, `app.js?v=18`.
* **Commands & Checks Run**:
  1. Unit tests (scratch script): real 8 models on 8151 MiB -> 14B models `offload`, `mistral-nemo:12b` `tight`, the five 4-5 GiB models `fits`; default with `qwen2.5:14b` listed first -> `gemma2:9b`; without gemma2 -> `deepseek-r1:8b`; nothing fits -> smallest; no GPU -> `unknown` ratings; 8k context makes `gemma2:9b` `tight`. All passed (first run showed the initial overhead formula was too small at 8k; recalibrated).
  2. Live API after restart: ratings as above; setting `selected_model` to a missing model -> `/api/status` switched it to `gemma2:9b` and saved it.
  3. Browser: picker groups correct with gemma2 selected; choosing `phi4:14b` showed the warning toast (switched back to gemma2 afterwards; settings confirmed `gemma2:9b`); Hardware & Health tags `partly CPU` / `tight` / `fits GPU`.

---

## 2026-11-16 - Task 21: Per-Task Model Routing ("Auto model", ADR-010)

* **Goal**: Use the installed specialist models automatically: coder for code, reasoning model for maths/logic, the picked model otherwise.
* **Files Created / Changed**:
  * `app/model_router.py` (new) - heuristic classifier, follow-up stickiness, `choose_model` (fits-only), cached Ollama capabilities.
  * `app/main.py` - `/api/chat/stream` routing + `route` event + `think` for thinking-capable models; `auto_route` request field; `auto_model_routing` setting.
  * `app/ollama_service.py` - `stream_chat(think=...)`; streams `message.thinking` as `thinking` events.
  * `app/config.py` - default `auto_model_routing: True`.
  * `static/app.js`, `static/index.html`, `static/styles.css` - **Auto model** composer chip, route pill on replies (tooltip explains), collapsible **Reasoning** block, inline `<think>` fallback, copy/speak/history use the answer only; cache-bust `styles.css?v=18`, `app.js?v=19`.
* **Commands & Checks Run**:
  1. Classifier tests (scratch): 18 labelled prompts (code / reasoning / general) + follow-up stickiness + fits-only fallback -> all pass (first run missed "17.5% of 2340" and a probability question; added strong-word weighting and "% of" arithmetic).
  2. Live API (GPU free, ctx 2048): python prompt -> `qwen2.5-coder:7b` (31.8 s incl. cold load); "15% of 240" -> `deepseek-r1:8b`, answer `36` with 1,287 chars of separate thinking (29.4 s); greeting -> `gemma2:9b` (9.5 s); `auto_route: false` -> stays on `gemma2:9b`. Models unloaded afterwards.
  3. Browser: Auto model chip checked; sample routed reply shows "Auto • Reasoning" pill, collapsible "Reasoning (21 words)", clean answer; fallback pill "Code • kept gemma2:9b"; no console errors; page reloaded (nothing saved). Not done in the UI: a full real chat turn (verified via API instead).

---

## 2026-11-16 - Task 22: Isolated Test Runner (tests can no longer touch real data)

* **Goal**: The verify suites cleared the index, memories, schedules and ledger and added chats in the real `data/`; Tasks 18-19 needed manual backup/restore. Make that impossible.
* **Files Created / Changed**:
  * `app/config.py` - `DATA_DIR` from `LOKI_DATA_DIR` (absolute path) when set; `inspect_stored_data` paths relative to `DATA_DIR.parent` (was `BASE_DIR`, which crashed `/api/status` with an external data folder).
  * `tests/run_tests.py` (new) - starts a second uvicorn on a free port with a temp `LOKI_DATA_DIR`, runs selected/all suites, prints PASS/FAIL with log tails, stops the server, deletes the temp folder (kept on failure), fingerprints real `data/` before/after, warns if the GPU is already busy.
  * `tests/_isolated.py` (new) - `base_url()` exits with instructions unless `LOKI_TEST_URL` is set; `test_data_dir()`.
  * `tests/verify_m1.py`-`m8.py` - use `base_url()`; m8 organizes the isolated data folder instead of the real one.
  * `README.md` (new section 8), `docs/ARCHITECTURE.md` (2.2c), `docs/HANDOFF.md` (constraint 4 rewritten), `docs/PROJECT_STATE.md`.
* **Commands & Checks Run**:
  1. `python tests/verify_m5.py` without the runner -> refused with instructions (exit 1).
  2. `python tests/run_tests.py` (real Loki open on 8420 throughout): first run 6/8 - m1/m8 hit a 500 from `/api/status` (`relative_to(BASE_DIR)` bug above); fixed; `run_tests.py m1 m8` 2/2; final full run **8/8 passed**, temp folder removed.
  3. Real `data/` md5 manifest identical to the one taken before the first isolated run.

---

## 2026-11-16 - Task 23: In-App Dialogs Replace Browser Pop-ups

* **Goal**: Replace the browser's native `confirm()` / `prompt()` boxes ("127.0.0.1:8420 says ...") with dialogs that match Loki.
* **Files Changed**:
  * `static/index.html` - one shared `<dialog id="app-dialog">` (title, message, optional text field, Cancel + primary button); Cancel is `type="button"` so Enter always confirms. Cache-bust `styles.css?v=19`, `app.js?v=21`.
  * `static/app.js` - `openAppDialog` / `confirmDialog` / `promptDialog` (Promise-based; Escape, Cancel or clicking outside cancels; destructive dialogs focus Cancel; empty text disables the primary button). Used for Rename chat, Delete chat and Wipe all data. No `confirm/prompt/alert` calls remain.
  * `static/styles.css` - `.app-dialog*` styles (dark surface, blurred backdrop, red destructive button, entry animation via `@starting-style`, reduced-motion respected).
* **Checks (browser, on a temporary API-created chat)**: delete dialog opens with focus on Cancel; Escape cancels; rename pre-selects the name, empty name disables Rename, Enter renames (server title updated); found and fixed a bug where Enter submitted through Cancel (first submit button); Delete chat removes only the test chat; Wipe dialog cancels on outside click with all data intact.
* **Noticed, not fixed**: in a narrow window (~800 px) the Privacy & Data tab overflows horizontally.

---

## 2026-11-16 - Task 24: Web Search, Link Reading and Sharper Answers (ADR-011)

* **Goal**: User asked for internet access and a more capable assistant; chose DuckDuckGo (no key), "automatically, always allowed", and research with sources, reading pasted links, better answers overall and working with files (files = next task).
* **Files Created / Changed**:
  * `app/web_tools.py` (new) - DuckDuckGo HTML search, safe page reader (public http(s) 80/443 only, private/loopback blocked after DNS and on every redirect, 1.5 MB / 10 s caps, page-chrome filter), `research()` reads top 3 pages concurrently.
  * `app/web_decider.py` (new) - heuristic: pasted link -> read; explicit/time-sensitive/who-when-where+proper-noun -> search; code/maths/creative/chat -> offline; follow-up query building.
  * `app/main.py` - web step in `/api/chat/stream` (`web_status`, `sources` events; results placed in the latest user turn inside `<untrusted_data>`; ledger entries); `web` route -> `qwen2.5:7b`; `web_access` setting.
  * `app/model_router.py` - `web` route. `app/ollama_service.py` - rewritten system prompt (lead with answer, no emoji, Windows-aware, cite web results, never claim to browse without results), today's date, `extra_system`. `app/config.py` - `web_access` default + `web_access_enabled()` with `LOKI_WEB_ACCESS=0` override. `app/cloud_gateway.py` - `web_requests_count`, web lookups not counted as cloud calls. `tests/run_tests.py` - sets `LOKI_WEB_ACCESS=0`.
  * `static/*` - web status line, Sources list under replies, Privacy page "Web search and links" switch, "Web lookups" ledger counter.
* **Checks**:
  1. Offline: 18 decider cases, 11 unsafe URLs blocked (localhost, 127.0.0.1:8420, 192.168/10.x, 169.254 metadata, [::1], :8443, .local, ftp, credentials), HTML extraction, DDG result parsing (ads skipped, redirect URLs decoded) - pass.
  2. Live (temporary isolated server): search 1.2 s, page read 0.4 s, research 3.3 s. "Latest Ollama version": gemma2:9b answered an outdated third-party figure (v0.40.5) even after grounding fixes; qwen2.5:7b answered v0.40.17 citing GitHub -> web route uses qwen2.5:7b. Link summary of Wikipedia "Loki" accurate with [1]. "Explain recursion" stayed offline. Ledger: 2 web lookups, 0 cloud calls.
  3. `tests/run_tests.py`: 8/8 pass, real data untouched.

---

## 2026-11-16 - Task 25: UI/UX Polish Pass (minimal, professional, no emoji)

* **Goal**: User asked to refine the whole UI/UX, minimise emoji, and keep it minimal and professional.
* **Changes** (`static/index.html`, `static/app.js`, `static/styles.css`; cache-bust `styles.css?v=25`, `app.js?v=24`):
  * Emoji/symbols removed: welcome cards use line icons; approval panel, model picker, refresh button and "Stop voice" use text/SVG. Emoji scan of UI and app text: none left.
  * Copy rewritten in plain language: nav (Chat, Documents, Workflows, System, Privacy), tab titles and descriptions, card headings, button labels, status labels in sentence case ("Active", "Disabled", "Read-only"); developer jargon (collector API names, file paths in headings, "Three-Switch", "TF-IDF", "Ledger") removed from view (collector notes hidden, still in code).
  * Accurate privacy wording now that web access exists: welcome text, sidebar pill ("AI on this PC - Web search on/Offline") and composer footnote follow the `web_access` setting; "Cloud Off" pill removed (cloud status lives on the Privacy page).
  * Welcome screen: plain headline (no gradient), four useful starters (news with sources, summarize a link, write code, solve step by step).
  * Layout: no sideways scrolling on narrow windows (cards shrink, tables scroll inside cards), buttons never wrap, no hover jump, top bar collapses to icon + status dot under 900 px.
  * Bug fix: every message re-ran its fade-in animation on each streamed token (conversation looked dim/flickery while replying); now only newly shown messages animate (`shownMessages` WeakSet, `.msg.settled`).
* **Checks**: all 145 `getElementById` targets present; JS syntax OK; browser review of all five tabs at 1280x800 and 820x700 (no overflow, no console errors); animation re-render check; `tests/run_tests.py m1 m5` pass, real data untouched.

---

## 2026-11-16 - Task 26: Model Picker Redesign

* **Goal**: The native `<select>` rendered as a white Windows menu with technical labels (GB, `Q4_K_M`) the user found unclear.
* **Changes**: styled `#model-picker` menu (button + `role="listbox"`) over the now visually hidden `#select-model` (still the source of truth for existing code). Plain names and sizes (`MODEL_INFO`, `friendlyModel`: "Gemma 2 9B", size from the tag, else rounded), one-line strengths, groups "Fast on this PC" / "May be slower" / "Slow on this PC" with short explanations, "Auto uses it for code / maths / web answers" notes and an Auto footer when Auto model is on, coloured fit dot on the button; technical details in hover titles. Keyboard (arrows, Home/End, Enter/Space, Escape, Tab), outside click closes, menu not rebuilt while open. Friendly names also in the welcome badge, reply header, route tooltips and reply footer ("On this PC" / "On this PC, with web results" replaces "100% Local"). Cache-bust `styles.css?v=27`, `app.js?v=27`.
* **Checks**: menu sizes correct for all 8 models (a stray backspace character from a Python edit had broken the size pattern; removed and scanned for control characters); no horizontal overflow; Escape returns focus to the button; ArrowDown/ArrowDown/Enter chose DeepSeek R1 and saved it, then restored Gemma 2 (settings confirmed `gemma2:9b`).

---

## 2026-11-16 - Task 27: Coding in Project Folders (ADR-012)

* **Goal**: User asked for Loki to work with their PC, see the screen and help with code. Choices: download a vision model (yes), "Loki proposes, I approve", build coding in project folders first.
* **Files Created / Changed**: `app/projects.py` (new); `app/main.py` (project endpoints, `project` on chat requests, code routing, 8k context when it fits, project context injection); `static/index.html` / `app.js` / `styles.css` (Project chip + menu, `file:` code blocks with Review change, diff dialog, Undo toast, "Read from <project>" line; code fences now accept info strings); cache-bust `styles.css?v=28`, `app.js?v=29`.
* **Checks**:
  1. Offline tests (throwaway data + fake project): registry rejects relative/missing/drive/system paths; `.env` and `node_modules` never listed; relevant-file ranking picks `src/player.py`; 7 unsafe edit paths refused (first run found `/etc/passwd` was treated as relative - fixed to refuse); apply/backup/stale-review refusal/undo; undo refuses after a later user edit; new-file create + undo; truncation and placeholder warnings; CRLF preserved (first run failed - `read_text` hides CRLF; fixed by checking bytes).
  2. Live (temporary server, real model): "health can go below zero" -> routed to `qwen2.5-coder:7b`, 8k context, read `src/player.py` + `src/main.py`, proposed `max(0, self.health - amount)` as a full `file:` block; preview 1+/1-, no warnings; apply -> game prints 0; undo restored the original.
  3. Browser (throwaway server on port 8431): project menu lists/attaches the project; Review change opens the diff (fixed double line spacing); Apply wrote the file + backup; Undo in the toast restored it.

---

## 2026-11-16 - Task 28: Screen Help (ADR-013)

* **Goal**: Let Loki look at the user's screen on request (user approved a vision model download).
* **Download**: `qwen3-vl:8b` via Ollama `/api/pull` (5.77 GiB) into `D:\OllamaModels` (D: had 210 GB free); capabilities `completion, vision, tools, thinking`.
* **Files**: `app/screen.py` (new); `app/main.py` (capture endpoint, screenshot routing, latest-image-only, ledger entry); `app/ollama_service.py` (forward `images`; `think` None/True/False); `app/config.py` (strip images when saving chats); `app/model_router.py` (`vision` route); `static/*` (monitor button with 3-2-1 countdown, attachment card with remove, image in user bubble, "Screenshot (not saved)" note, Qwen3-VL in the model menu); cache-bust `styles.css?v=29`, `app.js?v=30`.
* **Checks**:
  1. `screen.capture(0)` -> 1920x1080 primary monitor -> 1280x720 JPEG, 94 KB (not viewed, not saved).
  2. Saved-chat strip: image bytes absent from `conversations.json`, `had_screenshot: true`.
  3. Live (temporary server, synthetic error-dialog image, no real screen content): routed to `qwen3-vl:8b`; answer identified Windows Update error 0x80070005 "Access is denied" with Windows fixes; 58 s (43-49 s on reruns); 5.07 of 5.9 GiB on GPU. Tried `think: false` to speed it up: Ollama ignores it for this model (verified directly: 558 reasoning chars with false) - reverted to streaming reasoning.
  4. Browser (synthetic image): attachment card, image in bubble, "Auto - Screen" pill, Reasoning section, saved-screenshot note render; no real capture done in the UI test.

---

## 2026-11-16 - Task 29: PC Help - Reviewed PowerShell Commands (ADR-014)

* **Files**: `app/commands.py` (new); `app/main.py` (review/run/log endpoints with same-app checks, ledger entry, `pc` task handling: diagnose-first instruction, no implicit web); `app/model_router.py` (`pc` route -> qwen2.5:7b, Windows-trouble classifier, command-output follow-ups); `app/ollama_service.py` (system prompt: propose runnable read-only commands first, admin guidance, never disable security or run downloaded scripts; `think` None/True/False); `static/*` (Run button on PowerShell blocks, `#cmd-dialog`, risk badges, output view, "Ask Loki about this output"); cache-bust `styles.css?v=30`, `app.js?v=33`.
* **Checks**:
  1. Risk classifier: 43 sample commands (12 read, 9 change, 6 admin, 16 blocked) all rated as expected. Runner: output + exit code, HMAC token bound to exact command (reuse for another command refused), blocked refused even with a valid-looking token, readable errors (first run lost them inside PowerShell CLIXML; fixed by merging errors as text), UTF-8 output, native exit code 3 passed through, 2 s test timeout honoured, table formatting kept.
  2. Live API (temporary server): no header / evil Origin / cross-site / unreviewed / blocked -> all 403. Model comparison on troubleshooting prompts -> `pc` route uses qwen2.5:7b; "internet feels slow" then gave 4 read-only checks; `Get-NetIPConfiguration` ran (exit 0).
  3. Browser (throwaway server): Run dialog for read/change/admin/blocked samples shows the right badge and buttons; read-only ping ran and showed output; "Ask Loki about this output" sent the follow-up and Loki correctly read 2 ms pings as a healthy connection. Fixed: duplicate read-only wording, lower-case reasons, follow-up routed to the coder model (now `pc`).
  4. Environment issue found while testing: another desktop app was flooding a local DNS resolver, leaving ~21,000 TIME_WAIT sockets and exhausting Windows' ephemeral ports (WinError 10048 for every new connection). Closing that app fixed it; sockets drained in ~110 s.

---

## 2026-11-16 - Task 30: Clearer Model Menu Sections

* **Goal**: User found it hard to tell which section of the model menu a model belonged to (section headings looked like model names).
* **Changes**: `static/app.js` / `styles.css` - section headings now have a divider line, small all-caps coloured titles with a dot (green "Fast on this PC", amber "May be slower", red "Slow on this PC"); every model shows a matching coloured dot; Auto footer mentions PC help and screenshots. Cache-bust `styles.css?v=31`, `app.js?v=34`.
* **Check**: browser - three headings rendered with distinct colours and dividers; model dots match their section.

---

## 2026-11-16 - Task 31: "Why can't it build a website?" - Build and Preview (ADR-015)

* **Problem** (user screenshot): "can you create a small website to demo ur skillset" -> Gemma 2 replied it can't create websites and gave a bare Hello World; every code line had its own dark box.
* **Causes / fixes**: (1) request not recognised as coding -> build words (website, landing page, browser game, ...) now a strong code signal (first attempt failed: a Python edit turned `\b` into a hidden backspace again; fixed and scanned); (2) model not told it can build -> system prompt instructs one self-contained HTML file and never claiming inability; (3) global `code {}` pill style applied inside `<pre>` -> reset for `pre code`; (4) new Preview/Download on HTML blocks, `/api/preview` + `/preview/{id}`.
* **Preview debugging**: Preview first showed a blank frame. `frame-ancestors 'self'` can never match a sandboxed document (changed to explicit localhost origins), still blank; a side-by-side test page showed frames render without the iframe `sandbox` attribute and stay blank with it. Isolation probe without the attribute: origin null; parent DOM, cookies, localStorage, Loki API and internet all blocked -> attribute removed, header-only sandbox kept. Debug page deleted.
* **Checks**: routing (website / snake browser game / pong game -> code; "what game should I play tonight" -> general; existing router and web-decider tests pass); live: exact user prompt -> `qwen2.5-coder:7b`, self-contained page with `<style>` and `<script>`, no external refs; preview served with the restrictive CSP, `/api/preview` without header -> 403; Loki UI: Preview renders the generated site; `tests/run_tests.py` (see commit).
* **Follow-up ("why no css or styling?")**: the user's saved answer was Gemma 2's pre-fix reply, which contained no CSS at all. Added: (a) Preview/Download now assemble the page from the HTML block plus `css` / `javascript` blocks in the same reply (local `<link rel=stylesheet>` / `<script src>` replaced by inline content; external URLs left alone) - verified with a split three-block reply (styles applied, separate script ran); (b) system prompt asks for a polished design (CSS-variable palette, system fonts, spacing, centred max-width flex/grid layout, rounded cards with shadows, hover/focus states, responsive, real content). Fresh request: Qwen 2.5 Coder produced a CSS-variable themed, card-based, responsive page with no external references; still modest in ambition, which is the 7B model's limit. Cache-bust `app.js?v=37`.

---

## 2026-11-16 - Task 32: Coding agent (ADR-016)

* **Request**: "Right now it just gives me code, but I want it to be like a coding agent that can do more than just generate code." Choices: smart auto approvals; new projects in `D:\LokiProjects`.
* **Built**: `app/agent.py` (agent loop, six tools, smart-auto command policy, approvals, undo all, project preview, page check); chat routing + 5 endpoints in `app/main.py`; `commands.py` runs with closed stdin and kills the process tree on timeout; UI: Agent switch, live step list with diffs/output, Run it / Skip approvals, Preview / Open folder / Undo all, elapsed timer; `tests/verify_m9.py` (model-free checks) and `LOKI_PROJECTS_DIR` in the test runner.
* **Measured and fixed along the way**:
  1. The coder model wrote a plan with commands instead of calling tools -> agent-only system prompt.
  2. It saved a file whose body was `<10 lines saved>`, copying the marker used to shorten history -> full history, trimmed only when the context fills; marker bodies refused.
  3. Follow-up claimed "done" with no tool calls; after a failing test it described the fix instead of applying it -> nudges.
  4. Ran the failing tests 24 times without editing -> repeat detection, project code given up front, failure hints.
  5. qwen2.5:7b rewrote an 11-line file as 2 lines -> rewrites that delete most of a file are refused; `replace_in_file` tolerates indentation.
  6. A model-written `serve.py` web server hung a run past the 60 s limit (killing PowerShell left the child holding the pipes) -> tree kill + closed stdin (verified: 5 s limit returns in 5.5 s, `input()` fails at once, nothing left running).
  7. Websites had "Card 1 Title" placeholders and missing images -> page check before finishing.
  8. A live UI run ended with the model's confident-but-wrong closing text -> Loki reports a failed final check itself.
* **Benchmark** (5 tasks x 2 rounds, isolated servers): qwen2.5:7b 8/10 (both misses: the website size/section metric; pages had real content after the page check), qwen2.5-coder:7b 3/10 -> qwen2.5:7b is the agent model.
* **Checks**: `verify_m9` (70+ model-free checks: routing, command policy, parsing, file guards, undo, preview inlining, 403s); live API runs (new project + tests, follow-up, bug fix with tests passing, install waits for approval and Skip is honoured, Undo all restores originals); browser: live run in the Loki UI (3 steps, 12 s, tests pass), approval card, Preview of a project page, Undo all; `tests/run_tests.py` (see commit).

---

## 2026-11-16 - Task 33: "Generate a cool website" failed (ADR-016 addendum)

* **Problem** (user screenshot): the agent listed the empty folder, worked for 1m 49s and answered "I could not finish this task."
* **Cause** (found by logging raw replies): the model put the whole page in a `write_file` tool call; the HTML's quotes and newlines broke Ollama's tool-call parser, which returned an empty message (5 x ~1,200 tokens lost). In a second run the same thing dropped index.html and left a one-line script.js.
* **Fixes**: files are written as ```` ```file:path ```` blocks (no escaping), `write_file` no longer offered; lost-reply detection with a specific nudge; a clear message when nothing could be saved; Loki's designed web starter for new websites (pages went from plain white to a styled dark/light design with the model writing only content; per-project colour schemes); website summaries no longer tell the user to run pytest; blocks named after tools ignored; identical rewrites count as loops; a failing check is only cleared by the same command passing (the model "verified" a fix with `python test_calc.py`, which runs nothing); "fix the code, not the tests"; pytest exit 5 ("no tests ran") is not a failure; raw replies logged in `data/agent_runs/`.
* **Checks**: the exact request 3x before the starter (all produced a page) and 3x + a coffee-shop landing page after it (styled, specific content, different palettes, 17-35 s); benchmark 9/10 over 2 rounds (one bug-fix round failed and was reported as failed); `verify_m9` extended (file blocks, offered tools, starter, palettes, placeholder words); `verify_m9` passes. The full `tests/run_tests.py` run timed out in 8 model suites because the benchmarks had overloaded the PC (RAM near full; the user reported lag and crashes), so it says nothing about the code and must be re-run when the PC is idle.

---

## 2026-11-16 - Task 34: Gentle test runner

* **Problem**: a full-speed test run right after the agent benchmarks made the user's PC lag and crash (RAM near full with Chrome, Discord, Steam and Medal open). "Why can't it be like slowly and not flood the resource?"
* **Change**: `tests/run_tests.py` is gentle by default: waits for >= 4 GB free RAM and >= 5 GB free GPU memory before each AI suite (prints why it is waiting; never unloads models while waiting, since they may be the user's own chat), unloads models and pauses 8 s after each AI suite, runs the server and suites at below-normal priority, and sets `LOKI_OLLAMA_THREADS` (CPU threads / 4) and `LOKI_OLLAMA_KEEP_ALIVE=30s` for the isolated server (`ollama_service.apply_gentle`, a no-op in normal use). `--fast` keeps the old behaviour; Ctrl+C stops cleanly. A run that stops early now returns failure.
* **Checks**: memory readings (4.0 GB RAM / 6.7 GB VRAM free at the time), the wait loop holds while the PC is "busy" (forced threshold), `apply_gentle` adds `num_thread` / `keep_alive` only when set, `run_tests.py m9` passes. Full gentle run afterwards (user's go-ahead): it first waited while only 2.5-3.0 GB RAM was free, started once memory was freed, then **9/9 suites passed** (about 6 minutes of suites), real data untouched, no model left loaded. This also covers the Task 33 changes whose earlier full run had timed out under load.

---

## 2026-11-16 - Task 35: Image Paste (`Ctrl+V`), Drag-and-Drop & File Attachment in Chat

* **Goal**: Fix the inability to paste (`Ctrl+V`), drag-and-drop, or attach images directly in the Chat composer.
* **Files Changed**:
  * `app/screen.py` - Added `_encode_pil_image` (with RGBA transparency compositing onto white and max-1280px proportional scaling) and `grab_clipboard()` (`PIL.ImageGrab.grabclipboard()` supporting both clipboard bitmaps and copied image files from Windows File Explorer).
  * `app/main.py` - Added `POST /api/screen/clipboard` (protected by `_require_same_app`).
  * `static/index.html` - Added `#btn-attach-image` + hidden `#input-attach-image` file picker in `.composer-buttons`, `#screen-attachment-title` inside `#screen-attachment`, updated `#chat-input` placeholder, and bumped cache-busting to `styles.css?v=34` and `app.js?v=39`.
  * `static/app.js` - Added `attachImageBlob()` (client-side `<canvas>` resize to max 1280px JPEG), capture-phase `paste` listener on `document` (reading `e.clipboardData.items` / `e.clipboardData.files` first and falling back to `POST /api/screen/clipboard` when copying an image file in Windows Explorer), `dragenter`/`dragover`/`dragleave`/`drop` handlers on `#tab-chat`, and `#btn-attach-image` click handler.
  * `static/styles.css` - Added `.chat-composer.drag-over` highlight and `#btn-attach-image:disabled`.
* **Checks**:
  1. Restarted Uvicorn server on `127.0.0.1:8420` (also activating Task 33's `agent.py` changes).
  2. Verified `GET /` serves `btn-attach-image` and `app.js?v=39`.
  3. Verified `POST /api/screen/clipboard` with `X-Loki-Request: 1` returns `{"ok":false,"has_image":false}` when clipboard has no image, and verified `_encode_pil_image` scales a `2000x1000` RGBA image to `1280x640` JPEG (`5,087 B`).

---

## 2026-11-17 - Task 36: AI Intelligence & Quality Refinements (2-Pass Self-Refine, Model Escalation, Auto-Memory/Docs & Agent Starter Fix)

* **Goal**: Make Loki's responses and coding agent noticeably smarter on the 8 GB RTX 5050 without extra VRAM overhead.
* **Files Changed**:
  * `app/ollama_service.py` - Added two-pass `refine: bool = False` support in `stream_chat` (Pass 1 drafts inside the collapsible `thinking` drawer; Pass 2 critiques the draft for bugs/edge cases/placeholders and streams the refined answer), tuned sampling (`repeat_penalty=1.07`, `top_p=0.92`), and expanded `SYSTEM_PROMPT` with a depth/edge-case/no-placeholder rubric.
  * `app/main.py` - Added `refine: bool = False` on `ChatRequest`, automatic `8192` context promotion for `code` and `reasoning` routes when the chosen model fits 8 GB VRAM at 8k, conversational Auto-Memory (`"Remember that ..."` / `"Save to memory ..."`), and Auto-Document Recall (injecting top indexed chunks when `score >= 0.34` in normal chat).
  * `app/agent.py` - Fixed empty attached project folders (`folder_empty = not any(project_store.iter_files(root))`) so retrying a website build in an already-attached empty folder still seeds `app/web_starter/`, expanded `_PLACEHOLDER_TEXT` to catch generic `"details about ..."`, `"More about me and my journey"`, and `"Welcome to Cool Website"` filler, and added `repeat_penalty=1.07`, `top_p=0.92` to `_call_model`.
  * `static/index.html`, `static/app.js`, `static/styles.css` - Added the **Refine** composer chip (`#chk-refine`), added per-reply **Refine (2-pass)** and **Try model…** (`select-retry-model`, including `14B Max IQ` models) controls in `.msg-footer`, extracted `streamIntoAssistantMsg()` and `retryAssistantTurn()`, and bumped cache-busting to `styles.css?v=35` and `app.js?v=40`.
* **Checks**:
  1. `python -m py_compile app/main.py app/ollama_service.py app/agent.py app/screen.py` -> OK.
  2. Restarted Uvicorn server on `127.0.0.1:8420`.
  3. Ran `python tests/run_tests.py m9` -> `PASS m9 (1s)`, real `data/` untouched.

---

## 2026-11-17 - Task 37: Fix Desktop Launcher Port-8420 Race Condition (`WinError 10048`)

* **Problem** (user screenshot): Clicking the Desktop `Loki` shortcut showed `"Loki server failed to start. See D:\Loki\desktop\server.log.err"`, and `server.log.err` contained `ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8420)`.
* **Cause**: When an existing `python.exe -m uvicorn` process on port 8420 was slow to respond (or still importing `scikit-learn`/`pandas` from `D:` on a second click), `Test-Url` timed out after 2 s and `desktop/Loki.ps1` spawned a second `uvicorn` process that immediately exited with `WinError 10048`, triggering `Show-Error`.
* **Fix** (`desktop/Loki.ps1`):
  1. Increased `Test-Url` timeout and added a 12-second wait if an existing `uvicorn.*8420` process is already starting up.
  2. If an existing `uvicorn.*8420` process remains unresponsive after waiting, stop it before binding port `8420`.
  3. If `$server.HasExited` triggers because another instance bound port `8420` first, re-check `Test-Url` before failing.
  4. Explicitly set `$env:OLLAMA_MODELS = 'D:\OllamaModels'` when `D:\OllamaModels` exists, clean up any headless `msedge.exe` processes holding `D:\Loki\desktop\profile`, and bring the Edge window to the foreground (`[LokiShell]::BringToFront`).
* **Checks**: Launched `D:\Loki\desktop\Loki.ps1` -> server and Edge app window opened cleanly with HTTP 200.

---

## 2026-11-18 - Task 38: Workstation & Intelligence Upgrade Pass 2 (Code/Text File Drop, Interactive Python Runner, Edit & Resend, Persona Presets & Task-Specific Prompts)

* **Goal**: Make Loki smarter and more practical for day-to-day coding, debugging, and learning without downloading new models or increasing VRAM usage.
* **Files Changed**:
  * `app/ollama_service.py` - Added `TASK_PROMPTS` (`code`, `reasoning`, `pc`), `PERSONA_PROMPTS` (`engineer`, `tutor`, `concise`, `gamedev`), and `"min_p": 0.05` in `stream_chat` to cut low-probability hallucinated tokens on quantized `Q4` models.
  * `app/main.py` - Added `persona: str | None = None` to `ChatRequest`, added `attached_file` handling in `/api/chat/stream` (wrapping file content in `<untrusted_data source="attached_file:...">`, routing code extensions to the `code` specialist `qwen2.5-coder:7b` with `8192` context when it fits VRAM, and capping `code` task temperature to `<= 0.2`), and injected `TASK_PROMPTS` + `PERSONA_PROMPTS` into `extra_system`.
  * `app/commands.py` - Added `default_py` prelude in `_run_blocking()` so `python`, `python3`, `py`, and `pip` always resolve to `%LOCALAPPDATA%\Python\bin\python.exe` in reviewed command runs.
  * `app/config.py` - Updated `upsert_chat()` to strip `attached_file["content"]` when saving chat history while keeping `name`, `lines`, and `size` metadata.
  * `static/index.html`, `static/app.js`, `static/styles.css` - Added `#file-attachment` preview bar, expanded `#input-attach-image` and `#tab-chat` drag-and-drop to accept code/text/log/CSV files (`<= 96 KB`), added **Run Python** (`btn-run-python`) on `python` code blocks (routing through the reviewed `#cmd-dialog`), added **Edit** (`btn-edit-user-msg`) on user messages in chat, added the `#select-persona` (`Auto`, `Engineer`, `Tutor`, `Concise`, `Game Dev`) composer chip, and bumped cache-busting to `styles.css?v=36` and `app.js?v=41`.
* **Checks**:
  1. `python -m py_compile app/main.py app/ollama_service.py app/commands.py app/config.py` -> OK.
  2. `commands._run_blocking("python -c @'\nprint(21 * 2)\n'@", ...)` -> `exit_code == 0`, output `42`.
  3. `python tests/run_tests.py m9` -> `PASS m9 (1s)`, real `data/` untouched.
  4. Restarted Uvicorn server on `127.0.0.1:8420` and verified `GET /` serves `select-persona` and `app.js?v=41`.
