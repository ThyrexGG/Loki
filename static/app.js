/* Loki Frontend Controller — 100% Localhost */

const state = {
  messages: [],
  chatId: null, // id of the open chat; null = new chat not saved yet
  chats: [], // saved chat summaries for the sidebar
  modelFit: {}, // model name -> { fit, label } from /api/status (fits | tight | offload | unknown)
  autoRoute: true, // per-task model routing (code / reasoning / general), mirrors settings.auto_model_routing
  isStreaming: false,
  selectedModel: "llama3:latest",
  numCtx: 4096,
  temperature: 0.3,
  saveHistory: true,
  abortController: null,
  workflowDefs: [],
  workflowRuns: [],
  selectedWorkflowId: "pc_health_audit",
  activeRunId: null,
  wfPollTimer: null,
  docsSummary: null,
  memories: [],
  useMemoriesInChat: true,
  isMicListening: false,
  projects: [], // project folders the user added (ADR-012)
  project: (() => { try { return localStorage.getItem("loki.project") || null; } catch (e) { return null; } })(),
  // Coding agent (ADR-016): on by default, remembered per browser.
  agentMode: (() => { try { return localStorage.getItem("loki.agent") !== "0"; } catch (e) { return true; } })(),
  agentRunId: null,
  refineMode: false,
  persona: "auto",
  pendingFile: null,
};

function showToast(msg, action = null) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  if (action) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toast-action";
    btn.textContent = action.label;
    btn.addEventListener("click", () => { el.classList.add("hidden"); action.onClick(); });
    el.appendChild(btn);
  }
  el.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => el.classList.add("hidden"), action ? 10000 : 3500);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Safe, zero-dependency Markdown renderer (Claude/ChatGPT editorial style).
 * Escapes all HTML first, then formats code blocks, inline code, headings,
 * bold/italic, blockquotes, lists, and [file:Lstart-Lend] citation pills.
 */
function renderMarkdown(rawText) {
  if (!rawText) return "";

  const codeBlocks = [];
  let text = String(rawText).replace(/```([^\n`]*)\n([\s\S]*?)```/g, (_, info, code) => {
    const idx = codeBlocks.length;
    const infoStr = info.trim();
    const fileMatch = infoStr.match(/^file:\s*(.+)$/i);
    const escapedCode = escapeHtml(code.replace(/\n$/, ""));
    if (fileMatch) {
      // A proposed file change: show the path and a Review button (applied only after the user approves a diff).
      const path = fileMatch[1].trim();
      codeBlocks.push(
        `<div class="md-code-block md-file-block" data-path="${escapeHtml(path)}">` +
          `<div class="md-code-header"><span class="md-file-path">${escapeHtml(path)}</span>` +
          `<span class="md-code-actions"><button type="button" class="btn-copy-code">Copy</button>` +
          `<button type="button" class="btn-review-change">Review change</button></span></div>` +
          `<pre><code>${escapedCode}</code></pre>` +
        `</div>`
      );
      return `@@CODEBLOCK_${idx}@@`;
    }
    const cleanLang = escapeHtml(infoStr.split(/\s+/)[0] || "code");
    const langAttr = cleanLang.toLowerCase();
    const runnable = /^(powershell|pwsh|ps1|ps)$/i.test(cleanLang);
    const runnablePy = /^(python|py)$/i.test(cleanLang);
    const previewable = /^(html|htm)$/i.test(cleanLang);
    codeBlocks.push(
      `<div class="md-code-block${(runnable || runnablePy) ? " md-run-block" : ""}" data-lang="${langAttr}">` +
        `<div class="md-code-header"><span>${cleanLang}</span><span class="md-code-actions">` +
        `<button type="button" class="btn-copy-code">Copy</button>` +
        (runnable ? `<button type="button" class="btn-run-command" title="Review this command, then run it on this PC">Run</button>` : "") +
        (runnablePy ? `<button type="button" class="btn-run-python" title="Review and run this Python script on this PC">Run Python</button>` : "") +
        (previewable ? `<button type="button" class="btn-download-html" title="Save this page as an .html file">Download</button>` +
          `<button type="button" class="btn-preview-html" title="Open this page in a safe preview">Preview</button>` : "") +
        `</span></div>` +
        `<pre><code>${escapedCode}</code></pre>` +
      `</div>`
    );
    return `@@CODEBLOCK_${idx}@@`;
  });

  const lines = text.split("\n");
  const out = [];
  let inList = null; // 'ul' | 'ol'

  const closeList = () => {
    if (inList) {
      out.push(`</${inList}>`);
      inList = null;
    }
  };

  const formatInline = (lineStr) => {
    let s = escapeHtml(lineStr);
    // Inline code
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Citation pills like [ARCHITECTURE.md:L12-L34]
    s = s.replace(/\[([a-zA-Z0-9_./-]+:[a-zA-Z0-9_-]+)\]/g, '<span class="cite-pill">$1</span>');
    // Bold & italic
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
    return s;
  };

  for (let rawLine of lines) {
    const trimmed = rawLine.trim();

    if (/^@@CODEBLOCK_\d+@@$/.test(trimmed)) {
      closeList();
      const idx = parseInt(trimmed.replace(/\D/g, ""), 10);
      out.push(codeBlocks[idx] || "");
      continue;
    }

    if (!trimmed) {
      closeList();
      continue;
    }

    // Headings
    const hMatch = trimmed.match(/^(#{1,4})\s+(.*)$/);
    if (hMatch) {
      closeList();
      const level = hMatch[1].length;
      out.push(`<h${level}>${formatInline(hMatch[2])}</h${level}>`);
      continue;
    }

    // Blockquote
    if (trimmed.startsWith("> ")) {
      closeList();
      out.push(`<blockquote>${formatInline(trimmed.slice(2))}</blockquote>`);
      continue;
    }

    // Unordered list
    const ulMatch = trimmed.match(/^[-*]\s+(.*)$/);
    if (ulMatch) {
      if (inList !== "ul") {
        closeList();
        inList = "ul";
        out.push("<ul>");
      }
      out.push(`<li>${formatInline(ulMatch[1])}</li>`);
      continue;
    }

    // Ordered list
    const olMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (olMatch) {
      if (inList !== "ol") {
        closeList();
        inList = "ol";
        out.push("<ol>");
      }
      out.push(`<li>${formatInline(olMatch[1])}</li>`);
      continue;
    }

    closeList();
    out.push(`<p>${formatInline(rawLine)}</p>`);
  }

  closeList();
  let finalHtml = out.join("");
  finalHtml = finalHtml.replace(/@@CODEBLOCK_(\d+)@@/g, (_, i) => codeBlocks[parseInt(i, 10)] || "");
  return `<div class="md-prose">${finalHtml}</div>`;
}

// Event delegation for Copy Code / Review change buttons
document.addEventListener("click", (e) => {
  const previewBtn = e.target.closest(".btn-preview-html");
  if (previewBtn) {
    previewHtml(assemblePage(previewBtn.closest(".md-code-block")));
    return;
  }
  const downloadBtn = e.target.closest(".btn-download-html");
  if (downloadBtn) {
    const html = assemblePage(downloadBtn.closest(".md-code-block"));
    const title = (html.match(/<title>([^<]{1,60})<\/title>/i) || [])[1] || "loki-page";
    const name = title.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "loki-page";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    a.download = `${name}.html`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    showToast(`Saved ${name}.html to your Downloads folder`);
    return;
  }
  const runBtn = e.target.closest(".btn-run-command");
  if (runBtn) {
    const block = runBtn.closest(".md-code-block");
    const turn = runBtn.closest(".msg");
    reviewCommand(block.querySelector("code").textContent, turn ? turn.dataset.project : "");
    return;
  }
  const runPyBtn = e.target.closest(".btn-run-python");
  if (runPyBtn) {
    const block = runPyBtn.closest(".md-code-block");
    const turn = runPyBtn.closest(".msg");
    const pyCode = (block && block.querySelector("code") ? block.querySelector("code").textContent : "").replace(/\r\n/g, "\n");
    const safePy = pyCode.replace(/\n'@/g, "\n' @");
    reviewCommand(`python -c @'\n${safePy}\n'@`, turn ? turn.dataset.project : "");
    return;
  }
  const reviewBtn = e.target.closest(".btn-review-change");
  if (reviewBtn) {
    const block = reviewBtn.closest(".md-file-block");
    const turn = reviewBtn.closest(".msg");
    reviewFileChange(turn ? turn.dataset.project : "", block.dataset.path, block.querySelector("code").textContent);
    return;
  }
  const copyCodeBtn = e.target.closest(".btn-copy-code");
  if (copyCodeBtn) {
    const block = copyCodeBtn.closest(".md-code-block");
    const codeEl = block ? block.querySelector("code") : null;
    if (codeEl) {
      navigator.clipboard.writeText(codeEl.textContent || "");
      copyCodeBtn.textContent = "Copied!";
      setTimeout(() => (copyCodeBtn.textContent = "Copy"), 1800);
    }
  }
});

// Tab switching
document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const tabId = btn.getAttribute("data-tab");
    document.getElementById(`tab-${tabId}`).classList.add("active");
    refreshStatus();
    if (tabId === "analyst") {
      refreshTopProcesses();
      loadWorkflowsAndRuns();
    } else if (tabId === "docs") {
      loadDocsStatus();
    }
  });
});

document.getElementById("sidebar-privacy-pill").addEventListener("click", () => {
  document.querySelector('.nav-btn[data-tab="privacy"]').click();
});

// Quick prompts
document.querySelectorAll(".quick-prompt-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const prompt = btn.getAttribute("data-prompt");
    const input = document.getElementById("chat-input");
    input.value = prompt;
    autoResizeChatInput();
    input.focus();
  });
});

async function saveSettings(partial) {
  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(partial),
    });
  } catch (e) {
    console.error("Failed to save settings:", e);
  }
}

// ==========================================
// PROJECTS: attach a folder, review and apply proposed changes (ADR-012)
// ==========================================
const projectMenu = document.getElementById("project-menu");
const projectBtn = document.getElementById("btn-project");

function diffToHtml(diff) {
  return (diff || "").split("\n")
    .filter((l) => !l.startsWith("---") && !l.startsWith("+++"))
    .map((l) => {
      const cls = l.startsWith("+") ? "d-add" : l.startsWith("-") ? "d-del" : l.startsWith("@@") ? "d-hunk" : "d-ctx";
      return `<span class="${cls}">${escapeHtml(l || " ")}</span>`;
    }).join("");  // each line is already a block element
}

function setProject(path) {
  state.project = path || null;
  try { path ? localStorage.setItem("loki.project", path) : localStorage.removeItem("loki.project"); } catch (e) { /* ignore */ }
  renderProjectChip();
}

function renderProjectChip() {
  const p = state.projects.find((x) => x.path === state.project);
  if (state.project && !p && state.projects.length) state.project = null;
  document.getElementById("project-chip-label").textContent = p ? p.name : "No project";
  projectBtn.classList.toggle("active", Boolean(p));
  projectBtn.title = p ? `Project: ${p.path}. Loki reads this folder and can propose changes.` : "Attach a project folder so Loki can read your code and propose changes";
}

async function loadProjects() {
  try {
    const data = await (await fetch("/api/projects")).json();
    state.projects = data.projects || [];
  } catch (e) { state.projects = []; }
  renderProjectChip();
}

function closeProjectMenu() {
  projectMenu.classList.add("hidden");
  projectBtn.setAttribute("aria-expanded", "false");
}

function openProjectMenu() {
  projectMenu.innerHTML = "";
  const item = (label, sub, onClick, opts = {}) => {
    const row = document.createElement("div");
    row.className = "pm-row";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "pm-item" + (opts.selected ? " selected" : "");
    b.setAttribute("role", "menuitem");
    b.innerHTML = `<span class="pm-label">${escapeHtml(label)}</span>${sub ? `<span class="pm-sub">${escapeHtml(sub)}</span>` : ""}`;
    b.addEventListener("click", onClick);
    row.appendChild(b);
    if (opts.onRemove) {
      const x = document.createElement("button");
      x.type = "button";
      x.className = "pm-remove";
      x.title = `Remove ${label} from Loki (the folder itself is not touched)`;
      x.setAttribute("aria-label", x.title);
      x.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><line x1="6" y1="6" x2="18" y2="18"></line><line x1="18" y1="6" x2="6" y2="18"></line></svg>';
      x.addEventListener("click", opts.onRemove);
      row.appendChild(x);
    }
    projectMenu.appendChild(row);
  };
  item("No project", "Normal chat", () => { setProject(null); closeProjectMenu(); }, { selected: !state.project });
  for (const p of state.projects) {
    item(p.name, p.path, () => { setProject(p.path); closeProjectMenu(); showToast(`Project attached: ${p.name}`); },
      { selected: p.path === state.project, onRemove: async (e) => {
        e.stopPropagation();
        await fetch("/api/projects/remove", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: p.path }) });
        if (state.project === p.path) setProject(null);
        await loadProjects();
        openProjectMenu();
      } });
  }
  const add = document.createElement("button");
  add.type = "button";
  add.className = "pm-add";
  add.setAttribute("role", "menuitem");
  add.textContent = "Add a project folder...";
  add.addEventListener("click", async () => {
    closeProjectMenu();
    const path = await promptDialog({
      title: "Add a project folder",
      message: "Loki can read the code in this folder and propose changes. Nothing is changed until you review and apply it.",
      confirmLabel: "Add folder",
      input: { label: "Folder path, e.g. C:\\Users\\you\\Projects\\my-game", value: "", maxLength: 400 },
    });
    if (!path) return;
    const resp = await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
    const data = await resp.json();
    if (!resp.ok) { showToast(data.detail || "Could not add that folder"); return; }
    await loadProjects();
    setProject(data.project.path);
    showToast(`Project attached: ${data.project.name}`);
  });
  projectMenu.appendChild(add);
  projectMenu.classList.remove("hidden");
  projectBtn.setAttribute("aria-expanded", "true");
  (projectMenu.querySelector(".pm-item.selected") || projectMenu.querySelector("button")).focus();
}

projectBtn.addEventListener("click", () => (projectMenu.classList.contains("hidden") ? openProjectMenu() : closeProjectMenu()));
projectMenu.addEventListener("keydown", (e) => {
  const items = [...projectMenu.querySelectorAll(".pm-item, .pm-add")];
  const i = items.indexOf(document.activeElement);
  if (e.key === "ArrowDown") { e.preventDefault(); (items[i + 1] || items[0]).focus(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); (items[i - 1] || items[items.length - 1]).focus(); }
  else if (e.key === "Escape") { closeProjectMenu(); projectBtn.focus(); }
});
document.addEventListener("pointerdown", (e) => {
  if (!projectMenu.classList.contains("hidden") && !e.target.closest(".project-chip-wrap")) closeProjectMenu();
});

const diffDialog = document.getElementById("diff-dialog");

async function reviewFileChange(project, path, content) {
  if (state.isStreaming) { showToast("Wait for the reply to finish before reviewing changes"); return; }
  if (!project) { showToast("This change was not made with a project attached, so Loki doesn't know which folder it belongs to."); return; }
  const resp = await fetch("/api/projects/preview", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project, path, content }),
  });
  const pv = await resp.json();
  if (!resp.ok) { showToast(pv.detail || "Could not review this change"); return; }
  if (pv.unchanged) { showToast(`${path} already matches this version`); return; }

  document.getElementById("diff-title").textContent = pv.is_new ? `Create ${path}` : `Change ${path}`;
  document.getElementById("diff-summary").textContent = pv.is_new
    ? `New file, ${pv.new_lines} lines.`
    : `${pv.added} line${pv.added === 1 ? "" : "s"} added, ${pv.removed} removed. The current version is backed up and you can undo.`;
  const warnEl = document.getElementById("diff-warnings");
  warnEl.innerHTML = pv.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("");
  warnEl.classList.toggle("hidden", !pv.warnings.length);
  const view = document.getElementById("diff-view");
  view.innerHTML = diffToHtml(pv.diff);

  const applyBtn = document.getElementById("diff-apply");
  applyBtn.classList.toggle("app-dialog-danger", pv.warnings.length > 0);
  applyBtn.textContent = pv.warnings.length ? "Apply anyway" : (pv.is_new ? "Create file" : "Apply change");

  const choice = await new Promise((resolve) => {
    const done = (v) => { cleanup(); diffDialog.close(); resolve(v); };
    const onApply = () => done(true);
    const onCancel = () => done(false);
    const onClose = () => { cleanup(); resolve(false); };
    const onBackdrop = (e) => { if (e.target === diffDialog) done(false); };
    const cleanup = () => {
      applyBtn.removeEventListener("click", onApply);
      document.getElementById("diff-cancel").removeEventListener("click", onCancel);
      diffDialog.removeEventListener("close", onClose);
      diffDialog.removeEventListener("click", onBackdrop);
    };
    applyBtn.addEventListener("click", onApply);
    document.getElementById("diff-cancel").addEventListener("click", onCancel);
    diffDialog.addEventListener("close", onClose);
    diffDialog.addEventListener("click", onBackdrop);
    diffDialog.showModal();
    document.getElementById("diff-cancel").focus();
  });
  if (!choice) return;

  const ap = await fetch("/api/projects/apply", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project, path, content, base_sha: pv.base_sha }),
  });
  const res = await ap.json();
  if (!ap.ok) { showToast(res.detail || "Could not apply the change"); return; }
  showToast(`${pv.is_new ? "Created" : "Updated"} ${path}`, { label: "Undo", onClick: async () => {
    const u = await fetch("/api/projects/undo", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ change_id: res.change.id }) });
    const ud = await u.json();
    showToast(u.ok ? `Undid the change to ${path}` : (ud.detail || "Could not undo"));
  } });
}

// ==========================================
// LIVE PREVIEW of generated web pages (ADR-015)
// ==========================================
/**
 * Models often split a site into index.html + styles.css + script.js blocks. Fold the CSS and JavaScript
 * blocks from the same reply into the HTML (replacing local <link>/<script src> references) so Preview and
 * Download show the styled, working page instead of bare HTML.
 */
function assemblePage(htmlBlock) {
  let html = htmlBlock.querySelector("code").textContent;
  const reply = htmlBlock.closest(".msg-body") || htmlBlock.parentElement;
  const blocks = [...reply.querySelectorAll(".md-code-block")].filter((b) => b !== htmlBlock);
  const css = blocks.filter((b) => b.dataset.lang === "css").map((b) => b.querySelector("code").textContent);
  const js = blocks.filter((b) => /^(js|javascript)$/.test(b.dataset.lang || "")).map((b) => b.querySelector("code").textContent);
  const isLocal = (u) => !/^(https?:)?\/\//i.test(u) && !/^data:/i.test(u);
  if (css.length) {
    html = html.replace(/<link\b[^>]*rel=["']?stylesheet["']?[^>]*>/gi, (tag) => {
      const href = (tag.match(/href=["']([^"']+)["']/i) || [])[1] || "";
      return isLocal(href) ? "" : tag;
    });
    const style = `<style>\n${css.join("\n\n")}\n</style>`;
    html = /<\/head>/i.test(html) ? html.replace(/<\/head>/i, `${style}\n</head>`) : style + "\n" + html;
  }
  if (js.length) {
    html = html.replace(/<script\b[^>]*\bsrc=["']([^"']+)["'][^>]*>\s*<\/script>/gi, (tag, src) => (isLocal(src) ? "" : tag));
    const script = `<script>\n${js.join("\n\n")}\n</script>`;
    html = /<\/body>/i.test(html) ? html.replace(/<\/body>(?![\s\S]*<\/body>)/i, `${script}\n</body>`) : html + "\n" + script;
  }
  return html;
}

const previewDialog = document.getElementById("preview-dialog");

async function previewHtml(html) {
  if (state.isStreaming) { showToast("Wait for the reply to finish before previewing"); return; }
  try {
    const data = await lokiPost("/api/preview", { html });
    const frame = document.getElementById("preview-frame");
    frame.src = data.url;
    document.getElementById("preview-title").textContent =
      (html.match(/<title>([^<]{1,80})<\/title>/i) || [])[1] || "Preview";
    previewDialog.showModal();
    document.getElementById("preview-close").focus();
  } catch (e) {
    showToast(`Could not open the preview: ${e.message}`);
  }
}
function showPreviewUrl(url, title = "Preview") {
  document.getElementById("preview-frame").src = url;
  document.getElementById("preview-title").textContent = title;
  previewDialog.showModal();
  document.getElementById("preview-close").focus();
}
document.getElementById("preview-close").addEventListener("click", () => previewDialog.close());
document.getElementById("preview-reload").addEventListener("click", () => {
  const f = document.getElementById("preview-frame");
  f.src = f.src;
});
previewDialog.addEventListener("close", () => { document.getElementById("preview-frame").src = "about:blank"; });

// ==========================================
// PC HELP: review and run PowerShell commands Loki proposed (ADR-014)
// ==========================================
const cmdDialog = document.getElementById("cmd-dialog");
const RISK_TEXT = {
  read: { label: "Read-only", cls: "risk-read", note: "" },
  change: { label: "Changes your PC", cls: "risk-change", note: "This changes something on your PC. Make sure you understand it before running." },
  admin: { label: "Needs administrator", cls: "risk-admin", note: "Loki runs commands as your normal account and cannot do this. If you want to run it, open PowerShell as administrator and paste it there." },
  blocked: { label: "Not allowed", cls: "risk-blocked", note: "Loki will not run this because it could seriously damage your PC or its security. You can copy it and run it yourself only if you are sure." },
};

function cmdButton(label, cls, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `app-dialog-btn ${cls || ""}`;
  b.textContent = label;
  b.addEventListener("click", onClick);
  return b;
}

async function lokiPost(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Loki-Request": "1" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

async function reviewCommand(command, project) {
  if (state.isStreaming) { showToast("Wait for the reply to finish before running commands"); return; }
  command = command.trim();
  let rv;
  try { rv = await lokiPost("/api/commands/review", { command }); }
  catch (e) { showToast(`Could not review the command: ${e.message}`); return; }
  const risk = RISK_TEXT[rv.level] || RISK_TEXT.change;

  document.getElementById("cmd-title").textContent = rv.level === "read" || rv.level === "change" ? "Run this command?" : "Loki can't run this command";
  document.getElementById("cmd-risk").innerHTML =
    `<span class="risk-badge ${risk.cls}">${escapeHtml(risk.label)}</span>` +
    `<ul>${(rv.reasons || []).map((r) => `<li>${escapeHtml(r.charAt(0).toUpperCase() + r.slice(1))}</li>`).join("")}</ul>`;
  document.getElementById("cmd-view").textContent = command;
  document.getElementById("cmd-note").textContent = rv.token
    ? `${risk.note ? risk.note + " " : ""}It runs as you (not administrator), stops after ${rv.timeout_seconds} seconds, and is logged.`
    : risk.note;
  document.getElementById("cmd-output-wrap").classList.add("hidden");

  const actions = document.getElementById("cmd-actions");
  actions.innerHTML = "";
  const close = () => cmdDialog.close();
  actions.append(cmdButton(rv.token ? "Cancel" : "Close", "", close));
  if (!rv.token) {
    actions.append(cmdButton("Copy command", "app-dialog-primary", () => {
      navigator.clipboard.writeText(command);
      showToast("Command copied");
    }));
  } else {
    const runLabel = rv.level === "change" ? "Run anyway" : "Run";
    const runCls = rv.level === "change" ? "app-dialog-primary app-dialog-danger" : "app-dialog-primary";
    const runBtn = cmdButton(runLabel, runCls, async () => {
      runBtn.disabled = true;
      runBtn.textContent = "Running...";
      try {
        const res = await lokiPost("/api/commands/run", { command, token: rv.token, project: project || null });
        showCommandResult(command, res);
      } catch (e) {
        runBtn.disabled = false;
        runBtn.textContent = runLabel;
        showToast(`Could not run the command: ${e.message}`);
      }
    });
    actions.append(runBtn);
  }
  cmdDialog.showModal();
  actions.querySelector("button").focus();
}

function showCommandResult(command, res) {
  const ok = res.exit_code === 0;
  const head = res.timed_out
    ? `Stopped after ${res.duration_s} s (time limit)`
    : `${ok ? "Finished" : "Finished with errors"} in ${res.duration_s} s (exit code ${res.exit_code})`;
  document.getElementById("cmd-output-head").textContent = head;
  document.getElementById("cmd-output-head").className = `cmd-output-head ${ok ? "" : "cmd-failed"}`;
  document.getElementById("cmd-output").textContent = res.output.trim() || "(no output)";
  document.getElementById("cmd-output-wrap").classList.remove("hidden");
  document.getElementById("cmd-title").textContent = "Command finished";
  document.getElementById("cmd-note").textContent = "";
  const actions = document.getElementById("cmd-actions");
  actions.innerHTML = "";
  actions.append(cmdButton("Close", "", () => cmdDialog.close()));
  actions.append(cmdButton("Ask Loki about this output", "app-dialog-primary", () => {
    cmdDialog.close();
    const out = (res.output || "").trim();
    const clipped = out.length > 4000 ? out.slice(0, 4000) + "\n... (output cut)" : out;
    chatInputEl.value =
      `I ran this command:\n\`\`\`powershell\n${command}\n\`\`\`\n` +
      `Result: ${head}.\n\`\`\`text\n${clipped || "(no output)"}\n\`\`\`\n` +
      "What does this tell us, and what should I do next?";
    autoResizeChatInput();
    document.getElementById("chat-form").requestSubmit();
  }));
  actions.lastChild.focus();
}

