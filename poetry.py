"""Poetry page for Grace House — a running chapbook.

Reads ./poems.txt and builds the middle of /{key}/poetry/. server.py
wraps it in the usual page (HOME tag, logo, title tag), the same way it
does for Who We Are.

File format (lines starting with # are ignored):

    Title of the Poem          <- first line of each poem is its title
    [By: Name]                 <- optional, signs the poem at the bottom
    [Date: September 2026]     <- optional, any text you like

    First stanza, line one     <- blank lines separate stanzas,
    line two                      just like you'd expect
        an indented line       <- leading spaces are kept

    Second stanza

    ---                        <- three or more dashes between poems

    Next Poem's Title
    ...

Poems show in the order they're in the file, so put new ones at the top
if you want the newest first. With two or more poems, a contents list
appears at the top and each title jumps to its poem. If the file is
missing or has no poems yet, the front page shows "Soon".
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

POEMS_PATH = Path(__file__).resolve().parent / "poems.txt"

# A line of three or more dashes, alone, splits one poem from the next.
POEM_BREAK_RE = re.compile(r"^\s*-{3,}\s*$")
# [By: Name] / [Date: Fall 2026] on a line by themselves.
POEM_META_RE = re.compile(r"^\s*\[\s*(by|date)\s*:\s*([^\]]*?)\s*\]\s*$", re.IGNORECASE)

# The Grace House wheel, small and pink, set between poems.
WHEEL_BREAK = (
    '<div class="poem-break" aria-hidden="true">'
    '<svg width="26" height="26" viewBox="0 0 34 34">'
    '<circle cx="17" cy="17" r="13" stroke="#f01a8b" stroke-width="2" fill="none"/>'
    '<line x1="17" y1="4" x2="17" y2="30" stroke="#f01a8b" stroke-width="1.8"/>'
    '<line x1="4" y1="17" x2="30" y2="17" stroke="#f01a8b" stroke-width="1.8"/>'
    '<line x1="7.81" y1="7.81" x2="26.19" y2="26.19" stroke="#f01a8b" stroke-width="1.8"/>'
    '<line x1="26.19" y1="7.81" x2="7.81" y2="26.19" stroke="#f01a8b" stroke-width="1.8"/>'
    '<circle cx="17" cy="17" r="2.5" fill="#f01a8b"/>'
    "</svg></div>"
)


def parse_poems(path: Path = POEMS_PATH):
    """Return [{"title", "by", "date", "stanzas": [[line, ...], ...]}, ...]
    in file order, or None if the file is missing or has no poems."""
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").expandtabs(4)

    chunks, current = [], []
    for ln in raw.splitlines():
        if ln.strip().startswith("#"):
            continue
        if POEM_BREAK_RE.match(ln):
            chunks.append(current)
            current = []
        else:
            current.append(ln.rstrip())
    chunks.append(current)

    poems = []
    for chunk in chunks:
        meta, lines = {}, []
        for ln in chunk:
            m = POEM_META_RE.match(ln)
            if m:
                meta[m.group(1).lower()] = m.group(2)
            else:
                lines.append(ln)
        while lines and not lines[0].strip():
            lines.pop(0)
        if not lines:
            continue
        title = lines[0].strip()
        stanzas, stanza = [], []
        for ln in lines[1:]:
            if ln.strip():
                stanza.append(ln)
            elif stanza:
                stanzas.append(stanza)
                stanza = []
        if stanza:
            stanzas.append(stanza)
        poems.append({
            "title": title,
            "by": meta.get("by", ""),
            "date": meta.get("date", ""),
            "stanzas": stanzas,
        })
    return poems or None


def _anchor(title: str, used: set[str]) -> str:
    """A link-friendly id from the title ("Amazing Grace" -> amazing-grace),
    so a shared link to one poem keeps working when new poems are added."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "poem"
    anchor, n = base, 2
    while anchor in used:
        anchor = f"{base}-{n}"
        n += 1
    used.add(anchor)
    return anchor


