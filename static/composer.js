// Compact composer: one row (+ menu, project, Agent | options, voice, send).
// The less-used controls move into an Options popover. The elements themselves (and their app.js listeners)
// are moved, not copied, so everything keeps working.
"use strict";

(function compactComposer() {
  const toolbar = document.querySelector(".composer-toolbar");
  const pills = toolbar && toolbar.querySelector(".composer-pills");
  const buttons = toolbar && toolbar.querySelector(".composer-buttons");
  if (!pills || !buttons) return;
  const icon = (d) => `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const chipOf = (id) => document.getElementById(id)?.closest(".composer-chip");

  // "+" menu: attach a file, look at the screen
  const plusWrap = document.createElement("div");
  plusWrap.className = "cc-pop-wrap";
  plusWrap.innerHTML =
    `<button type="button" class="cc-icon-btn" id="cc-plus" aria-haspopup="menu" aria-expanded="false" aria-label="Add a file or screenshot" title="Add a file or screenshot">${icon('<path d="M12 5v14M5 12h14"/>')}</button>` +
    `<div class="cc-pop cc-menu hidden" role="menu">` +
    `<button type="button" role="menuitem" data-click="btn-attach-image">${icon('<path d="M21.4 11.1 12.2 20.3a5 5 0 0 1-7.1-7.1l9.2-9.2a3.3 3.3 0 0 1 4.7 4.7l-9.2 9.2a1.7 1.7 0 0 1-2.4-2.4l8.5-8.5"/>')}<span>Attach a file or image</span></button>` +
    `<button type="button" role="menuitem" data-click="btn-screen">${icon('<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>')}<span>Look at my screen</span></button>` +
    `</div>`;

  // Options popover: context, temperature, style and the less-used switches
  const optWrap = document.createElement("div");
  optWrap.className = "cc-pop-wrap";
  optWrap.innerHTML =
    `<button type="button" class="cc-icon-btn" id="cc-options" aria-haspopup="dialog" aria-expanded="false" aria-label="Chat options" title="Chat options">` +
    `${icon('<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>')}` +
    `<span class="cc-dot hidden" aria-hidden="true"></span></button>` +
    `<div class="cc-pop cc-options hidden" role="dialog" aria-label="Chat options">` +
    `<div class="cc-opt-head">Answers</div><div class="cc-opt-selects"></div>` +
    `<div class="cc-opt-head">Switches</div><div class="cc-opt-toggles"></div></div>`;
  const selects = optWrap.querySelector(".cc-opt-selects");
  const toggles = optWrap.querySelector(".cc-opt-toggles");
  ["select-ctx", "select-temp", "select-persona"].forEach((id) => { const c = chipOf(id); if (c) selects.appendChild(c); });
  ["chk-auto-model", "chk-refine", "chk-save-history", "chk-use-memories"].forEach((id) => { const c = chipOf(id); if (c) toggles.appendChild(c); });

  pills.prepend(plusWrap);
  buttons.prepend(optWrap);
  ["btn-attach-image", "btn-screen"].forEach((id) => document.getElementById(id)?.classList.add("cc-moved"));
  toolbar.classList.add("cc-compact");
  const input = document.getElementById("chat-input");
  if (input) input.placeholder = "Ask Loki anything, or drop a file";

  // Refine changes how answers are made: show a dot on Options while it is on.
  const refine = document.getElementById("chk-refine");
  const syncDot = () => optWrap.querySelector(".cc-dot").classList.toggle("hidden", !(refine && refine.checked));
  refine?.addEventListener("change", syncDot);
  setTimeout(syncDot, 500);

  const pops = [plusWrap, optWrap];
  const isOpen = (w) => !w.querySelector(".cc-pop").classList.contains("hidden");
  const close = (except) => pops.forEach((w) => {
    if (w === except) return;
    w.querySelector(".cc-pop").classList.add("hidden");
    w.querySelector(".cc-icon-btn").setAttribute("aria-expanded", "false");
  });
  pops.forEach((w) => {
    const btn = w.querySelector(".cc-icon-btn");
    const pop = w.querySelector(".cc-pop");
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = !isOpen(w);
      close(w);
      pop.classList.toggle("hidden", !open);
      btn.setAttribute("aria-expanded", String(open));
      if (open) pop.querySelector("button, select, input")?.focus();
    });
  });
  plusWrap.querySelector(".cc-menu").addEventListener("click", (e) => {
    const item = e.target.closest("[data-click]");
    if (!item) return;
    close();
    document.getElementById(item.dataset.click)?.click();
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".cc-pop-wrap")) close(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && pops.some(isOpen)) {
      close();
      input?.focus();
    }
  });
})();