cmdDialog.addEventListener("click", (e) => { if (e.target === cmdDialog) cmdDialog.close(); });

// ==========================================
// SCREEN & IMAGE HELP: screenshot capture, Ctrl+V paste, drag & drop, and file attach (ADR-013)
// ==========================================
function clearScreenshot() {
  state.pendingScreenshot = null;
  state.pendingImageKind = null;
  document.getElementById("screen-attachment").classList.add("hidden");
  document.getElementById("screen-thumb").removeAttribute("src");
}

function setPendingImage(base64Jpeg, titleText = "Image attached", kind = "image") {
  state.pendingScreenshot = base64Jpeg;
  state.pendingImageKind = kind;
  const titleEl = document.getElementById("screen-attachment-title");
  if (titleEl) titleEl.textContent = titleText;
  document.getElementById("screen-thumb").src = `data:image/jpeg;base64,${base64Jpeg}`;
  document.getElementById("screen-attachment").classList.remove("hidden");
}

function attachImageBlob(fileOrBlob, label = "Image attached") {
  if (state.isStreaming) {
    showToast("Wait for the current reply to finish before attaching an image");
    return;
  }
  if (!fileOrBlob) return;
  const mime = (fileOrBlob.type || "").toLowerCase();
  const name = (fileOrBlob.name || "").toLowerCase();
  const isImage = mime.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(name);
  if (!isImage) {
    showToast("Please paste or attach an image file (PNG, JPG, WebP, GIF, or BMP)");
    return;
  }
  const reader = new FileReader();
  reader.onerror = () => showToast("Could not read that image");
  reader.onload = () => {
    const img = new Image();
    img.onerror = () => showToast("Could not decode that image");
    img.onload = () => {
      const maxDim = 1280;
      let w = img.naturalWidth || img.width || 1;
      let h = img.naturalHeight || img.height || 1;
      if (w > maxDim || h > maxDim) {
        const scale = Math.min(maxDim / w, maxDim / h);
        w = Math.max(1, Math.round(w * scale));
        h = Math.max(1, Math.round(h * scale));
      }
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.86);
      const b64 = (dataUrl.split(",")[1] || "").trim();
      if (!b64) {
        showToast("Could not encode that image");
        return;
      }
      setPendingImage(b64, label, "image");
      showToast(`${label}. Ask your question, or press Send.`);
      if (typeof chatInputEl !== "undefined" && chatInputEl) chatInputEl.focus();
    };
    img.src = String(reader.result || "");
  };
  reader.readAsDataURL(fileOrBlob);
}

function clearPendingFile() {
  state.pendingFile = null;
  const el = document.getElementById("file-attachment");
  if (el) el.classList.add("hidden");
}

function isImageFile(fileOrBlob) {
  if (!fileOrBlob) return false;
  const mime = (fileOrBlob.type || "").toLowerCase();
  const name = (fileOrBlob.name || "").toLowerCase();
  return mime.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(name);
}

function attachTextOrCodeFile(file) {
  if (state.isStreaming) {
    showToast("Wait for the current reply to finish before attaching a file");
    return;
  }
  if (!file) return;
  const maxBytes = 96 * 1024;
  if (file.size > maxBytes) {
    showToast(`File is larger than 96 KB (${Math.round(file.size / 1024)} KB). Attach the project folder instead.`);
    return;
  }
  const reader = new FileReader();
  reader.onerror = () => showToast("Could not read that file");
  reader.onload = () => {
    const content = String(reader.result || "");
    if (content.includes("\u0000")) {
      showToast("That looks like a binary file. Attach a text, code, log, or CSV file, or an image.");
      return;
    }
    const lines = content ? content.replace(/\r\n/g, "\n").split("\n").length : 0;
    state.pendingFile = {
      name: file.name || "attached.txt",
      size: file.size || content.length,
      lines,
      content,
    };
    const titleEl = document.getElementById("file-attachment-title");
    const subEl = document.getElementById("file-attachment-sub");
    if (titleEl) titleEl.textContent = `${state.pendingFile.name} (${lines} line${lines === 1 ? "" : "s"})`;
    if (subEl) subEl.textContent = "Included with your next question (code files route to Qwen 2.5 Coder).";
    const bar = document.getElementById("file-attachment");
    if (bar) bar.classList.remove("hidden");
    showToast(`Attached ${state.pendingFile.name} (${lines} lines). Ask your question, or press Send.`);
    if (typeof chatInputEl !== "undefined" && chatInputEl) chatInputEl.focus();
  };
  reader.readAsText(file);
}

function handleAttachedFile(file) {
  if (!file) return;
  if (isImageFile(file)) {
    attachImageBlob(file, file.name ? `Image attached (${file.name})` : "Image attached");
  } else {
    attachTextOrCodeFile(file);
  }
}

document.getElementById("btn-remove-screenshot").addEventListener("click", clearScreenshot);
const btnRemoveFile = document.getElementById("btn-remove-file");
if (btnRemoveFile) btnRemoveFile.addEventListener("click", clearPendingFile);

const inputAttachImage = document.getElementById("input-attach-image");
const btnAttachImage = document.getElementById("btn-attach-image");
if (btnAttachImage && inputAttachImage) {
  btnAttachImage.addEventListener("click", () => {
    if (state.isStreaming) return;
    inputAttachImage.click();
  });
  inputAttachImage.addEventListener("change", () => {
    const file = inputAttachImage.files && inputAttachImage.files[0];
    if (file) handleAttachedFile(file);
    inputAttachImage.value = "";
  });
}

// Paste image from clipboard anywhere on the Chat screen (Ctrl+V / Win+Shift+S snip / Explorer copied image file)
document.addEventListener("paste", async (e) => {
  const chatTab = document.getElementById("tab-chat");
  if (!chatTab || !chatTab.classList.contains("active")) return;
  if (document.querySelector("dialog[open]")) return;
  const cd = e.clipboardData;
  let imgBlob = null;
  if (cd && cd.items) {
    for (const item of cd.items) {
      if (item.kind === "file" && (item.type || "").toLowerCase().startsWith("image/")) {
        imgBlob = item.getAsFile();
        if (imgBlob) break;
      }
    }
  }
  if (!imgBlob && cd && cd.files && cd.files.length) {
    for (const f of cd.files) {
      if ((f.type || "").toLowerCase().startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(f.name || "")) {
        imgBlob = f;
        break;
      }
    }
  }
  if (imgBlob) {
    e.preventDefault();
    attachImageBlob(imgBlob, "Image pasted from clipboard");
    return;
  }
  // If no plain text was pasted (e.g. user copied an image file in Windows File Explorer), check OS clipboard
  const plainText = cd ? cd.getData("text/plain") : "";
  if (!plainText) {
    try {
      const resp = await fetch("/api/screen/clipboard", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Loki-Request": "1" },
      });
      const data = await resp.json();
      if (resp.ok && data.has_image && data.image_b64) {
        setPendingImage(data.image_b64, data.label || "Image pasted from clipboard", "image");
        showToast(`${data.label || "Image pasted"}. Ask your question, or press Send.`);
        if (typeof chatInputEl !== "undefined" && chatInputEl) chatInputEl.focus();
      }
    } catch (_) {
      // ignore if clipboard has no image
    }
  }
}, true);

// Drag & drop image onto the chat tab / composer
const chatTabDropZone = document.getElementById("tab-chat");
const chatComposerForm = document.getElementById("chat-form");
if (chatTabDropZone && chatComposerForm) {
  let dragDepth = 0;
  chatTabDropZone.addEventListener("dragenter", (e) => {
    if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files")) {
      dragDepth += 1;
      chatComposerForm.classList.add("drag-over");
    }
  });
  chatTabDropZone.addEventListener("dragover", (e) => {
    if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  });
  chatTabDropZone.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) chatComposerForm.classList.remove("drag-over");
  });
  chatTabDropZone.addEventListener("drop", (e) => {
    dragDepth = 0;
    chatComposerForm.classList.remove("drag-over");
    const files = e.dataTransfer && e.dataTransfer.files;
    if (!files || !files.length) return;
    e.preventDefault();
    const file = files[0];
    handleAttachedFile(file);
  });
}

document.getElementById("btn-screen").addEventListener("click", async () => {
  if (state.isStreaming) return;
  const btn = document.getElementById("btn-screen");
  btn.disabled = true;
  let n = 3;
  showToast(`Taking a screenshot in ${n}... switch to the window you need help with`);
  const timer = setInterval(() => { n -= 1; if (n > 0) showToast(`Taking a screenshot in ${n}...`); }, 1000);
  try {
    const resp = await fetch("/api/screen/capture", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ delay_seconds: 3 }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "capture failed");
    setPendingImage(data.image_b64, "Screenshot attached", "screenshot");
    showToast(data.vision_ready
      ? "Screenshot ready. Ask your question, or just press Send."
      : "Screenshot ready, but the vision model is still downloading. Try again in a few minutes.");
    chatInputEl.focus();
  } catch (e) {
    showToast(`Could not take a screenshot: ${e.message}`);
  } finally {
    clearInterval(timer);
    btn.disabled = false;
  }
});

// ==========================================
// MODEL PICKER (styled menu over a hidden <select>)
// ==========================================
// Plain-language names and strengths for the models Loki knows; unknown models fall back to their tag.
const MODEL_INFO = {
  "gemma2:9b": { name: "Gemma 2", about: "Everyday chat and writing" },
  "qwen3:8b": { name: "Qwen 3", about: "Next-gen reasoning, coding and everyday chat" },
  "llama3:latest": { name: "Llama 3", about: "Everyday chat" },
  "qwen2.5:7b": { name: "Qwen 2.5", about: "Answers from web results, following instructions" },
  "qwen2.5-coder:7b": { name: "Qwen 2.5 Coder", about: "Writing and fixing code" },
  "deepseek-r1:8b": { name: "DeepSeek R1", about: "Maths and step-by-step reasoning" },
  "mistral-nemo:12b": { name: "Mistral Nemo", about: "Longer, more detailed answers" },
  "phi4:14b": { name: "Phi-4", about: "Strong reasoning" },
  "qwen2.5:14b": { name: "Qwen 2.5", about: "Higher-quality general answers" },
  "qwen3-vl:8b": { name: "Qwen3-VL", about: "Understands screenshots and images" },
};
// Which models Auto model may switch to, and for what.
const AUTO_ROLES = { "qwen2.5-coder:7b": "code", "deepseek-r1:8b": "maths", "qwen2.5:7b": "web answers and PC help", "qwen3-vl:8b": "screenshots" };

