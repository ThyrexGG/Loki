// Loki UI layer: home screen "today" line and action deck, Ctrl+K command palette, Tools page,
// tool result cards in chat, and in-app reminder alerts. Loaded after app.js and uses its globals
// (state, lokiPost, showToast, escapeHtml, chatInputEl, autoResizeChatInput, startNewChat, ...).
"use strict";

const H = { "X-Loki-Request": "1" };
const lokiGet = (url) => fetch(url, { headers: H }).then(async (r) => {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
});
const goTab = (tab) => document.querySelector(`.nav-btn[data-tab="${tab}"]`)?.click();
const esc = (s) => escapeHtml(String(s ?? ""));

// ---------------------------------------------------------------------------
// Home: greeting, today line, action deck
// ---------------------------------------------------------------------------
function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Working late?" : h < 12 ? "Good morning." : h < 18 ? "Good afternoon." : "Good evening.";
}

async function refreshToday() {
  const g = document.getElementById("hero-greeting");
  if (g) g.textContent = greeting();
  try {
    const { reminders } = await lokiGet("/api/tools/reminders");
    const next = reminders.find((r) => !r.done);
    document.getElementById("today-reminder-v").textContent = next ? `${next.when}: ${next.text}` : "None set";
  } catch (e) { /* keep the last value */ }
  try {
    const data = await fetch("/api/status").then((r) => r.json());
    const ram = data.hardware && data.hardware.ram;
    const gpu = data.hardware && data.hardware.gpu;
    const parts = [];
    if (ram && ram.available) parts.push(`${Math.round(ram.load_percent)}% memory used`);
    if (gpu && gpu.available) parts.push(`GPU ${Math.round(gpu.vram_percent)}%`);
    document.getElementById("today-pc-v").textContent = parts.join(", ") || "Not available";
    document.getElementById("today-pc").classList.toggle("warn", Boolean(ram && ram.load_percent >= 88));
  } catch (e) { /* ignore */ }
  try {
    const mem = await fetch("/api/memories").then((r) => r.json());
    const n = (mem.memories || []).filter((m) => m.enabled !== false).length;
    document.getElementById("today-mem-v").textContent = n ? `${n} thing${n === 1 ? "" : "s"} about you` : "Nothing yet";
  } catch (e) { /* ignore */ }
}

function fillComposer(text, send) {
  chatInputEl.value = text;
  autoResizeChatInput();
  chatInputEl.focus();
  chatInputEl.setSelectionRange(text.length, text.length);
  if (send) document.getElementById("chat-form").requestSubmit();
}

document.querySelectorAll(".deck-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const a = btn.dataset.action;
    if (a === "send") fillComposer(btn.dataset.prompt, true);
    else if (a === "prefill") fillComposer(btn.dataset.prompt, false);
    else if (a === "build") {
      const chk = document.getElementById("chk-agent");
      if (chk && !chk.checked) chk.click();
      fillComposer(btn.dataset.prompt, false);
    } else if (a === "handsfree") { if (!handsFree.on) startHandsFree(); }
    else if (a === "goto") goTab(btn.dataset.goto);
  });
});
document.querySelectorAll(".today-item").forEach((b) => b.addEventListener("click", () => goTab(b.dataset.goto)));

// ---------------------------------------------------------------------------
// Command palette (Ctrl+K)
// ---------------------------------------------------------------------------
const palette = document.getElementById("palette");
const palInput = document.getElementById("palette-input");
const palList = document.getElementById("palette-list");
let palActive = 0;
let palItems = [];

