# Loki — Architectural & Product Decision Records (ADR)

*Last Updated: 2026-11-15*

Record meaningful architectural, privacy, resource, and workflow design decisions here in chronological order. Do not silently reverse earlier decisions without recording a superseding entry.

---

## ADR-001: Local-First FastAPI + Vanilla Web UI Stack (Zero New Dependencies)
* **Date**: 2026-11-15
* **Context**: The user requested a small, dependable Windows-friendly assistant around Ollama without installing software or downloading models without asking first. Inspection showed Python 3.14.7 (`%LOCALAPPDATA%\Python\bin\python.exe`) already had `fastapi`, `uvicorn`, `httpx`, `pydantic`, `sqlite3`, and `scikit-learn` installed.
* **Chosen Option**: Build the backend in Python with FastAPI/Uvicorn bound strictly to `127.0.0.1:8420`, serving a dependency-free vanilla HTML/CSS/JS frontend with strict `Content-Security-Policy` headers (`connect-src 'self'`).
* **Alternatives Considered**:
  * *Electron / Tauri Desktop Wrapper*: Requires downloading large build toolchains (Rust/C++ build tools or multi-hundred-MB Electron binaries).
  * *Streamlit*: Already installed, but less flexible for fine-grained streaming abort controls, step-by-step workflow inspectors, and custom CSP headers.
* **Consequences**: Zero package installations or downloads required; ~50 MB RAM footprint; instant startup and easy inspection.

---

## ADR-002: Single-Model Foreground Inference Lock & Explicit VRAM Unload for 8 GB GPU
* **Date**: 2026-11-15
* **Context**: Hardware verification confirmed 15.23 GB usable system RAM and an NVIDIA GeForce RTX 5050 Laptop GPU with 8,151 MiB (~8 GB) VRAM. The installed `llama3:latest` model (4.34 GB on disk) consumes ~4,530 MiB of VRAM when loaded with a 2,048–4,096 context window.
* **Chosen Option**:
  1. Default context window (`num_ctx`) to `4096` tokens (configurable between `2048`, `4096`, and `8192`).
  2. Enforce a process-wide `asyncio.Lock` (`OllamaService.inference_lock`) so chat and workflow AI steps never run concurrently.
  3. Provide a one-click **Unload Model (Free VRAM)** button that calls `POST /api/generate` with `keep_alive: 0` to immediately evict model weights from GPU VRAM.
* **Alternatives Considered**:
  * *Running separate chat and embedding models concurrently in VRAM*: Would risk exceeding 8 GB VRAM and spilling onto system RAM / CPU, severely degrading latency.
* **Consequences**: Predictable VRAM usage (~4.5–5.5 GB during inference, 0 MB when unloaded) and no background inference lag while chatting.

---

## ADR-003: CPU-Based Hybrid Local Search (SQLite FTS5 + TF-IDF) for Document Q&A
* **Date**: 2026-11-15
* **Context**: Only `llama3:latest` is currently downloaded in Ollama; no dedicated embedding model (e.g., `nomic-embed-text`) is installed, and downloading models requires explicit permission and uses extra disk/VRAM.
* **Chosen Option**: Implement local document search using Python's built-in `sqlite3` (FTS5 keyword search) combined with `scikit-learn` `TfidfVectorizer` cosine similarity on CPU.
* **Alternatives Considered**:
  * *Downloading an Ollama embedding model*: Would require user download approval and model switching or extra VRAM/RAM overhead. (Can still be added as an optional upgrade later.)
* **Consequences**: 100% offline local indexing with zero downloads, zero GPU VRAM usage, fast exact keyword + lexical similarity matching, and deterministic file/line citations.

---

## ADR-004: Three-Switch Cloud Provider Gate (Off by Default)
* **Date**: 2026-11-15
* **Context**: Loki must support connecting to cloud AI providers (ChatGPT, Claude, Gemini) in the future, but cloud use must be off by default and visibly opt-in per provider and per request.
* **Chosen Option**: Enforce a three-level check in `app/ollama_service.py` before any non-local provider call can proceed:
  1. Global setting `cloud_global_opt_in` must be `True`.
  2. Provider-specific setting `cloud_providers[provider]["enabled"]` must be `True`.
  3. The individual API request must explicitly pass `cloud_request_opt_in=True`.
* **Alternatives Considered**:
  * *Single global toggle or automatic fallback to cloud when local model is slow*: Rejected because it violates strict per-provider and per-request opt-in.