function friendlyModel(tag, paramSize) {
  const info = MODEL_INFO[tag];
  // Prefer the tag's own size ("gemma2:9b" -> 9B) over Ollama's exact count ("9.2B"); round otherwise.
  const tagSize = (tag.match(/:(\d+(?:\.\d+)?)b(?![a-z])/i) || [])[1];
  const exact = parseFloat(paramSize || "");
  const size = tagSize ? `${tagSize}B` : (exact ? `${Math.round(exact)}B` : "");
  if (info) return { name: info.name, size, about: info.about, label: size ? `${info.name} ${size}` : info.name };
  const base = tag.split(":")[0].replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return { name: base, size, about: "", label: size ? `${base} ${size}` : base };
}

const modelPicker = {
  btn: document.getElementById("model-picker-btn"),
  menu: document.getElementById("model-picker-menu"),
  select: document.getElementById("select-model"),
  models: [],
  isOpen() { return !this.menu.classList.contains("hidden"); },
  options() { return [...this.menu.querySelectorAll('[role="option"]')]; },

  updateButton() {
    const m = this.models.find((x) => x.name === this.select.value);
    const f = friendlyModel(this.select.value, m && m.parameter_size);
    document.getElementById("model-picker-name").textContent = f.label;
    const fit = (m && m.vram_fit) || "unknown";
    document.getElementById("model-picker-dot").className = `model-pill-dot fit-dot-${fit}`;
    this.btn.title = m ? `${m.name} \u00b7 ${m.vram_fit_label || ""}` : this.select.value;
    document.getElementById("chat-banner-model").textContent = f.label;
  },

  render(models) {
    this.models = models;
    const current = this.select.value;
    const groups = [
      { key: "fits", title: "Fast on this PC" },
      { key: "tight", title: "May be slower", note: "Only just fits the graphics card." },
      { key: "offload", title: "Slow on this PC", note: "Too large for the graphics card, so part of it runs on the processor." },
      { key: "unknown", title: "Installed" },
    ];
    this.menu.innerHTML = "";
    for (const g of groups) {
      const list = models.filter((m) => (m.vram_fit || "unknown") === g.key).sort((a, b) => (b.size_gb || 0) - (a.size_gb || 0));
      if (!list.length) continue;
      const head = document.createElement("div");
      head.className = `mp-group mp-group-${g.key}`;
      head.setAttribute("role", "presentation");
      head.innerHTML = `<span class="mp-group-title"><span class="mp-dot" aria-hidden="true"></span>${escapeHtml(g.title)}</span>` +
        (g.note ? `<small>${escapeHtml(g.note)}</small>` : "");
      this.menu.appendChild(head);
      for (const m of list) {
        const f = friendlyModel(m.name, m.parameter_size);
        const opt = document.createElement("div");
        opt.className = `mp-option mp-option-${m.vram_fit || "unknown"}`;
        opt.id = `mp-opt-${m.name.replace(/[^\w-]/g, "_")}`;
        opt.setAttribute("role", "option");
        opt.setAttribute("aria-selected", String(m.name === current));
        opt.dataset.value = m.name;
        opt.title = `${m.name} \u00b7 ${m.size_gb} GB${m.quantization_level ? " \u00b7 " + m.quantization_level : ""}`;
        const role = state.autoRoute && AUTO_ROLES[m.name] ? `<span class="mp-role">Auto uses it for ${AUTO_ROLES[m.name]}</span>` : "";
        opt.innerHTML = `
          <div class="mp-main">
            <div class="mp-title"><span class="mp-dot" aria-hidden="true"></span><span>${escapeHtml(f.name)}</span>${f.size ? `<span class="mp-size">${escapeHtml(f.size)}</span>` : ""}</div>
            ${f.about || role ? `<div class="mp-about">${escapeHtml(f.about)}${role}</div>` : ""}
          </div>
          <svg class="mp-check" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
        opt.addEventListener("click", () => this.choose(m.name));
        opt.addEventListener("mousemove", () => this.setActive(opt));
        this.menu.appendChild(opt);
      }
    }
    if (state.autoRoute) {
      const foot = document.createElement("div");
      foot.className = "mp-foot";
      foot.textContent = "Auto model is on: code, maths, web, PC-help and screenshot questions may use a specialist. Everything else uses the model you pick here.";
      this.menu.appendChild(foot);
    }
    this.updateButton();
  },

  setActive(opt) {
    this.options().forEach((o) => o.classList.toggle("active", o === opt));
    if (opt) {
      this.menu.setAttribute("aria-activedescendant", opt.id);
      opt.scrollIntoView({ block: "nearest" });
    }
  },

  open() {
    if (this.isOpen()) return;
    this.render(this.models);
    this.menu.classList.remove("hidden");
    this.btn.setAttribute("aria-expanded", "true");
    this.setActive(this.options().find((o) => o.getAttribute("aria-selected") === "true") || this.options()[0]);
    this.menu.focus();
  },

  close(focusButton = true) {
    if (!this.isOpen()) return;
    this.menu.classList.add("hidden");
    this.btn.setAttribute("aria-expanded", "false");
    if (focusButton) this.btn.focus();
  },

  choose(value) {
    this.close();
    if (value !== this.select.value) {
      this.select.value = value;
      this.select.dispatchEvent(new Event("change"));
    }
    this.updateButton();
  },
};

modelPicker.btn.addEventListener("click", () => (modelPicker.isOpen() ? modelPicker.close() : modelPicker.open()));
modelPicker.btn.addEventListener("keydown", (e) => {
  if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); modelPicker.open(); }
});
modelPicker.menu.addEventListener("keydown", (e) => {
  const opts = modelPicker.options();
  const i = opts.findIndex((o) => o.classList.contains("active"));
  if (e.key === "ArrowDown") { e.preventDefault(); modelPicker.setActive(opts[Math.min(opts.length - 1, i + 1)]); }
  else if (e.key === "ArrowUp") { e.preventDefault(); modelPicker.setActive(opts[Math.max(0, i - 1)]); }
  else if (e.key === "Home") { e.preventDefault(); modelPicker.setActive(opts[0]); }
  else if (e.key === "End") { e.preventDefault(); modelPicker.setActive(opts[opts.length - 1]); }
  else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (opts[i]) modelPicker.choose(opts[i].dataset.value); }
  else if (e.key === "Escape" || e.key === "Tab") { modelPicker.close(e.key === "Escape"); }
});
document.addEventListener("pointerdown", (e) => {
  if (modelPicker.isOpen() && !document.getElementById("model-picker").contains(e.target)) modelPicker.close(false);
});

document.getElementById("select-model").addEventListener("change", (e) => {
  state.selectedModel = e.target.value;
  modelPicker.updateButton();
  saveSettings({ selected_model: state.selectedModel });
  const fit = state.modelFit[state.selectedModel];
  const label = friendlyModel(state.selectedModel).label;
  if (fit && fit.fit === "offload") {
    showToast(`${label} is too large for your graphics card, so replies will be slower.`);
  } else if (fit && fit.fit === "tight") {
    showToast(`${label} only just fits your graphics card and may be slower.`);
  } else {
    showToast(`Now using ${label}`);
  }
});

document.getElementById("select-ctx").addEventListener("change", (e) => {
  state.numCtx = parseInt(e.target.value, 10);
  saveSettings({ num_ctx: state.numCtx });
  showToast(`Context window set to ${state.numCtx} tokens`);
});

document.getElementById("select-temp").addEventListener("change", (e) => {
  state.temperature = parseFloat(e.target.value);
  saveSettings({ temperature: state.temperature });
});

const personaSelect = document.getElementById("select-persona");
if (personaSelect) {
  personaSelect.addEventListener("change", (e) => {
    state.persona = e.target.value || "auto";
    const labels = {
      auto: "Auto style",
      engineer: "Senior Staff Engineer style",
      tutor: "Step-by-step Tutor style",
      concise: "Concise / Direct style",
      gamedev: "Game & Luau Dev style",
    };
    showToast(`Switched to ${labels[state.persona] || state.persona}`);
  });
}

document.getElementById("chk-save-history").addEventListener("change", async (e) => {
  state.saveHistory = e.target.checked;
  await saveSettings({ save_chat_history: state.saveHistory });
  showToast(state.saveHistory ? "Local chat history saving enabled" : "Ephemeral mode: stored history cleared");
  if (!state.saveHistory) state.chatId = null;
  await loadChatList();
  refreshStatus();
});

document.getElementById("chk-web-access").addEventListener("change", async (e) => {
  await saveSettings({ web_access: e.target.checked });
  document.getElementById("web-access-state").textContent = e.target.checked ? "On" : "Off";
  showToast(e.target.checked
    ? "Web access on: Loki will search the web and read links when a question needs it"
    : "Web access off: Loki answers from its local models only");
});

const agentChk = document.getElementById("chk-agent");
agentChk.checked = state.agentMode;
agentChk.addEventListener("change", (e) => {
  state.agentMode = e.target.checked;
  try { localStorage.setItem("loki.agent", state.agentMode ? "1" : "0"); } catch (err) { /* ignore */ }
  showToast(state.agentMode
    ? "Agent on: with a project attached (or when you ask for something new) Loki writes the files, runs them and fixes errors itself"
    : "Agent off: Loki answers in chat and proposes changes for you to review");
});

document.getElementById("chk-auto-model").addEventListener("change", async (e) => {
  state.autoRoute = e.target.checked;
  modelPicker.render(modelPicker.models);
  await saveSettings({ auto_model_routing: state.autoRoute });
  showToast(state.autoRoute
    ? "Auto model on: code questions use qwen2.5-coder, maths/logic use deepseek-r1, everything else your picked model"
    : `Auto model off: every reply uses ${state.selectedModel}`);
});

const refineChk = document.getElementById("chk-refine");
if (refineChk) {
  refineChk.checked = state.refineMode;
  refineChk.addEventListener("change", (e) => {
    state.refineMode = e.target.checked;
    showToast(state.refineMode
      ? "Deep Refine on: Loki drafts first, self-critiques, and writes a refined answer"
      : "Deep Refine off: fast single-pass replies");
  });
}

document.getElementById("chk-use-memories").addEventListener("change", async (e) => {
  state.useMemoriesInChat = e.target.checked;
  await saveSettings({ use_memories_in_chat: state.useMemoriesInChat });
  showToast(
    state.useMemoriesInChat
      ? "Personal/project memories enabled for chat"
      : "Personal/project memories paused for chat"
  );
  refreshStatus();
});

// Push-to-Talk Local Microphone button
document.getElementById("btn-ptt-mic").addEventListener("click", async () => {
  if (state.isMicListening) {
    await fetch("/api/voice/stop-listening", { method: "POST" });
    setMicBannerState(false);
    return;
  }
  setMicBannerState(true);
  try {
    const resp = await fetch("/api/voice/listen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timeout_seconds: 6 }),
    });
    const data = await resp.json();
    if (data.ok && data.text) {
      const cur = chatInputEl.value.trim();
      chatInputEl.value = cur ? `${cur} ${data.text}` : data.text;
      autoResizeChatInput();
      chatInputEl.focus();
      showToast(`Recognized locally: "${data.text}"`);
    } else {
      showToast(data.error || "No speech detected in push-to-talk window");
    }
  } catch (err) {
    showToast(`Local mic error: ${err.message}`);
  } finally {
    setMicBannerState(false);
  }
});

document.getElementById("btn-stop-mic").addEventListener("click", async () => {
  await fetch("/api/voice/stop-listening", { method: "POST" });
  setMicBannerState(false);
  showToast("Stopped microphone capture");
});

document.getElementById("btn-stop-tts").addEventListener("click", async () => {
  await fetch("/api/voice/stop-speaking", { method: "POST" });
  document.getElementById("btn-stop-tts").classList.add("hidden");
  showToast("Stopped local speech playback");
});

function setMicBannerState(active) {
  state.isMicListening = active;
  const banner = document.getElementById("mic-active-banner");
  const micBtn = document.getElementById("btn-ptt-mic");
  if (active) {
    banner.classList.remove("hidden");
    micBtn.classList.add("listening");
  } else {
    banner.classList.add("hidden");
    micBtn.classList.remove("listening");
  }
}

// Start Ollama button
document.getElementById("btn-start-ollama").addEventListener("click", async () => {
  showToast("Starting local Ollama daemon on 127.0.0.1:11434...");
  await fetch("/api/ollama/start", { method: "POST" });
  setTimeout(refreshStatus, 1800);
});

// Unload model from VRAM
document.getElementById("btn-unload-model").addEventListener("click", async () => {
  showToast("Unloading model from GPU VRAM...");
  const resp = await fetch("/api/ollama/unload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: state.selectedModel }),
  });
  const data = await resp.json();
  const unloaded = (data.unloaded_models || []).join(", ") || state.selectedModel;
  showToast(`Unloaded ${unloaded} from VRAM`);
  await refreshStatus();
});

// ==========================================
// IN-APP DIALOGS (instead of window.confirm / prompt / alert)
// ==========================================
/**
 * Open the shared <dialog>. Resolves to true/false (confirm) or the entered text / null (prompt).
 * Escape, Cancel and clicking outside all cancel. Destructive dialogs focus Cancel by default.
 */
function openAppDialog({ title, message = "", confirmLabel = "OK", cancelLabel = "Cancel", danger = false, input = null }) {
  const dlg = document.getElementById("app-dialog");
  const okBtn = document.getElementById("app-dialog-ok");
  const cancelBtn = document.getElementById("app-dialog-cancel");
  const field = document.getElementById("app-dialog-field");
  const inputEl = document.getElementById("app-dialog-input");

  document.getElementById("app-dialog-title").textContent = title;
  const msgEl = document.getElementById("app-dialog-message");
  msgEl.textContent = message;
  msgEl.classList.toggle("hidden", !message);
  okBtn.textContent = confirmLabel;
  cancelBtn.textContent = cancelLabel;
  okBtn.classList.toggle("app-dialog-danger", danger);
  okBtn.disabled = false;
  field.classList.toggle("hidden", !input);

  const syncOk = () => { okBtn.disabled = !inputEl.value.trim(); };
  if (input) {
    document.getElementById("app-dialog-label").textContent = input.label || "";
    inputEl.value = input.value || "";
    inputEl.maxLength = input.maxLength || 200;
    inputEl.addEventListener("input", syncOk);
    syncOk();
  }

  return new Promise((resolve) => {
    const onBackdrop = (e) => { if (e.target === dlg) dlg.close("cancel"); };
    const onCancel = () => dlg.close("cancel");
    dlg.addEventListener("click", onBackdrop);
    cancelBtn.addEventListener("click", onCancel);
    dlg.addEventListener("close", () => {
      dlg.removeEventListener("click", onBackdrop);
      cancelBtn.removeEventListener("click", onCancel);
      inputEl.removeEventListener("input", syncOk);
      const ok = dlg.returnValue === "ok";
      resolve(input ? (ok ? inputEl.value.trim() : null) : ok);
    }, { once: true });

    dlg.returnValue = "cancel";
    dlg.showModal();
    if (input) {
      inputEl.focus();
      inputEl.select();
    } else {
      (danger ? cancelBtn : okBtn).focus();
    }
  });
}

const confirmDialog = (opts) => openAppDialog(opts);
const promptDialog = (opts) => openAppDialog({ ...opts, input: opts.input || {} });

// ==========================================
// MULTI-CHAT HISTORY (sidebar list)
// ==========================================
function newChatId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, "");
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
}

function relativeTime(iso) {
  const t = Date.parse(iso || "");
  if (!t) return "";
  const mins = Math.round((Date.now() - t) / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.round(hrs / 24);
  if (days < 7) return `${days}d`;
  return new Date(t).toLocaleDateString([], { month: "short", day: "numeric" });
}

async function loadChatList() {
  try {
    const data = await (await fetch("/api/chats")).json();
    state.chats = Array.isArray(data.chats) ? data.chats : [];
  } catch (e) {
    console.error("Failed to load chats:", e);
    state.chats = [];
  }
  renderChatList();
}

function renderChatList() {
  const list = document.getElementById("chat-list");
  const searchInput = document.getElementById("chat-search-input");
  const filter = (searchInput && searchInput.value ? searchInput.value.trim().toLowerCase() : "");
  list.innerHTML = "";
  const visibleChats = filter
    ? state.chats.filter((c) => (c.title || "").toLowerCase().includes(filter))
    : state.chats;
  if (visibleChats.length === 0) {
    const empty = document.createElement("div");
    empty.className = "chat-list-empty";
    empty.textContent = filter
      ? "No matching chats"
      : (state.saveHistory ? "No saved chats yet" : "History saving is off");
    list.appendChild(empty);
    return;
  }
  for (const c of visibleChats) {
    const item = document.createElement("div");
    item.className = "chat-item" + (c.id === state.chatId ? " active" : "") + (c.pinned ? " pinned" : "");
    item.title = `${c.title}\nDouble-click to rename`;

    const pin = document.createElement("button");
    pin.className = "chat-item-pin" + (c.pinned ? " is-pinned" : "");
    pin.title = c.pinned ? "Unpin chat" : "Pin chat to top";
    pin.setAttribute("aria-label", c.pinned ? `Unpin chat ${c.title}` : `Pin chat ${c.title}`);
    pin.textContent = c.pinned ? "★" : "☆";
    pin.addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/chats/${encodeURIComponent(c.id)}/pin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pinned: !c.pinned }),
      });
      await loadChatList();
    });

    const open = document.createElement("button");
    open.className = "chat-item-open";
    open.innerHTML = `<span class="chat-item-title">${escapeHtml(c.title)}</span><span class="chat-item-time">${escapeHtml(relativeTime(c.updated))}</span>`;
    open.addEventListener("click", () => openChat(c.id));
    open.addEventListener("dblclick", () => renameChat(c));

    const del = document.createElement("button");
    del.className = "chat-item-delete";
    del.title = "Delete chat";
    del.setAttribute("aria-label", `Delete chat ${c.title}`);
    del.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path></svg>`;
    del.addEventListener("click", (e) => { e.stopPropagation(); deleteChat(c); });

    item.append(pin, open, del);
    list.appendChild(item);
  }
}

function blockedWhileStreaming() {
  if (!state.isStreaming) return false;
  showToast("Wait for the reply to finish (or press Stop) before switching chats");
  return true;
}

async function openChat(id) {
  if (blockedWhileStreaming()) return;
  try {
    const resp = await fetch(`/api/chats/${encodeURIComponent(id)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const chat = await resp.json();
    state.chatId = chat.id;
    state.messages = Array.isArray(chat.messages) ? chat.messages : [];
    renderMessages();
    renderChatList();
    document.querySelector('.nav-btn[data-tab="chat"]').click();
  } catch (e) {
    showToast("Could not open that chat");
    await loadChatList();
  }
}

function startNewChat() {
  if (blockedWhileStreaming()) return;
  state.chatId = null;
  state.messages = [];
  renderMessages();
  renderChatList();
  document.querySelector('.nav-btn[data-tab="chat"]').click();
  chatInputEl.focus();
}

async function renameChat(c) {
  const title = await promptDialog({
    title: "Rename chat",
    confirmLabel: "Rename",
    input: { label: "Chat name", value: c.title, maxLength: 60 },
  });
  if (!title || title === c.title) return;
  await fetch(`/api/chats/${encodeURIComponent(c.id)}/rename`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  await loadChatList();
}

async function deleteChat(c) {
  if (blockedWhileStreaming()) return;
  const ok = await confirmDialog({
    title: "Delete this chat?",
    message: `"${c.title}" will be permanently deleted. This can't be undone.`,
    confirmLabel: "Delete chat",
    danger: true,
  });
  if (!ok) return;
  await fetch(`/api/chats/${encodeURIComponent(c.id)}`, { method: "DELETE" });
  if (c.id === state.chatId) {
    state.chatId = null;
    state.messages = [];
    renderMessages();
  }
  await loadChatList();
  showToast("Chat deleted");
}

// New chat: starts a fresh conversation; saved chats stay in the sidebar.
document.getElementById("btn-clear-chat").addEventListener("click", startNewChat);

const chatSearchInput = document.getElementById("chat-search-input");
if (chatSearchInput) {
  chatSearchInput.addEventListener("input", renderChatList);
}

const btnExportChat = document.getElementById("btn-export-chat");
if (btnExportChat) {
  btnExportChat.addEventListener("click", () => {
    if (!state.messages || state.messages.length === 0) {
      showToast("Start a conversation first to export it as Markdown");
      return;
    }
    const activeChat = state.chats.find((c) => c.id === state.chatId);
    const title = (activeChat && activeChat.title) || "Loki Chat Export";
    const lines = [`# ${title}`, "", `_Exported from Loki on ${new Date().toLocaleString()}_`, ""];
    for (const m of state.messages) {
      if (m.role === "user") {
        lines.push(`## You${m.timestamp ? ` (${m.timestamp})` : ""}`);
        if (m.attached_file && m.attached_file.name) {
          lines.push(`> Attached file: \`${m.attached_file.name}\``);
        }
        lines.push("", m.content || "", "");
      } else {
        const parts = splitThinking(m);
        const modLabel = friendlyModel(m.model || state.selectedModel).label;
        lines.push(`## Loki — ${modLabel}${m.timestamp ? ` (${m.timestamp})` : ""}`);
        if (parts.thinking && parts.thinking.trim()) {
          lines.push("", "<details><summary>Reasoning</summary>", "", parts.thinking.trim(), "", "</details>", "");
        }
        lines.push("", parts.answer || "", "");
      }
    }
    const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "loki-chat";
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${slug}.md`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    showToast(`Exported ${slug}.md to your Downloads folder`);
  });
}

const btnBackupData = document.getElementById("btn-backup-data");
if (btnBackupData) {
  btnBackupData.addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = "/api/privacy/backup";
    document.body.appendChild(a);
    a.click();
    a.remove();
    showToast("Downloading your local Loki data backup (.zip)...");
  });
}

const btnRestoreData = document.getElementById("btn-restore-data");
const inputRestoreZip = document.getElementById("input-restore-zip");
if (btnRestoreData && inputRestoreZip) {
  btnRestoreData.addEventListener("click", () => inputRestoreZip.click());
  inputRestoreZip.addEventListener("change", async () => {
    const file = inputRestoreZip.files && inputRestoreZip.files[0];
    inputRestoreZip.value = "";
    if (!file) return;
    if (file.size > 18 * 1024 * 1024) {
      showToast("Backup archive is too large (> 18 MB).");
      return;
    }
    const ok = await confirmDialog({
      title: "Restore from this backup?",
      message: `This will restore saved chats, memories, settings, schedules, and exports from "${file.name}".`,
      confirmLabel: "Restore backup",
    });
    if (!ok) return;
    const reader = new FileReader();
    reader.onerror = () => showToast("Could not read that backup file");
    reader.onload = async () => {
      const dataUrl = String(reader.result || "");
      const b64 = (dataUrl.split(",")[1] || "").trim();
      try {
        const res = await lokiPost("/api/privacy/restore", { zip_b64: b64 });
        showToast(`Restored ${(res.restored_files || []).length} file(s) from backup`);
        await loadChatList();
        await refreshStatus();
      } catch (err) {
        showToast(`Restore failed: ${err.message}`);
      }
    };
    reader.readAsDataURL(file);
  });
}

// Wipe all data
document.getElementById("btn-wipe-data").addEventListener("click", async () => {
  const ok = await confirmDialog({
    title: "Wipe all Loki data?",
    message: "This deletes everything Loki has stored: chats, memories, settings, the document index, workflow history and exports. Your own files on this PC are never touched. This can't be undone.",
    confirmLabel: "Wipe everything",
    danger: true,
  });
  if (!ok) return;
  const resp = await fetch("/api/privacy/wipe", { method: "POST" });
  const data = await resp.json();
  state.messages = [];
  state.chatId = null;
  state.workflowRuns = [];
  state.activeRunId = null;
  renderMessages();
  loadChatList();
  renderWorkflowHistory();
  renderActiveRun(null);
  showToast(`Wiped ${data.removed_files.length} file(s) from loki/data/`);
  await refreshStatus();
});

document.getElementById("btn-refresh-status").addEventListener("click", refreshStatus);
document.getElementById("btn-manual-refresh").addEventListener("click", refreshStatus);

// Auto-resize textarea
const chatInputEl = document.getElementById("chat-input");
function autoResizeChatInput() {
  chatInputEl.style.height = "auto";
  chatInputEl.style.height = Math.min(180, chatInputEl.scrollHeight) + "px";
}
chatInputEl.addEventListener("input", autoResizeChatInput);

// Reasoning models stream thinking separately (m.thinking); older replies may hold it inline as <think>…</think>.
function splitThinking(m) {
  let answer = m.content || "";
  let thinking = m.thinking || "";
  const match = answer.match(/^\s*<think>([\s\S]*?)(<\/think>|$)/);
  if (match) {
    thinking = (thinking ? thinking + "\n" : "") + match[1];
    answer = answer.slice(match[0].length);
  }
  return { thinking, answer: answer.replace(/^\s+/, "") };
}

// Global keyboard shortcuts: Ctrl+K (new chat), Ctrl+/ (search chats), Ctrl+Shift+E (export .md)
document.addEventListener("keydown", (e) => {
  if (document.querySelector("dialog[open]")) return;
  const ctrl = e.ctrlKey || e.metaKey;
  if (!ctrl) return;
  const key = (e.key || "").toLowerCase();
  if (key === "k" && !e.shiftKey && !e.altKey) {
    e.preventDefault();
    startNewChat();
  } else if (e.key === "/" && !e.shiftKey && !e.altKey) {
    const searchEl = document.getElementById("chat-search-input");
    if (searchEl) {
      e.preventDefault();
      searchEl.focus();
      searchEl.select();
    }
  } else if (key === "e" && e.shiftKey && !e.altKey) {
    const expBtn = document.getElementById("btn-export-chat");
    if (expBtn) {
      e.preventDefault();
      expBtn.click();
    }
  }
});

function buildFollowUpChips(m, answerText) {
  const task = (m.route && m.route.task) || "";
  if (m.agent) {
    return [
      "Add another feature or polish the UI",
      "Write unit tests and run them to verify edge cases",
      "Explain how the project files work together",
    ];
  }
  if (task === "code" || /```/.test(answerText || "")) {
    return [
      "Write unit tests for this code",
      "Check for edge cases or performance bottlenecks",
      "Explain how this code works step by step",
    ];
  }
  if (task === "pc") {
    return [
      "What should I check next if that looks normal?",
      "Give me another read-only PowerShell diagnostic check",
      "Summarize the most likely root cause in plain English",
    ];
  }
  if (task === "reasoning") {
    return [
      "Verify this result using a second independent method",
      "Show a concrete real-world example of this",
      "Summarize the key takeaway in 3 bullet points",
    ];
  }
  return [
    "Go deeper into the technical details",
    "Turn this into a step-by-step action checklist",
    "Give me concrete examples",
  ];
}

const shownMessages = new WeakSet();

// Render chat messages (Claude / ChatGPT / Gemini hybrid layout)
function renderMessages() {
  const viewport = document.getElementById("chat-messages");
  const column = document.getElementById("chat-stream-column");
  const emptyState = document.getElementById("chat-empty-state");

  column.innerHTML = "";

  if (state.messages.length === 0) {
    emptyState.classList.remove("hidden");
    return;
  }
  emptyState.classList.add("hidden");

  for (const m of state.messages) {
    const turn = document.createElement("div");
    // Only messages appearing for the first time fade in; re-renders while streaming stay still.
    const settled = shownMessages.has(m);
    shownMessages.add(m);
    turn.className = `msg ${m.role === "user" ? "msg-user" : "msg-assistant"}${settled ? " settled" : ""}`;
    if (m.projectPath) turn.dataset.project = m.projectPath;

    if (m.role === "user") {
      const bubble = document.createElement("div");
      bubble.className = "msg-user-bubble";
      bubble.textContent = m.content;
      if (m.attached_file && m.attached_file.name) {
        const fBadge = document.createElement("div");
        fBadge.className = "msg-file-badge";
        const linesTxt = m.attached_file.lines ? ` · ${m.attached_file.lines} lines` : "";
        fBadge.textContent = `📄 ${m.attached_file.name}${linesTxt}`;
        bubble.prepend(fBadge);
      }
      if (m.images && m.images.length) {
        const img = document.createElement("img");
        img.className = "msg-screenshot";
        img.alt = "Screenshot sent to Loki";
        img.src = `data:image/jpeg;base64,${m.images[0]}`;
        bubble.prepend(img);
      } else if (m.had_screenshot) {
        const note = document.createElement("div");
        note.className = "msg-screenshot-note";
        note.textContent = "Screenshot (not saved)";
        bubble.prepend(note);
      }
      turn.appendChild(bubble);

      const meta = document.createElement("div");
      meta.className = "msg-user-meta";
      if (m.timestamp) {
        const tsSpan = document.createElement("span");
        tsSpan.textContent = m.timestamp;
        meta.appendChild(tsSpan);
      }
      if (!state.isStreaming) {
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn-edit-user-msg";
        editBtn.title = "Edit this message and resend from here";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", () => {
          if (state.isStreaming) return;
          const idx = state.messages.indexOf(m);
          if (idx < 0) return;
          chatInputEl.value = m.content || "";
          if (m.attached_file && m.attached_file.content) {
            state.pendingFile = { ...m.attached_file };
            const titleEl = document.getElementById("file-attachment-title");
            if (titleEl) titleEl.textContent = `${m.attached_file.name} (${m.attached_file.lines || 0} lines)`;
            const bar = document.getElementById("file-attachment");
            if (bar) bar.classList.remove("hidden");
          }
          state.messages = state.messages.slice(0, idx);
          renderMessages();
          autoResizeChatInput();
          chatInputEl.focus();
          showToast("Message loaded into composer — edit and press Send");
        });
        meta.appendChild(editBtn);
      }
      turn.appendChild(meta);
    } else {
      const modelLabel = m.model || state.selectedModel;
      const ctxLabel = m.num_ctx ? `ctx ${m.num_ctx}` : "";

      const row = document.createElement("div");
      row.className = "assistant-turn-row";

      const avatar = document.createElement("div");
      avatar.className = "assistant-avatar";
      avatar.innerHTML = `
        <img src="/static/loki-mark.svg?v=15" width="24" height="24" alt="" />
      `;

      const wrap = document.createElement("div");
      wrap.className = "assistant-content-wrap";

      const header = document.createElement("div");
      header.className = "msg-header";
      const parts = splitThinking(m);
      const r = m.route;
      let routePill = "";
      if (r && r.auto && (r.routed || r.task !== "general")) {
        const text = r.routed ? `Auto &bull; ${escapeHtml(r.task_label)}` : `${escapeHtml(r.task_label)} &bull; kept ${escapeHtml(friendlyModel(r.selected_model).label)}`;
        const tip = r.routed
          ? `Auto model: ${r.reason}, so Loki used ${friendlyModel(modelLabel).label} instead of ${friendlyModel(r.selected_model).label}. Turn off "Auto model" to always use your picked model.`
          : `Detected: ${r.reason}. ${r.note || ""}`;
        routePill = `<span class="route-pill${r.routed ? "" : " route-fallback"}" title="${escapeHtml(tip)}">${text}</span>`;
      }
      header.innerHTML = `
        <span class="model-badge">Loki</span>
        <span class="model-sub-pill" title="${escapeHtml(modelLabel)}${ctxLabel ? " \u00b7 " + escapeHtml(ctxLabel) : ""}">${escapeHtml(friendlyModel(modelLabel).label)}</span>
        ${routePill}
        <span class="step-meta">${escapeHtml(m.timestamp || "")}</span>
      `;

      wrap.appendChild(header);

      if (parts.thinking) {
        const details = document.createElement("details");
        details.className = "thinking-block";
        const stillThinking = state.isStreaming && !parts.answer && m === state.messages[state.messages.length - 1];
        details.open = m.thinkingOpen === undefined ? stillThinking : m.thinkingOpen;
        const words = parts.thinking.trim().split(/\s+/).length;
        details.innerHTML = `<summary>${stillThinking ? "Reasoning…" : `Reasoning (${words} words)`}</summary><div class="thinking-body"></div>`;
        details.querySelector(".thinking-body").textContent = parts.thinking.trim();
        details.addEventListener("toggle", () => { m.thinkingOpen = details.open; });
        wrap.appendChild(details);
      }

      const isLive = state.isStreaming && m === state.messages[state.messages.length - 1];
      if (m.agent) wrap.appendChild(renderAgentPanel(m, isLive));

      const body = document.createElement("div");
      body.className = "msg-body";
      if (m.agent && !parts.answer) {
        body.classList.add("hidden");
      } else if (!parts.answer && isLive && !parts.thinking) {
        body.innerHTML = `<p class="msg-pending">${escapeHtml(m.webStatus || "Thinking...")}</p>`;
      } else {
        body.innerHTML = renderMarkdown(parts.answer);
      }
      wrap.appendChild(body);

      if (m.projectName) {
        const pf = document.createElement("div");
        pf.className = "msg-project";
        const files = (m.projectFiles || []);
        pf.textContent = files.length
          ? `Read from ${m.projectName}: ${files.join(", ")}`
          : `Project ${m.projectName} attached (no files matched; mention a file name to include it)`;
        wrap.appendChild(pf);
      }

      if (Array.isArray(m.sources) && m.sources.length > 0) {
        const src = document.createElement("div");
        src.className = "msg-sources";
        const head = document.createElement("div");
        head.className = "msg-sources-head";
        head.textContent = "Sources";
        if (m.webReason) head.title = `Loki searched the web because ${m.webReason}.`;
        src.appendChild(head);
        const list = document.createElement("ol");
        for (const s of m.sources) {
          let host = "";
          try { host = new URL(s.url).hostname.replace(/^www\./, ""); } catch (e) { host = ""; }
          const li = document.createElement("li");
          const a = document.createElement("a");
          a.href = s.url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = s.title || host || s.url;
          const hostEl = document.createElement("span");
          hostEl.className = "msg-sources-host";
          hostEl.textContent = host;
          li.append(a, hostEl);
          list.appendChild(li);
        }
        src.appendChild(list);
        wrap.appendChild(src);
      }

      if (m.footer) {
        const footer = document.createElement("div");
        footer.className = "msg-footer";

        const metaSpan = document.createElement("span");
        metaSpan.textContent = m.footer;
        footer.appendChild(metaSpan);

        if (m.content) {
          const copyBtn = document.createElement("button");
          copyBtn.type = "button";
          copyBtn.className = "btn-copy-turn";
          copyBtn.textContent = "Copy reply";
          copyBtn.addEventListener("click", () => {
            navigator.clipboard.writeText(splitThinking(m).answer);
            copyBtn.textContent = "Copied!";
            setTimeout(() => (copyBtn.textContent = "Copy reply"), 1800);
          });
          footer.appendChild(copyBtn);

          const speakBtn = document.createElement("button");
          speakBtn.type = "button";
          speakBtn.className = "btn-copy-turn";
          speakBtn.textContent = "Speak (Local TTS)";
          speakBtn.addEventListener("click", async () => {
            document.getElementById("btn-stop-tts").classList.remove("hidden");
            await fetch("/api/voice/speak", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ text: splitThinking(m).answer }),
            });
            showToast("Speaking reply locally via Windows System.Speech");
          });
          footer.appendChild(speakBtn);

          if (!state.isStreaming && !m.agent) {
            const refineBtn = document.createElement("button");
            refineBtn.type = "button";
            refineBtn.className = "btn-copy-turn";
            refineBtn.title = "Re-run this answer with a 2-pass self-critique & refinement pass";
            refineBtn.textContent = m.refined ? "Refined (2-pass)" : "Refine (2-pass)";
            refineBtn.addEventListener("click", () => {
              retryAssistantTurn(m, {
                model: m.model || state.selectedModel,
                autoRoute: false,
                refine: true,
              });
            });
            footer.appendChild(refineBtn);

            if (modelPicker.models && modelPicker.models.length > 1) {
              const retrySelect = document.createElement("select");
              retrySelect.className = "select-retry-model";
              retrySelect.title = "Re-run this question with another installed model (including 14B heavyweights)";
              const placeholderOpt = document.createElement("option");
              placeholderOpt.value = "";
              placeholderOpt.textContent = "Try model…";
              retrySelect.appendChild(placeholderOpt);
              for (const mod of modelPicker.models) {
                const f = friendlyModel(mod.name, mod.parameter_size);
                const opt = document.createElement("option");
                opt.value = mod.name;
                const tag = mod.vram_fit === "offload" ? " (14B Max IQ)" : (mod.vram_fit === "tight" ? " (12B)" : "");
                opt.textContent = `${f.label}${tag}`;
                retrySelect.appendChild(opt);
              }
              retrySelect.addEventListener("change", () => {
                const chosen = retrySelect.value;
                retrySelect.value = "";
                if (!chosen) return;
                retryAssistantTurn(m, {
                  model: chosen,
                  autoRoute: false,
                  refine: false,
                });
              });
              footer.appendChild(retrySelect);
            }
          }
        }

        wrap.appendChild(footer);

        const isLatestTurn = m === state.messages[state.messages.length - 1];
        if (!state.isStreaming && isLatestTurn && parts.answer && parts.answer.length > 20) {
          const chipsWrap = document.createElement("div");
          chipsWrap.className = "followup-chips";
          for (const promptText of buildFollowUpChips(m, parts.answer)) {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "btn-followup-chip";
            chip.textContent = promptText;
            chip.addEventListener("click", () => {
              if (state.isStreaming) return;
              chatInputEl.value = promptText;
              autoResizeChatInput();
              document.getElementById("chat-form").requestSubmit();
            });
            chipsWrap.appendChild(chip);
          }
          wrap.appendChild(chipsWrap);
        }
      }

      row.appendChild(avatar);
      row.appendChild(wrap);
      turn.appendChild(row);
    }

    column.appendChild(turn);
  }
  viewport.scrollTop = viewport.scrollHeight;
}

