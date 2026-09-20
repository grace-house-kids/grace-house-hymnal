#!/usr/bin/env python3
"""Grace House Kids — a one-page printable activity sheet.

The page lives at /{key}/kids/. It shows one US Letter sheet exactly as
it will print. The teacher taps any box on the sheet to shuffle it, and
presses Print when they like what they have. Everything on the sheet is
made in the visitor's browser, so the static build on GitHub Pages still
gives a fresh sheet every time, with nothing to rebuild.

    ┌──────────────────────────────────────────┐
    │ GRACE HOUSE KIDS  [ACTIVITY SHEET]       │
    ├──────────────────────────────────────────┤
    │ LOOK IT UP  directions                   │
    │ (coded verse, with blanks to fill in)    │
    │ KEY (symbols and what they stand for)    │
    ├────────────────────┬─────────────────────┤
    │ MAZE               │ WORD SEARCH         │
    │ (runs the whole    │                     │
    │  left side)        ├─────────────────────┤
    │                    │ DRAW IT             │
    ├────────────────────┴─────────────────────┤
    │ NEXT UP  (next event from events.txt)    │
    └──────────────────────────────────────────┘

Where things come from:
    Look it up   a random reference from verses.txt (the same list as the
                 front page's verse chip), written in a secret code of
                 little symbols, with a key underneath. Kids crack the
                 code, then look the verse up in a Bible.
                 Each shuffle picks a new verse and new symbols. The
                 answer shows above the sheet, on screen only.
    Maze         a fresh maze on every shuffle, down the whole left side,
                 walled into 3 or 4 parts joined only by green jump
                 circles (same picture = hop across), plus two pairs
                 that jump into sealed-off dead ends. A few gaps
                 are drawn as dotted "false walls": each is the only way
                 into the room behind it. One is needed to finish; the
                 rest lead nowhere. Drawn over a faint grid. Each maze is
                 checked before it's drawn: solvable, needs a jump, no
                 pair joins places you could walk between, and it can't
                 be done if the dotted walls were real.
                 The two rules sit beside the MAZE label.
    Next up      the first event in events.txt that's today or later.
                 Worked out in the browser, so it stays current by itself.

server.py hands in the verses and events. This file never reads files
and never imports server.py.

How shuffling works: every box with a data-act name has a maker in
ACTIVITIES inside KIDS_JS. maker(body, rng, box) fills the box's body.
rng() gives a random number from 0 to 1 and is seeded, so the same seed
always makes the same puzzle. Makers marked PLACEHOLDER are still to be
built.
"""
from __future__ import annotations

import json
from html import escape

# Used only if verses.txt is missing or empty.
FALLBACK_VERSES = ["John 3:16", "Psalm 23:1", "Philippians 4:13"]


# ─────────────────────────────────────────────────────────────
# Styles (only on the kids page)