* **Consequences**: Accidental data egress to cloud APIs is impossible by default.

---

## ADR-005: Inspectable Step-Based Workflow Engine with Deterministic/AI Separation
* **Date**: 2026-11-15
* **Context**: The continuation prompt expands Loki into a personal assistant and automation platform where jobs are turned into reusable, inspectable workflows with clear steps, run history, cancellation, and approval gates before writes.
* **Chosen Option**:
  1. Build a modular workflow engine (`app/workflows.py`) where each workflow declares its trigger (`manual` first), inputs, allowed folders/services, ordered steps (`deterministic` vs. `ai_reasoning` vs. `approval_gate`), expected outputs, and approval points before execution.
  2. Persist every workflow run and step transition (`pending`, `running`, `completed`, `failed`, `cancelled`, `awaiting_approval`) in `data/workflow_runs.json`.
  3. Start with manually triggered, read-only workflows in Stage 2 (`pc_health_audit`), then add preview-and-approval gates for new-copy file outputs in Stage 4, and defer scheduled/watched background runs until manual execution, permissions, and cancellation are proven.
* **Alternatives Considered**:
  * *Autonomous free-form agent loops (ReAct tool calling without fixed workflow steps)*: Harder to inspect before execution, harder to bound permissions, and more prone to prompt injection from untrusted files/logs.
* **Consequences**: Every automation run is predictable, auditable, cancellable, and safe against untrusted file/log content.

---

## ADR-006: Built-In Windows `System.Speech` for Offline Push-to-Talk Voice & Local TTS
* **Date**: 2026-11-15
* **Context**: The user requested a voice interface only if it can be implemented locally, clearly showing when the microphone is active, and never recording continuously or uploading audio—without downloading models or installing packages without asking first.
* **Chosen Option**: Use built-in Windows `.NET System.Speech` (`System.Speech.Recognition.SpeechRecognitionEngine` with `MS-1033-80-DESK` for bounded push-to-talk capture and `System.Speech.Synthesis.SpeechSynthesizer` with `Microsoft Zira Desktop` / `Microsoft David Desktop` for local TTS), accompanied by a prominent red `#mic-active-banner` and Stop Recording button.
* **Alternatives Considered**:
  * *Browser `webkitSpeechRecognition`*: Sends audio to cloud speech servers in Chromium-based browsers, violating the local-only / no-upload requirement.
  * *Local Whisper / Piper models*: Would require downloading new model weights and installing audio dependencies (`faster-whisper`, `pyaudio`), plus extra RAM/VRAM usage.
* **Consequences**: 100% offline speech recognition and TTS with zero downloads, 0 MB GPU VRAM overhead, and strict single-utterance push-to-talk capture.

---

## ADR-007: Explicit User-Controlled Memory Store (`data/memories.json`)
* **Date**: 2026-11-15
* **Context**: Loki should let the user choose what it remembers and show/remove stored memories at any time.
* **Chosen Option**: Implement `app/memory.py` (`MemoryStore`) where memories (`personal`, `project`, `preference`, `workflow`) are explicitly added, toggled (`enabled`), or deleted by the user in `data/memories.json`, and visibly attributed (`memories_used`) whenever injected into local Ollama chat.
* **Alternatives Considered**:
  * *Silent background LLM extraction of user facts*: Runs extra background inference on the 8 GB GPU and risks storing inaccurate or unwanted personal details without explicit user consent.
* **Consequences**: Complete user control and transparency over every stored memory, with zero background GPU load.

---

## ADR-008: Desktop App via Edge App-Mode Window + PowerShell Launcher (Zero New Dependencies)
* **Date**: 2026-11-15
* **Context**: The user asked for a native-feeling desktop app. ADR-001 forbids new dependencies without asking, and Loki must stay localhost-only.
* **Chosen Option**: `desktop/Loki.ps1` starts Ollama and a hidden Uvicorn server (only if not already running), opens `msedge.exe --app=http://127.0.0.1:8420` with a dedicated `--user-data-dir` (`desktop/profile`), waits for the window to close, then calls `POST /api/ollama/unload` and stops only the server it started. `desktop/Install_Shortcuts.ps1` creates Desktop + Start Menu shortcuts with `desktop/loki.ico` (generated by `desktop/make_icon.py` from the UI brand mark; also served as `static/loki.png` favicon). Falls back to Chrome, then the default browser.
* **Alternatives Considered**:
  * *pywebview / Tauri / Electron*: True native shell, but require new packages or toolchains (and Electron adds ~150 MB RAM).
  * *PyInstaller .exe*: New dependency; still needs Ollama and the same browser engine for the UI.