function paletteCommands() {
  const agentOn = document.getElementById("chk-agent")?.checked;
  const cmds = [
    { group: "Chat", label: "New chat", hint: "Ctrl K, Enter", run: () => startNewChat() },
    { group: "Chat", label: "Search chats", hint: "Ctrl /", run: () => document.getElementById("chat-search-input")?.focus() },
    { group: "Chat", label: "Export this chat as Markdown", hint: "Ctrl Shift E", run: () => document.getElementById("btn-export-chat")?.click() },
    { group: "Chat", label: agentOn ? "Turn the coding agent off" : "Turn the coding agent on", run: () => document.getElementById("chk-agent")?.click() },
    { group: "Voice", label: handsFree.on ? "Turn hands-free off" : "Talk hands-free (Hey Loki)", run: () => (handsFree.on ? stopHandsFree("Hands-free off") : startHandsFree()) },
    { group: "Do", label: "Build a new project...", run: () => { if (!agentOn) document.getElementById("chk-agent")?.click(); fillComposer("Build me a ", false); } },
    { group: "Do", label: "Check what is slowing my PC", run: () => fillComposer("Why is my PC slow? Check what is using my memory, GPU and disk.", true) },
    { group: "Do", label: "Set a reminder...", run: () => fillComposer("Remind me ", false) },
    { group: "Do", label: "Show my reminders", run: () => goTab("tools") },
    { group: "Do", label: "Find the largest files in a folder", run: () => { goTab("tools"); document.getElementById("files-folder")?.focus(); } },
    { group: "Do", label: "Check a Godot or Unity project", run: () => { goTab("tools"); document.getElementById("game-folder")?.focus(); } },
    { group: "Go to", label: "Tools", run: () => goTab("tools") },
    { group: "Go to", label: "Documents", run: () => goTab("docs") },
    { group: "Go to", label: "Workflows", run: () => goTab("analyst") },
    { group: "Go to", label: "System", run: () => goTab("status") },
    { group: "Go to", label: "Memories and privacy", run: () => goTab("privacy") },
    { group: "Model", label: "Free GPU memory (unload the model)", run: () => document.getElementById("btn-unload-model")?.click() },
  ];
  for (const m of (modelPicker && modelPicker.models) || []) {
    const f = friendlyModel(m.name, m.parameter_size);
    cmds.push({ group: "Model", label: `Use ${f.label}`, hint: m.name, run: () => selectModelByName(m.name) });
  }
  return cmds;
}

function selectModelByName(name) {
  modelPicker.choose(name);
}

function scoreCmd(label, q) {
  if (!q) return 1;
  const l = label.toLowerCase();
  if (l.includes(q)) return 3 - l.indexOf(q) / 100;
  // all words present in any order
  return q.split(/\s+/).every((w) => l.includes(w)) ? 1 : 0;
}

function renderPalette() {
  const q = palInput.value.trim().toLowerCase();
  palItems = paletteCommands().map((c) => ({ ...c, s: scoreCmd(c.label + " " + (c.hint || ""), q) }))
    .filter((c) => c.s > 0).sort((a, b) => (q ? b.s - a.s : 0));
  if (q) palItems.push({ group: "Ask", label: `Ask Loki: "${palInput.value.trim()}"`, run: () => fillComposer(palInput.value.trim(), true) });
  palActive = Math.min(palActive, palItems.length - 1);
  if (palActive < 0) palActive = 0;
  let lastGroup = "";
  palList.innerHTML = palItems.map((c, i) => {
    const head = c.group !== lastGroup && !q ? `<li class="pal-group" role="presentation">${esc(c.group)}</li>` : "";
    lastGroup = c.group;
    return head + `<li role="option" id="pal-${i}" class="pal-item${i === palActive ? " active" : ""}" aria-selected="${i === palActive}" data-i="${i}">` +
      `<span>${esc(c.label)}</span>${c.hint ? `<span class="pal-hint">${esc(c.hint)}</span>` : ""}</li>`;
  }).join("");
  palInput.setAttribute("aria-activedescendant", palItems.length ? `pal-${palActive}` : "");
  palList.querySelector(".pal-item.active")?.scrollIntoView({ block: "nearest" });
}

function openPalette() {
  if (palette.open) return;
  palInput.value = "";
  palActive = 0;
  renderPalette();
  palette.showModal();
  palInput.focus();
}

function runPalette(i) {
  const c = palItems[i];
  if (!c) return;
  palette.close();
  setTimeout(() => c.run(), 0);
}

palInput.addEventListener("input", () => { palActive = 0; renderPalette(); });
palInput.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { e.preventDefault(); palActive = Math.min(palItems.length - 1, palActive + 1); renderPalette(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); palActive = Math.max(0, palActive - 1); renderPalette(); }
  else if (e.key === "Enter") { e.preventDefault(); runPalette(palActive); }
});
palList.addEventListener("click", (e) => {
  const li = e.target.closest(".pal-item");
  if (li) runPalette(Number(li.dataset.i));
});
palette.addEventListener("click", (e) => { if (e.target === palette) palette.close(); });