KIDS_CSS = r"""
/* The sheet is the printed page: 8.5 x 11 inches, with a half-inch
   margin inside it. margin: 0 on the page also keeps the browser from
   printing the web address (and the access key) on every sheet. */
@page { size: letter; margin: 0; }

/* Wide enough to show the sheet at full size on a computer. On a
   phone, KIDS_JS shrinks the preview to fit. */
main { max-width: calc(8.5in + 50px); }

/* ── Toolbar above the sheet ─────────────────────────────── */
.kids-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 18px;
  margin: 24px 0 20px;
}
.kids-print {
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 26px;
  line-height: 1;
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 10px 20px 11px;
  background: #0a0a0a;
  color: #f2ede4;
  border: 3px solid #0a0a0a;
  border-radius: 0;
  box-shadow: 5px 5px 0 #f01a8b;
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.kids-print:active { transform: translate(3px, 3px); box-shadow: 2px 2px 0 #f01a8b; }
.kids-print:focus-visible { outline: 3px solid #f01a8b; outline-offset: 4px; }
.kids-hint {
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
}
.kids-hint b { font-weight: normal; color: #f01a8b; }

/* ── The sheet ───────────────────────────────────────────── */
.sheet-wrap { position: relative; overflow: hidden; }   /* KIDS_JS sets the height */
.sheet {
  width: 8.5in;
  height: 11in;
  padding: 0.5in;
  transform-origin: 0 0;
  background: #ffffff;
  color: #0a0a0a;
  box-shadow: inset 0 0 0 1.5px #0a0a0a, 6px 6px 0 #0a0a0a;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  row-gap: 0.16in;
  font-family: 'Special Elite', 'Courier New', monospace;
  -webkit-print-color-adjust: exact;   /* print the black label chips */
  print-color-adjust: exact;
}

/* White paper, not dotted beige, so no beige halo on the sheet's text
   (or on the print button, which has its own solid background). */
.kids-print,
.sheet, .sheet * {
  -webkit-text-stroke-width: 0 !important;
  -webkit-text-stroke-color: transparent !important;
  paint-order: normal !important;
}

/* Title row: GRACE HOUSE KIDS with the Activity Sheet chip beside it */
.sh-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.08in 0.22in;
}
.sh-brand {
  display: flex;
  align-items: center;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 34pt;
  line-height: 0.85;
  letter-spacing: -0.5px;
  text-transform: uppercase;
  white-space: nowrap;
}
/* The 8-spoke wheel stands in for the O in HOUSE, same as the site's
   logo, but drawn heavier to match the solid letters. */
.sh-wheel {
  width: 0.77em;
  height: 0.77em;
  margin: 0 -0.02em 0 -0.04em;
  flex-shrink: 0;
}
/* Read aloud by screen readers, never shown */
.sh-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
.sh-kind {
  padding: 2px 10px 4px;
  background: #0a0a0a;
  color: #ffffff;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 15pt;
  line-height: 1;
  letter-spacing: 3px;
  text-transform: uppercase;
  transform: rotate(-1.5deg);
}


/* The four activity boxes */
.sh-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  grid-template-areas: "maze words" "maze draw";   /* the maze runs the whole left side */
  gap: 0.16in;
  min-height: 0;
}
.act-maze { grid-area: maze; }
.act-words { grid-area: words; }
.act-draw { grid-area: draw; }
.act {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 0.12in 0.14in 0.14in;
  border: 2px solid #0a0a0a;
}
.act-label {
  align-self: flex-start;
  margin: 0 0 0.1in;
  padding: 3px 8px 4px;
  background: #0a0a0a;
  color: #ffffff;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 13pt;
  line-height: 1;
  letter-spacing: 2px;
  text-transform: uppercase;
  transform: rotate(-1.5deg);
}
.act-body { position: relative; flex: 1; min-height: 0; }

/* Look it up, full width: label and directions, then the coded
   reference, big enough to write in, then the key under it. */
.act-verse {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  column-gap: 0.14in;
  row-gap: 0.12in;
}
.act-verse .act-label { margin: 0; }
.act-verse .act-body {
  grid-column: 1 / -1;
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.16in;
}
.act-note { margin: 0; font-size: 9.5pt; line-height: 1.3; }

/* Code symbols: drawn in the text color, a few of them filled in */
.cs {
  display: block;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
  overflow: visible;
}
.cs .f { fill: currentColor; }

/* The coded reference. Words never split; a long one wraps whole. */
.code-msg {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  column-gap: 0.2in;
  row-gap: 0.12in;
}
.cw { display: flex; align-items: flex-end; }
.cc {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 0.31in;
}
.cc .cs { width: 0.24in; height: 0.24in; }
.cc i {                       /* the blank to write the letter on */
  display: block;
  width: 0.24in;
  height: 0.32in;
  border-bottom: 1.5px solid #0a0a0a;
}
.cp {                         /* a colon or dash, printed as is */
  width: 0.16in;
  text-align: center;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 20pt;
  line-height: 1;
}

/* The key: each symbol over the letter or number it stands for */
.code-key {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.05in;
}
.code-key-label {
  margin-right: 0.06in;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 11pt;
  letter-spacing: 1.5px;
  text-transform: uppercase;
}
.kp {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 0.3in;
  padding: 4px 0 3px;
  border: 1px solid #0a0a0a;
}
.kp .cs { width: 0.19in; height: 0.19in; }
.kp b {
  margin-top: 3px;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 12.5pt;
  line-height: 1;
}
.kp-gap { width: 0.1in; }     /* between the letters and the numbers */

/* Next up */
.sh-foot {
  display: flex;
  align-items: center;
  gap: 0.16in;
  padding-top: 0.1in;
  border-top: 2.5px solid #0a0a0a;
}
.sh-foot .act-label { margin: 0; flex-shrink: 0; }
.ev-text { min-width: 0; }
.ev-title {
  margin: 0;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 15pt;
  line-height: 1.05;
  text-transform: uppercase;
}
.ev-more {
  margin: 3px 0 0;
  font-size: 10pt;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ev-when { font-weight: 700; }

/* Maze: label with the two rules beside it, the maze filling the rest.
   Jump circles are green so they never look like walls; false walls
   are dotted. */
.act-maze {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto minmax(0, 1fr);
  align-items: center;
  column-gap: 0.14in;
  row-gap: 0.08in;
}
.act-maze .act-label { margin: 0; }
.act-maze .act-body { grid-column: 1 / -1; align-self: stretch; }
.maze-rules {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 8.5pt;
  line-height: 1.15;
}
.maze-rules span { display: flex; align-items: center; gap: 5px; }
.maze-rules svg { width: 0.17in; height: 0.17in; flex-shrink: 0; }
.maze-svg { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
.maze-end {
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 11px;
  letter-spacing: 1px;
  fill: #0a0a0a;
}

/* PLACEHOLDER look, until each activity is built */
.ph {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0.25in;
  border: 1.5px dashed #b5b0a6;
  text-align: center;
  color: #6b665d;
  font-size: 10.5pt;
  line-height: 1.4;
}
.ph b {
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 16pt;
  color: #0a0a0a;
  text-transform: uppercase;
}
.ph small { font-size: 9pt; }

/* ── On screen only: tap to shuffle ──────────────────────── */
@media screen {
  .act[data-act] { cursor: pointer; }
  .act[data-act]::after {
    content: "\21BB  shuffle";
    position: absolute;
    top: -10px;                /* sits on the top border, clear of the box's contents */
    right: 10px;
    padding: 3px 7px 4px;
    background: #f01a8b;
    color: #0a0a0a;
    font-family: 'Special Elite', 'Courier New', monospace;
    font-size: 11px;
    line-height: 1;
    letter-spacing: 1px;
    text-transform: uppercase;
    opacity: 0;
    transition: opacity 0.15s;
    pointer-events: none;
  }
  .act[data-act]:focus-visible { outline: 3px solid #f01a8b; outline-offset: 3px; }
  .act[data-act]:focus-visible::after { opacity: 1; }
  .act.shuffled { animation: kids-flash 0.45s ease-out; }
}
@media screen and (hover: hover) {
  .act[data-act]:hover { outline: 3px dashed #f01a8b; outline-offset: 3px; }
  .act[data-act]:hover::after { opacity: 1; }
}
@media screen and (hover: none) {
  .act[data-act]::after { opacity: 0.9; }   /* phones: always show the hint */
}
@keyframes kids-flash { from { background: #fde3f0; } to { background: #ffffff; } }
@media (prefers-reduced-motion: reduce) {
  .act.shuffled { animation: none; }
}

/* ── Printing: only the sheet, full size, one page ───────────
   Don't lock html/body to a height or hide their overflow here:
   Safari then prints from wherever the page was scrolled to, and the
   top of the sheet gets cut off. Instead the sheet is a hair shorter
   than the paper, so rounding can never spill a blank second page. */
@media print {
  html, body { margin: 0 !important; padding: 0 !important; }
  main { max-width: none !important; margin: 0 !important; padding: 0 !important; }
  main > :not(.sheet-wrap) { display: none !important; }
  .sheet-wrap { height: auto !important; overflow: visible !important; }
  .sheet {
    height: 10.98in;
    transform: none !important;
    box-shadow: none !important;
    break-inside: avoid;
    page-break-inside: avoid;
  }
}
"""


# ─────────────────────────────────────────────────────────────
# Behavior