* **Consequences**: Own window, taskbar icon, and clean start/stop lifecycle with no installs; UI code unchanged. Depends on Edge being present (default on Windows 11). Because Edge app windows otherwise group under Edge's taskbar identity, the launcher assigns AppUserModelID `Loki.LocalAI` to the window (via `SHGetPropertyStoreForWindow`) matching the shortcuts, so the taskbar shows Loki's icon and name.

---

## ADR-009: VRAM-Aware Model Ratings and Default Selection
* **Date**: 2026-11-16
* **Context**: When the saved model was missing, `/api/status` selected Ollama's *first* listed model, which on this PC is `qwen2.5:14b` (8.37 GiB) - larger than the 8 GB RTX 5050, so it runs partly on CPU and is slow. The picker gave no hint which models fit.
* **Chosen Option**: `app/model_fit.py` rates each model from its size plus a context-dependent overhead (`1 GiB + 1 GiB per 4k context`, calibrated on `gemma2:9b` loading ~6.6 GiB at 4k): `fits`, `tight` (weights fit but context will likely spill), `offload` (too big). Fallback order: `gemma2:9b` if it fits, else the largest fitting model, else the smallest installed model. The picker groups models by rating, warns when a tight/too-big model is chosen, and the Hardware & Health table tags each model.
* **Alternatives Considered**:
  * *Query Ollama for exact memory needs*: Ollama only reports memory for loaded models; loading each model to measure would stress the GPU.
  * *Hide too-big models*: They still work (slowly) and the user may want them.
* **Consequences**: Sensible default on a fresh/broken config; users still choose any model, with a clear warning. Ratings are estimates (KV cache size varies by architecture) and assume nothing else is using the GPU.

---

## ADR-010: Per-Task Local Model Routing (Heuristic Classifier)
* **Date**: 2026-11-16
* **Context**: Eight local models are installed; specialists (`qwen2.5-coder:7b`, `deepseek-r1:8b`) answer code and reasoning questions better than the general default, but users should not have to switch manually.
* **Chosen Option**: `app/model_router.py` classifies the latest user message with deterministic keyword/shape heuristics (code words and code-like syntax; strong/weak reasoning words and arithmetic) into `code` / `reasoning` / `general`; vague short follow-ups inherit the route of the previous two user messages. `/api/chat/stream` routes to the specialist only if it is installed and rated `fits` (ADR-009), emits a `route` NDJSON event first, and enables Ollama `think` for models whose capabilities include `thinking`, streaming it as `thinking` events. Setting `auto_model_routing` (default on) / per-request `auto_route` disables routing.
* **Alternatives Considered**:
  * *LLM-based classifier*: More accurate on edge cases but adds a model call per message, needs the single inference lock, and may force an extra model load on the 8 GB GPU.
  * *Always use one model*: Simpler, but leaves the installed specialists unused.
* **Consequences**: Zero extra inference for routing; each switch costs a cold model load (~20-30 s measured on first use). Misclassification falls back to sensible models and is visible via the reply pill; users can turn Auto off.

---