// ==========================================
// CODING AGENT (ADR-016): live step list, approvals, undo, preview
// ==========================================
const AGENT_ICONS = {
  running: '<span class="ag-spin" aria-hidden="true"></span>',
  ok: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="5 12.5 10 17 19 7"></polyline></svg>',
  error: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><line x1="7" y1="7" x2="17" y2="17"></line><line x1="17" y1="7" x2="7" y2="17"></line></svg>',
  skipped: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><line x1="6" y1="12" x2="18" y2="12"></line></svg>',
  waiting: '<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><rect x="7" y="6" width="3.2" height="12" rx="1"></rect><rect x="13.8" y="6" width="3.2" height="12" rx="1"></rect></svg>',
};

function formatSecs(s) {
  s = Math.round(s || 0);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function renderAgentPanel(m, isLive) {
  const a = m.agent;
  const live = isLive && !a.done;
  const panel = document.createElement("div");
  panel.className = "agent-panel";
  const toolSteps = a.steps.filter((s) => s.kind !== "note");
  const head = document.createElement("div");
  head.className = "agent-head";
  head.innerHTML =
    `<span class="agent-title">${live ? "Working in" : "Worked in"} <strong>${escapeHtml(a.projectName || "project")}</strong>` +
    `${a.created ? '<span class="agent-new">New project</span>' : ""}</span>` +
    (live
      ? `<span class="agent-timer" data-start="${a.startedAt}" data-label="${escapeHtml(a.status || "Thinking")}">${escapeHtml(a.status || "Thinking")}…</span>`
      : `<span class="agent-meta">${toolSteps.length} step${toolSteps.length === 1 ? "" : "s"}${a.seconds ? " · " + formatSecs(a.seconds) : ""}</span>`);
  panel.appendChild(head);

  if (a.steps.length) {
    const list = document.createElement("ol");
    list.className = "agent-steps";
    for (const s of a.steps) {
      const li = document.createElement("li");
      if (s.kind === "note") {
        li.className = "agent-note";
        li.textContent = s.text;
        list.appendChild(li);
        continue;
      }
      // A step still running or waiting when the run ended (stopped, or the window was closed) did not happen.
      const status = (s.status === "running" || s.status === "waiting") && !live ? "skipped" : s.status;
      li.className = `agent-step st-${status}`;
      const row = `<span class="ag-icon">${AGENT_ICONS[status] || ""}</span>` +
        `<span class="ag-title">${escapeHtml(s.title)}</span>` +
        (s.summary ? `<span class="ag-sum">${escapeHtml(s.summary)}</span>` : "");
      if (s.diff || s.output) {
        const det = document.createElement("details");
        det.open = Boolean(s.open);
        det.innerHTML = `<summary class="ag-row">${row}</summary>`;
        const pre = document.createElement("pre");
        if (s.diff) { pre.className = "ag-detail diff-view"; pre.innerHTML = diffToHtml(s.diff); }
        else { pre.className = "ag-detail ag-output"; pre.textContent = s.output; }
        det.appendChild(pre);
        det.addEventListener("toggle", () => { s.open = det.open; });
        li.appendChild(det);
      } else {
        li.innerHTML = `<div class="ag-row">${row}</div>`;
      }
      if (s.status === "waiting" && live) {
        const box = document.createElement("div");
        box.className = "ag-approve";
        box.innerHTML =
          `<div class="ag-why">Needs your OK: ${escapeHtml((s.reasons || []).join("; "))}</div>` +
          `<code class="ag-cmd">${escapeHtml(s.command || "")}</code>` +
          `<div class="ag-btns">` +
          `<button type="button" class="btn btn-sm btn-primary agent-decide" data-approval="${escapeHtml(s.approvalId)}" data-approve="1">Run it</button>` +
          `<button type="button" class="btn btn-sm btn-secondary agent-decide" data-approval="${escapeHtml(s.approvalId)}" data-approve="0">Skip</button></div>`;
        li.appendChild(box);
      }
      list.appendChild(li);
    }
    panel.appendChild(list);
  }

  if (a.done) {
    const bar = document.createElement("div");
    bar.className = "agent-actions";
    const changed = [...new Set((a.changes || []).map((c) => c.path))];
    const sum = document.createElement("span");
    sum.className = "agent-changed";
    sum.textContent = a.undone ? "All changes undone"
      : changed.length ? `Changed ${changed.length} file${changed.length === 1 ? "" : "s"}: ${changed.slice(0, 4).join(", ")}${changed.length > 4 ? "…" : ""}`
      : "No files changed";
    bar.appendChild(sum);
    const btn = (label, cls, action) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `btn btn-sm ${cls} agent-action`;
      b.dataset.action = action;
      b.textContent = label;
      bar.appendChild(b);
    };
    if (a.hasIndex && !a.undone) btn("Preview", "btn-primary", "preview");
    btn("Open folder", "btn-secondary", "open");
    if (changed.length && !a.undone) btn("Undo all", "btn-secondary", "undo");
    panel.appendChild(bar);
  }
  return panel;
}

