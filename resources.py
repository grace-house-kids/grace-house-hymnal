"""resources.py — downloadable files, grouped into categories.

Drop files into ./resources/<category>/ and they show up under the
Resources section: the Resources page lists each category, and each
category page lists its files with a download link (image files also
get a small preview).

    resources/
      tracts/
        01-the-gospel.pdf
        02-who-is-jesus.pdf
      shirt-designs/
        wheel-front.png
        wheel-back.png

Adding a category is just making a new folder — no code changes, same
as dropping a hymn in ./hymns.

Names: category folders and file names both take an OPTIONAL "NN-"
number prefix that sets their order and is stripped from what's shown.
The rest of the name becomes a title (dashes/underscores -> spaces,
Title Case). So "01-the-gospel.pdf" is shown as "The Gospel", and the
folder "02-shirt designs" is shown as "Shirt Designs" at the address
/resources/shirt-designs/.

Optional blurb: put an "about.txt" in a category folder. Its first
line is shown as a one-line description under the category. It is not
listed as a downloadable file.

Speed drills: put a "drills.txt" in a category folder and that category
becomes a Bible speed drill instead of a file list. Pressing New counts
down (like the musician page's countdown before scrolling), then shows
a random reference and starts a stopwatch; "Found it" stops the clock
and shows the verse to check. Every verse comes up once before any
repeats. One verse per line, # for comments:

    Ephesians 2:8-9 | For by grace are ye saved through faith; ...
    Romans 5:8                     <- text is optional

Any other files in that folder are still listed for download below the
drill. See resources/speed-drills/.
"""
from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
RESOURCES_DIR = HERE / "resources"

# Never listed as downloadable files.
_HIDDEN = {"about.txt", "drills.txt", ".ds_store", "thumbs.db"}
# Seconds of countdown before a speed-drill verse appears.
DRILL_COUNTDOWN = 3
# Files we show a thumbnail for instead of a type badge.
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
# Leading "01-", "02_", "3 " ... used for ordering, stripped from display.
_NUM_PREFIX = re.compile(r"^\s*(\d+)\s*[-_. ]\s*(.+)$")


def _split_order(name: str) -> tuple[int, str]:
    """'01-the-gospel' -> (1, 'the-gospel'). No prefix -> (big, name)."""
    m = _NUM_PREFIX.match(name)
    if m:
        return int(m.group(1)), m.group(2)
    return 10 ** 9, name


def _titleize(stem: str) -> str:
    words = re.split(r"[-_ ]+", stem.strip())
    return " ".join(w[:1].upper() + w[1:] for w in words if w) or stem