KIDS_JS = r"""
(function () {
  var sheet = document.getElementById('sheet');
  if (!sheet) return;
  var wrap = document.getElementById('sheet-wrap');

  function read(attr) {
    try { return JSON.parse(sheet.getAttribute(attr)) || []; } catch (e) { return []; }
  }
  var VERSES = read('data-verses');
  var EVENTS = read('data-events');   // [["2026-09-27", ["Fall potluck", ...]], ...] soonest first

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* Seeded random numbers (mulberry32): same seed, same puzzle. */
  function makeRng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function newSeed() { return Math.floor(Math.random() * 4294967296); }
  function pick(list, rng) { return list[Math.floor(rng() * list.length)]; }

  /* PLACEHOLDER maker: shows what goes in the box, and counts shuffles
     so you can see tapping works. */
  function placeholder(name, what) {
    return function (body, rng, box) {
      var n = (+box.getAttribute('data-n') || 0) + 1;
      box.setAttribute('data-n', n);
      body.innerHTML =
        '<div class="ph"><b>' + name + '</b><span>' + what + '</span>' +
        '<small>Shuffle #' + n + '</small></div>';
    };
  }

  /* ── Look it up: the secret code ────────────────────────
     Every letter and number in the reference gets its own symbol,
     picked fresh on each shuffle. The key lists those plus a few
     decoy letters, so matching by count won't give the answer away. */
  var SHAPES = [
    '<circle cx="10" cy="10" r="7"/>',                                        // ring
    '<circle class="f" cx="10" cy="10" r="7"/>',                              // dot
    '<rect x="3.5" y="3.5" width="13" height="13"/>',                         // square
    '<rect class="f" x="3.5" y="3.5" width="13" height="13"/>',               // block
    '<path d="M10 3L17.5 16.5H2.5Z"/>',                                       // triangle
    '<path class="f" d="M10 3L17.5 16.5H2.5Z"/>',
    '<path d="M10 2.5L17.5 10L10 17.5L2.5 10Z"/>',                            // diamond
    '<path class="f" d="M10 2.5L17.5 10L10 17.5L2.5 10Z"/>',
    '<path d="M10 16.5C4.5 12.5 2.5 9.8 2.5 7.2C2.5 4.8 4.3 3.3 6.3 3.3C7.9 3.3 9.2 4.2 10 5.6C10.8 4.2 12.1 3.3 13.7 3.3C15.7 3.3 17.5 4.8 17.5 7.2C17.5 9.8 15.5 12.5 10 16.5Z"/>',
    '<path class="f" d="M10 16.5C4.5 12.5 2.5 9.8 2.5 7.2C2.5 4.8 4.3 3.3 6.3 3.3C7.9 3.3 9.2 4.2 10 5.6C10.8 4.2 12.1 3.3 13.7 3.3C15.7 3.3 17.5 4.8 17.5 7.2C17.5 9.8 15.5 12.5 10 16.5Z"/>',
    '<path d="M10 2.4L12.1 8L18 8.2L13.3 11.9L14.9 17.6L10 14.3L5.1 17.6L6.7 11.9L2 8.2L7.9 8Z"/>',
    '<path class="f" d="M10 2.4L12.1 8L18 8.2L13.3 11.9L14.9 17.6L10 14.3L5.1 17.6L6.7 11.9L2 8.2L7.9 8Z"/>',
    '<path d="M10 3V17M3 10H17"/>',                                           // plus
    '<path d="M4.5 4.5L15.5 15.5M15.5 4.5L4.5 15.5"/>',                       // x
    '<path class="f" d="M13 3.4A7.25 7.25 0 1 0 13 16.6A7 7 0 0 1 13 3.4Z"/>', // moon
    '<circle cx="10" cy="10" r="3.6"/><path d="M10 1.5V4.2M10 15.8V18.5M1.5 10H4.2M15.8 10H18.5M4 4L5.9 5.9M14.1 14.1L16 16M16 4L14.1 5.9M5.9 14.1L4 16"/>', // sun
    '<path d="M1.8 13.5C5 6 12.5 5 17.5 10C12.5 15 5 14 1.8 6.5"/>',          // fish
    '<path d="M10 17.5V3M4.5 8.5L10 3L15.5 8.5"/>',                           // arrow
    '<path class="f" d="M11.5 1.8L4.5 11H9.5L8 18.2L15.5 8.5H10.5Z"/>',       // lightning
    '<path d="M10 2.5C10 2.5 4.5 9 4.5 12.3A5.5 5.5 0 0 0 15.5 12.3C15.5 9 10 2.5 10 2.5Z"/>', // drop
    '<path d="M3 15.5V6L7 10L10 4L13 10L17 6V15.5Z"/>',                       // crown
    '<path d="M1.5 10.5Q4 5 6.5 10.5T11.5 10.5T16.5 10.5"/>'                  // wave
  ];
  var LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

  function shuffled(list, rng) {
    var a = list.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }
  function symbol(shape) {
    return '<svg class="cs" viewBox="0 0 20 20" aria-hidden="true">' + shape + '</svg>';
  }

  function secretCode(ref, rng) {
    var text = ref.toUpperCase();
    var used = [];
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      if (/[A-Z0-9]/.test(ch) && used.indexOf(ch) === -1) used.push(ch);
    }
    // Up to 4 decoy letters, fewer for long references so the key
    // stays on one row, and never more than there are symbols
    var decoys = Math.max(0, Math.min(4, 17 - used.length, SHAPES.length - used.length));
    var spare = LETTERS.split('').filter(function (c) { return used.indexOf(c) === -1; });
    var keyChars = used.concat(shuffled(spare, rng).slice(0, decoys));
    var shapes = shuffled(SHAPES, rng);
    var map = {};
    keyChars.forEach(function (c, n) { map[c] = shapes[n % shapes.length]; });

    // The message: a symbol and a blank for each letter or number
    var msg = text.split(/\s+/).filter(Boolean).map(function (word) {
      var cells = word.split('').map(function (c) {
        return map[c]
          ? '<span class="cc">' + symbol(map[c]) + '<i></i></span>'
          : '<span class="cp">' + esc(c) + '</span>';
      }).join('');
      return '<span class="cw">' + cells + '</span>';
    }).join('');

    // The key: letters A to Z, then numbers
    var letters = keyChars.filter(function (c) { return /[A-Z]/.test(c); }).sort();
    var digits = keyChars.filter(function (c) { return /[0-9]/.test(c); }).sort();
    function pair(c) { return '<span class="kp">' + symbol(map[c]) + '<b>' + c + '</b></span>'; }
    var key = letters.map(pair).join('') +
      (digits.length ? '<span class="kp-gap"></span>' + digits.map(pair).join('') : '');

    return '<div class="code-msg" role="img" aria-label="' + esc(ref) + ' in secret code">' + msg + '</div>' +
      '<div class="code-key"><span class="code-key-label">Key</span>' + key + '</div>';
  }

  /* ── Maze ────────────────────────────────────────────────
     How one gets made:
       1. Carve one long winding maze.
       2. Wall it into 2 or 3 parts along the way from START to FINISH,
          so walking alone can never get you there.
       3. Join the parts with numbered jump circles (same number = hop
          across). One extra pair leads into a small sealed-off pocket:
          a dead end you can only get into, and out of, by jumping.
          No pair ever joins two places you could just walk between.
       4. Open a few extra gaps so each part has loops.
       5. False walls: draw a few gaps as dotted walls. Each one is the
          only way into the area behind it, so that area looks like a
          sealed room. At least one is on the way to FINISH; the others
          are rooms that go nowhere.
       6. Check it: solvable, needs a jump, and impossible if you treat
          the dotted walls as real walls.
     Up to 300 tries per shuffle (fewer for a big maze); the best one
     gets drawn. */
  var CELL = 20;                       // one square, in drawing units (about 0.21 inch)
  var MAZE_GREEN = '#15803d';
  // Pictures for the jump circles: solid shapes, easy to tell apart small
  var PAD_SHAPES = [
    'M10 2.4L12.1 8L18 8.2L13.3 11.9L14.9 17.6L10 14.3L5.1 17.6L6.7 11.9L2 8.2L7.9 8Z',   // star
    'M10 16.5C4.5 12.5 2.5 9.8 2.5 7.2C2.5 4.8 4.3 3.3 6.3 3.3C7.9 3.3 9.2 4.2 10 5.6C10.8 4.2 12.1 3.3 13.7 3.3C15.7 3.3 17.5 4.8 17.5 7.2C17.5 9.8 15.5 12.5 10 16.5Z', // heart
    'M13 3.4A7.25 7.25 0 1 0 13 16.6A7 7 0 0 1 13 3.4Z',                              // moon
    'M10 2L18 10L10 18L2 10Z',                                                        // diamond
    'M10 2.5L18 17H2Z',                                                               // triangle
    'M3.5 3.5H16.5V16.5H3.5Z',                                                        // square
    'M11.5 1.5L4 11H9.5L8 18.5L16 8.5H10.5Z'                                          // lightning
  ];

  function randInt(rng, n) { return Math.floor(rng() * n); }
  function r1(n) { return Math.round(n * 10) / 10; }

  // Each square's neighbors, worked out once per maze size (the checks
  // walk the maze thousands of times per shuffle, so this matters)
  var NBR_CACHE = {};
  function neighborLists(R, C) {
    var k = R + 'x' + C;
    if (NBR_CACHE[k]) return NBR_CACHE[k];
    var lists = [];
    for (var id = 0; id < R * C; id++) {
      var r = Math.floor(id / C), c = id % C, out = [];
      if (r > 0) out.push(id - C);
      if (r < R - 1) out.push(id + C);
      if (c > 0) out.push(id - 1);
      if (c < C - 1) out.push(id + 1);
      lists.push(out);
    }
    return (NBR_CACHE[k] = lists);
  }

  function Grid(R, C) {
    this.R = R; this.C = C; this.N = R * C;
    this.nb = neighborLists(R, C);
    this.openR = new Uint8Array(this.N);            // gap to the right of a square
    this.openD = new Uint8Array(this.N);            // gap below a square
    this.fake = {};                                 // gaps drawn as dotted "false walls"
    this.partner = new Int32Array(this.N).fill(-1); // jump circle -> its twin
    this.sym = {};                                  // jump circle -> its picture
  }
  Grid.prototype.nbrs = function (id) { return this.nb[id]; };
  Grid.prototype.key = function (a, b) {
    var lo = Math.min(a, b), hi = Math.max(a, b);
    return lo * 2 + (hi - lo === 1 ? 0 : 1);
  };
  Grid.prototype.isOpen = function (a, b) {
    var lo = Math.min(a, b), hi = Math.max(a, b);
    return (hi - lo === 1 ? this.openR[lo] : this.openD[lo]) === 1;
  };
  Grid.prototype.setOpen = function (a, b, v) {
    var lo = Math.min(a, b), hi = Math.max(a, b);
    if (hi - lo === 1) this.openR[lo] = v; else this.openD[lo] = v;
  };
  Grid.prototype.adjacent = function (a, b) { return this.nbrs(a).indexOf(b) !== -1; };
  Grid.prototype.degree = function (id) {
    var g = this;
    return this.nbrs(id).filter(function (n) { return g.isOpen(id, n); }).length;
  };
  // Where can you go from here? jumps: allow hopping between circles.
  // solidFake: pretend the dotted walls are real walls.
  Grid.prototype.moves = function (id, jumps, solidFake) {
    var g = this, out = [];
    this.nbrs(id).forEach(function (n) {
      if (!g.isOpen(id, n)) return;
      if (solidFake && g.fake[g.key(id, n)]) return;
      out.push(n);
    });
    if (jumps && this.partner[id] >= 0) out.push(this.partner[id]);
    return out;
  };
  Grid.prototype.walk = function (src, jumps, solidFake) {
    var dist = new Int32Array(this.N).fill(-1), prev = new Int32Array(this.N).fill(-1);
    var q = [src], h = 0;
    dist[src] = 0;
    while (h < q.length) {
      var cur = q[h++], ms = this.moves(cur, jumps, solidFake);
      for (var i = 0; i < ms.length; i++) {
        if (dist[ms[i]] < 0) { dist[ms[i]] = dist[cur] + 1; prev[ms[i]] = cur; q.push(ms[i]); }
      }
    }
    return { dist: dist, prev: prev };
  };

  function carve(g, rng) {            // one long winding maze (a "recursive backtracker")
    var seen = new Uint8Array(g.N), stack = [randInt(rng, g.N)];
    seen[stack[0]] = 1;
    while (stack.length) {
      var cur = stack[stack.length - 1];
      var opts = g.nbrs(cur).filter(function (n) { return !seen[n]; });
      if (!opts.length) { stack.pop(); continue; }
      var nx = opts[randInt(rng, opts.length)];
      g.setOpen(cur, nx, 1);
      seen[nx] = 1;
      stack.push(nx);
    }
    g.start = randInt(rng, g.C);
    g.finish = (g.R - 1) * g.C + randInt(rng, g.C);
  }

  function mazeAttempt(R, C, rng, useFakes) {
    var g = new Grid(R, C), N = g.N, start, finish;
    carve(g, rng);
    start = g.start; finish = g.finish;

    // Wall it into parts at 1 or 2 spots along the way from START to FINISH
    var t = g.walk(start, false), path = [];
    for (var p = finish; p !== -1; p = t.prev[p]) path.unshift(p);
    var L = path.length - 1;
    if (L < 8) return null;
    function spot(lo, hi) {
      var a = Math.floor(L * lo), span = Math.max(1, Math.floor(L * (hi - lo)));
      return Math.min(L - 1, a + randInt(rng, span));
    }
    var cuts;
    if (N >= 250) cuts = rng() < 0.5 ? [spot(0.15, 0.3), spot(0.42, 0.58), spot(0.7, 0.85)]
                                     : [spot(0.2, 0.42), spot(0.58, 0.8)];
    else if (N >= 90 && rng() < 0.65) cuts = [spot(0.2, 0.42), spot(0.58, 0.8)];
    else cuts = [spot(0.3, 0.7)];
    cuts.forEach(function (i) { g.setOpen(path[i], path[i + 1], 0); });

    // Seal off a small pocket away from the route (two in a big maze).
    // An extra jump pair leads into each: a dead end you can only reach,
    // and only leave, by jumping.
    var routeCell = new Uint8Array(N), inPocket = new Uint8Array(N);
    path.forEach(function (c) { routeCell[c] = 1; });
    var pocketMax = Math.min(24, Math.max(8, Math.round(N * 0.11)));
    var pocketCells = [], pocketsWanted = N >= 250 ? 2 : 1;
    for (var pk = 0; pk < pocketsWanted; pk++) {
      var tree = [];
      for (var u = 0; u < N; u++) {
        g.nbrs(u).forEach(function (v) {
          if (v > u && g.isOpen(u, v) && !inPocket[u] && !inPocket[v]) tree.push([u, v]);
        });
      }
      shuffled(tree, rng).slice(0, 40).some(function (e) {
        if (routeCell[e[0]] && routeCell[e[1]]) return false;
        g.setOpen(e[0], e[1], 0);
        var sides = [e[0], e[1]].map(function (c) {
          var d = g.walk(c, false).dist, n = 0, touchesPath = false;
          for (var k = 0; k < N; k++) if (d[k] >= 0) { n++; if (routeCell[k]) touchesPath = true; }
          return { cell: c, size: n, touchesPath: touchesPath, dist: d };
        });
        var pocket = sides.filter(function (sd) { return !sd.touchesPath; })[0];
        if (pocket && pocket.size >= 5 && pocket.size <= pocketMax) {
          pocketCells.push(pocket.cell);
          for (var k2 = 0; k2 < N; k2++) if (pocket.dist[k2] >= 0) inPocket[k2] = 1;
          return true;
        }
        g.setOpen(e[0], e[1], 1);               // not a good pocket: put the gap back
        return false;
      });
    }

    var comp = new Int32Array(N).fill(-1), sizes = [];
    for (var s = 0; s < N; s++) {
      if (comp[s] >= 0) continue;
      var d0 = g.walk(s, false).dist, n = 0;
      for (var k = 0; k < N; k++) if (d0[k] >= 0) { comp[k] = sizes.length; n++; }
      sizes.push(n);
    }
    var chain = [comp[start]];      // the parts, in the order you pass through them
    cuts.forEach(function (i) { chain.push(comp[path[i + 1]]); });
    if (chain[chain.length - 1] !== comp[finish]) return null;
    var minPart = chain.length >= 4 ? 0.12 : 0.18;
    if (chain.some(function (c) { return sizes[c] < N * minPart; })) return null;

    // A few extra gaps inside each part, so there are loops to get lost in
    var walls = [];
    for (var a = 0; a < N; a++) {
      g.nbrs(a).forEach(function (b) {
        if (b > a && !g.isOpen(a, b) && comp[a] === comp[b]) walls.push([a, b]);
      });
    }
    shuffled(walls, rng).slice(0, Math.round(N / 15)).forEach(function (w) {
      g.setOpen(w[0], w[1], 1);
    });

    // Jump circles: never on START/FINISH or right beside them, never
    // touching each other, and happiest tucked into dead ends.
    var dS = g.walk(start, false).dist, dF = g.walk(finish, false).dist;
    var pads = [];
    function placePad(c, awayFrom) {
      var cands = [];
      for (var id = 0; id < N; id++) {
        if (comp[id] !== c || id === start || id === finish) continue;
        if ((dS[id] >= 0 && dS[id] < 3) || (dF[id] >= 0 && dF[id] < 3)) continue;
        if (pads.some(function (q) { return q === id || g.adjacent(q, id); })) continue;
        cands.push(id);
      }
      if (!cands.length) return -1;
      var dead = cands.filter(function (id) { return g.degree(id) === 1; });
      var pool = dead.length >= 3 ? dead : cands;
      if (awayFrom != null) {                 // pick from the farther half
        var d = g.walk(awayFrom, false).dist;
        pool = pool.slice().sort(function (x, y) { return d[y] - d[x]; });
        pool = pool.slice(0, Math.max(1, Math.ceil(pool.length / 2)));
      }
      var pick = pool[randInt(rng, pool.length)];
      pads.push(pick);
      return pick;
    }
    var pairs = [], from = placePad(chain[0], start);
    for (var j = 1; j < chain.length; j++) {
      var last = j === chain.length - 1;
      var to = placePad(chain[j], last ? finish : null);
      if (from < 0 || to < 0) return null;
      pairs.push([from, to]);
      if (!last) from = placePad(chain[j], to);
    }
    pocketCells.forEach(function (pc) {                // pairs that lead nowhere
      var e1 = placePad(chain[randInt(rng, chain.length)], null);
      var e2 = e1 < 0 ? -1 : placePad(comp[pc], null);
      if (e1 >= 0 && e2 >= 0) pairs.push([e1, e2]);
    });
    // Each pair gets its own picture, so there's no order to read into
    var pics = shuffled(PAD_SHAPES.map(function (x, i) { return i; }), rng);
    pairs.forEach(function (pr, i) {
      g.partner[pr[0]] = pr[1];
      g.partner[pr[1]] = pr[0];
      g.sym[pr[0]] = g.sym[pr[1]] = pics[i % pics.length];
    });

    // False walls. Each one goes on a gap that is the only way (on foot)
    // into the area behind it, so drawn dotted, that area looks sealed.
    // Never touching START or FINISH, and spread out.
    var fakes = [];
    function tooClose(e) {
      return fakes.some(function (o) {
        return o.some(function (x) {
          return e.some(function (y) {
            return Math.abs(Math.floor(x / C) - Math.floor(y / C)) + Math.abs(x % C - y % C) <= 2;
          });
        });
      });
    }
    function room(e) {               // size of the smaller side, or 0 if it isn't sealed
      g.setOpen(e[0], e[1], 0);
      var d0 = g.walk(e[0], false).dist, d1 = g.walk(e[1], false).dist;
      g.setOpen(e[0], e[1], 1);
      if (d0[e[1]] >= 0) return 0;   // there's another way round: not a room
      var n0 = 0, n1 = 0;
      for (var k = 0; k < N; k++) { if (d0[k] >= 0) n0++; if (d1[k] >= 0) n1++; }
      return { size: Math.min(n0, n1), side: n0 <= n1 ? d0 : d1 };
    }
    function usable(e) {
      return e[0] !== start && e[1] !== start && e[0] !== finish && e[1] !== finish &&
             !g.fake[g.key(e[0], e[1])] && !tooClose(e);
    }
    if (useFakes) {
      // On the way to FINISH, ones you can't do without (2 in a big maze)
      var run0 = g.walk(start, true), route = [];
      for (var p2 = finish; p2 !== -1; p2 = run0.prev[p2]) route.unshift(p2);
      var steps = route.slice(1).map(function (c, i) { return [route[i], c]; });
      var mustHave = N >= 250 ? 2 : 1;
      shuffled(steps, rng).some(function (e) {
        if (fakes.length >= mustHave) return true;
        if (!g.adjacent(e[0], e[1]) || !usable(e)) return false;   // a jump, or a bad spot
        var rm = room(e);
        if (!rm || rm.size < 3) return false;
        g.setOpen(e[0], e[1], 0);                                  // is there any way round it?
        var needed = g.walk(start, true).dist[finish] < 0;
        g.setOpen(e[0], e[1], 1);
        if (!needed) return false;
        g.fake[g.key(e[0], e[1])] = true;
        fakes.push(e);
        return false;
      });
      if (!fakes.length) return null;

      // More that lead into rooms with no START or FINISH in them
      var extra = N >= 250 ? 3 + randInt(rng, 3) : 2 + randInt(rng, 2);
      var want = fakes.length + extra, gaps = [];
      for (var x = 0; x < N; x++) {
        g.nbrs(x).forEach(function (y) { if (y > x && g.isOpen(x, y)) gaps.push([x, y]); });
      }
      shuffled(gaps, rng).some(function (e) {
        if (fakes.length >= want) return true;
        if (!usable(e)) return false;
        var rm = room(e);
        if (!rm || rm.size < 3 || rm.size > N * 0.3) return false;
        if (rm.side[start] >= 0 || rm.side[finish] >= 0) return false;
        g.fake[g.key(e[0], e[1])] = true;
        fakes.push(e);
        return false;
      });
    }

    // The checks
    var run = g.walk(start, true), len = run.dist[finish];
    if (len < 0) return null;                                        // must be solvable
    if (g.walk(start, false).dist[finish] >= 0) return null;          // must need a jump
    if (pairs.some(function (pr) {                                   // never jump where you could walk
      return g.walk(pr[0], false).dist[pr[1]] >= 0;
    })) return null;
    if (useFakes && g.walk(start, true, true).dist[finish] >= 0) return null;  // must need a false wall
    var onRoute = 0, reach = 0;
    for (var q = finish; q !== start; q = run.prev[q]) {
      var pq = run.prev[q];
      if (g.adjacent(pq, q) && g.fake[g.key(pq, q)]) onRoute++;
    }
    for (var z = 0; z < N; z++) if (run.dist[z] >= 0) reach++;
    g.good = !useFakes || len >= R + C;
    g.score = len + 5 * Math.min(onRoute, 2) + 2 * fakes.length - 0.15 * (N - reach);
    return g;
  }

  function makeMaze(R, C, rng) {
    var best = null, g, i;
    var tries = Math.max(40, Math.round(300 * 126 / (R * C)));   // fewer for a big maze
    for (i = 0; i < tries; i++) {
      g = mazeAttempt(R, C, rng, true);
      if (!g) continue;
      if (!best || (g.good && !best.good) || (g.good === best.good && g.score > best.score)) best = g;
    }
    if (best) return best;
    for (i = 0; i < 60; i++) {              // no false walls: jumps only
      g = mazeAttempt(R, C, rng, false);
      if (g) return g;
    }
    g = new Grid(R, C);                      // last resort: a plain maze
    carve(g, rng);
    return g;
  }

  function drawMaze(g) {
    var R = g.R, C = g.C, W = C * CELL, H = R * CELL, LAB = 15, M = 2;
    var ox = M, oy = LAB + M, vw = W + 2 * M, vh = H + 2 * LAB + 2 * M;
    function cx(id) { return ox + (id % C + 0.5) * CELL; }
    function cy(id) { return oy + (Math.floor(id / C) + 0.5) * CELL; }

    var d = '', grid = '', dots = '';
    function seg(x1, y1, x2, y2) { return 'M' + x1 + ' ' + y1 + 'L' + x2 + ' ' + y2; }
    for (var id = 0; id < g.N; id++) {
      var r = Math.floor(id / C), c = id % C, x = ox + c * CELL, y = oy + r * CELL;
      // walls
      if (r === 0 ? id !== g.start : !g.isOpen(id, id - C)) d += seg(x, y, x + CELL, y);
      if (c === 0 || !g.isOpen(id, id - 1)) d += seg(x, y, x, y + CELL);
      if (c === C - 1) d += seg(x + CELL, y, x + CELL, y + CELL);
      if (r === R - 1 && id !== g.finish) d += seg(x, y + CELL, x + CELL, y + CELL);
      // faint grid on open gaps, and dots on false walls
      if (c < C - 1 && g.isOpen(id, id + 1)) {
        if (g.fake[g.key(id, id + 1)]) dots += seg(x + CELL, y + 2.6, x + CELL, y + CELL - 2.6);
        else grid += seg(x + CELL, y, x + CELL, y + CELL);
      }
      if (r < R - 1 && g.isOpen(id, id + C)) {
        if (g.fake[g.key(id, id + C)]) dots += seg(x + 2.6, y + CELL, x + CELL - 2.6, y + CELL);
        else grid += seg(x, y + CELL, x + CELL, y + CELL);
      }
    }
    var out = '<svg class="maze-svg" viewBox="0 0 ' + vw + ' ' + vh + '" ' +
      'preserveAspectRatio="xMidYMid meet" role="img" aria-label="Maze">' +
      '<path d="' + grid + '" fill="none" stroke="#d6d6d6" stroke-width="0.8"/>' +
      '<path d="' + d + '" fill="none" stroke="#0a0a0a" stroke-width="2" stroke-linecap="square"/>' +
      // Dots packed tight: reads as a wall from across the page, clearly
      // broken up close
      '<path d="' + dots + '" fill="none" stroke="#0a0a0a" stroke-width="2.5" ' +
      'stroke-linecap="round" stroke-dasharray="0 3.6"/>';

    for (var i = 0; i < g.N; i++) {
      if (g.partner[i] < 0) continue;
      out += '<circle cx="' + cx(i) + '" cy="' + cy(i) + '" r="8.2" fill="#ffffff" stroke="' +
        MAZE_GREEN + '" stroke-width="1.8"/>' +
        '<path transform="translate(' + r1(cx(i) - 5.25) + ' ' + r1(cy(i) - 5.25) + ') scale(0.525)" ' +
        'fill="' + MAZE_GREEN + '" d="' + PAD_SHAPES[g.sym[i]] + '"/>';
    }

    function label(cell, text, ty) {
      var c = cell % C, tx = cx(cell), anchor = 'middle';
      if (c === 0) { tx = ox + 1; anchor = 'start'; }
      else if (c === C - 1) { tx = ox + W - 1; anchor = 'end'; }
      return '<text class="maze-end" x="' + tx + '" y="' + ty + '" text-anchor="' + anchor + '">' + text + '</text>';
    }
    out += label(g.start, 'START', oy - 5) + label(g.finish, 'FINISH', oy + H + 12);
    return out + '</svg>';
  }

  /* ── The activities ─────────────────────────────────── */
  var ACTIVITIES = {
    verse: function (body, rng, box) {
      var list = VERSES.length ? VERSES : ['John 3:16'];
      var last = box.getAttribute('data-ref');
      var ref = pick(list, rng);
      for (var tries = 0; ref === last && tries < 20; tries++) ref = pick(list, rng);
      box.setAttribute('data-ref', ref);
      body.innerHTML = secretCode(ref, rng);
      // Only on screen, above the sheet: which verse this sheet has
      var answer = document.getElementById('kids-answer');
      if (answer) answer.textContent = ref;
    },
    words: placeholder('Word search',
      'A letter grid with a word bank underneath.'),
    maze: function (body, rng) {
      // As many quarter-inch squares as fit the box
      var C = Math.max(8, Math.min(18, Math.floor((body.clientWidth - 4) / CELL)));
      var R = Math.max(6, Math.min(30, Math.floor((body.clientHeight - 34) / CELL)));
      body.innerHTML = drawMaze(makeMaze(R, C, rng));
    },
    draw: placeholder('Draw it',
      'A drawing prompt and a big open box.')
  };

  function shuffle(box, flash) {
    var make = ACTIVITIES[box.getAttribute('data-act')];
    if (!make) return;
    var seed = newSeed();
    box.setAttribute('data-seed', seed);
    make(box.querySelector('.act-body'), makeRng(seed), box);
    if (flash) {
      box.classList.remove('shuffled');
      void box.offsetWidth;   // restart the flash
      box.classList.add('shuffled');
    }
  }

  var boxes = sheet.querySelectorAll('.act[data-act]');
  for (var i = 0; i < boxes.length; i++) {
    (function (box) {
      box.addEventListener('click', function () { shuffle(box, true); });
      box.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); shuffle(box, true); }
      });
      shuffle(box, false);
    })(boxes[i]);
  }

  /* ── Next up: the first event that's today or later ──── */
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  // A short line with a number and am/pm, noon, or a colon: "10:30 AM", "6pm"
  var TIME_RE = /^(?=.*\d)(?=.*(a\.?m|p\.?m|noon|\d:\d\d)).{1,24}$/i;
  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function drawEvent() {
    var out = document.getElementById('sheet-event');
    var now = new Date();
    var today = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
    var next = null;
    for (var j = 0; j < EVENTS.length; j++) {
      if (EVENTS[j][0] >= today) { next = EVENTS[j]; break; }
    }
    if (!next) {
      out.innerHTML = '<p class="ev-title">See you next time at Grace House!</p>';
      return;
    }
    var p = next[0].split('-');
    var d = new Date(+p[0], +p[1] - 1, +p[2]);
    var when = (next[0] === today ? 'Today' : DAYS[d.getDay()]) + ', ' +
               MONTHS[d.getMonth()] + ' ' + d.getDate();
    var title = '', more = [];
    next[1].forEach(function (line) {
      line = line.replace(/^[-*]\s+/, '').trim();
      if (!line) return;
      if (TIME_RE.test(line)) when += ', ' + line;
      else if (!title) title = line;
      else more.push(line);
    });
    out.innerHTML =
      '<p class="ev-title">' + esc(title || 'Gathering at Grace House') + '</p>' +
      '<p class="ev-more"><span class="ev-when">' + esc(when) + '.</span> ' +
      esc(more.join(' ')) + '</p>';
  }
  drawEvent();

  /* ── Fit the preview to the screen (printing ignores this) ── */
  var SHADOW = 6;
  function fit() {
    var s = Math.min(1, (wrap.clientWidth - SHADOW) / sheet.offsetWidth);
    sheet.style.transform = s < 1 ? 'scale(' + s + ')' : '';
    wrap.style.height = Math.ceil(sheet.offsetHeight * s) + SHADOW + 'px';
  }
  fit();
  window.addEventListener('resize', fit);

  /* ── Printing ───────────────────────────────────────── */
  // Some browsers (Safari) print from the current scroll position, so
  // jump to the top while printing and come back afterward. Covers both
  // the Print button and Cmd+P / Ctrl+P.
  var savedY = null;
  function toTop() {
    if (savedY === null) savedY = window.scrollY;
    window.scrollTo(0, 0);
  }
  function comeBack() {
    if (savedY !== null) { window.scrollTo(0, savedY); savedY = null; }
  }
  window.addEventListener('beforeprint', toTop);
  window.addEventListener('afterprint', comeBack);
  document.getElementById('kids-print').onclick = function () { toTop(); window.print(); };
})();
"""


