Loki already put a finished design in this folder: style.css and script.js. Do NOT rewrite them.
Write index.html that links them and uses their classes, like this outline (change all text to fit the request,
and add, remove or repeat sections and cards as needed):

```file:index.html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Site name</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="nav"><div class="container">
    <a class="brand" href="#">Site<span>name</span></a>
    <ul class="nav-links"><li><a href="#features">Features</a></li><li><a href="#about">About</a></li><li><a href="#contact">Contact</a></li></ul>
    <button class="theme-toggle" type="button">Light mode</button>
  </div></header>
  <main>
    <section class="hero"><div class="container">
      <span class="eyebrow">Short label</span>
      <h1>Big headline with <span class="gradient-text">highlighted words</span></h1>
      <p class="lead">One or two sentences that explain the site.</p>
      <div class="actions"><a class="btn" href="#features">Main action</a><a class="btn ghost" href="#contact">Second action</a></div>
    </div></section>
    <section class="section" id="features"><div class="container">
      <div class="section-head"><h2>Section title</h2><p class="section-intro">What this section shows.</p></div>
      <div class="grid">
        <article class="card reveal"><div class="icon">AI</div><h3>Card title</h3><p>Specific description.</p><div class="tags"><span class="tag">Tag</span></div></article>
        (more cards)
      </div>
    </div></section>
    <section class="section"><div class="container"><div class="stats">
      <div class="stat reveal"><strong>24/7</strong><span>What the number means</span></div> (3 or 4 stats)
    </div></div></section>
    <section class="section" id="about"><div class="container split">
      <div><h2>Title</h2><p class="section-intro">Text.</p><ul class="list"><li>Point</li><li>Point</li></ul></div>
      <div class="panel reveal"><h3>Panel title</h3><p>Text.</p></div>
    </div></section>
    <section class="section" id="contact"><div class="container"><div class="cta reveal">
      <h2>Call to action</h2><p>Text.</p>
      <form class="form"><input placeholder="Your email" type="email"><textarea rows="4" placeholder="Message"></textarea><button class="btn" type="submit">Send</button></form>
    </div></div></section>
  </main>
  <footer class="footer"><div class="container"><span>© 2026 Site name</span><span>Short tagline</span></div></footer>
  <script src="script.js"></script>
</body>
</html>
```

Available classes: nav, brand, nav-links, theme-toggle, hero, eyebrow, gradient-text, lead, actions, btn, btn ghost,
section, section-head, section-intro, grid, card, icon (2-3 letters or a symbol), tags, tag, stats, stat, split,
panel, list, cta, form, footer, reveal (fades in on scroll), container.
To change the look, edit only the colour variables at the top of style.css with replace_in_file
(--accent, --accent-2, --bg). Write real, specific text everywhere; no placeholders.
Do not run any commands for this website (there is nothing to test): save index.html, then finish with a short
summary that tells the user to click Preview under your reply.