def render_poetry(poems) -> str:
    """The page's middle: count strip, contents, then every poem."""
    if not poems:
        return ""
    used = {"contents"}
    ids = [_anchor(p["title"], used) for p in poems]
    many = len(poems) > 1

    parts = [
        '<div class="meta-strip">'
        f'<span class="count-tag">{len(poems)} poem{"s" if many else ""}</span>'
        '<div class="dash-rule"></div>'
        '<span class="hint">↓ read</span>'
        "</div>"
    ]

    # Links carry "poetry/" because the page's <base> points at the
    # front page; a bare "#id" would jump there instead.
    if many:
        items = []
        for p, pid in zip(poems, ids):
            date = f'<span class="poem-toc-date">{escape(p["date"])}</span>' if p["date"] else ""
            items.append(
                f'<li><a href="poetry/#{pid}">'
                f'<span class="poem-toc-title">{escape(p["title"])}</span>{date}</a></li>'
            )
        parts.append('<ol class="poem-toc" id="contents">' + "".join(items) + "</ol>")

    for i, (p, pid) in enumerate(zip(poems, ids)):
        if many or i:
            parts.append(WHEEL_BREAK)
        body = "".join(
            '<div class="stanza">'
            + "".join(f'<div class="poem-line">{escape(ln)}</div>' for ln in stanza)
            + "</div>"
            for stanza in p["stanzas"]
        )
        bits = [b for b in (p["by"], p["date"]) if b]
        sign = ("— " if p["by"] else "") + ", ".join(bits)
        top = '<a class="poem-top" href="poetry/#contents">↑ contents</a>' if many else ""
        sign_html = f'<p class="poem-sign">{escape(sign)}</p>' if sign else ""
        foot = f'<div class="poem-foot">{top}{sign_html}</div>' if (top or sign_html) else ""
        parts.append(
            f'<section class="poem" id="{pid}">'
            f'<h2 class="poem-title">{escape(p["title"])}</h2>'
            f'<div class="poem-body">{body}</div>'
            f"{foot}</section>"
        )
    return "\n".join(parts)


# Added onto server.py's CSS.
POETRY_CSS = r"""
/* ────────────────────────────────────────────────────────────
   POETRY — a running chapbook: contents, then poem after poem
   with the wheel between them.
   ──────────────────────────────────────────────────────────── */
.poem-toc {
  list-style: none;
  margin: 22px 0 0;
  padding: 0;
}
.poem-toc li { border-bottom: 1.5px solid #0a0a0a; }
.poem-toc li:last-child { border-bottom: none; }
.poem-toc a {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 6px;
  color: inherit;
}
.poem-toc a:active { opacity: 0.6; }
@media (hover: hover) {
  .poem-toc a:hover .poem-toc-title { color: #f01a8b; }
}
.poem-toc-title {
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 700;
  font-size: 20px;
  letter-spacing: 0.5px;
  line-height: 1.05;
  text-transform: uppercase;
}
.poem-toc-date {
  flex-shrink: 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  color: #f01a8b;
}

.poem-break {
  display: flex;
  justify-content: center;
  padding: 30px 0 4px;
}
.poem-break svg { display: block; }

.poem {
  padding: 18px 0 6px;
  scroll-margin-top: 14px;
}
.poem-title {
  margin: 0 0 18px;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 34px;
  line-height: 0.95;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.poem-body {
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 15px;
  line-height: 1.7;
}
.stanza + .stanza { margin-top: 1.3em; }
/* Keep typed indents; a line too long for a phone wraps with a
   hanging indent so it still reads as one line of the poem. */
.poem-line {
  white-space: pre-wrap;
  padding-left: 1.5em;
  text-indent: -1.5em;
}
.poem-foot {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-top: 20px;
}
.poem-sign {
  margin: 0 0 0 auto;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 13px;
  text-align: right;
  color: #f01a8b;
}
.poem-top {
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  color: #0a0a0a;
  opacity: 0.55;
}
"""
