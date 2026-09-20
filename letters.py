#!/usr/bin/env python3
"""Grace House — Letters.

Every letter and sermon lives in one file, ./letters.txt, one after
another with a line of three dashes between them:

    A Letter to Grubthorn        <- line 1: how it shows in the list
    A Letter to Grubthorn        <- line 2: the heading on its own page
    [Date: September 2026]       <- optional, shown under the heading

    Dear Grubthorn,

    Today has been troubling.

    Sincerely,
    Wurmtongue

    ---

    On Being Small               <- the next letter starts here
    A Sermon on Being Small
    ...

Line 1 and line 2 are separate on purpose, so the list can say
"On Being Small" while the page itself says "A Sermon on Being Small".
Type only one line and it's used for both.

Inside a letter:
    blank line        starts a new paragraph
    - item            a bullet
    > quoted line     an indented quote (scripture, someone else's words)
    # at line start   a note to yourself; never shown on the site

Lines inside a paragraph keep the breaks you typed, so a greeting or a
signature sits the way you wrote it.

Each letter gets its own page at /{key}/letters/<slug>/, where <slug>
is made from line 1 ("A Letter to Grubthorn" -> a-letter-to-grubthorn).
The address comes from the words, not from the letter's position in the
file, so you can put new letters at the top without breaking old links.
Two letters with the same line 1 get -2, -3 on the end.
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
LETTERS_PATH = HERE / "letters.txt"

# A line of three or more dashes (or underscores / equals) separates letters.
SEPARATOR_RE = re.compile(r"^\s*[-\u2013\u2014_=]{3,}\s*$")
# [Date: whatever] on a line by itself, just under the title.
DATE_RE = re.compile(r"^\s*\[\s*date\s*:\s*(.*?)\s*\]\s*$", re.IGNORECASE)


def _slugify(text: str, used: set[str]) -> str:
    """"A Letter to Grubthorn" -> "a-letter-to-grubthorn" (never a repeat)."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-")
    if not slug:
        slug = "letter"
    base, n = slug, 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def parse_letters():
    """Return [(slug, link_text, title, date, [body lines]), ...] in file
    order, or None if letters.txt doesn't exist or has nothing in it."""
    if not LETTERS_PATH.exists():
        return None
    raw = LETTERS_PATH.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.lstrip().startswith("#")]

    blocks: list[list[str]] = [[]]
    for ln in lines:
        if SEPARATOR_RE.match(ln):
            blocks.append([])
        else:
            blocks[-1].append(ln)

    letters = []
    used: set[str] = set()
    for block in blocks:
        while block and not block[0].strip():
            block.pop(0)
        while block and not block[-1].strip():
            block.pop()
        if not block:
            continue
        link = block[0].strip()
        rest = block[1:]
        while rest and not rest[0].strip():
            rest.pop(0)
        title = rest[0].strip() if rest else link
        body = rest[1:]
        # An optional [Date: ...] line (and any blank lines) before the letter.
        date = ""
        while body and (not body[0].strip() or DATE_RE.match(body[0])):
            m = DATE_RE.match(body[0])
            if m:
                date = m.group(1).strip()
            body.pop(0)
        letters.append((_slugify(link, used), link, title, date, body))
    return letters or None


def find_letter(letters, slug: str):
    """Index of the letter with this slug, or None."""
    return next((i for i, l in enumerate(letters) if l[0] == slug), None)


def render_letter_body(lines) -> str:
    """Blank lines separate paragraphs; lines inside one keep their breaks.
    "- " makes a bullet, "> " an indented quote."""
    out: list[str] = []
    para: list[str] = []
    bullets: list[str] = []
    quote: list[str] = []

    def flush():
        if para:
            out.append("<p>" + "<br>".join(escape(p) for p in para) + "</p>")
            para.clear()
        if bullets:
            out.append("<ul>" + "".join(f"<li>{escape(b)}</li>" for b in bullets) + "</ul>")
            bullets.clear()
        if quote:
            out.append("<blockquote>" + "<br>".join(escape(q) for q in quote) + "</blockquote>")
            quote.clear()

    for raw in lines:
        s = raw.strip()
        if not s:
            flush()
        elif s.startswith("- ") or s.startswith("* "):
            if para or quote:
                flush()
            bullets.append(s[2:].strip())
        elif s.startswith("> "):
            if para or bullets:
                flush()
            quote.append(s[2:].strip())
        else:
            if bullets or quote:
                flush()
            para.append(s)
    flush()
    return "\n".join(out)