def _slugify(stem: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f}".rstrip("0").rstrip(".") + f" {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def parse_drills(path: Path) -> list[list[str]]:
    """[[reference, text], ...] from a drills.txt ("Ref | text" per
    line, text optional, # lines and blank lines skipped)."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    drills = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        ref, _, text = s.partition("|")
        if ref.strip():
            drills.append([ref.strip(), text.strip()])
    return drills


def parse_resources():
    """Return [category, ...] or None if there's nothing to show.

    Each category is a dict:
        slug   URL segment ("shirt-designs")
        folder on-disk folder name (used to find files, never in a URL)
        title  display name ("Shirt Designs")
        desc   one-line blurb from about.txt, or ""
        files  [file, ...]
        drills [[reference, text], ...] from drills.txt, or []
    Each file is a dict:
        name     on-disk filename ("01-the-gospel.pdf")
        title    display title ("The Gospel")
        ext      lowercase extension without dot ("pdf")
        size     human size ("1.2 MB") or ""
        is_image whether to show a preview thumbnail
    """
    if not RESOURCES_DIR.is_dir():
        return None
    categories = []
    for folder in RESOURCES_DIR.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        desc = ""
        about = folder / "about.txt"
        if about.exists():
            try:
                lines = about.read_text(encoding="utf-8").strip().splitlines()
                desc = lines[0].strip() if lines else ""
            except OSError:
                desc = ""

        files = []
        for f in folder.iterdir():
            if (not f.is_file() or f.name.startswith(".")
                    or f.name.lower() in _HIDDEN):
                continue
            order, stem_name = _split_order(f.stem)
            try:
                size = _human_size(f.stat().st_size)
            except OSError:
                size = ""
            files.append({
                "name": f.name,
                "title": _titleize(stem_name),
                "ext": f.suffix.lower().lstrip("."),
                "size": size,
                "is_image": f.suffix.lower() in _IMAGE_EXTS,
                "_order": (order, f.name.lower()),
            })
        drills = parse_drills(folder / "drills.txt")
        if not files and not drills:
            continue
        files.sort(key=lambda d: d["_order"])

        order, slug_stem = _split_order(folder.name)
        categories.append({
            "slug": _slugify(slug_stem),
            "folder": folder.name,
            "title": _titleize(slug_stem),
            "desc": desc,
            "files": files,
            "drills": drills,
            "_order": (order, folder.name.lower()),
        })
    if not categories:
        return None
    categories.sort(key=lambda c: c["_order"])
    return categories


def find_category(categories, slug):
    return next((c for c in categories if c["slug"] == slug), None)


def find_resource_file(categories, slug, filename):
    """The Path to a file, or None. Only returns files that are actually
    listed (a whitelist match on the exact name), so a crafted URL can't
    reach outside the category folder — no path traversal is possible."""
    cat = find_category(categories, slug)
    if cat is None:
        return None
    for f in cat["files"]:
        if f["name"] == filename:
            p = RESOURCES_DIR / cat["folder"] / f["name"]
            if p.is_file():
                return p
    return None


# ─────────────────────────────────────────────────────────────
# Rendering  (returns the inner body; server.py wraps it with the
# brand mark + page() shell, same as the other sections.)
def render_resources(categories) -> str:
    """The Resources index: the bulletin button, then one card per category."""
    bulletin = (
        '<ul class="sections bulletin-cta">\n'
        '<li><a class="sec" href="bulletin">'
        '<span><span class="sec-name">Print the Bulletin</span>'
        "<span class=\"sec-sub\">This week's tri-fold, ready to fold &amp; print</span>"
        '</span><span class="sec-arrow" aria-hidden="true">→</span></a></li>\n'
        "</ul>\n"
    )
    if not categories:
        return (bulletin
                + '<p class="res-empty">Nothing here yet. Make a folder under '
                "./resources (like resources/tracts) and drop files in.</p>")
    total = sum(len(c["files"]) for c in categories)
    items = []
    for c in categories:
        n = len(c["files"])
        if c["drills"] and not c["desc"]:
            sub = f'{len(c["drills"])} verses'
        else:
            sub = c["desc"] or f"{n} file" + ("" if n == 1 else "s")
        items.append(
            f'<li><a class="sec" href="resources/{quote(c["slug"])}/">'
            f'<span><span class="sec-name">{escape(c["title"])}</span>'
            f'<span class="sec-sub">{escape(sub)}</span></span>'
            f'<span class="sec-arrow" aria-hidden="true">→</span></a></li>'
        )
    plural = "" if total == 1 else "s"
    meta = (
        '<div class="meta-strip">'
        f'<span class="count-tag">{total} file{plural}</span>'
        '<div class="dash-rule"></div>'
        '<span class="hint">↓ pick one</span>'
        "</div>\n"
    )
    return bulletin + meta + '<ul class="sections">\n' + "\n".join(items) + "\n</ul>"

def render_drill(category) -> str:
    """A speed-drill category: the reference card, New / Found it, the
    stopwatch and the countdown card (the musician page's .countdown /
    .cd-box look from server.py's CSS). DRILL_JS does the rest."""
    drills = category["drills"]
    n = len(drills)
    data = escape(json.dumps(drills, ensure_ascii=False))
    meta = (
        '<div class="meta-strip">'
        f'<span class="count-tag">{n} verse{"" if n == 1 else "s"}</span>'
        '<div class="dash-rule"></div>'
        '<span class="hint">↓ tap new</span>'
        "</div>\n"
    )
    desc_html = (f'<p class="res-desc">{escape(category["desc"])}</p>'
                 if category["desc"] else "")
    return (
        f'<div class="title-tag"><h1>{escape(category["title"].upper())}</h1></div>\n'
        f"{meta}{desc_html}"
        f'<div class="drill" id="drill" data-drills="{data}" data-countdown="{DRILL_COUNTDOWN}">'
        '<div class="drill-card">'
        '<p class="drill-ref" id="drill-ref" aria-live="polite">Bibles closed.</p>'
        '<p class="drill-clock" id="drill-clock">Tap New when everyone’s ready.</p>'
        '<p class="drill-text" id="drill-text" hidden></p>'
        "</div>"
        '<div class="drill-btns">'
        '<button type="button" class="drill-new" id="drill-new">New</button>'
        '<button type="button" class="drill-found" id="drill-found" hidden>Found it</button>'
        "</div>"
        "</div>\n"
        '<div id="drill-cd" class="countdown" hidden aria-live="polite">'
        '<div class="cd-box">'
        '<div class="cd-msg">Swords ready</div>'
        f'<div id="drill-cd-num" class="cd-num">{DRILL_COUNTDOWN}</div>'
        '<div class="cd-hint">tap new to skip</div>'
        "</div></div>\n"
        f"<script>{DRILL_JS}</script>"
    )


# New → countdown → random reference + stopwatch → Found it stops the
# clock and shows the verse. A shuffled deck, so every verse comes up
# once before any repeats (and never the same one twice in a row).
DRILL_JS = r"""
(function () {
  var box = document.getElementById('drill');
  if (!box) return;
  var drills = [];
  try { drills = JSON.parse(box.getAttribute('data-drills')) || []; } catch (e) {}
  if (!drills.length) return;
  var COUNT = parseInt(box.getAttribute('data-countdown'), 10) || 3;
  function $(id) { return document.getElementById(id); }
  var refEl = $('drill-ref'), clockEl = $('drill-clock'), textEl = $('drill-text');
  var newBtn = $('drill-new'), foundBtn = $('drill-found');
  var cd = $('drill-cd'), cdNum = $('drill-cd-num');

  var deck = [], last = -1;
  function draw() {
    if (!deck.length) {
      for (var i = 0; i < drills.length; i++) deck.push(i);
      for (var j = deck.length - 1; j > 0; j--) {        // shuffle
        var k = Math.floor(Math.random() * (j + 1)), t = deck[j]; deck[j] = deck[k]; deck[k] = t;
      }
      if (deck.length > 1 && deck[deck.length - 1] === last) deck.unshift(deck.pop());
    }
    last = deck.pop();
    return drills[last];
  }

  var timer = 0, raf = 0, started = 0, counting = false;
  function secs(ms) { return (ms / 1000).toFixed(1) + 's'; }
  function tick() {
    clockEl.textContent = secs(Date.now() - started);
    raf = requestAnimationFrame(tick);
  }
  function stopClock() { cancelAnimationFrame(raf); raf = 0; }

  function reveal() {
    counting = false;
    cd.hidden = true;
    var d = draw();
    refEl.textContent = d[0];
    textEl.textContent = d[1] || '';
    textEl.hidden = true;
    foundBtn.hidden = false;
    clockEl.classList.remove('done');
    started = Date.now();
    stopClock(); tick();
  }

  newBtn.onclick = function () {
    clearInterval(timer);
    stopClock();
    if (counting) { reveal(); return; }           // tap again to skip the countdown
    counting = true;
    foundBtn.hidden = true;
    textEl.hidden = true;
    refEl.textContent = 'Bibles closed.';
    clockEl.textContent = 'Get ready…';
    clockEl.classList.remove('done');
    var left = COUNT;
    cdNum.textContent = left;
    cd.hidden = false;
    timer = setInterval(function () {
      left -= 1;
      if (left > 0) { cdNum.textContent = left; return; }
      clearInterval(timer);
      reveal();
    }, 1000);
  };

  foundBtn.onclick = function () {
    stopClock();
    clockEl.textContent = 'Found in ' + secs(Date.now() - started);
    clockEl.classList.add('done');
    foundBtn.hidden = true;
    textEl.hidden = !textEl.textContent;
  };
})();
"""


def render_resource_category(category) -> str:
    """One category: its own title tag, an optional blurb, then the
    file list. Images get a preview; everything else a type badge.
    A category with a drills.txt is a speed drill instead (render_drill),
    with any other files listed below it."""
    if category.get("drills"):
        rest = ""
        if category["files"]:
            rest = render_resource_category({**category, "drills": [], "desc": "",
                                             "title": "Files"})
        return render_drill(category) + rest
    files = category["files"]
    n = len(files)
    count = f"{n} file" + ("" if n == 1 else "s")

    rows = []
    for f in files:
        href = ("resources/" + quote(category["slug"]) + "/" + quote(f["name"]))
        if f["is_image"]:
            left = (f'<img class="res-thumb" src="{escape(href)}" alt="" '
                    'loading="lazy">')
        else:
            left = f'<span class="res-icon">{escape(f["ext"].upper() or "FILE")}</span>'
        sub = escape(" · ".join(b for b in (f["ext"].upper(), f["size"]) if b))
        rows.append(
            f'<li><a class="res-file" href="{escape(href)}" download>'
            f"{left}"
            '<span class="res-meta">'
            f'<span class="res-name">{escape(f["title"])}</span>'
            f'<span class="res-sub">{sub}</span></span>'
            '<span class="res-dl" aria-hidden="true">↓</span>'
            "</a></li>"
        )

    desc_html = (f'<p class="res-desc">{escape(category["desc"])}</p>'
                 if category["desc"] else "")
    meta = (
        '<div class="meta-strip">'
        f'<span class="count-tag">{count}</span>'
        '<div class="dash-rule"></div>'
        '<span class="hint">↓ tap to save</span>'
        "</div>\n"
    )
    return (
        f'<div class="title-tag"><h1>{escape(category["title"].upper())}</h1></div>\n'
        f"{meta}"
        f"{desc_html}"
        '<ul class="res-files">\n' + "\n".join(rows) + "\n</ul>"
    )


# ─────────────────────────────────────────────────────────────
# Styles  (server.py does:  CSS += RESOURCES_CSS)

RESOURCES_CSS = r"""
/* The bulletin button sits below the title tag and above the file
   categories, with a little air on both sides so it doesn't jam up
   under the RESOURCES chip. */
.bulletin-cta { margin: 24px 0 22px; }
/* ────────────────────────────────────────────────────────────
   RESOURCES — category cards reuse .sec; per-category file lists
   get their own rows with an image preview or a type badge.
   ──────────────────────────────────────────────────────────── */
.res-files {
  list-style: none;
  margin: 20px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.res-file {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  background: #f2ede4;
  border: 3px solid #0a0a0a;
  box-shadow: 4px 4px 0 #0a0a0a;
  color: #0a0a0a !important;
  transition: transform 0.08s, box-shadow 0.08s;
}
.res-file:active { transform: translate(3px, 3px); box-shadow: 1px 1px 0 #0a0a0a; }
.res-file:active { background: #f01a8b; }
@media (hover: hover) { .res-file:hover { background: #f01a8b; } }
.res-file:focus-visible { outline: 3px solid #f01a8b; outline-offset: 4px; }

.res-thumb {
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  object-fit: cover;
  background: #ffffff;
  border: 2px solid #0a0a0a;
}
.res-icon {
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a0a0a;
  color: #f2ede4;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 14px;
  letter-spacing: 1px;
}
.res-meta { flex: 1; min-width: 0; }
.res-name {
  display: block;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 700;
  font-size: 20px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  line-height: 1.05;
  word-break: break-word;
}
.res-sub {
  display: block;
  margin-top: 4px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 12px;
  color: #3a3a3a;
}
.res-dl {
  flex-shrink: 0;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 30px;
  color: #f01a8b;
}
.res-file:active .res-dl,
.res-file:active .res-name,
.res-file:active .res-sub { color: #0a0a0a; }
@media (hover: hover) {
  .res-file:hover .res-dl,
  .res-file:hover .res-name,
  .res-file:hover .res-sub { color: #0a0a0a; }
}

.res-desc {
  margin: 8px 0 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.55;
  color: #3a3a3a;
}
.res-empty {
  margin: 26px 0 6px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.55;
}

/* ────────────────────────────────────────────────────────────
   SPEED DRILLS — a big reference card, New / Found it, a stopwatch.
   The countdown card is the musician page's .countdown / .cd-box.
   ──────────────────────────────────────────────────────────── */
.drill { margin-top: 22px; }
.drill-card {
  padding: 26px 18px 24px;
  background: #f2ede4;
  border: 3px solid #0a0a0a;
  box-shadow: 5px 5px 0 #0a0a0a;
  text-align: center;
}
.drill-ref {
  margin: 0;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 48px;
  line-height: 0.95;
  text-transform: uppercase;
  color: #0a0a0a;
  word-break: break-word;
}
.drill-clock {
  margin: 14px 0 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 15px;
  letter-spacing: 1px;
  color: #3a3a3a;
  font-variant-numeric: tabular-nums;
}
.drill-clock.done { color: #f01a8b; font-size: 18px; }
.drill-text {
  margin: 18px 0 0;
  padding-top: 16px;
  border-top: 1.5px dashed rgba(10, 10, 10, 0.35);
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 16px;
  line-height: 1.6;
  text-align: left;
  color: #0a0a0a;
}
.drill-text[hidden] { display: none; }
.drill-btns { display: flex; gap: 12px; margin-top: 18px; }
.drill-new, .drill-found {
  flex: 1;
  height: 58px;
  border: 3px solid #0a0a0a;
  border-radius: 0;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 28px;
  letter-spacing: 1px;
  text-transform: uppercase;
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.drill-new { background: #0a0a0a; color: #f2ede4; }
.drill-found { background: #f01a8b; color: #0a0a0a; }
.drill-found[hidden] { display: none; }
.drill-new:active, .drill-found:active { transform: translateY(2px); }
.drill-new:focus-visible, .drill-found:focus-visible { outline: 3px solid #f01a8b; outline-offset: 3px; }

/* These rows have their own solid background, so kill the beige halo
   inherited from body (same reason the other chips/cards do). */
.drill-card, .drill-card *, .drill-btns, .drill-btns *,
.res-file, .res-file *,
.res-icon {
  -webkit-text-stroke-width: 0 !important;
  -webkit-text-stroke-color: transparent !important;
  paint-order: normal !important;
}
"""
