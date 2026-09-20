"""Who We Are page for Grace House.

Reads ./who-we-are.txt and builds the middle of /{key}/who-we-are/.
server.py wraps it in the usual page (HOME tag, logo, title tag), the
same way it does for the kids sheet.

File format (blank line between blocks; lines starting with # are
ignored, so you can leave yourself notes or park a section you're not
ready to show):

    Know Grace.                <- First block: the big headline,
    Live Grace.                   one line per line.
    Share Grace.

    Welcome to Grace House...  <- Second block: the welcome. Each line
                                  is its own paragraph, so keep a
                                  paragraph on one line.

    Fellowship                 <- Every block after that is a section.
    [Time: 6:00 p.m.]             First line is its name.
    [Who: Jeremiah]               [Time:] and [Who:] are optional and
    Before service we...          can go anywhere in the block. Each
                                  [Who:] becomes a black name tag.

Lines starting "- " in a section become bullets, same as the zine.
If the file is missing or empty, the front page shows "Soon".
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

WHO_PATH = Path(__file__).resolve().parent / "who-we-are.txt"

# [Time: 6:00 p.m.] / [Who: Jeremiah] on a line by themselves.
WHO_META_RE = re.compile(r"^\s*\[\s*(time|who)\s*:\s*([^\]]*?)\s*\]\s*$", re.IGNORECASE)


def parse_who(path: Path = WHO_PATH):
    """Return (headline_lines, welcome_lines, sections) or None if the
    file is missing or has nothing in it.

    sections: [(name, time, [names], [body lines]), ...] in file order.
    """
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("#")]
    blocks = []
    for block in re.split(r"\n\s*\n", "\n".join(lines)):
        block_lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if block_lines:
            blocks.append(block_lines)
    if not blocks:
        return None

    headline = blocks[0]
    welcome = blocks[1] if len(blocks) > 1 else []
    sections = []
    for block in blocks[2:]:
        time, names, rest = "", [], []
        for ln in block:
            m = WHO_META_RE.match(ln)
            if not m:
                rest.append(ln)
            elif m.group(1).lower() == "time":
                time = m.group(2)
            elif m.group(2):
                names.append(m.group(2))
        if rest:
            sections.append((rest[0], time, names, rest[1:]))
    return headline, welcome, sections


def _body(lines: list[str]) -> str:
    """Paragraphs, with runs of "- " / "* " lines turned into a list."""
    parts, bullets = [], []

    def flush():
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{escape(b)}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for ln in lines:
        if ln.startswith(("- ", "* ")):
            bullets.append(ln[2:].strip())
        else:
            flush()
            parts.append(f"<p>{escape(ln)}</p>")
    flush()
    return "\n".join(parts)


def render_who(data) -> str:
    """The page's middle: headline, welcome, then one block per section."""
    if not data:
        return ""
    headline, welcome, sections = data
    parts = []
    if headline:
        spans = "".join(f"<span>{escape(ln)}</span>" for ln in headline)
        parts.append(f'<h2 class="who-headline">{spans}</h2>')
    if welcome:
        parts.append(f'<div class="who-welcome">{_body(welcome)}</div>')
    if sections:
        items = []
        for name, time, names, body in sections:
            time_html = f'<p class="who-time">{escape(time)}</p>' if time else ""
            names_html = ""
            if names:
                tags = "".join(f'<span class="who-name">{escape(n)}</span>' for n in names)
                names_html = f'<div class="who-names">{tags}</div>'
            items.append(
                '<section class="zine-section who-section">'
                f'<div class="who-top"><div>{time_html}'
                f'<h3 class="zine-heading">{escape(name)}</h3></div>{names_html}</div>'
                f'<div class="zine-body">{_body(body)}</div>'
                "</section>"
            )
        parts.append('<div class="who-list">\n' + "\n".join(items) + "\n</div>")
    return "\n".join(parts)


# Added onto server.py's CSS. Section headings and body text reuse the
# zine styles, so this only covers what's new on this page.
WHO_CSS = r"""
/* ────────────────────────────────────────────────────────────
   WHO WE ARE — headline, welcome, then the evening's sections
   ──────────────────────────────────────────────────────────── */
.who-headline {
  margin: 30px 0 0;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: clamp(42px, 13vw, 58px);
  line-height: 0.9;
  text-transform: uppercase;
  color: transparent;
  -webkit-text-stroke: 2px #0a0a0a;
}
.who-headline span { display: block; }

/* The welcome gets the same pink rule as a chorus in the hymnal. */
.who-welcome {
  margin: 26px 0 0;
  padding: 2px 0 2px 16px;
  border-left: 3px solid #f01a8b;
}
.who-welcome p {
  margin: 0 0 12px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 15px;
  line-height: 1.65;
}
.who-welcome p:last-child { margin-bottom: 0; }

.who-list {
  margin-top: 30px;
  border-top: 3px solid #0a0a0a;
}
.who-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.who-top > div:first-child { min-width: 0; }
.who-time {
  margin: 0 0 6px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 14px;
  letter-spacing: 1px;
  color: #f01a8b;
}

/* Black name tags, tilted like the title tag. They lean the other way
   on every other section so the page doesn't look stamped. */
.who-names {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
  padding-top: 8px;
}
.who-name {
  background: #0a0a0a;
  color: #f2ede4;
  padding: 3px 11px 5px;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 19px;
  line-height: 1.1;
  letter-spacing: 0.5px;
  white-space: nowrap;
  transform: rotate(3deg);
}
.who-section:nth-of-type(even) .who-name { transform: rotate(-3deg); }

/* Name tags have their own background, so no beige halo (see the
   NO HALO note in server.py's CSS). */
.who-name {
  -webkit-text-stroke-width: 0 !important;
  -webkit-text-stroke-color: transparent !important;
  paint-order: normal !important;
}
"""