## ADR-011: Automatic Web Search and Link Reading (Server-Side, DuckDuckGo)
* **Date**: 2026-11-16
* **Context**: The user asked for internet access so Loki can help with current information and pasted links, chose DuckDuckGo without an API key, and chose "automatically, always allowed" over a per-chat toggle. This changes the original local-only boundary (ADR-001/004).
* **Chosen Option**: The FastAPI server (not the browser; CSP stays `connect-src 'self'`) performs web access via `app/web_tools.py`: DuckDuckGo HTML search, page fetch with BeautifulSoup/lxml text extraction, top 3 pages read concurrently. `app/web_decider.py` decides per message with heuristics (links -> read; explicit requests, time-sensitive words, who/when/where + proper noun -> search; code/maths/creative/chat -> offline). Results are placed in the latest user turn inside `<untrusted_data source="web">` (small models ground far better there than in the system prompt), answers cite [n], and a `sources` NDJSON event drives the UI list. With Auto model on, web-backed general questions route to `qwen2.5:7b` (task `web`). Setting `web_access` (default on, Privacy page switch); `LOKI_WEB_ACCESS=0` forces it off (the isolated test runner sets this).
* **Safety**: only public http(s) on ports 80/443; loopback/private/link-local/reserved addresses refused after DNS resolution and on every redirect; no credentials in URLs; GET only, no cookies, generic User-Agent; 1.5 MB / 10 s caps; page chrome filtered; every lookup recorded in the Activity Ledger (`web_search` / `web_read`, counted separately from cloud AI calls). Known residual risk: DNS rebinding between the check and the request.
* **Alternatives Considered**: Brave Search API (needs a key), Wikipedia only (too narrow), self-hosted SearXNG (Docker install), LLM tool-calling (gemma2/llama3 lack tool support; extra inference on the 8 GB GPU).
* **Measured**: same sources, "latest Ollama version": `gemma2:9b` repeated an outdated third-party figure (v0.40.5) even with stricter instructions; `qwen2.5:7b` answered v0.40.17 citing GitHub releases.
* **Consequences**: Search text and pasted links leave the PC; everything else stays local. DuckDuckGo's HTML page may change or rate-limit; failures fall back to answering offline with a visible status message.

---