// Live elapsed time on the running agent step ("Working… 14s").
setInterval(() => {
  for (const el of document.querySelectorAll(".agent-timer")) {
    const secs = (Date.now() - Number(el.dataset.start || Date.now())) / 1000;
    el.textContent = `${el.dataset.label}… ${formatSecs(secs)}`;
  }
}, 1000);

function agentMessageFor(el) {
  const turn = el.closest(".msg");
  const idx = [...document.querySelectorAll("#chat-stream-column > .msg")].indexOf(turn);
  return idx >= 0 ? state.messages[idx] : null;
}

async function saveCurrentChat() {
  if (!state.saveHistory || !state.chatId) return;
  try {
    await fetch(`/api/chats/${encodeURIComponent(state.chatId)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: state.messages }),
    });
  } catch (e) { /* the next save will catch up */ }
}

document.getElementById("chat-stream-column").addEventListener("click", async (e) => {
  const decideBtn = e.target.closest(".agent-decide");
  if (decideBtn) {
    const m = agentMessageFor(decideBtn);
    if (!m || !m.agent) return;
    decideBtn.closest(".ag-btns").querySelectorAll("button").forEach((b) => { b.disabled = true; });
    try {
      await lokiPost(`/api/agent/${encodeURIComponent(m.agent.runId)}/decide`,
        { approval_id: decideBtn.dataset.approval, approve: decideBtn.dataset.approve === "1" });
    } catch (err) { showToast(err.message); }
    return;
  }
  const actionBtn = e.target.closest(".agent-action");
  if (!actionBtn) return;
  const m = agentMessageFor(actionBtn);
  if (!m || !m.agent) return;
  const a = m.agent;
  if (actionBtn.dataset.action === "preview") {
    try {
      const pv = await lokiPost("/api/agent/preview", { path: a.project });
      showPreviewUrl(pv.url);
    } catch (err) { showToast(`Preview failed: ${err.message}`); }
  } else if (actionBtn.dataset.action === "open") {
    try { await lokiPost("/api/projects/open", { path: a.project }); }
    catch (err) { showToast(`Could not open the folder: ${err.message}`); }
  } else if (actionBtn.dataset.action === "undo") {
    const ok = await confirmDialog({
      title: "Undo all changes?",
      message: `Put back every file this run changed in ${a.projectName} (${a.changes.length} change${a.changes.length === 1 ? "" : "s"}). New files it created are removed.`,
      confirmLabel: "Undo all", danger: true,
    });
    if (!ok) return;
    try {
      const res = await lokiPost("/api/agent/undo", { change_ids: a.changes.map((c) => c.id) });
      if (res.failed && res.failed.length) {
        showToast(`Undid ${res.undone.length}; ${res.failed.length} could not be undone: ${res.failed[0].error}`);
      } else {
        a.undone = true;
        showToast("All changes undone");
      }
      renderMessages();
      saveCurrentChat();
    } catch (err) { showToast(`Undo failed: ${err.message}`); }
  }
});

// Stop active generation
document.getElementById("btn-stop-gen").addEventListener("click", async () => {
  if (state.agentRunId) {
    // Let the agent finish its current step and report what it changed (so Undo all stays available).
    try { await lokiPost(`/api/agent/${encodeURIComponent(state.agentRunId)}/stop`, {}); } catch (e) { /* ignore */ }
    await fetch("/api/chat/stop", { method: "POST" });
    showToast("Stopping the agent");
    return;
  }
  if (state.abortController) {
    state.abortController.abort();
  }
  await fetch("/api/chat/stop", { method: "POST" });
  showToast("Stopped generation");
});

// Handle Enter / Shift+Enter in textarea
chatInputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    document.getElementById("chat-form").requestSubmit();
  }
});

async function streamIntoAssistantMsg(assistantMsg, historyForApi, opts = {}) {
  const chatIdAtSend = state.chatId || (state.chatId = newChatId());
  const messagesAtSend = state.messages;
  const chosenModel = opts.model || state.selectedModel;
  const useAutoRoute = opts.autoRoute !== undefined ? opts.autoRoute : state.autoRoute;
  const useRefine = opts.refine !== undefined ? opts.refine : state.refineMode;
  const useAgent = opts.agent !== undefined ? opts.agent : state.agentMode;

  state.isStreaming = true;
  state.abortController = new AbortController();
  document.getElementById("btn-send-chat").disabled = true;
  document.getElementById("btn-stop-gen").classList.remove("hidden");

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: historyForApi,
        model: chosenModel,
        num_ctx: state.numCtx,
        temperature: state.temperature,
        provider: "ollama",
        cloud_request_opt_in: false,
        auto_route: useAutoRoute,
        project: state.project || null,
        agent: useAgent,
        refine: Boolean(useRefine),
        persona: state.persona || "auto",
      }),
      signal: state.abortController.signal,
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;
        const evt = JSON.parse(line);
        if (evt.type === "route") {
          assistantMsg.route = {
            auto: evt.auto, task: evt.task, task_label: evt.task_label, reason: evt.reason,
            routed: evt.routed, note: evt.note, selected_model: evt.selected_model,
          };
          assistantMsg.model = evt.model;
          renderMessages();
        } else if (evt.type === "meta") {
          assistantMsg.model = evt.model;
          assistantMsg.num_ctx = evt.num_ctx;
          assistantMsg.refined = Boolean(evt.refined);
        } else if (evt.type === "thinking") {
          assistantMsg.thinking = (assistantMsg.thinking || "") + evt.content;
          renderMessages();
        } else if (evt.type === "project_context") {
          assistantMsg.projectPath = state.project;
          assistantMsg.projectName = evt.project;
          assistantMsg.projectFiles = evt.files || [];
          renderMessages();
        } else if (evt.type === "agent_start") {
          state.agentRunId = evt.run_id;
          assistantMsg.projectPath = evt.project;
          assistantMsg.agent = {
            runId: evt.run_id, project: evt.project, projectName: evt.project_name, created: evt.created_project,
            steps: [], status: "Thinking", startedAt: Date.now(), done: false, changes: [],
          };
          assistantMsg.model = evt.model;
          assistantMsg.num_ctx = evt.num_ctx;
          if (evt.created_project) {
            await loadProjects();
            setProject(evt.project);
            showToast(`Created project folder ${evt.project}`);
          }
          renderMessages();
        } else if (evt.type === "agent_status" && assistantMsg.agent) {
          assistantMsg.agent.status = evt.text;
          renderMessages();
        } else if (evt.type === "agent_note" && assistantMsg.agent) {
          assistantMsg.agent.steps.push({ kind: "note", text: evt.text });
          renderMessages();
        } else if (evt.type === "agent_step" && assistantMsg.agent) {
          assistantMsg.agent.steps.push({ id: evt.id, tool: evt.tool, title: evt.title, status: "running", command: evt.command || "" });
          assistantMsg.agent.status = evt.title;
          renderMessages();
        } else if (evt.type === "agent_step_update" && assistantMsg.agent) {
          const s = assistantMsg.agent.steps.find((x) => x.id === evt.id);
          if (s) {
            s.status = evt.status;
            if (evt.summary !== undefined) s.summary = evt.summary;
            if (evt.diff) s.diff = evt.diff;
            if (evt.output) s.output = evt.output;
            if (evt.change_id) s.changeId = evt.change_id;
            if (evt.approval_id) { s.approvalId = evt.approval_id; s.reasons = evt.reasons || []; }
            assistantMsg.agent.status = evt.status === "waiting" ? "Waiting for you" : "Working";
          }
          renderMessages();
        } else if (evt.type === "agent_done" && assistantMsg.agent) {
          Object.assign(assistantMsg.agent, {
            done: true, changes: evt.changes || [], hasIndex: evt.has_index_html, seconds: evt.seconds,
          });
          renderMessages();
        } else if (evt.type === "web_status") {
          assistantMsg.webStatus = evt.message;
          renderMessages();
        } else if (evt.type === "sources") {
          assistantMsg.sources = evt.items || [];
          assistantMsg.webReason = evt.reason || "";
          assistantMsg.webStatus = "";
          renderMessages();
        } else if (evt.type === "token") {
          assistantMsg.content += evt.content;
          renderMessages();
        } else if (evt.type === "done") {
          const speed = evt.tokens_per_sec ? `${evt.tokens_per_sec} tok/s` : "";
          const counts = `${evt.prompt_tokens || 0} in / ${evt.completion_tokens || 0} out`;
          const memInfo = evt.memories_used ? ` • ${evt.memories_used} mem` : "";
          const refInfo = assistantMsg.refined ? " • Refined (2-pass)" : "";
          const where = assistantMsg.sources && assistantMsg.sources.length ? "On this PC, with web results" : "On this PC";
          assistantMsg.footer = `${friendlyModel(evt.model).label}${refInfo} • ${counts}${speed ? " • " + speed : ""}${memInfo} • ${where}`;
          renderMessages();
        } else if (evt.type === "aborted") {
          assistantMsg.footer = `Generation stopped by user (${evt.model})`;
          renderMessages();
        } else if (evt.type === "error") {
          assistantMsg.content += `\n[Error: ${evt.error}]`;
          assistantMsg.footer = "Error during local inference";
          renderMessages();
        }
      }
    }
  } catch (err) {
    if (err.name === "AbortError") {
      assistantMsg.footer = `Generation stopped by user (${chosenModel})`;
    } else {
      assistantMsg.content += `\n[Connection error: ${err.message}]`;
      assistantMsg.footer = "Failed to reach local server";
    }
    renderMessages();
  } finally {
    state.isStreaming = false;
    state.abortController = null;
    state.agentRunId = null;
    if (assistantMsg.agent && !assistantMsg.agent.done) {
      assistantMsg.agent.done = true;
      assistantMsg.agent.seconds = (Date.now() - assistantMsg.agent.startedAt) / 1000;
      assistantMsg.agent.changes = assistantMsg.agent.steps.filter((s) => s.changeId)
        .map((s) => ({ id: s.changeId, path: s.title.replace(/^(Writing|Editing) /, "") }));
      renderMessages();
    }
    document.getElementById("btn-send-chat").disabled = false;
    document.getElementById("btn-stop-gen").classList.add("hidden");

    if (state.saveHistory) {
      try {
        await fetch(`/api/chats/${encodeURIComponent(chatIdAtSend)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: messagesAtSend }),
        });
        await loadChatList();
      } catch (e) {
        console.error("Failed to save chat:", e);
      }
    }
    refreshStatus();
  }
}