// Ctrl+K opens the palette (capture phase, before app.js's own Ctrl+K = new chat; "New chat" is the first command).
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && (e.key || "").toLowerCase() === "k") {
    if (document.querySelector("dialog[open]:not(#palette)")) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (palette.open) palette.close(); else openPalette();
  }
}, true);

// ---------------------------------------------------------------------------
// Tools page
// ---------------------------------------------------------------------------
function meter(label, pct, detail, tone) {
  const p = Math.max(0, Math.min(100, Math.round(pct)));
  return `<div class="pc-meter ${tone || (p >= 88 ? "hot" : p >= 70 ? "warm" : "")}">
    <div class="pc-meter-top"><span>${esc(label)}</span><span>${esc(detail)}</span></div>
    <div class="pc-bar"><i style="width:${p}%"></i></div></div>`;
}

function systemCardHtml(r) {
  const out = [meter("Memory", r.ram.used_pct, `${r.ram.free_gb} GB free of ${r.ram.total_gb} GB`)];
  if (r.gpu) out.push(meter("Graphics memory", (100 * r.gpu.used_mb) / r.gpu.total_mb, `${(r.gpu.used_mb / 1024).toFixed(1)} of ${(r.gpu.total_mb / 1024).toFixed(1)} GB, ${r.gpu.temp_c} °C`));
  for (const d of r.disks || []) out.push(meter(`Drive ${d.drive}`, d.used_pct, `${d.free_gb} GB free`));
  const top = (r.top_memory || []).slice(0, 6);
  const maxMb = Math.max(1, ...top.map((p) => p.memory_mb));
  out.push(`<div class="pc-sub">Using the most memory</div><ol class="pc-procs">` + top.map((p) =>
    `<li><span class="pp-name">${esc(p.name)}${p.count > 1 ? ` <span class="pp-n">×${p.count}</span>` : ""}</span>` +
    `<span class="pp-bar"><i style="width:${(100 * p.memory_mb) / maxMb}%"></i></span><span class="pp-mb">${(p.memory_mb / 1024).toFixed(1)} GB</span></li>`).join("") + `</ol>`);
  if ((r.startup_apps || []).length) {
    out.push(`<details class="pc-startup"><summary>${r.startup_apps.length} apps start with Windows</summary><ul>` +
      r.startup_apps.map((s) => `<li>${esc(s.name)} <span class="text-muted">(${esc(s.where)})</span></li>`).join("") + `</ul></details>`);
  }
  return out.join("");
}

async function loadToolsPc() {
  const body = document.getElementById("tools-pc-body");
  body.classList.add("loading");
  try {
    body.innerHTML = systemCardHtml(await lokiGet("/api/tools/system"));
  } catch (err) {
    body.innerHTML = `<p class="tool-empty">Could not read the PC state: ${esc(err.message)}</p>`;
  } finally { body.classList.remove("loading"); }
}

async function loadReminders() {
  const list = document.getElementById("rem-list");
  try {
    const { reminders } = await lokiGet("/api/tools/reminders");
    const open = reminders.filter((r) => !r.done);
    const done = reminders.filter((r) => r.done).slice(-5);
    if (!reminders.length) {
      list.innerHTML = `<li class="tool-empty">No reminders yet. Add one above, or say "remind me ..." in chat.</li>`;
      return;
    }
    list.innerHTML = [...open, ...done].map((r) => `
      <li class="rem-item${r.done ? " done" : ""}${!r.done && r.notified ? " due" : ""}" data-id="${esc(r.id)}">
        <button type="button" class="rem-check" aria-label="${r.done ? "Mark as not done" : "Mark as done"}" aria-pressed="${r.done}"></button>
        <span class="rem-body"><span class="rem-text">${esc(r.text)}</span><span class="rem-when">${esc(r.when)}</span></span>
        <button type="button" class="rem-del" aria-label="Delete reminder">×</button>
      </li>`).join("");
  } catch (err) {
    list.innerHTML = `<li class="tool-empty">${esc(err.message)}</li>`;
  }
}