# ─────────────────────────────────────────────────────────────
# Markup

# The Grace House wheel (8 spokes), drawn in the text color. Same shape
# as BRAND_LOGO in server.py, with heavier lines for the solid title.
# Rim and spokes share one line weight.
SHEET_WHEEL = (
    '<svg class="sh-wheel" viewBox="0 0 34 34" aria-hidden="true" '
    'fill="none" stroke="currentColor">'
    '<circle cx="17" cy="17" r="13.6" stroke-width="3"/>'
    '<line x1="17" y1="4" x2="17" y2="30" stroke-width="3"/>'
    '<line x1="4" y1="17" x2="30" y2="17" stroke-width="3"/>'
    '<line x1="7.81" y1="7.81" x2="26.19" y2="26.19" stroke-width="3"/>'
    '<line x1="26.19" y1="7.81" x2="7.81" y2="26.19" stroke-width="3"/>'
    '<circle cx="17" cy="17" r="3.4" fill="currentColor" stroke="none"/>'
    "</svg>"
)

# The maze's two rules, drawn the same way the maze draws them.
MAZE_RULES = (
    '<div class="maze-rules">'
    '<span><svg viewBox="0 0 20 20" aria-hidden="true">'
    '<circle cx="10" cy="10" r="8.2" fill="#ffffff" stroke="#15803d" stroke-width="1.8"/>'
    '<path transform="translate(4.75 4.75) scale(0.525)" fill="#15803d" '
    'd="M10 2.4L12.1 8L18 8.2L13.3 11.9L14.9 17.6L10 14.3L5.1 17.6L6.7 11.9L2 8.2L7.9 8Z"/>'
    "</svg>Same picture? Hop across!</span>"
    '<span><svg viewBox="0 0 20 20" aria-hidden="true">'
    '<path d="M0.5 10H4M16 10H19.5" stroke="#0a0a0a" stroke-width="2"/>'
    '<path d="M6.4 10H13.6" stroke="#0a0a0a" stroke-width="2.3" stroke-linecap="round" stroke-dasharray="0 2.4"/>'
    "</svg>Dotted wall? Walk through!</span>"
    "</div>"
)