def render_letters_index(letters) -> str:
    """The list of letters — the middle of /{key}/letters/."""
    if not letters:
        return ('<p class="ev-none">No letters yet. '
                "Add one to letters.txt and build again.</p>")
    items = "\n".join(
        f'<li><a href="letters/{slug}/">'
        f'<span class="letter-mark" aria-hidden="true">&#10022;</span>'
        f'<span class="letter-name">{escape(link)}</span>'
        + (f'<span class="letter-date">{escape(date)}</span>' if date else "")
        + "</a></li>"
        for slug, link, _title, date, _body in letters
    )
    n = len(letters)
    return (
        '<div class="meta-strip">'
        f'<span class="count-tag">{n} letter{"" if n == 1 else "s"}</span>'
        '<div class="dash-rule"></div>'
        '<span class="hint">↓ tap one</span>'
        "</div>\n"
        f'<ul class="letter-list">\n{items}\n</ul>'
    )


def render_letter(letters, idx: int) -> str:
    """One letter — the middle of /{key}/letters/<slug>/."""
    _slug, _link, title, date, body = letters[idx]
    prev_l = letters[idx - 1] if idx > 0 else None
    next_l = letters[idx + 1] if idx < len(letters) - 1 else None
    date_html = ""
    if date:
        date_html = ('<div class="meta-strip">'
                     f'<span class="count-tag">{escape(date)}</span>'
                     '<div class="dash-rule"></div></div>\n')
    prev_link = (f'<a class="nav-prev" href="letters/{prev_l[0]}/">← PREV</a>'
                 if prev_l else "<span></span>")
    next_link = (f'<a class="nav-next" href="letters/{next_l[0]}/">NEXT →</a>'
                 if next_l else "<span></span>")
    return (
        "<article>\n"
        f'<span class="print-slug">Grace House</span>'
        f"<h1>{escape(title)}</h1>\n"
        "</article>\n"
        f"{date_html}"
        f'<div class="letter-body">\n{render_letter_body(body)}\n</div>\n'
        '<nav class="foot">\n'
        f"{prev_link}\n"
        '<a class="home" href="letters/">INDEX</a>\n'
        f"{next_link}\n"
        "</nav>\n"
    )


# ─────────────────────────────────────────────────────────────
# Styles (appended to server.CSS, so this wins over anything above it)

LETTERS_CSS = r"""
/* ────────────────────────────────────────────────────────────
   LETTERS — the list, then one page per letter.
   ──────────────────────────────────────────────────────────── */
.letters-chip { cursor: default; user-select: none; -webkit-user-select: none; }

ul.letter-list {
  list-style: none;
  padding: 0;
  margin: 22px 0 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
ul.letter-list li { border-bottom: 1.5px solid #0a0a0a; }
ul.letter-list li:last-child { border-bottom: none; }
ul.letter-list a {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 12px 6px;
  color: inherit;
}
ul.letter-list a:active { opacity: 0.6; }
.letter-mark {
  color: #f01a8b;
  font-size: 16px;
  line-height: 1;
  min-width: 18px;
  text-align: right;
}
.letter-name {
  flex: 1;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 700;
  font-size: 20px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  line-height: 1.05;
}
.letter-date {
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 10px;
  letter-spacing: 1px;
  text-transform: uppercase;
  opacity: 0.55;
  white-space: nowrap;
}

/* The letter itself. Sits on the dotted paper, so it keeps the beige
   halo it inherits from body — don't zero it out here. */
.letter-body {
  padding-top: 20px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 15px;
  line-height: 1.7;
}
.letter-body p { margin: 0 0 16px; }
.letter-body p:last-child { margin-bottom: 0; }
.letter-body ul { margin: 0 0 16px; padding-left: 22px; }
.letter-body li { margin: 4px 0; padding-left: 4px; }
.letter-body li::marker { color: #f01a8b; }
.letter-body blockquote {
  margin: 0 0 16px;
  padding: 2px 0 2px 14px;
  border-left: 3px solid #f01a8b;
  font-style: italic;
}

@media print {
  .letter-body {
    font-size: 11.5pt;
    line-height: 1.5;
    padding-top: 10pt;
  }
  .letter-body blockquote { border-left: 2pt solid #000 !important; }
  .letter-body li::marker { color: #000; }
}
"""