document.getElementById("rem-list").addEventListener("click", async (e) => {
  const li = e.target.closest(".rem-item");
  if (!li) return;
  const id = li.dataset.id;
  if (e.target.closest(".rem-del")) {
    await fetch(`/api/tools/reminders/${encodeURIComponent(id)}`, { method: "DELETE", headers: H });
  } else if (e.target.closest(".rem-check")) {
    await fetch(`/api/tools/reminders/${encodeURIComponent(id)}`, {
      method: "PUT", headers: { ...H, "Content-Type": "application/json" },
      body: JSON.stringify({ done: !li.classList.contains("done") }),
    });
  } else return;
  loadReminders();
  refreshToday();
});

document.getElementById("rem-add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("rem-add-input");
  const text = input.value.trim();
  if (!text) return;
  try {
    const res = await lokiPost("/api/tools/reminders", { text: /^remind me/i.test(text) ? text : `remind me ${text}` });
    input.value = "";
    showToast(`Reminder set for ${res.reminder.when}`);
    loadReminders();
    refreshToday();
  } catch (err) { showToast(err.message); }
});

// Files
const QUICK_FOLDERS = ["Downloads", "Desktop", "Documents", "Pictures", "Videos"];
document.getElementById("files-quick").innerHTML = QUICK_FOLDERS.map((f) =>
  `<button type="button" class="quick-folder" data-folder="${f}">${f}</button>`).join("");
document.getElementById("files-quick").addEventListener("click", (e) => {
  const b = e.target.closest(".quick-folder");
  if (b) document.getElementById("files-folder").value = `%USERPROFILE%\\${b.dataset.folder}`;
});

function filesResultHtml(kind, r) {
  if (kind === "largest") {
    if (!r.files.length) return `<p class="tool-empty">No files found in ${esc(r.folder)}.</p>`;
    const max = Math.max(1, r.files[0].bytes);
    return `<p class="tool-summary">${r.files_scanned.toLocaleString()} files, ${esc(r.total)} in total. The largest:</p><ol class="file-list">` +
      r.files.map((f) => `<li><span class="fl-bar" style="--w:${(100 * f.bytes) / max}%"></span><span class="fl-size">${esc(f.size)}</span><span class="fl-path" title="${esc(f.path)}">${esc(f.path)}</span></li>`).join("") + `</ol>`;
  }
  if (kind === "duplicates") {
    if (!r.groups.length) return `<p class="tool-empty">No duplicate files (100 KB or larger) in ${esc(r.folder)}.</p>`;
    return `<p class="tool-summary">${r.groups.length} sets of identical files; removing the extra copies would free ${esc(r.wasted_total)}. Loki does not delete anything: remove the copies you do not need yourself.</p>` +
      r.groups.map((g) => `<div class="dupe-group"><div class="dupe-head">${esc(g.size)} each, ${esc(g.wasted)} extra</div>` +
        g.paths.map((p) => `<div class="fl-path" title="${esc(p)}">${esc(p)}</div>`).join("") + `</div>`).join("");
  }
  // organise plan
  if (!r.count) return `<p class="tool-empty">Nothing to organise: there are no loose files of known types at the top of ${esc(r.folder)}.</p>`;
  const sum = Object.entries(r.summary).map(([k, v]) => `<span class="org-chip">${esc(k)} <b>${v}</b></span>`).join("");
  return `<p class="tool-summary">Plan: move ${r.count} loose files into folders by type. Nothing has moved yet.</p>
    <div class="org-sum">${sum}</div>
    <details class="org-detail"><summary>See every move</summary><ul>${r.moves.map((m) =>
      `<li>${esc(m.from.split("\\").pop())} <span class="text-muted">to</span> ${esc(m.folder)}\\</li>`).join("")}</ul></details>
    <div class="org-actions"><button type="button" class="btn btn-primary" data-apply="${esc(r.plan_id)}">Move ${r.count} files</button></div>`;
}

document.querySelectorAll("[data-files]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const folder = document.getElementById("files-folder").value.trim();
    const out = document.getElementById("files-result");
    if (!folder) { showToast("Enter a folder first, or pick one of the quick folders"); document.getElementById("files-folder").focus(); return; }
    const kind = btn.dataset.files;
    document.querySelectorAll("[data-files]").forEach((b) => b.classList.toggle("active", b === btn));
    out.innerHTML = `<p class="tool-empty">Looking through ${esc(folder)}...</p>`;
    try {
      const r = await lokiPost(`/api/tools/files/${kind === "organise" ? "organise/plan" : kind}`, { folder });
      out.innerHTML = filesResultHtml(kind, r);
    } catch (err) { out.innerHTML = `<p class="tool-error">${esc(err.message)}</p>`; }
  });
});