async function retryAssistantTurn(assistantMsg, opts = {}) {
  if (state.isStreaming) return;
  const idx = state.messages.indexOf(assistantMsg);
  if (idx <= 0) return;
  const historyForApi = state.messages
    .slice(0, idx)
    .map((m) => {
      const out = { role: m.role, content: m.role === "assistant" ? splitThinking(m).answer : m.content };
      if (m.images) out.images = m.images;
      if (m.attached_file) out.attached_file = m.attached_file;
      return out;
    });
  const chosenModel = opts.model || assistantMsg.model || state.selectedModel;
  assistantMsg.content = "";
  assistantMsg.thinking = "";
  assistantMsg.thinkingOpen = undefined;
  assistantMsg.sources = [];
  assistantMsg.webStatus = opts.refine ? "Pass 1/2: Drafting & self-checking..." : `Re-running with ${friendlyModel(chosenModel).label}...`;
  assistantMsg.model = chosenModel;
  assistantMsg.refined = Boolean(opts.refine);
  assistantMsg.route = null;
  assistantMsg.footer = "Streaming locally from Ollama...";
  renderMessages();
  await streamIntoAssistantMsg(assistantMsg, historyForApi, { ...opts, agent: false });
}

// Submit chat prompt
document.getElementById("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (state.isStreaming) return;

  const shot = state.pendingScreenshot;
  const attachedFile = state.pendingFile;
  const defaultImgPrompt = state.pendingImageKind === "screenshot"
    ? "What's on my screen? Explain it and help me with what I'm doing."
    : "What is in this image? Explain it and help me with what it shows.";
  const defaultFilePrompt = attachedFile
    ? `Review ${attachedFile.name}, explain what it does, and point out any bugs or improvements.`
    : "";
  const text = chatInputEl.value.trim() || (shot ? defaultImgPrompt : defaultFilePrompt);
  if (!text) return;
  clearScreenshot();
  clearPendingFile();

  chatInputEl.value = "";
  autoResizeChatInput();
  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  if (!state.chatId) state.chatId = newChatId();
  const userMsg = { role: "user", content: text, timestamp: now };
  if (shot) userMsg.images = [shot];
  if (attachedFile) userMsg.attached_file = attachedFile;
  state.messages.push(userMsg);
  const assistantMsg = {
    role: "assistant",
    content: "",
    model: state.selectedModel,
    num_ctx: state.numCtx,
    timestamp: now,
    footer: "Streaming locally from Ollama...",
  };
  state.messages.push(assistantMsg);
  renderMessages();

  const historyForApi = state.messages
    .slice(0, -1)
    .map((m) => {
      const out = { role: m.role, content: m.role === "assistant" ? splitThinking(m).answer : m.content };
      if (m.images) out.images = m.images;
      if (m.attached_file) out.attached_file = m.attached_file;
      return out;
    });

  await streamIntoAssistantMsg(assistantMsg, historyForApi, { refine: state.refineMode });
});

// ==========================================
// PC ANALYST & WORKFLOW ENGINE LOGIC
// ==========================================

async function refreshTopProcesses() {
  const tbody = document.getElementById("procs-table-body");
  try {
    const resp = await fetch("/api/diagnostics/processes?limit=10");
    const data = await resp.json();
    if (data.collector) {
      document.getElementById("procs-collector-note").textContent = `Collector: ${data.collector}`;
    }
    if (!data.ok || !Array.isArray(data.processes) || data.processes.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4">${data.error || "No processes returned."}</td></tr>`;
      return;
    }
    tbody.innerHTML = "";
    for (const p of data.processes) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(p.name)}</strong></td>
        <td><code>${escapeHtml(p.pid)}</code></td>
        <td>${escapeHtml(p.memory_mb)} MB</td>
        <td>${escapeHtml(p.cpu_seconds ?? 0)} s</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4">Error loading process snapshot: ${escapeHtml(err.message)}</td></tr>`;
  }
}

document.getElementById("btn-refresh-procs").addEventListener("click", refreshTopProcesses);

async function loadWorkflowsAndRuns() {
  try {
    const resp = await fetch("/api/workflows");
    const data = await resp.json();
    state.workflowDefs = data.definitions || [];
    state.workflowRuns = data.runs || [];

    const sel = document.getElementById("wf-select");
    if (sel.options.length !== state.workflowDefs.length && state.workflowDefs.length > 0) {
      sel.innerHTML = "";
      for (const d of state.workflowDefs) {
        const opt = document.createElement("option");
        opt.value = d.id;
        opt.textContent = d.title;
        if (d.id === state.selectedWorkflowId) opt.selected = true;
        sel.appendChild(opt);
      }
    }
    renderSelectedWorkflowBlueprint();
    renderWorkflowHistory();

    if (!state.activeRunId && state.workflowRuns.length > 0) {
      state.activeRunId = state.workflowRuns[0].run_id;
    }
    if (state.activeRunId) {
      const current = state.workflowRuns.find((r) => r.run_id === state.activeRunId);
      renderActiveRun(current || null);
    }
  } catch (e) {
    console.error("Failed to load workflows:", e);
  }
}

document.getElementById("wf-select").addEventListener("change", (e) => {
  state.selectedWorkflowId = e.target.value;
  renderSelectedWorkflowBlueprint();
});

function renderSelectedWorkflowBlueprint() {
  const defn = state.workflowDefs.find((d) => d.id === state.selectedWorkflowId);
  if (!defn) return;

  document.getElementById("wf-desc").textContent = defn.description;
  document.getElementById("wf-trigger").textContent = defn.trigger;
  document.getElementById("wf-perm").textContent = defn.read_only ? "Read-only" : "Needs approval";
  document.getElementById("wf-approvals").textContent = (defn.approval_points || []).join(" ");

  const srcList = document.getElementById("wf-sources");
  srcList.innerHTML = "";
  for (const s of defn.allowed_sources || []) {
    const li = document.createElement("li");
    li.textContent = s;
    srcList.appendChild(li);
  }

  const stepsList = document.getElementById("wf-steps-blueprint");
  stepsList.innerHTML = "";
  for (const st of defn.steps || []) {
    const li = document.createElement("li");
    let badge = "[Deterministic]";
    if (st.kind === "ai_reasoning") badge = "[Local AI]";
    else if (st.kind === "approval_gate") badge = "[Approval Gate]";
    li.innerHTML = `<strong>${badge}</strong> ${escapeHtml(st.title)} <span class="text-muted">(${escapeHtml(st.tool_or_model)})</span>`;
    stepsList.appendChild(li);
  }

  const winEventsRow = document.getElementById("wf-row-win-events");
  if (defn.id === "pc_health_audit") {
    winEventsRow.classList.remove("hidden");
  } else {
    winEventsRow.classList.add("hidden");
  }
}

// Sample log helper button
document.getElementById("btn-use-sample-log").addEventListener("click", async () => {
  const resp = await fetch("/api/diagnostics/sample-log", { method: "POST" });
  const data = await resp.json();
  if (data.ok) {
    document.getElementById("wf-input-log-path").value = data.path;
    showToast(`Created sample log (${data.lines} lines) in loki/data/sample_system.log`);
  }
});

// Sample messy CSV helper button
document.getElementById("btn-use-sample-csv").addEventListener("click", async () => {
  const resp = await fetch("/api/diagnostics/sample-csv", { method: "POST" });
  const data = await resp.json();
  if (data.ok) {
    document.getElementById("wf-input-log-path").value = data.path;
    state.selectedWorkflowId = "clean_csv_to_new_copy";
    document.getElementById("wf-select").value = "clean_csv_to_new_copy";
    renderSelectedWorkflowBlueprint();
    showToast("Created sample messy CSV in loki/data/sample_messy_tasks.csv");
  }
});

// Preview log tail button
document.getElementById("btn-preview-log").addEventListener("click", async () => {
  const pathVal = document.getElementById("wf-input-log-path").value.trim();
  const box = document.getElementById("log-preview-box");
  if (!pathVal) {
    showToast("Enter a .log or .txt file path first (or click Use Sample Log)");
    return;
  }
  const resp = await fetch("/api/diagnostics/log-preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_path: pathVal, max_lines: 50 }),
  });
  const data = await resp.json();
  box.classList.remove("hidden");
  if (!data.ok) {
    box.textContent = `[Read Error] ${data.error}`;
  } else {
    box.textContent = `// ${data.resolved_path} (${data.lines_returned} lines, ${data.total_size_bytes} bytes)\n` + data.content;
  }
});

// Natural-Language Job-to-Workflow Planner
document.getElementById("btn-plan-workflow")?.addEventListener("click", async () => {
  const promptInput = document.getElementById("wf-nl-prompt-input");
  const reasonEl = document.getElementById("wf-planner-reason");
  const promptVal = (promptInput?.value || "").trim();
  if (!promptVal) {
    showToast("Describe your task in plain language first");
    return;
  }
  const resp = await fetch("/api/workflows/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: promptVal }),
  });
  const data = await resp.json();
  if (!resp.ok || !data.ok) {
    showToast(`Planner error: ${data.detail || data.error || "failed"}`);
    return;
  }

  state.selectedWorkflowId = data.matched_workflow_id;
  const sel = document.getElementById("wf-select");
  if (sel) sel.value = data.matched_workflow_id;
  renderSelectedWorkflowBlueprint();

  const sug = data.suggested_inputs || {};
  const pathVal =
    sug.project_folder_path || sug.target_folder_path || sug.csv_file_path || sug.log_file_path || "";
  if (pathVal) {
    document.getElementById("wf-input-log-path").value = pathVal;
  }
  if (sug.focus_question) {
    document.getElementById("wf-input-focus").value = sug.focus_question;
  }
  if (typeof sug.include_windows_events === "boolean") {
    document.getElementById("wf-input-win-events").checked = sug.include_windows_events;
  }

  if (reasonEl) {
    reasonEl.textContent = `Planner Matched '${data.workflow.title}': ${data.planner_reasoning}`;
    reasonEl.classList.remove("hidden");
  }
  showToast(`Configured workflow: ${data.workflow.title}`);
});

// Start workflow run manually
document.getElementById("btn-run-workflow").addEventListener("click", async () => {
  const wfId = state.selectedWorkflowId;
  const pathVal = document.getElementById("wf-input-log-path").value.trim();
  const inputs = {
    log_file_path: pathVal,
    csv_file_path: pathVal,
    project_folder_path: pathVal,
    target_folder_path: pathVal,
    include_windows_events: document.getElementById("wf-input-win-events").checked,
    focus_question: document.getElementById("wf-input-focus").value.trim(),
  };

  await startWorkflowRun(wfId, inputs);
});

async function startWorkflowRun(workflowId, inputs) {
  showToast(`Starting workflow '${workflowId}'...`);
  const resp = await fetch("/api/workflows/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow_id: workflowId,
      inputs: inputs,
      model: state.selectedModel,
      wait: false,
    }),
  });
  const data = await resp.json();
  if (!data.ok || !data.run) {
    showToast("Failed to start workflow");
    return;
  }
  state.activeRunId = data.run.run_id;
  renderActiveRun(data.run);
  startPollingActiveRun(data.run.run_id);
}

function startPollingActiveRun(runId) {
  clearInterval(state.wfPollTimer);
  state.wfPollTimer = setInterval(async () => {
    try {
      const resp = await fetch(`/api/workflows/runs/${runId}`);
      if (!resp.ok) return;
      const run = await resp.json();
      renderActiveRun(run);
      if (!["running", "paused"].includes(run.status)) {
        clearInterval(state.wfPollTimer);
        await loadWorkflowsAndRuns();
        await refreshStatus();
      }
    } catch (e) {
      console.error("Poll error:", e);
    }
  }, 1000);
}