def _act(name: str, title: str, note: str = "", note_html: str = "") -> str:
    """One shuffleable box: a label chip, optional directions beside it
    (plain text as note, or ready-made markup as note_html), and an
    empty body for its maker."""
    if note:
        note_html = f'<p class="act-note">{escape(note)}</p>'
    return (
        f'<section class="act act-{name}" data-act="{name}" role="button" tabindex="0" '
        f'aria-label="{escape(title)}. Tap to shuffle.">'
        f'<h2 class="act-label">{escape(title)}</h2>'
        f"{note_html}"
        '<div class="act-body"></div>'
        "</section>"
    )


def render_kids_sheet(verses: list[str], events) -> str:
    """The toolbar, the printable sheet, and its own CSS and JS.

    verses: ["John 3:16", ...]              from server.load_verses()
    events: [(date, [detail lines]), ...]   from server.parse_events()[0]
    """
    verse_data = escape(json.dumps(verses or FALLBACK_VERSES, ensure_ascii=False))
    event_data = escape(json.dumps(
        [[when.isoformat(), list(lines)] for when, lines in events],
        ensure_ascii=False,
    ))
    return (
        f"<style>{KIDS_CSS}</style>\n"
        '<div class="kids-bar">'
        '<button id="kids-print" class="kids-print" type="button">Print this sheet</button>'
        '<span class="kids-hint">Tap any box to shuffle it.<br>'
        'This sheet\'s verse: <b id="kids-answer"></b></span>'
        "</div>\n"
        '<div id="sheet-wrap" class="sheet-wrap">\n'
        f'<div id="sheet" class="sheet" data-verses="{verse_data}" data-events="{event_data}">\n'
        '<header class="sh-head">'
        '<div class="sh-brand">'
        '<span class="sh-sr">Grace House Kids</span>'
        f'<span aria-hidden="true">Grace H</span>{SHEET_WHEEL}'
        '<span aria-hidden="true">use Kids</span>'
        "</div>"
        '<div class="sh-kind">Activity Sheet</div>'
        "</header>\n"
        f'{_act("verse", "Look it up", "Crack the code, then find the verse in a Bible.")}\n'
        '<div class="sh-grid">\n'
        f'{_act("words", "Word search")}\n'
        f'{_act("maze", "Maze", note_html=MAZE_RULES)}\n'
        f'{_act("draw", "Draw it")}\n'
        "</div>\n"
        '<footer class="sh-foot">'
        '<h2 class="act-label">Next up</h2>'
        '<div id="sheet-event" class="ev-text"></div>'
        "</footer>\n"
        "</div>\n"
        "</div>\n"
        f"<script>{KIDS_JS}</script>"
    )