## ADR-012: Coding in Project Folders - Loki Proposes, the User Approves
* **Date**: 2026-11-16
* **Context**: The user wants Loki to work with their PC and help with code, and chose "Loki proposes, I approve" (over read-only or full autonomy) and "coding in project folders" first.
* **Chosen Option**: `app/projects.py` + `/api/projects*`. Project folders are an explicit allowlist in settings. Chat with a project attached gets a PROJECT CONTEXT block (file list + top 3 relevant files by name/keyword score, ~9k chars) in the latest user turn and edit instructions: full new file content in ```file:<relative path>``` blocks (full-file rewrites are more reliable for 7B models than diff formats). The UI turns those into **Review change** -> diff (with truncation / "rest unchanged" placeholder warnings) -> Apply (base SHA check against stale reviews; backup under `data/backups/<change-id>/`; audit log `data/project_changes.json`; CRLF preserved) -> Undo (refused if the file changed after Loki's write). Project chats route to `qwen2.5-coder:7b` and use an 8k context when it still fits the GPU; implicit web search is skipped unless explicitly requested.
* **Path safety**: relative paths only, resolved inside the project (no `..`, absolute, `~` or drive paths), no writes into dependency/build/VCS folders, secret files (`.env`, keys, credentials) never read or written; drive roots, `C:\Windows`, `C:\Program Files`, `C:\Users` and Loki's data folder cannot be projects.
* **Alternatives Considered**: unified-diff output from the model (frequent malformed hunks with 7B models); autonomous file writes (rejected by the user's choice and by the risk profile); running commands (deferred to "PC help", same approve-first pattern).
* **Consequences**: Very large files may be truncated by the model; the diff review shows this and warns. Context is limited to a few files per message; mentioning a file name pulls it in.

---

## ADR-013: On-Demand Screen Help with a Local Vision Model
* **Date**: 2026-11-16
* **Context**: The user wants Loki to see their screen. None of the 8 installed models accept images. The user approved downloading a vision model.
* **Chosen Option**: `qwen3-vl:8b` (5.77 GiB, Q4_K_M; capabilities vision/tools/thinking), chosen over `qwen2.5vl:7b` (5.56 GiB) and `gemma3:4b` (3.12 GiB) for stronger on-screen text reading at a size that fits 8 GB. `POST /api/screen/capture` (PIL `ImageGrab`, primary monitor, 0-10 s delay, default 3 s) returns a 1280-px-wide JPEG in memory; the UI attaches it to the next user message (`images`), `/api/chat/stream` routes any message with a screenshot to the vision model (task `vision`, label "Screen"), sends only the latest screenshot, skips implicit web/project context, and `upsert_chat` strips images before saving (`had_screenshot: true`). Captures are recorded in the Activity Ledger as local (`screen_capture`).
* **Alternatives Considered**: continuous screen watching (privacy, GPU load); larger vision models (llama3.2-vision 11B, gemma3 12B: do not fit 8 GB); capturing a chosen window (more UI; the countdown covers the common case).
* **Measured**: synthetic Windows Update dialog -> correctly read "0x80070005 / Access is denied" with Windows-specific fixes in 43-58 s; ~0.8 GiB of the model offloads to CPU. `think: false` is ignored by this model in Ollama 0.40.13 (reasoning still produced), so reasoning is streamed into the collapsed Reasoning section to show progress.
* **Consequences**: Slow but private screen help; the Loki window itself is captured if the user does not switch windows during the countdown.

---

## ADR-014: PC Help - PowerShell Commands Run Only After Review
* **Date**: 2026-11-16
* **Context**: The user wants Loki to help with their PC and chose "Loki proposes, I approve" (ADR-012 pattern) over read-only or full autonomy.
* **Chosen Option**: `app/commands.py`. Risk rating by pattern: `blocked` (disk formatting/wiping, boot config, shadow-copy deletion, deleting system folders or whole drives, weakening Defender, download-and-execute, encoded commands, creating users/admins, deleting HKLM keys, credential access, machine-wide execution-policy downgrade, shutdown/restart), `admin` (sfc, DISM, chkdsk, network stack reset, service control, HKLM writes), `change` (state-changing verbs, file create/move/delete, installs, network/registry/scheduled-task/power changes, output redirection), else `read`. `POST /api/commands/review` returns the rating and an HMAC token bound to the exact command text (per-process secret); `POST /api/commands/run` refuses blocked/admin and any command without a matching token, runs `powershell.exe -NoProfile -NonInteractive -EncodedCommand` (errors merged as text, cmdlet errors -> exit 1), never elevated, 60 s timeout, 20k-char output cap, cwd = attached project or the user's home; logs to `data/command_log.json` and the Activity Ledger (`pc_command`). Both endpoints require header `X-Loki-Request: 1` and reject non-localhost `Origin` / `Sec-Fetch-Site: cross-site` (CSRF protection for the only endpoint that executes code).
* **Routing**: new task `pc` (Windows thing + trouble word, or a "I ran this command" follow-up) -> `qwen2.5:7b` with a diagnose-first instruction in the latest turn; implicit web search skipped. Measured on "internet feels slow" / "PC slow since this morning": qwen2.5:7b gave 4 relevant read-only checks; gemma2:9b gave 0-1 (once proposing `netsh ... autotuninglevel=disabled` as a "speed test"); qwen2.5-coder gave none.
* **Alternatives Considered**: autonomous execution (rejected: small models make mistakes, e.g. the netsh suggestion above); elevated execution (no safe way to approve per command); allowlist-only commands (too restrictive for troubleshooting).
* **Consequences**: Pattern-based rating is a guard rail, not a sandbox: the user's review is the real control, which is why every run needs an explicit click and risky ones are labelled.

---

## ADR-015: Build-and-Preview for Generated Web Pages
* **Date**: 2026-11-16
* **Context**: Asked to "create a small website", Loki replied that it could not create websites, routed the request to the general model, and the chat showed every code line boxed. The user asked why it couldn't.
* **Chosen Option**: (1) build requests (website, web page, landing page, web app, browser game, named small games) count as strong coding signals -> `qwen2.5-coder:7b`; (2) system prompt: build ONE self-contained HTML file (inline CSS/JS, no external resources) in a ```html block and never claim inability; (3) HTML code blocks get **Preview** and **Download**; (4) `POST /api/preview` (same-app header, 2 MB cap, last 20 kept in memory) + `GET /preview/{id}` served with `Content-Security-Policy: default-src 'none'; script-src/style-src 'unsafe-inline'; img/font/media data: (blob:); connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors http://127.0.0.1:* http://localhost:*; sandbox allow-scripts allow-modals`.
* **Isolation finding**: `frame-ancestors 'self'` never matches a sandboxed (opaque-origin) document, and an iframe `sandbox` attribute combined with the CSP `sandbox` header made the frame render blank in this browser. The header alone was verified in-frame: origin `null`; parent DOM, cookies, localStorage, Loki API and internet all blocked. So the iframe carries no `sandbox` attribute and isolation comes from the header.
* **Alternatives Considered**: `srcdoc` iframe (inherits Loki's CSP, which blocks the page's inline scripts); opening the page in a new browser window (loses the in-app flow); writing files to disk (needs a project folder; Download covers the no-project case).
* **Consequences**: Generated pages run but are offline-only; pages that rely on CDNs or web fonts will look plainer, which the prompt steers away from.
* **Addendum**: Preview/Download fold sibling `css` / `javascript` blocks from the same reply into the page (replacing local `<link>` / `<script src>`), because models often split a site into several files; the prompt also specifies a concrete visual style so pages are not bare.