// Pause / Resume workflow run
document.getElementById("btn-pause-workflow").addEventListener("click", async () => {
  if (!state.activeRunId) return;
  const btn = document.getElementById("btn-pause-workflow");
  const action = btn.textContent.trim().toLowerCase() === "pause" ? "pause" : "resume";
  await fetch(`/api/workflows/runs/${state.activeRunId}/pause`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  showToast(`Workflow ${action}d`);
});

// Cancel workflow run
document.getElementById("btn-cancel-workflow").addEventListener("click", async () => {
  if (!state.activeRunId) return;
  await fetch(`/api/workflows/runs/${state.activeRunId}/cancel`, { method: "POST" });
  showToast("Cancelled workflow run");
});

// Clear workflow history
document.getElementById("btn-clear-wf-history").addEventListener("click", async () => {
  await fetch("/api/workflows/runs", { method: "DELETE" });
  state.workflowRuns = [];
  state.activeRunId = null;
  renderWorkflowHistory();
  renderActiveRun(null);
  showToast("Cleared workflow run history");
  refreshStatus();
});

function renderActiveRun(run) {
  const titleEl = document.getElementById("wf-active-title");
  const badgeEl = document.getElementById("wf-active-badge");
  const bodyEl = document.getElementById("wf-active-body");
  const pauseBtn = document.getElementById("btn-pause-workflow");
  const cancelBtn = document.getElementById("btn-cancel-workflow");
  const runBtn = document.getElementById("btn-run-workflow");

  if (!run) {
    titleEl.textContent = "Workflow Execution & Step Inspector";
    badgeEl.className = "status-pill st-pending";
    badgeEl.textContent = "IDLE";
    bodyEl.innerHTML = `<p class="text-muted">No workflow run selected yet. Start a manual run above or click a run in history below.</p>`;
    pauseBtn.classList.add("hidden");
    cancelBtn.classList.add("hidden");
    runBtn.disabled = false;
    return;
  }

  titleEl.textContent = `${run.workflow_title} (${run.run_id})`;
  badgeEl.className = `status-pill st-${run.status}`;
  badgeEl.textContent = run.status.toUpperCase();

  const isRunningOrPaused = ["running", "paused"].includes(run.status);
  runBtn.disabled = isRunningOrPaused;
  if (isRunningOrPaused) {
    pauseBtn.classList.remove("hidden");
    cancelBtn.classList.remove("hidden");
    pauseBtn.textContent = run.status === "paused" ? "Resume" : "Pause";
  } else {
    pauseBtn.classList.add("hidden");
    cancelBtn.classList.add("hidden");
  }

  const act = run.activity_summary || {};
  let html = `
    <div class="kv-list" style="margin-bottom:14px">
      <div class="kv-row">
        <span>Model / Provider</span>
        <strong>${escapeHtml(act.provider || "ollama (local)")} &bull; ${escapeHtml(act.model || state.selectedModel)} (ctx ${act.num_ctx || state.numCtx})</strong>
      </div>
      <div class="kv-row">
        <span>Tools Invoked</span>
        <code>${escapeHtml((act.tools_used || []).join(", ") || "None yet")}</code>
      </div>
      <div class="kv-row">
        <span>Data Left PC?</span>
        <strong class="text-green">${act.data_left_pc ? "YES" : "NO (100% Localhost)"}</strong>
      </div>
    </div>
  `;

  if (run.error) {
    html += `<div class="step-card" style="border-color:var(--accent-coral);color:#ff8b82"><strong>Workflow Halted Safely:</strong> ${escapeHtml(run.error)}</div>`;
  }

  if (run.approved_output_path) {
    html += `
      <div class="step-card" style="border-color:rgba(16,163,127,0.45);background:rgba(16,163,127,0.07)">
        <strong class="text-green">Saved new copy:</strong>
        <code style="margin-left:6px">${escapeHtml(run.approved_output_path)}</code>
      </div>
    `;
  }

  if (run.status === "awaiting_approval" && run.pending_approval) {
    const pa = run.pending_approval;
    html += `
      <div class="approval-gate-card">
        <h4>Review before saving</h4>
        <div class="kv-list" style="margin-bottom:10px">
          <div class="kv-row"><span>Action</span> <strong>Create New File Copy (Never overwrites or deletes originals)</strong></div>
          <div class="kv-row"><span>Destination Path</span> <code>${escapeHtml(pa.target_path)}</code></div>
          <div class="kv-row"><span>Size</span> <span>${escapeHtml(pa.byte_size)} bytes</span></div>
          <div class="kv-row"><span>Diff / Summary</span> <span>${escapeHtml(pa.diff_summary)}</span></div>
        </div>
        <strong class="sub-heading">Preview of New File Content:</strong>
        <div class="code-preview" style="margin-bottom:12px">${escapeHtml(pa.preview_content)}</div>
        <div class="wf-controls-bar">
          <button type="button" class="btn btn-primary btn-decide-approval" data-apr-id="${escapeHtml(pa.approval_id)}" data-decision="approve">
            Approve and save copy
          </button>
          <button type="button" class="btn btn-danger btn-decide-approval" data-apr-id="${escapeHtml(pa.approval_id)}" data-decision="reject">
            Reject
          </button>
        </div>
      </div>
    `;
  }

  for (const st of run.steps || []) {
    const dur = st.duration_ms !== null && st.duration_ms !== undefined ? `${st.duration_ms} ms` : "";
    html += `
      <div class="step-card">
        <div class="step-header">
          <div>
            <strong>${escapeHtml(st.title)}</strong>
            <span class="step-meta">&bull; ${escapeHtml(st.kind)} (${escapeHtml(st.tool_or_model)}) ${dur ? "&bull; " + dur : ""}</span>
          </div>
          <span class="status-pill st-${st.status}">${escapeHtml(st.status)}</span>
        </div>
        ${st.summary ? `<div class="step-meta">${escapeHtml(st.summary)}</div>` : ""}
        ${st.error ? `<div style="color:#ff8b82;margin-top:4px;font-size:12.5px"><strong>Step Error:</strong> ${escapeHtml(st.error)}</div>` : ""}
        ${
          st.output_preview
            ? `<details class="step-details"><summary>Inspect step output</summary><div class="code-preview mt-8">${escapeHtml(st.output_preview)}</div></details>`
            : ""
        }
      </div>
    `;
  }

  if (run.final_output) {
    html += `
      <div class="mt-12">
        <strong class="sub-heading">Final Local AI Report (${escapeHtml(act.model || "")})</strong>
        <div class="ai-report-box">${renderMarkdown(run.final_output)}</div>
      </div>
    `;
  }

  bodyEl.innerHTML = html;

  bodyEl.querySelectorAll(".btn-decide-approval").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const aprId = btn.getAttribute("data-apr-id");
      const decision = btn.getAttribute("data-decision");
      const resp = await fetch(`/api/approvals/${aprId}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        showToast(`Approval error: ${data.detail || data.error || "failed"}`);
        return;
      }
      showToast(
        decision === "approve"
          ? `Approved! Saved new copy to ${data.written_path}`
          : "Rejected — no file was written to disk"
      );
      await loadWorkflowsAndRuns();
      await refreshStatus();
    });
  });
}

function renderWorkflowHistory() {
  const tbody = document.getElementById("wf-history-body");
  tbody.innerHTML = "";
  if (!state.workflowRuns || state.workflowRuns.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7">No workflow runs recorded yet.</td></tr>`;
    return;
  }

  for (const r of state.workflowRuns) {
    const act = r.activity_summary || {};
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><code>${escapeHtml(r.run_id)}</code></td>
      <td><strong>${escapeHtml(r.workflow_title)}</strong></td>
      <td>${escapeHtml(r.created_at || "")}</td>
      <td><span class="status-pill st-${r.status}">${escapeHtml(r.status)}</span></td>
      <td><small>${escapeHtml(act.model || "")} (${(act.tools_used || []).length} tools)</small></td>
      <td><span class="text-green">No (Local)</span></td>
      <td>
        <button class="btn btn-sm btn-secondary btn-inspect-run" data-run-id="${escapeHtml(r.run_id)}">Inspect</button>
        <button class="btn btn-sm btn-secondary btn-retry-run" data-run-id="${escapeHtml(r.run_id)}">Retry</button>
      </td>
    `;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll(".btn-inspect-run").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-run-id");
      state.activeRunId = id;
      const found = state.workflowRuns.find((x) => x.run_id === id);
      renderActiveRun(found || null);
    });
  });

  tbody.querySelectorAll(".btn-retry-run").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-run-id");
      const found = state.workflowRuns.find((x) => x.run_id === id);
      if (found) {
        await startWorkflowRun(found.workflow_id, found.inputs || {});
      }
    });
  });
}

// ==========================================
// DOCUMENT Q&A & LOCAL INDEXER LOGIC
// ==========================================

async function loadDocsStatus() {
  try {
    const resp = await fetch("/api/docs/status");
    const summary = await resp.json();
    renderDocsSummary(summary);
  } catch (e) {
    console.error("Failed to load docs status:", e);
  }
}

function renderDocsSummary(summary) {
  if (!summary) return;
  state.docsSummary = summary;

  const folders = summary.enabled_folders || [];
  const files = summary.indexed_files || [];
  const paused = Boolean(summary.indexing_paused);

  document.getElementById("docs-folder-count").textContent = `${folders.length}`;
  document.getElementById("docs-file-count").textContent = `${summary.indexed_files_count || 0}`;
  document.getElementById("docs-chunk-count").textContent = `${summary.indexed_chunks_count || 0}`;
  document.getElementById("docs-db-path").textContent = summary.index_db_path || "loki/data/index.db";

  const badge = document.getElementById("docs-pause-badge");
  const pauseBtn = document.getElementById("btn-toggle-pause-docs");
  if (paused) {
    badge.className = "status-pill st-paused";
    badge.textContent = "Paused";
    pauseBtn.textContent = "Resume access";
  } else {
    badge.className = "status-pill st-completed";
    badge.textContent = "Active";
    pauseBtn.textContent = "Pause access";
  }

  const fTbody = document.getElementById("docs-folders-tbody");
  fTbody.innerHTML = "";
  if (folders.length === 0) {
    fTbody.innerHTML = `<tr><td colspan="2">No folders approved yet.</td></tr>`;
  } else {
    for (const folder of folders) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code>${escapeHtml(folder)}</code></td>
        <td>
          <button class="btn btn-sm btn-danger btn-remove-folder" data-folder="${escapeHtml(folder)}">
            Remove Folder
          </button>
        </td>
      `;
      fTbody.appendChild(tr);
    }
  }

  fTbody.querySelectorAll(".btn-remove-folder").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const folderPath = btn.getAttribute("data-folder");
      const resp = await fetch("/api/docs/folders/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_path: folderPath }),
      });
      const data = await resp.json();
      renderDocsSummary(data.summary);
      showToast(`Removed folder from allowlist and index`);
      refreshStatus();
    });
  });

  const filesTbody = document.getElementById("docs-files-tbody");
  filesTbody.innerHTML = "";
  if (files.length === 0) {
    filesTbody.innerHTML = `<tr><td colspan="6">No files currently indexed.</td></tr>`;
  } else {
    for (const f of files) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(f.file_name)}</strong></td>
        <td><code>${escapeHtml(f.relative_path)}</code></td>
        <td><small><code>${escapeHtml(f.folder_path)}</code></small></td>
        <td>${f.size_bytes} B</td>
        <td>${f.chunk_count}</td>
        <td>
          <button class="btn btn-sm btn-secondary btn-remove-file" data-file="${escapeHtml(f.file_path)}">
            Remove File
          </button>
        </td>
      `;
      filesTbody.appendChild(tr);
    }
  }

  filesTbody.querySelectorAll(".btn-remove-file").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const filePath = btn.getAttribute("data-file");
      const resp = await fetch("/api/docs/files/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: filePath }),
      });
      const data = await resp.json();
      renderDocsSummary(data.summary);
      showToast(`Removed file from index`);
    });
  });
}

document.getElementById("btn-add-docs-folder").addEventListener("click", async () => {
  const pathVal = document.getElementById("docs-folder-input").value.trim();
  if (!pathVal) {
    showToast("Enter a folder path to index");
    return;
  }
  await addAndIndexFolder(pathVal);
});

document.getElementById("btn-add-sample-docs").addEventListener("click", async () => {
  const sampleFolder = state.docsSummary && state.docsSummary.sample_docs_folder;
  if (!sampleFolder) return;
  document.getElementById("docs-folder-input").value = sampleFolder;
  await addAndIndexFolder(sampleFolder);
});

async function addAndIndexFolder(folderPath) {
  showToast(`Indexing folder: ${folderPath}...`);
  const resp = await fetch("/api/docs/folders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_path: folderPath }),
  });
  const data = await resp.json();
  if (!data.ok) {
    showToast(`Index error: ${data.error}`);
    return;
  }
  renderDocsSummary(data.summary);
  showToast(`Indexed ${data.files_indexed} files (${data.chunks_created} chunks)`);
  refreshStatus();
}

document.getElementById("btn-toggle-pause-docs").addEventListener("click", async () => {
  const currentlyPaused = state.docsSummary ? Boolean(state.docsSummary.indexing_paused) : false;
  const resp = await fetch("/api/docs/pause", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paused: !currentlyPaused }),
  });
  const data = await resp.json();
  renderDocsSummary(data.summary);
  showToast(data.indexing_paused ? "Document index access PAUSED" : "Document index access RESUMED");
});

document.getElementById("btn-reindex-docs").addEventListener("click", async () => {
  showToast("Re-indexing approved folders...");
  const resp = await fetch("/api/docs/reindex", { method: "POST" });
  const data = await resp.json();
  renderDocsSummary(data.summary);
  showToast(`Re-indexed ${data.files_indexed} files (${data.chunks_created} chunks)`);
});

document.getElementById("btn-clear-docs-index").addEventListener("click", async () => {
  const resp = await fetch("/api/docs/clear", { method: "POST" });
  const data = await resp.json();
  renderDocsSummary(data.summary);
  document.getElementById("docs-answer-container").innerHTML =
    `<p class="text-muted">Index cleared. Add a folder to index files locally.</p>`;
  showToast("Cleared document index and folder allowlist");
  refreshStatus();
});

document.getElementById("btn-search-docs-only").addEventListener("click", async () => {
  const q = document.getElementById("docs-question-input").value.trim();
  if (!q) {
    showToast("Enter a search query first");
    return;
  }
  const container = document.getElementById("docs-answer-container");
  container.innerHTML = `<p class="text-muted">Searching local SQLite + TF-IDF index...</p>`;
  const resp = await fetch("/api/docs/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: q, top_k: 5 }),
  });
  const data = await resp.json();
  if (!data.ok) {
    container.innerHTML = `<div class="step-card" style="border-color:var(--accent-coral);color:#ff8b82"><strong>Search Blocked / Error:</strong> ${escapeHtml(data.error)}</div>`;
    return;
  }
  renderDocsCitationsOnly(data.results || [], data.total_chunks_searched || 0);
});

document.getElementById("btn-ask-docs").addEventListener("click", async () => {
  const q = document.getElementById("docs-question-input").value.trim();
  if (!q) {
    showToast("Enter a question first");
    return;
  }
  const container = document.getElementById("docs-answer-container");
  const askBtn = document.getElementById("btn-ask-docs");
  askBtn.disabled = true;
  container.innerHTML = `<p class="text-muted">Retrieving passages and generating cited answer with local Ollama (${escapeHtml(state.selectedModel)})...</p>`;

  try {
    const resp = await fetch("/api/docs/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, top_k: 4, model: state.selectedModel }),
    });
    const data = await resp.json();
    if (!data.ok) {
      container.innerHTML = `<div class="step-card" style="border-color:var(--accent-coral);color:#ff8b82"><strong>Document Q&amp;A Error:</strong> ${escapeHtml(data.error)}</div>`;
      return;
    }

    const speed = data.tokens_per_sec ? ` &bull; ${data.tokens_per_sec} tok/s` : "";
    let html = `
      <div class="ai-report-box">
        <div class="step-header" style="margin-bottom:8px">
          <span class="model-sub-pill">LOCAL &bull; ollama / ${escapeHtml(data.model || state.selectedModel)}${speed}</span>
          <span class="text-green" style="font-size:11.5px;font-weight:600">Untrusted-Data Isolated &bull; 0 Bytes Left PC</span>
        </div>
        ${renderMarkdown(data.answer)}
      </div>
    `;
    html += buildCitationsHtml(data.citations || []);
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<div class="step-card" style="border-color:var(--accent-coral);color:#ff8b82">Error: ${escapeHtml(err.message)}</div>`;
  } finally {
    askBtn.disabled = false;
    refreshStatus();
  }
});

function renderDocsCitationsOnly(citations, totalSearched) {
  const container = document.getElementById("docs-answer-container");
  container.innerHTML =
    `<div class="step-meta" style="margin-bottom:8px">Searched ${totalSearched} indexed chunks (Deterministic TF-IDF + Keyword Search, No AI invoked):</div>` +
    buildCitationsHtml(citations);
}

function buildCitationsHtml(citations) {
  if (!citations || citations.length === 0) {
    return `<p class="text-muted mt-8">No matching passages found.</p>`;
  }
  let html = `<div class="mt-12"><strong class="sub-heading">Cited Source Passages (${citations.length})</strong>`;
  for (const c of citations) {
    html += `
      <div class="step-card">
        <div class="step-header">
          <span class="cite-pill">${escapeHtml(c.citation)}</span>
          <span class="step-meta">Score: ${c.score} &bull; ${escapeHtml(c.file_name)} (Lines ${c.start_line}&ndash;${c.end_line})</span>
        </div>
        <details class="step-details">
          <summary>View passage text (${escapeHtml(c.file_path)})</summary>
          <div class="code-preview mt-8">${escapeHtml(c.content)}</div>
        </details>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

// ==========================================
// SYSTEM STATUS POLLING
// ==========================================

async function refreshStatus() {
  try {
    const resp = await fetch("/api/status");
    const data = await resp.json();

    const { ollama, hardware, settings, storage } = data;

    const dot = document.getElementById("ollama-conn-dot");
    const text = document.getElementById("ollama-conn-text");
    const startBtn = document.getElementById("btn-start-ollama");

    if (ollama.connected) {
      dot.className = "dot dot-green";
      text.textContent = `Ollama v${ollama.version || "local"}`;
      startBtn.classList.add("hidden");
    } else {
      dot.className = "dot dot-red";
      text.textContent = "Ollama Offline";
      startBtn.classList.remove("hidden");
    }

    const webChk = document.getElementById("chk-web-access");
    if (document.activeElement !== webChk) {
      webChk.checked = settings.web_access !== false;
      document.getElementById("web-access-state").textContent = webChk.checked ? "On" : "Off";
    }
    const webOn = settings.web_access !== false;
    document.getElementById("privacy-pill-detail").textContent = webOn ? "AI on this PC \u00b7 Web search on" : "AI on this PC \u00b7 Offline";
    document.getElementById("composer-footnote-text").textContent = webOn
      ? "AI runs on this PC. Only web search text leaves it."
      : "AI runs on this PC. Web search is off.";

    const autoChk = document.getElementById("chk-auto-model");
    if (typeof settings.auto_model_routing === "boolean" && document.activeElement !== autoChk) {
      state.autoRoute = settings.auto_model_routing;
      autoChk.checked = state.autoRoute;
    }

    const modelSelect = document.getElementById("select-model");
    if (ollama.installed_models && ollama.installed_models.length > 0) {
      const currentVal = settings.selected_model || state.selectedModel;
      // Skip rebuilding while the menu is open, so the 4 s refresh never closes it.
      const rebuild = !modelPicker.isOpen();
      state.modelFit = {};
      for (const m of ollama.installed_models) {
        state.modelFit[m.name] = { fit: m.vram_fit || "unknown", label: m.vram_fit_label || "" };
      }
      if (rebuild) {
        modelSelect.innerHTML = "";
        // Group by VRAM fit: models that fit first, then tight / too-big ones (largest last).
        const groups = [
          { key: "fits", label: "Fits your GPU (fast)" },
          { key: "tight", label: "Tight fit (may be slower)" },
          { key: "offload", label: "Too big for GPU (slower)" },
          { key: "unknown", label: "Installed models" },
        ];
        for (const g of groups) {
          const models = ollama.installed_models
            .filter((m) => (m.vram_fit || "unknown") === g.key)
            .sort((a, b) => (b.size_gb || 0) - (a.size_gb || 0));
          if (models.length === 0) continue;
          const og = document.createElement("optgroup");
          og.label = g.label;
          for (const m of models) {
            const opt = document.createElement("option");
            opt.value = m.name;
            const quant = m.quantization_level ? ` • ${m.quantization_level}` : "";
            const warn = m.vram_fit === "offload" ? " (slower)" : m.vram_fit === "tight" ? " (tight fit)" : "";
            opt.textContent = `${m.name} (${m.size_gb} GB${quant})${warn}`;
            opt.title = m.vram_fit_label || "";
            if (m.name === currentVal) opt.selected = true;
            og.appendChild(opt);
          }
          modelSelect.appendChild(og);
        }
      }
      state.selectedModel = modelSelect.value;
      if (rebuild) modelPicker.render(ollama.installed_models);
    }

    const runningList = ollama.running_models || [];
    const vramBox = document.getElementById("sidebar-vram-status");
    if (runningList.length > 0) {
      const desc = runningList.map((r) => `${r.name} (${r.size_vram_mb} MiB ${r.processor})`).join(", ");
      vramBox.textContent = `Loaded: ${desc}`;
      document.getElementById("st-vram-models").textContent = desc;
    } else {
      vramBox.textContent = "VRAM: No model loaded (0 MiB)";
      document.getElementById("st-vram-models").textContent = "None (0 MiB used by Ollama)";
    }

    if (hardware.cpu && hardware.cpu.available) {
      const cpuPct = hardware.cpu.load_percent ?? 0;
      document.getElementById("mini-cpu-val").textContent = `${cpuPct}%`;
      document.getElementById("mini-cpu-bar").style.width = `${Math.min(100, cpuPct)}%`;
      document.getElementById("st-cpu-percent").textContent = `${cpuPct}%`;
      document.getElementById("st-cpu-bar").style.width = `${Math.min(100, cpuPct)}%`;
      document.getElementById("st-cpu-name").textContent = hardware.cpu.name;
      document.getElementById("st-cpu-collector").textContent = `Collector: ${hardware.cpu.collector}`;
    }

    if (hardware.ram && hardware.ram.available) {
      const { used_gb, total_gb, available_gb, load_percent } = hardware.ram;
      document.getElementById("mini-ram-val").textContent = `${used_gb} / ${total_gb} GB`;
      document.getElementById("mini-ram-bar").style.width = `${Math.min(100, load_percent)}%`;
      document.getElementById("st-ram-summary").textContent = `${used_gb} / ${total_gb} GB`;
      document.getElementById("st-ram-bar").style.width = `${Math.min(100, load_percent)}%`;
      document.getElementById("st-ram-percent").textContent = `${load_percent}%`;
      document.getElementById("st-ram-avail").textContent = `${available_gb} GB`;
      document.getElementById("st-ram-collector").textContent = `Collector: ${hardware.ram.collector}`;
    }

    if (hardware.gpu && hardware.gpu.available) {
      const { name, load_percent, vram_used_mib, vram_free_mib, vram_total_mib, vram_percent, temperature_c } =
        hardware.gpu;
      document.getElementById("mini-vram-val").textContent = `${vram_used_mib} / ${vram_total_mib} MiB`;
      document.getElementById("mini-vram-bar").style.width = `${Math.min(100, vram_percent)}%`;
      document.getElementById("st-gpu-vram").textContent = `${vram_used_mib} / ${vram_total_mib} MiB`;
      document.getElementById("st-gpu-vram-bar").style.width = `${Math.min(100, vram_percent)}%`;
      document.getElementById("st-gpu-name").textContent = name;
      document.getElementById("st-gpu-util").textContent = `${load_percent}%`;
      document.getElementById("st-gpu-temp").textContent = temperature_c !== null ? `${temperature_c} °C` : "N/A";
      document.getElementById("st-gpu-free").textContent = `${vram_free_mib} MiB`;
      document.getElementById("st-gpu-collector").textContent = `Collector: ${hardware.gpu.collector}`;
    }

    document.getElementById("st-ollama-state").textContent = ollama.connected ? "Connected (Localhost)" : "Offline";
    document.getElementById("st-ollama-url").textContent = ollama.base_url;
    document.getElementById("st-ollama-ver").textContent = ollama.version || "N/A";
    document.getElementById("st-selected-model").textContent = state.selectedModel;
    document.getElementById("st-ctx-len").textContent = `${state.numCtx} tokens`;

    const tbody = document.getElementById("models-table-body");
    tbody.innerHTML = "";
    if ((ollama.installed_models || []).length === 0) {
      tbody.innerHTML = `<tr><td colspan="6">No models reported by Ollama.</td></tr>`;
    } else {
      for (const m of ollama.installed_models) {
        const tr = document.createElement("tr");
        const isSel = m.name === state.selectedModel;
        tr.innerHTML = `
          <td><strong>${escapeHtml(m.name)}</strong></td>
          <td>${escapeHtml(m.family || "-")}</td>
          <td>${escapeHtml(m.parameter_size || "-")}</td>
          <td><code>${escapeHtml(m.quantization_level || "-")}</code></td>
          <td>${escapeHtml(m.size_gb)} GB<span class="fit-tag fit-${escapeHtml(m.vram_fit || "unknown")}" title="${escapeHtml(m.vram_fit_label || "")}">${escapeHtml({ fits: "fits GPU", tight: "tight", offload: "partly CPU", unknown: "" }[m.vram_fit || "unknown"])}</span></td>
          <td>${isSel ? '<span class="tag-locked">Selected</span>' : ""}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    if (storage) {
      document.getElementById("priv-data-dir").textContent = storage.data_directory;
      const pbody = document.getElementById("privacy-files-body");
      pbody.innerHTML = "";
      if (!storage.files || storage.files.length === 0) {
        pbody.innerHTML = `<tr><td colspan="4">No files stored in loki/data/</td></tr>`;
      } else {
        for (const f of storage.files) {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td><strong>${escapeHtml(f.name)}</strong></td>
            <td><code>${escapeHtml(f.relative_path)}</code></td>
            <td><code>${escapeHtml(f.absolute_path)}</code></td>
            <td>${escapeHtml(f.size_bytes)} B</td>
          `;
          pbody.appendChild(tr);
        }
      }
    }

    if (Array.isArray(data.memories)) {
      renderMemoriesTable(data.memories, settings.use_memories_in_chat !== false);
    }

    if (data.cloud_gateway || data.activity_ledger) {
      renderCloudGatewayAndLedger(data.cloud_gateway, data.activity_ledger);
    }

    if (data.scheduler) {
      renderSchedulerState(data.scheduler);
    }
  } catch (err) {
    console.error("Status poll error:", err);
  }
}

// ==========================================
// CLOUD PRIVACY GATE & ACTIVITY/COST LEDGER
// ==========================================

function renderCloudGatewayAndLedger(cg, ledger) {
  if (cg) {
    state.cloudGateway = cg;
    const globalOn = Boolean(cg.cloud_global_opt_in);
    const globalBadge = document.getElementById("cg-global-badge");
    const globalBtn = document.getElementById("btn-toggle-cloud-global");
    if (globalBadge) {
      globalBadge.className = globalOn ? "status-pill st-paused" : "tag-locked";
      globalBadge.textContent = globalOn ? "Allowed" : "Off";
    }
    if (globalBtn) {
      globalBtn.textContent = globalOn ? "Turn off cloud AI" : "Allow cloud AI";
    }

    for (const provKey of ["openai", "anthropic", "gemini"]) {
      const p = (cg.providers || {})[provKey];
      if (!p) continue;
      const envEl = document.getElementById(`cg-env-${provKey}`);
      const btnEl = document.getElementById(`cg-btn-${provKey}`);
      if (envEl) {
        envEl.textContent = p.api_key_in_env ? "Key found" : "No key";
        envEl.className = p.api_key_in_env ? "text-green" : "text-muted";
      }
      if (btnEl) {
        btnEl.textContent = p.enabled ? "Enabled" : "Disabled";
        btnEl.className = p.enabled
          ? "btn btn-sm btn-warning btn-toggle-cloud-prov"
          : "btn btn-sm btn-secondary btn-toggle-cloud-prov";
      }
    }
  }

  if (ledger) {
    const locEl = document.getElementById("led-local-count");
    const blkEl = document.getElementById("led-blocked-count");
    const cldEl = document.getElementById("led-cloud-count");
    const bytEl = document.getElementById("led-ext-bytes");
    const cstEl = document.getElementById("led-est-cost");

    if (locEl) locEl.textContent = `${ledger.local_calls_count || 0}`;
    if (blkEl) blkEl.textContent = `${ledger.blocked_cloud_attempts || 0}`;
    if (cldEl) cldEl.textContent = `${ledger.cloud_calls_count || 0}`;
    const webEl = document.getElementById("led-web-count");
    if (webEl) webEl.textContent = `${ledger.web_requests_count || 0}`;
    if (bytEl) bytEl.textContent = `${ledger.total_bytes_sent_external || 0} B`;
    if (cstEl) cstEl.textContent = `$${Number(ledger.total_estimated_cost_usd || 0).toFixed(6)}`;

    const tbody = document.getElementById("activity-ledger-body");
    if (tbody) {
      tbody.innerHTML = "";
      const entries = ledger.entries || [];
      if (entries.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8">No gateway activity recorded yet.</td></tr>`;
      } else {
        for (const e of entries.slice(0, 25)) {
          const tr = document.createElement("tr");
          const leftPcHtml = e.data_left_pc
            ? `<strong style="color:#ff8b82">YES (${e.bytes_sent_external || 0} B)</strong>`
            : `<span class="text-green">No (0 B)</span>`;
          tr.innerHTML = `
            <td><small>${escapeHtml(e.timestamp || "")}</small></td>
            <td><span class="cite-pill">${escapeHtml(e.kind || "chat")}</span></td>
            <td><strong>${escapeHtml(e.provider || "")}</strong> / <code>${escapeHtml(e.model || "")}</code></td>
            <td><span class="status-pill ${e.status === "completed" ? "st-completed" : "st-failed"}">${escapeHtml(e.status || "")}</span></td>
            <td>${e.prompt_tokens || 0} / ${e.eval_tokens || 0}</td>
            <td>${leftPcHtml}</td>
            <td><code>$${Number(e.estimated_cost_usd || 0).toFixed(6)}</code></td>
            <td><small>${escapeHtml(e.detail || "")}</small></td>
          `;
          tbody.appendChild(tr);
        }
      }
    }
  }
}

document.getElementById("btn-toggle-cloud-global")?.addEventListener("click", async () => {
  const current = state.cloudGateway ? Boolean(state.cloudGateway.cloud_global_opt_in) : false;
  const resp = await fetch("/api/cloud/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cloud_global_opt_in: !current }),
  });
  const data = await resp.json();
  if (data.ok) {
    renderCloudGatewayAndLedger(data.cloud_gateway, null);
    showToast(
      !current
        ? "Switch 1 (Global Cloud Opt-In) enabled. Individual providers remain disabled until toggled."
        : "Global Cloud Opt-In disabled — locked to 100% Local-Only."
    );
  }
});

