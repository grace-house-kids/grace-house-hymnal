#!/usr/bin/env python3
"""JerJer — the floating-head critic on the musician song pages.

He sits in the bottom-right corner, just above the control bar. Every
so often he flaps his mouth and a speech bubble pops up with a random
line from critique.txt. Tap him (or his bubble) and he's gone for the
rest of that song; the next song brings him back. Press 9 on a
keyboard and he says something right away (and comes back if he was
tapped away). He never shows in
dark mode or when a page is printed, and never on the public hymnal.

critique.txt: one critique per line, next to server.py. Blank lines and
lines starting with # are ignored. No critique.txt, or an empty one,
means no JerJer.

Pictures: JerJer.png (mouth shut) and JerJerSpeaks.png (mouth open),
next to server.py. They're stacked on top of each other, so they need
to be the same size. If either one is missing, he just doesn't show.

Timing lives at the top of JERJER_JS: FIRST is how long he waits
before his first critique on a song, GAP is how long between critiques
after that (both in seconds, a random pick between the two numbers).
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
CRITIQUE_PATH = HERE / "critique.txt"

# File name on the site -> file on disk. server.py serves these and
# build.py copies them into dist/{key}/.
JERJER_IMAGES = {
    "JerJer.png": HERE / "JerJer.png",
    "JerJerSpeaks.png": HERE / "JerJerSpeaks.png",
}


def load_critiques() -> list[str]:
    """Critiques from critique.txt, one per line (# = comment)."""
    if not CRITIQUE_PATH.exists():
        return []
    return [
        ln.strip() for ln in CRITIQUE_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


JERJER_CSS = r"""
/* ────────────────────────────────────────────────────────────
   JERJER — floating-head critic on musician song pages (jerjer.py)
   ──────────────────────────────────────────────────────────── */
.jerjer {
  position: fixed;
  right: 10px;
  /* The script moves him to just above the control bar; this is the
     fallback if it can't measure the bar. */
  bottom: calc(112px + env(safe-area-inset-bottom));
  z-index: 55;                 /* over the lyrics, under the countdown card */
  display: flex;
  align-items: flex-end;
  gap: 16px;
  pointer-events: none;        /* only his face and his bubble take taps */
  transform-origin: 100% 100%;
  animation: jj-in 0.4s cubic-bezier(.2, 1.5, .4, 1) both;
}
.jerjer[hidden] { display: none; }
.jerjer.leaving { animation: jj-out 0.28s ease-in both; }

.jj-head {
  position: relative;
  flex-shrink: 0;
  width: 78px;
  margin: 0;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  pointer-events: auto;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
  transform-origin: 50% 85%;
  transition: transform 0.2s ease-out;
}
.jj-head img { display: block; width: 100%; height: auto; }
.jj-head .jj-open { position: absolute; inset: 0; height: 100%; visibility: hidden; }
.jerjer.open .jj-open { visibility: visible; }
.jerjer.talking .jj-head { transform: rotate(-7deg); }   /* leans in to say it */
.jj-head:focus-visible { outline: 3px solid #f01a8b; outline-offset: 3px; border-radius: 50%; }

/* The speech bubble */
.jj-bubble {
  position: relative;
  max-width: min(230px, calc(100vw - 126px));
  margin-bottom: 22px;         /* puts the tail level with his mouth */
  padding: 9px 13px 10px;
  background: #f2ede4;
  border: 3px solid #0a0a0a;
  border-radius: 16px;
  box-shadow: 4px 4px 0 #f01a8b;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 18px;
  line-height: 1.08;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: #0a0a0a;
  opacity: 0;
  visibility: hidden;
  transform: rotate(-2deg) scale(0.3);
  transform-origin: 100% 85%;
  transition: transform 0.16s ease-in, opacity 0.16s, visibility 0s linear 0.16s;
}
.jerjer.talking .jj-bubble {
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
  transform: rotate(-2deg) scale(1);
  transition: transform 0.24s cubic-bezier(.2, 1.6, .4, 1), opacity 0.1s, visibility 0s;
}
/* The tail: a black triangle with a beige one inside it, pointing
   right at his mouth. */
.jj-bubble::before,
.jj-bubble::after {
  content: "";
  position: absolute;
  width: 0;
  height: 0;
  border-style: solid;
  border-color: transparent;
}
.jj-bubble::before {
  right: -21px;
  bottom: 4px;
  border-width: 10px 0 10px 18px;
  border-left-color: #0a0a0a;
}
.jj-bubble::after {
  right: -14px;
  bottom: 8px;
  border-width: 6px 0 6px 14px;
  border-left-color: #f2ede4;
}

@media (min-width: 700px) {
  .jj-head { width: 100px; }
  .jj-bubble { max-width: 280px; margin-bottom: 30px; font-size: 20px; }
}

@keyframes jj-in {
  from { opacity: 0; transform: translateY(30px) scale(0.3); }
  to   { opacity: 1; transform: none; }
}
@keyframes jj-out {
  to { opacity: 0; transform: translateY(24px) rotate(25deg) scale(0.2); }
}
@media (prefers-reduced-motion: reduce) {
  .jerjer, .jerjer.leaving { animation: none; }
  .jj-head, .jj-bubble, .jerjer.talking .jj-bubble { transition: none; }
  .jerjer.talking .jj-head { transform: none; }
}

/* He has his own backgrounds, so no beige halo on his text. */
.jerjer, .jerjer * {
  -webkit-text-stroke-width: 0 !important;
  -webkit-text-stroke-color: transparent !important;
  paint-order: normal !important;
}

/* Not in dark mode, not on paper. */
html.dark .jerjer { display: none !important; }
@media print { .jerjer { display: none !important; } }
"""


# Plain string (not an f-string) so the JavaScript braces don't need escaping.
JERJER_JS = r"""
(function () {
  var jj = document.getElementById('jerjer');
  if (!jj) return;
  var lines = [];
  try { lines = JSON.parse(jj.getAttribute('data-critiques')) || []; } catch (e) {}
  if (!lines.length) return;

  var FIRST = [8, 18];      // seconds before his first critique on a song
  var GAP = [35, 80];       // seconds between critiques after that

  var bubble = document.getElementById('jj-bubble');
  var player = document.getElementById('player');
  var timers = [], gone = false, broken = false, hideTimer = 0;

  function later(fn, sec) { timers.push(setTimeout(fn, sec * 1000)); }
  function between(r) { return r[0] + Math.random() * (r[1] - r[0]); }
  function quit() {
    gone = true;
    timers.forEach(clearTimeout);
    jj.classList.remove('talking');
    jj.classList.remove('open');
  }

  // Sit just above the control bar, however tall it ends up.
  function place() {
    if (player) jj.style.bottom = (player.offsetHeight + 12) + 'px';
  }

  // A random critique, never the same one twice in a row (even across songs).
  function pick() {
    var last = null;
    try { last = sessionStorage.getItem('gh-jj-last'); } catch (e) {}
    var pool = lines.filter(function (l) { return l !== last; });
    if (!pool.length) pool = lines;
    var line = pool[Math.floor(Math.random() * pool.length)];
    try { sessionStorage.setItem('gh-jj-last', line); } catch (e) {}
    return line;
  }

  // Mouth open, shut, open, shut... n swaps, ending shut.
  function flap(n) {
    if (gone) return;
    if (n <= 0) { jj.classList.remove('open'); return; }
    jj.classList.toggle('open');
    later(function () { flap(n - 1); }, 0.11 + Math.random() * 0.1);
  }

  function speak() {
    if (gone) return;
    var line = pick();
    bubble.textContent = line;
    jj.classList.add('talking');
    var words = line.split(/\s+/).length;
    flap(2 * Math.max(3, Math.min(12, words)));          // about one flap a word
    var readFor = Math.max(4.5, Math.min(11, 2 + line.length * 0.06));
    later(function () {
      jj.classList.remove('talking');
      later(speak, between(GAP));
    }, readFor);
  }

  // Tap him (or his bubble) and he's gone until the next song.
  jj.addEventListener('click', function () {
    if (gone) return;
    quit();
    jj.classList.add('leaving');
    hideTimer = setTimeout(function () { jj.hidden = true; }, 300);
  });

  // Press 9 and he says something right now, even if he was tapped away.
  document.addEventListener('keydown', function (e) {
    if (e.key !== '9' || e.repeat || e.ctrlKey || e.metaKey || e.altKey || broken) return;
    quit();
    timers = [];
    clearTimeout(hideTimer);
    gone = false;
    jj.classList.remove('leaving');
    jj.hidden = false;
    void jj.offsetWidth;            // so the bubble pops in fresh
    speak();
  });

  // A missing picture means no JerJer, rather than a broken-image box.
  var imgs = jj.getElementsByTagName('img');
  for (var i = 0; i < imgs.length; i++) {
    if (imgs[i].complete && !imgs[i].naturalWidth) { broken = true; quit(); return; }
    imgs[i].addEventListener('error', function () { broken = true; quit(); jj.hidden = true; });
  }

  place();
  window.addEventListener('resize', place);
  jj.hidden = false;
  later(speak, between(FIRST));
})();
"""


def render_jerjer(critiques: list[str]) -> str:
    """JerJer's HTML + script, or "" when there's nothing for him to say
    or a picture is missing. Goes at the end of a musician song page,
    after the control bar (he measures it to sit on top of it)."""
    if not critiques or not all(p.exists() for p in JERJER_IMAGES.values()):
        return ""
    data = escape(json.dumps(critiques, ensure_ascii=False))
    return (
        f'<div id="jerjer" class="jerjer" data-critiques="{data}" hidden>'
        '<div id="jj-bubble" class="jj-bubble"></div>'
        '<button id="jj-head" class="jj-head" type="button" aria-label="Send JerJer away">'
        '<img class="jj-shut" src="JerJer.png" alt="">'
        '<img class="jj-open" src="JerJerSpeaks.png" alt="">'
        "</button>"
        "</div>\n"
        f"<script>{JERJER_JS}</script>"
    )