document.getElementById("files-result").addEventListener("click", async (e) => {
  const apply = e.target.closest("[data-apply]");
  const undo = e.target.closest("[data-undo]");
  const out = document.getElementById("files-result");
  if (apply) {
    apply.disabled = true;
    try {
      const r = await lokiPost("/api/tools/files/organise/apply", { plan_id: apply.dataset.apply });
      out.innerHTML = `<p class="tool-summary">Moved ${r.moved} files${r.skipped ? ` (${r.skipped} skipped because a file with that name was already there)` : ""}.</p>
        <div class="org-actions"><button type="button" class="btn btn-secondary" data-undo="${esc(r.undo_id)}">Undo the move</button></div>`;
    } catch (err) { out.innerHTML = `<p class="tool-error">${esc(err.message)}</p>`; }
  } else if (undo) {
    undo.disabled = true;
    try {
      const r = await lokiPost("/api/tools/files/organise/undo", { plan_id: undo.dataset.undo });
      out.innerHTML = `<p class="tool-summary">Put ${r.restored} files back where they were.</p>`;
    } catch (err) { out.innerHTML = `<p class="tool-error">${esc(err.message)}</p>`; }
  }
});

function gameResultHtml(r) {
  const label = { error: "Will break", warn: "Worth fixing", info: "Tidy-up" };
  const head = `<p class="tool-summary"><strong>${esc(r.name)}</strong>, ${esc(r.engine)} ${esc(r.engine_version)}: ${r.scripts} scripts${r.scenes !== undefined ? `, ${r.scenes} scenes` : ""}.
    ${r.issues.length ? `${r.counts.error} that will break, ${r.counts.warn} worth fixing, ${r.counts.info} tidy-ups.` : "No problems found."}</p>`;
  return head + `<ul class="issue-list">` + r.issues.map((i) => `
    <li class="issue lvl-${esc(i.level)}"><span class="issue-lvl">${esc(label[i.level] || i.level)}</span>
      <span class="issue-body"><code>${esc(i.where)}</code> ${esc(i.what)}<span class="issue-fix">${esc(i.fix)}</span></span></li>`).join("") + `</ul>`;
}

async function runGameCheck() {
  const folder = document.getElementById("game-folder").value.trim() || (state.project || "");
  const out = document.getElementById("game-result");
  if (!folder) { showToast("Enter the game project folder first"); return; }
  document.getElementById("game-folder").value = folder;
  out.innerHTML = `<p class="tool-empty">Checking ${esc(folder)}...</p>`;
  try { out.innerHTML = gameResultHtml(await lokiPost("/api/tools/game/check", { folder })); }
  catch (err) { out.innerHTML = `<p class="tool-error">${esc(err.message)}</p>`; }
}
document.getElementById("btn-game-check").addEventListener("click", runGameCheck);
document.getElementById("game-folder").addEventListener("keydown", (e) => { if (e.key === "Enter") runGameCheck(); });
document.getElementById("files-folder").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.querySelector('[data-files="largest"]').click();
});
document.getElementById("btn-tools-pc").addEventListener("click", loadToolsPc);

document.querySelector('.nav-btn[data-tab="tools"]').addEventListener("click", () => {
  loadReminders();
  loadToolsPc();
  if (!document.getElementById("game-folder").value && state.project) document.getElementById("game-folder").value = state.project;
});

