// Starter interactivity added by Loki: theme toggle, scroll reveal, smooth in-page links, form message.
(function () {
  const root = document.documentElement;
  const toggle = document.querySelector(".theme-toggle");
  if (toggle) {
    const setLabel = () => { toggle.textContent = root.dataset.theme === "light" ? "Dark mode" : "Light mode"; };
    setLabel();
    toggle.addEventListener("click", () => {
      root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
      setLabel();
    });
  }

  const items = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) { e.target.classList.add("visible"); io.unobserve(e.target); }
      }
    }, { threshold: 0.12 });
    items.forEach((el) => io.observe(el));
  } else {
    items.forEach((el) => el.classList.add("visible"));
  }

  document.querySelectorAll("form.form").forEach((form) => {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const btn = form.querySelector("button");
      if (btn) { btn.textContent = "Thanks! Message noted"; btn.disabled = true; }
    });
  });
})();