document.querySelectorAll(".btn-toggle-cloud-prov").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const prov = btn.getAttribute("data-prov");
    const current =
      state.cloudGateway &&
      state.cloudGateway.providers &&
      state.cloudGateway.providers[prov]
        ? Boolean(state.cloudGateway.providers[prov].enabled)
        : false;
    const resp = await fetch("/api/cloud/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: prov, enabled: !current }),
    });
    const data = await resp.json();
    if (data.ok) {
      renderCloudGatewayAndLedger(data.cloud_gateway, null);
      showToast(`Provider '${prov}' ${!current ? "enabled" : "disabled"}`);
    }
  });
});

document.getElementById("btn-clear-ledger")?.addEventListener("click", async () => {
  const resp = await fetch("/api/activity/ledger", { method: "DELETE" });
  const data = await resp.json();
  if (data.ok) {
    renderCloudGatewayAndLedger(null, data.summary);
    showToast("Cleared Model Gateway Activity & Cost Ledger");
  }
});

// ==========================================
// PERSONAL & PROJECT MEMORY MANAGEMENT
// ==========================================

function renderMemoriesTable(memories, useMemoriesInChat) {
  state.memories = memories || [];
  state.useMemoriesInChat = Boolean(useMemoriesInChat);

  const activeCount = state.memories.filter((m) => m.enabled).length;
  const chk = document.getElementById("chk-use-memories");
  const lbl = document.getElementById("composer-mem-label");
  if (chk) chk.checked = state.useMemoriesInChat;
  if (lbl) lbl.textContent = `Memories (${activeCount})`;

  const tbody = document.getElementById("memories-table-body");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (state.memories.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5">No memories stored yet. Add an explicit memory above.</td></tr>`;
    return;
  }

  for (const m of state.memories) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="cite-pill">${escapeHtml(m.category || "personal")}</span></td>
      <td><strong>${escapeHtml(m.title || "")}</strong></td>
      <td>${escapeHtml(m.content || "")}</td>
      <td>
        <span class="status-pill ${m.enabled ? "st-completed" : "st-paused"}">
          ${m.enabled ? "Active" : "Paused"}
        </span>
      </td>
      <td>
        <button class="btn btn-sm btn-secondary btn-toggle-mem" data-mem-id="${escapeHtml(m.memory_id)}" data-enabled="${m.enabled ? "true" : "false"}">
          ${m.enabled ? "Pause" : "Enable"}
        </button>
        <button class="btn btn-sm btn-danger btn-del-mem" data-mem-id="${escapeHtml(m.memory_id)}">
          Delete
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll(".btn-toggle-mem").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const memId = btn.getAttribute("data-mem-id");
      const currentlyEnabled = btn.getAttribute("data-enabled") === "true";
      const resp = await fetch(`/api/memories/${memId}/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !currentlyEnabled }),
      });
      const data = await resp.json();
      if (data.ok) {
        renderMemoriesTable(data.memories, state.useMemoriesInChat);
        showToast(!currentlyEnabled ? "Memory enabled for chat" : "Memory paused");
      }
    });
  });

  tbody.querySelectorAll(".btn-del-mem").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const memId = btn.getAttribute("data-mem-id");
      const resp = await fetch(`/api/memories/${memId}`, { method: "DELETE" });
      const data = await resp.json();
      if (data.ok) {
        renderMemoriesTable(data.memories, state.useMemoriesInChat);
        showToast("Deleted memory");
      }
    });
  });
}

document.getElementById("btn-add-memory")?.addEventListener("click", async () => {
  const titleInput = document.getElementById("mem-title-input");
  const contentInput = document.getElementById("mem-content-input");
  const catSelect = document.getElementById("mem-category-select");
  const titleVal = (titleInput?.value || "").trim();
  const contentVal = (contentInput?.value || "").trim();
  const catVal = catSelect?.value || "personal";
  if (!titleVal || !contentVal) {
    showToast("Enter both a short title and memory content first");
    return;
  }
  const resp = await fetch("/api/memories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: titleVal, content: contentVal, category: catVal }),
  });
  const data = await resp.json();
  if (!resp.ok || !data.ok) {
    showToast(`Failed to add memory: ${data.detail || data.error || "error"}`);
    return;
  }
  titleInput.value = "";
  contentInput.value = "";
  renderMemoriesTable(data.memories, state.useMemoriesInChat);
  showToast(`Saved explicit ${catVal} memory (${data.memory.memory_id})`);
});

document.getElementById("btn-clear-memories")?.addEventListener("click", async () => {
  const resp = await fetch("/api/memories", { method: "DELETE" });
  const data = await resp.json();
  if (data.ok) {
    renderMemoriesTable([], state.useMemoriesInChat);
    showToast("Cleared all stored memories");
  }
});

// ==========================================
// OPT-IN SCHEDULED AUTOMATION & GUARDRAILS
// ==========================================

function renderSchedulerState(sch) {
  if (!sch) return;
  state.scheduler = sch;

  const globalOn = Boolean(sch.scheduler_enabled);
  const badge = document.getElementById("sch-global-badge");
  const toggleBtn = document.getElementById("btn-toggle-sch-global");
  const guardEl = document.getElementById("sch-guardrail-status");

  if (badge) {
    badge.className = globalOn ? "status-pill st-completed" : "tag-locked";
    badge.textContent = globalOn ? "OPT-IN ENABLED" : "OFF (Disabled by Default)";
  }
  if (toggleBtn) {
    toggleBtn.textContent = globalOn ? "Disable Scheduled Automation" : "Enable Scheduled Automation";
  }
  if (guardEl) {
    guardEl.textContent = sch.resource_guardrail_status || "Idle & within guardrails";
    guardEl.className = sch.foreground_busy ? "text-muted" : "text-green";
  }

  const tbody = document.getElementById("schedules-table-body");
  if (tbody) {
    tbody.innerHTML = "";
    const schedules = sch.schedules || [];
    if (schedules.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8">No scheduled workflows configured.</td></tr>`;
    } else {
      for (const s of schedules) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><code>${escapeHtml(s.schedule_id)}</code></td>
          <td><strong>${escapeHtml(s.title)}</strong></td>
          <td>${escapeHtml(s.workflow_title || s.workflow_id)}</td>
          <td>Every ${s.interval_minutes} min</td>
          <td>
            <span class="status-pill ${s.enabled ? "st-completed" : "st-paused"}">
              ${s.enabled ? "On" : "Paused"}
            </span>
          </td>
          <td>${s.run_count || 0} / ${s.skipped_count || 0} skipped</td>
          <td><span class="cite-pill">${escapeHtml(s.last_status || "never_run")}</span></td>
          <td>
            <button class="btn btn-sm btn-secondary btn-toggle-sch" data-sch-id="${escapeHtml(s.schedule_id)}" data-enabled="${s.enabled ? "true" : "false"}">
              ${s.enabled ? "Pause" : "Enable"}
            </button>
            <button class="btn btn-sm btn-primary btn-run-sch-now" data-sch-id="${escapeHtml(s.schedule_id)}">
              Run Now
            </button>
            <button class="btn btn-sm btn-danger btn-del-sch" data-sch-id="${escapeHtml(s.schedule_id)}">
              Delete
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      }

      tbody.querySelectorAll(".btn-toggle-sch").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-sch-id");
          const cur = btn.getAttribute("data-enabled") === "true";
          const resp = await fetch(`/api/schedules/${id}/toggle`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: !cur }),
          });
          const data = await resp.json();
          if (data.ok) {
            renderSchedulerState(data.status);
            showToast(!cur ? "Schedule enabled" : "Schedule paused");
          }
        });
      });

      tbody.querySelectorAll(".btn-run-sch-now").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-sch-id");
          showToast(`Triggering scheduled workflow (${id})...`);
          const resp = await fetch(`/api/schedules/${id}/run-now`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ simulate_foreground_busy: false, wait: false }),
          });
          const data = await resp.json();
          if (data.ok) {
            renderSchedulerState(data.status);
            if (data.skipped) {
              showToast(`Skipped by Guardrail: ${data.reason}`);
            } else if (data.run) {
              state.activeRunId = data.run.run_id;
              renderActiveRun(data.run);
              startPollingActiveRun(data.run.run_id);
              showToast(`Started scheduled run ${data.run.run_id}`);
            }
          }
        });
      });

      tbody.querySelectorAll(".btn-del-sch").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-sch-id");
          const resp = await fetch(`/api/schedules/${id}`, { method: "DELETE" });
          const data = await resp.json();
          if (data.ok) {
            renderSchedulerState(data.status);
            showToast("Deleted schedule");
          }
        });
      });
    }
  }

  const evBody = document.getElementById("schedule-events-body");
  if (evBody) {
    evBody.innerHTML = "";
    const events = sch.events || [];
    if (events.length === 0) {
      evBody.innerHTML = `<tr><td colspan="5">No scheduler events recorded yet.</td></tr>`;
    } else {
      for (const ev of events.slice(0, 15)) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><small>${escapeHtml(ev.timestamp || "")}</small></td>
          <td><code>${escapeHtml(ev.schedule_id || "")}</code></td>
          <td><span class="cite-pill">${escapeHtml(ev.event_type || "")}</span></td>
          <td><code>${escapeHtml(ev.run_id || "-")}</code></td>
          <td><small>${escapeHtml(ev.detail || "")}</small></td>
        `;
        evBody.appendChild(tr);
      }
    }
  }
}

document.getElementById("btn-toggle-sch-global")?.addEventListener("click", async () => {
  const cur = state.scheduler ? Boolean(state.scheduler.scheduler_enabled) : false;
  const resp = await fetch("/api/schedules/global", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: !cur }),
  });
  const data = await resp.json();
  if (data.ok) {
    renderSchedulerState(data.status);
    showToast(
      !cur
        ? "Scheduled automation master switch ENABLED"
        : "Scheduled automation master switch DISABLED (Off)"
    );
  }
});

document.getElementById("btn-create-schedule")?.addEventListener("click", async () => {
  const titleEl = document.getElementById("sch-title-input");
  const wfEl = document.getElementById("sch-workflow-select");
  const intEl = document.getElementById("sch-interval-select");
  const titleVal = (titleEl?.value || "").trim();
  if (!titleVal) {
    showToast("Enter a schedule title first");
    return;
  }
  const resp = await fetch("/api/schedules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: titleVal,
      workflow_id: wfEl?.value || "pc_health_audit",
      interval_minutes: parseInt(intEl?.value || "60", 10),
      inputs: {
        focus_question: "Scheduled diagnostic summary of top memory consumers and system health.",
      },
      enabled: false,
    }),
  });
  const data = await resp.json();
  if (!resp.ok || !data.ok) {
    showToast(`Failed to create schedule: ${data.detail || data.error || "error"}`);
    return;
  }
  titleEl.value = "";
  renderSchedulerState(data.status);
  showToast(`Created schedule '${data.schedule.title}' (paused by default)`);
});

async function initApp() {
  await refreshStatus();
  await loadWorkflowsAndRuns();
  await loadDocsStatus();
  await loadProjects();
  // Reopen the most recent chat, as before; older chats are in the sidebar.
  await loadChatList();
  if (state.chats.length > 0) await openChat(state.chats[0].id);
  setInterval(refreshStatus, 4000);
}

initApp();