// ---------------------------------------------------------------------------
// Tool cards in chat (rendered by app.js through window.renderToolCard)
// ---------------------------------------------------------------------------
window.renderToolCard = function renderToolCard(card) {
  const el = document.createElement("div");
  el.className = `tool-card tc-${card.tool}`;
  const titles = { system: "Your PC right now", largest: "Largest files", duplicates: "Duplicate files", organise: "Organise plan",
    game_check: "Game project check", reminder_add: "Reminder set", reminder_list: "Your reminders" };
  let body = "";
  if (card.error) body = `<p class="tool-error">${esc(card.error)}</p>`;
  else if (card.tool === "system") body = systemCardHtml(card.data);
  else if (["largest", "duplicates", "organise"].includes(card.tool)) body = filesResultHtml(card.tool, card.data);
  else if (card.tool === "game_check") body = gameResultHtml(card.data);
  else if (card.tool === "reminder_add") body = `<p class="tool-summary">${esc(card.data.text)}</p>`;
  else if (card.tool === "reminder_list") body = (card.data || []).length
    ? `<ol class="rem-list compact">${card.data.map((r) => `<li class="rem-item"><span class="rem-body"><span class="rem-text">${esc(r.text)}</span></span></li>`).join("")}</ol>` : "";
  if (!body) return null;
  el.innerHTML = `<div class="tool-card-head"><span>${esc(titles[card.tool] || "Tool")}</span><span class="tool-card-local">Checked on this PC</span></div><div class="tool-card-body">${body}</div>`;
  // Organise from chat: apply / undo work the same way as on the Tools page.
  el.addEventListener("click", async (e) => {
    const apply = e.target.closest("[data-apply]");
    const undo = e.target.closest("[data-undo]");
    const target = el.querySelector(".tool-card-body");
    if (apply) {
      apply.disabled = true;
      try {
        const r = await lokiPost("/api/tools/files/organise/apply", { plan_id: apply.dataset.apply });
        target.innerHTML = `<p class="tool-summary">Moved ${r.moved} files.</p><div class="org-actions"><button type="button" class="btn btn-secondary" data-undo="${esc(r.undo_id)}">Undo the move</button></div>`;
      } catch (err) { target.innerHTML = `<p class="tool-error">${esc(err.message)}</p>`; }
    } else if (undo) {
      undo.disabled = true;
      try {
        const r = await lokiPost("/api/tools/files/organise/undo", { plan_id: undo.dataset.undo });
        target.innerHTML = `<p class="tool-summary">Put ${r.restored} files back where they were.</p>`;
      } catch (err) { target.innerHTML = `<p class="tool-error">${esc(err.message)}</p>`; }
    }
  });
  return el;
};

// ---------------------------------------------------------------------------
// Reminder alerts inside Loki (Windows also shows a notification)
// ---------------------------------------------------------------------------
let dueAfter = new Date().toISOString().slice(0, 16);
const alertEl = document.getElementById("reminder-alert");
let alertId = null;
async function pollDue() {
  try {
    const { due } = await lokiGet(`/api/tools/reminders/due?after=${encodeURIComponent(dueAfter)}`);
    if (due.length) {
      const r = due[due.length - 1];
      dueAfter = due.map((x) => x.due).sort().pop();
      alertId = r.id;
      document.getElementById("reminder-alert-text").textContent = r.text;
      alertEl.classList.remove("hidden");
      if (typeof chime === "function") { chime(true); setTimeout(() => chime(true), 260); }
      refreshToday();
    }
  } catch (e) { /* server restarting */ }
}
document.getElementById("reminder-alert-done").addEventListener("click", async () => {
  alertEl.classList.add("hidden");
  if (alertId) {
    await fetch(`/api/tools/reminders/${encodeURIComponent(alertId)}`, {
      method: "PUT", headers: { ...H, "Content-Type": "application/json" }, body: JSON.stringify({ done: true }),
    }).catch(() => {});
  }
  refreshToday();
});
setInterval(pollDue, 30000);

refreshToday();
setInterval(refreshToday, 60000);

// ---------------------------------------------------------------------------
// Narrow windows: menu button for the sidebar
// ---------------------------------------------------------------------------
(function navToggle() {
  const left = document.querySelector(".topbar-left");
  if (!left) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "nav-toggle";
  btn.setAttribute("aria-label", "Show menu");
  btn.setAttribute("aria-controls", "sidebar");
  btn.setAttribute("aria-expanded", "false");
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
  left.prepend(btn);
  const setOpen = (open) => {
    document.body.classList.toggle("nav-open", open);
    btn.setAttribute("aria-expanded", String(open));
  };
  btn.addEventListener("click", () => setOpen(!document.body.classList.contains("nav-open")));
  document.addEventListener("click", (e) => {
    if (!document.body.classList.contains("nav-open")) return;
    if (e.target.closest(".nav-btn, .chat-item, #btn-new-chat") || (!e.target.closest(".sidebar") && !e.target.closest(".nav-toggle"))) setOpen(false);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
})();
