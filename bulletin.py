"""bulletin.py — the printable Sunday bulletin, as an 8-page booklet.

Two sheets of Letter paper, printed double-sided in LANDSCAPE (short-edge
binding), folded in half and nested (sheet 2 inside sheet 1), then stapled on
the fold. Each printed side holds two 5.5 x 8.5in booklet pages, already in
the order a folded booklet needs:

    sheet 1, outside   page 8 (back cover)           |  page 1 (cover)
    sheet 1, inside    page 2 (order of service)     |  page 7 (kids activity page)
    sheet 2, outside   page 6 (coming up + notes)    |  page 3 (prayer list)
    sheet 2, inside    page 4 (zine)                 |  page 5 (zine)   <- center spread

Served at /{key}/bulletin. Pulls at render time from: GraceHouseCover.png
(repo root, 5.5 x 8.5 portrait, e.g. 1650 x 2550px; embedded, with the live
"coming Sunday" date drawn over it in the browser), who-we-are.txt (the "Know
Grace / Live Grace / Share Grace" headline + welcome, and the timed
order-of-service sections), prayer.txt (the prayer list, with the same
one-month drop-off applied here at print time), zine.txt (this week's zine,
editable on the page; it runs across the center spread and long weeks carry
on at the top of page 6), the events list (this week's events),
bulletin-verses.txt (the back-cover verse, chosen at random; their references
are also the kids page's secret-code verses) and words.txt (the kids page's
word-search themes, same file the kids sheet uses).

Page 7 is a half-size kids activity page built from kids.py's own puzzle
makers (the code, the maze, the word search), lifted out of its KIDS_JS at
render time, so the two never drift apart. kids.py itself is unchanged.

The hymnal QR sits on the back cover. The zine, prayer-list and events QR
codes only appear when that section runs out of room, standing in for
whatever got cut. QR codes point at the site's pages,
worked out in the browser from this page's own address, so they always match
the current access key. Everything interactive runs in the browser, so it
works on the static GitHub Pages build too (JavaScript required).

server.py wiring:
    from bulletin import render_bulletin, parse_bulletin_verses
    ... plus a /bulletin route that calls render_bulletin(key, ...).
resources.py gets the button that opens it.
"""
from __future__ import annotations

import base64
import calendar
import datetime
import json
import re
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
COVER_PATH = HERE / "GraceHouseCover.png"
BVERSES_PATH = HERE / "bulletin-verses.txt"


def parse_bulletin_verses(path: Path = BVERSES_PATH):
    """[(text, reference), ...] from bulletin-verses.txt (same shape as
    quote.txt: verse text, then a dash line with the reference). Lines
    starting with # are ignored. Missing/empty file -> []."""
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("#")]
    out = []
    for block in re.split(r"\n\s*\n", "\n".join(lines)):
        text_lines, ref = [], ""
        for ln in (l.strip() for l in block.splitlines()):
            if not ln:
                continue
            if ln[0] in "-—–" and text_lines:
                ref = ln.lstrip("-—– ").strip()
            else:
                text_lines.append(ln)
        text = " ".join(text_lines).strip().strip('"“”').strip()
        if text:
            out.append((text, ref))
    return out


def _cover_data_uri() -> str:
    if not COVER_PATH.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(COVER_PATH.read_bytes()).decode()


def _ends(when: datetime.date) -> datetime.date:
    """One month after a date — when its prayer requests drop off
    (same rule as prayer.py)."""
    y, m = when.year + when.month // 12, when.month % 12 + 1
    return datetime.date(y, m, min(when.day, calendar.monthrange(y, m)[1]))


def _para(lines) -> str:
    """Paragraphs; runs of "- "/"* " lines become a list."""
    parts, bullets = [], []

    def flush():
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{escape(b)}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith(("- ", "* ")):
            bullets.append(s[2:].strip())
        else:
            flush()
            parts.append(f"<p>{escape(s)}</p>")
    flush()
    return "\n".join(parts)


def _prayer_rows(prayer_data, today: datetime.date) -> str:
    """Open requests from gatherings still inside their month, newest
    first — each request line with the asker as a name chip."""
    if not prayer_data:
        return ""
    rows = []
    for when, items in prayer_data["days"]:
        if _ends(when) <= today:
            continue
        for it in items:
            if it.get("answered"):
                continue
            chip = (f'<span class="tag pr-chip">{escape(it["asker"])}</span>'
                    if it.get("asker") else "")
            rows.append(f'<div class="pr-row"><span class="pr-req">{escape(it["text"])}</span>{chip}</div>')
    return "\n".join(rows)


def _welcome_html(who_data):
    """(headline_html, welcome_html) for the welcome page."""
    if not who_data:
        return "", ""
    headline, welcome, _sections = who_data
    head = "<br>".join(escape(l) for l in headline) if headline else ""
    return head, _para(welcome)


def _order_html(who_data) -> str:
    """Order-of-service blocks from who-we-are.txt sections."""
    if not who_data:
        return ""
    _headline, _welcome, sections = who_data
    blocks = []
    for name, time, names, body in sections:
        time_html = f'<div class="svc-time">{escape(time)}</div>' if time else ""
        tags = "".join(f'<span class="tag">{escape(n)}</span>' for n in names)
        tags_html = f'<div class="svc-tags">{tags}</div>' if tags else ""
        text = " ".join(l.strip() for l in body if l.strip())
        blocks.append(
            '<div class="svc"><div class="svc-top"><div>'
            f'{time_html}<h3>{escape(name)}</h3></div>{tags_html}</div>'
            f'<p>{escape(text)}</p></div>'
        )
    return "\n".join(blocks)


def _zine_html(zine_data) -> str:
    """Zine sections as editable heading + paragraph blocks."""
    if not zine_data:
        return ""
    _title, sections = zine_data
    out = []
    for heading, body_lines in sections:
        out.append(f"<h4>{escape(heading)}</h4>")
        out.append(_para(body_lines))
    return "\n".join(out)


_EV_DAYS3 = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_EV_MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
            "Sep", "Oct", "Nov", "Dec"]


def _events_html(events_data) -> str:
    """One <div class="be-item"> per event (date chip + title). The browser
    shows only those in the coming-Sunday-to-next-Sunday window; the rest
    stay hidden. events_data is server.parse_events()[0], newest last."""
    if not events_data:
        return ""
    rows = []
    for when, details in events_data:
        title = next((ln.strip() for ln in details if ln.strip()), "")
        if not title:
            continue
        label = f"{_EV_DAYS3[when.weekday()]} {_EV_MON3[when.month - 1]} {when.day}"
        rows.append(
            f'<div class="be-item" data-when="{when.isoformat()}">'
            f'<div class="be-when">{escape(label)}</div>'
            f'<div class="be-what">{escape(title)}</div>'
            f'</div>'
        )
    return "\n".join(rows)


_KID_ENGINE_START = "  function esc(s) {"
_KID_ENGINE_END = "  /* ── The activities"


def _kids_page(verses):
    """(inner html, refs attr, themes attr, engine js) for page 7, built
    from kids.py: its puzzle makers are the part of KIDS_JS between
    "function esc" and "The activities". If kids.py is missing or those
    markers move, page 7 says so instead of breaking the bulletin."""
    try:
        import kids
        js = kids.KIDS_JS
        a, b = js.index(_KID_ENGINE_START), js.index(_KID_ENGINE_END)
        words_path = HERE / "words.txt"
        words_text = words_path.read_text(encoding="utf-8") if words_path.exists() else ""
        themes = kids.parse_word_themes(words_text) or kids.parse_word_themes(kids.STARTER_WORDS)
        refs = [r for _t, r in verses if r] or list(kids.FALLBACK_VERSES)
        wheel, rules = kids.SHEET_WHEEL, kids.MAZE_RULES
    except Exception:
        return ('<p class="kid-missing">Kids page: kids.py (or its puzzle code) '
                'wasn\'t found next to bulletin.py.</p>', "[]", "[]", "")
    inner = (
        '<header class="kid-head"><div class="kid-brand"><span>Grace H</span>'
        f'{wheel}<span>use Kids</span></div><div class="kid-kind">Activity Page</div></header>'
        '<section class="act act-verse" data-act="verse"><div class="act-top">'
        '<h3 class="act-label">Look it up</h3>'
        '<p class="act-note">Crack the code, then find the verse in a Bible.</p></div>'
        '<div class="act-body"></div></section>'
        '<section class="act act-words" data-act="words"><div class="act-top">'
        '<h3 class="act-label">Word search</h3><p class="ws-theme"></p></div>'
        '<div class="act-body"></div></section>'
        '<section class="act act-maze" data-act="maze"><div class="act-top">'
        f'<h3 class="act-label">Maze</h3>{rules}</div>'
        '<div class="act-body"></div></section>'
    )
    return (inner, escape(json.dumps(refs, ensure_ascii=False)),
            escape(json.dumps(themes, ensure_ascii=False)), js[a:b])


_FALLBACK_VERSE = ("For God so loved the world, that he gave his only Son, "
                   "that whoever believes in him should not perish but have "
                   "eternal life.", "John 3:16")

CSS = r"""
  :root{ color-scheme:light; box-sizing:border-box; }
  *,*::before,*::after{ box-sizing:inherit; }
  html,body{ margin:0; padding:0; }
  body{ background:#5f5f5f; color:#eee; font-family:'Special Elite','Courier New',monospace; -webkit-font-smoothing:antialiased; }

  .chrome{ max-width:1056px; margin:0 auto; padding:22px 18px 6px; }
  .chrome h1{ font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; letter-spacing:1px; font-size:22px; margin:0 0 8px; }
  .chrome p{ margin:0 0 14px; font-size:13px; line-height:1.55; opacity:.85; max-width:80ch; }
  .bar{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:6px; }
  .btn{ font-family:'Special Elite',monospace; font-size:13px; letter-spacing:.5px; padding:9px 14px; border:2px solid #eee; background:transparent; color:#eee; cursor:pointer; border-radius:0; }
  .btn.primary{ background:#eee; color:#111; }
  .btn:active{ transform:translateY(1px); }
  .back{ display:inline-block; text-decoration:none; margin:0 0 14px; }
  .chk{ display:flex; align-items:center; gap:7px; font-size:13px; opacity:.9; }
  .hint{ font-size:12px; opacity:.6; }
  .warn{ font-size:12px; color:#ffc4b8; }

  .stage{ padding:14px 18px 60px; }
  .sheet-wrap{ margin:0 auto 26px; }
  .sheet-label{ max-width:1056px; margin:0 auto 6px; font-size:11px; letter-spacing:2px; text-transform:uppercase; opacity:.6; }

  /* one printed side = two 5.5 x 8.5in booklet pages; it folds down the middle */
  .sheet{ width:11in; height:8.5in; background:#fff; color:#000; transform-origin:top left; position:relative; box-shadow:0 10px 34px rgba(0,0,0,.4); }
  .flipwrap{ position:relative; display:flex; width:100%; height:100%; }
  .page{ flex:0 0 5.5in; height:100%; position:relative; overflow:hidden; }
  .fold{ position:absolute; top:0; bottom:0; left:50%; width:0; border-left:1px dashed #cfcfcf; pointer-events:none; }
  .pad{ position:absolute; top:0.5in; right:0.5in; bottom:0.5in; left:0.5in; display:flex; flex-direction:column; }
  /* long-edge printers: the backs (sheet insides) print upside down */
  .sheet.backside.flip .flipwrap{ transform:rotate(180deg); transform-origin:center; }

  .h-stencil{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; text-transform:uppercase; line-height:.92; color:#000; margin:0; }

  /* shared name chip (order of service + prayer) */
  .tag{ background:#000; color:#fff; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; white-space:nowrap; }

  .brandmark{ display:flex; align-items:center; gap:2px; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:15px; letter-spacing:2px; color:#000; }
  .brandmark svg{ width:16px; height:16px; }

  /* ── PAGE 1 · COVER ────────────────────────────────── */
  .cover img{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; display:block; }
  /* the date reads up the cover's rule, at its top end, mirroring SADIEVILLE at its foot */
  .cover .date{ position:absolute; left:46.1%; top:13.1%; transform:translateX(-50%) rotate(180deg); writing-mode:vertical-rl; white-space:nowrap; font-family:'Montserrat','Segoe UI',sans-serif; font-weight:400; font-size:21px; line-height:1; letter-spacing:.5px; text-transform:uppercase; color:#000; }
  .cover-fallback{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; text-align:center; padding:0.4in; }
  .cf-mark{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; font-size:72px; line-height:.82; letter-spacing:1px; color:#000; }
  .cf-hint{ font-family:'Special Elite',monospace; font-size:11px; line-height:1.4; color:#b00; }

  /* ── PAGE 2 · ORDER OF SERVICE ─────────────────────── */
  /* sized in em off the page's font-size, which the script sets to the
     largest that fits (up to 15px), so the sections fill the page */
  .pad-order{ justify-content:flex-start; font-size:12px; }
  .svc{ padding:.9em 0 1em; border-top:2px solid #000; }
  .svc:first-of-type{ border-top:0; padding-top:0; }
  .svc-top{ display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
  .svc-tags{ display:flex; flex-wrap:wrap; justify-content:flex-end; gap:6px; }
  .svc-time{ font-family:'Special Elite',monospace; font-size:1.08em; letter-spacing:.5px; }
  .svc h3{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; text-transform:uppercase; font-size:2.4em; line-height:.9; margin:2px 0 0; }
  .svc .tag{ padding:2px 9px 3px; font-size:1.2em; transform:rotate(3deg); }
  .svc:nth-of-type(even) .tag{ transform:rotate(-3deg); }
  .svc p{ font-family:'Special Elite',monospace; font-size:1em; line-height:1.45; margin:.6em 0 0; }

  /* ── PAGES 4–5 · ZINE (the center spread) ──────────── */
  /* page 4, then page 5, then page 6 are filled in turn by the script (CSS
     columns can't do it: Safari prints only the first column) */
  .z-title{ font-size:36px; margin:0 0 12px; }
  .z-area{ flex:1; min-height:0; overflow:hidden; }
  .z-hint{ position:absolute; top:0.2in; left:0.5in; font-size:9px; letter-spacing:2px; text-transform:uppercase; opacity:.55; pointer-events:none; }
  .zine{ outline:none; font-size:13px; }
  .zine h4{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; text-transform:uppercase; font-size:1.4em; line-height:1; margin:.75em 0 .3em; }
  .zine h4:first-child{ margin-top:0; }
  .zine p{ font-family:'Special Elite',monospace; line-height:1.45; margin:0 0 .55em; }
  .zine ul{ font-family:'Special Elite',monospace; line-height:1.45; margin:0 0 .55em; padding-left:1.2em; }

  /* ── PAGE 6 · ZINE CARRY-OVER + COMING UP + NOTES ──── */
  .z-over{ margin-bottom:20px; }
  .z-over-label{ font-size:9px; letter-spacing:2px; text-transform:uppercase; opacity:.55; margin-bottom:6px; }
  /* fixed shares of page 6, so a long zine and a busy week can't squeeze each other out */
  .z-over-area{ max-height:2.2in; overflow:hidden; }
  .be-title{ font-size:36px; margin:0 0 8px; }
  .be-list{ flex-shrink:0; max-height:2.6in; overflow:hidden; }
  .be-item{ display:flex; align-items:baseline; gap:12px; padding:7px 0 8px; border-top:1px solid #000; }
  .be-item:first-child{ border-top:0; }
  .be-item[hidden]{ display:none; }
  .be-when{ flex:0 0 1.05in; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:15px; letter-spacing:.5px; text-transform:uppercase; }
  .be-what{ font-family:'Special Elite',monospace; font-size:13px; line-height:1.3; }
  .be-none{ font-family:'Special Elite',monospace; font-size:13px; opacity:.7; margin:6px 0 0; }
  .notes-title{ font-size:26px; margin:24px 0 2px; }
  /* ruled lines filling the rest of the page */
  .notes-lines{ flex:1; min-height:0; background-color:#fff; background-image:repeating-linear-gradient(to bottom, #fff 0, #fff 29px, #000 29px, #000 30px); }

  /* ── PAGE 3 · PRAYER LIST ──────────────────────────── */
  .p-title{ font-size:44px; letter-spacing:.5px; }
  .pr-list{ margin-top:14px; display:flex; flex-direction:column; flex:1; min-height:0; overflow:hidden; }
  .pr-row{ display:flex; align-items:center; gap:10px; min-height:30px; padding:6px 1px 7px; border-bottom:1px solid #000; }
  .pr-req{ flex:1; min-width:0; font-family:'Special Elite',monospace; font-size:13px; line-height:1.2; }
  .pr-chip{ font-size:13px; padding:1px 8px 2px; transform:rotate(-2deg); }
  .pr-row:nth-child(even) .pr-chip{ transform:rotate(2deg); }
  /* ruled write-in lines filling the leftover space */
  .pr-fill{ flex:1; min-height:0.9in; background-color:#fff; background-image:repeating-linear-gradient(to bottom, #fff 0, #fff 29px, #000 29px, #000 30px); }

  /* QR codes: the hymnal one on the back cover, and the ones that stand in
     for whatever didn't fit (zine, prayer list, events) */
  .verse-ref{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; font-size:36px; line-height:.95; margin:0 0 10px; }
  .verse-txt{ font-size:14px; line-height:1.5; font-style:italic; margin:0; }
  .qr-block{ display:flex; flex-direction:column; align-items:center; gap:6px; }
  .qr,.qr img,.qr canvas{ width:1.05in!important; height:1.05in!important; }
  .qr-cap{ font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:700; font-size:14px; letter-spacing:1px; text-transform:uppercase; }
  .more-qr{ display:flex; align-items:center; gap:0.14in; margin-top:10px; }
  .more-qr[hidden]{ display:none; }
  .more-qr .qr,.more-qr .qr img,.more-qr .qr canvas{ width:0.8in!important; height:0.8in!important; }
  .more-qr .qr-cap{ font-size:15px; line-height:1.15; }
  .pr-row.cut,.be-item.cut{ display:none; }

  /* ── PAGE 7 · KIDS: kids.py's puzzles at half size, in its look ── */
  .kidp{ gap:0.13in; color:#0a0a0a; }
  .kid-head{ display:flex; align-items:center; gap:0.16in; }
  .kid-brand{ display:flex; align-items:center; font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; font-size:27pt; line-height:.85; letter-spacing:-.5px; text-transform:uppercase; white-space:nowrap; }
  .kid-brand .sh-wheel{ width:.77em; height:.77em; margin:0 -.02em 0 -.04em; flex-shrink:0; }
  .kid-kind{ padding:2px 8px 3px; background:#0a0a0a; color:#fff; font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:800; font-size:11pt; line-height:1; letter-spacing:2.5px; text-transform:uppercase; transform:rotate(-1.5deg); }
  .kidp .act{ position:relative; display:flex; flex-direction:column; min-height:0; padding:0.1in 0.12in 0.12in; border:2px solid #0a0a0a; }
  .kidp .act-top{ display:flex; align-items:center; gap:0.12in; margin-bottom:0.1in; }
  .kidp .act-label{ flex-shrink:0; margin:0; padding:3px 7px 4px; background:#0a0a0a; color:#fff; font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:800; font-size:11.5pt; line-height:1; letter-spacing:2px; text-transform:uppercase; transform:rotate(-1.5deg); }
  .kidp .act-body{ position:relative; flex:1; min-height:0; }
  .kidp .act-verse .act-body{ flex:none; display:flex; flex-direction:column; align-items:flex-start; gap:0.12in; }
  .kidp .act-words{ flex:0 0 2.3in; }
  .kidp .act-maze{ flex:1; }
  .kidp .act-note{ margin:0; font-size:9pt; line-height:1.3; }
  .kid-missing{ margin:auto 0; font-size:12px; color:#b00; }
  @media screen{ .kidp .act[data-act]{ cursor:pointer; } .kidp .act[data-act]:hover{ outline:2px dashed #888; outline-offset:2px; } }
  /* the pieces kids.py's makers draw (same as on the kids sheet, a touch smaller) */
  .cs{ display:block; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; overflow:visible; }
  .cs .f{ fill:currentColor; }
  /* one line, shrunk by the script (--ms) when the verse is long */
  .code-msg{ --ms:1; display:flex; align-items:flex-end; column-gap:calc(0.18in*var(--ms)); align-self:stretch; min-width:0; overflow:hidden; }
  .cw{ display:flex; align-items:flex-end; flex-shrink:0; }
  .cc{ display:flex; flex-direction:column; align-items:center; width:calc(0.28in*var(--ms)); }
  .cc .cs{ width:calc(0.22in*var(--ms)); height:calc(0.22in*var(--ms)); }
  .cc i{ display:block; width:calc(0.22in*var(--ms)); height:calc(0.3in*var(--ms)); border-bottom:1.5px solid #0a0a0a; }
  .cp{ width:calc(0.15in*var(--ms)); text-align:center; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:calc(18pt*var(--ms)); line-height:1; }
  .code-key{ display:flex; align-items:center; gap:0.04in; align-self:stretch; min-width:0; --ks:1; }
  .kp-wrap{ display:flex; align-items:center; gap:calc(0.04in*var(--ks)); flex:1; min-width:0; overflow:hidden; }
  .code-key-label{ margin-right:0.05in; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:10pt; letter-spacing:1.5px; text-transform:uppercase; }
  .kp{ display:flex; flex-direction:column; align-items:center; flex-shrink:0; width:calc(0.26in*var(--ks)); padding:3px 0 2px; border:1px solid #0a0a0a; }
  .kp .cs{ width:calc(0.16in*var(--ks)); height:calc(0.16in*var(--ks)); }
  .kp b{ margin-top:2px; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:calc(11pt*var(--ks)); line-height:1; }
  .kp-gap{ flex-shrink:0; width:calc(0.08in*var(--ks)); }
  .maze-rules{ display:flex; flex-direction:column; gap:2px; font-size:8pt; line-height:1.15; }
  .maze-rules span{ display:flex; align-items:center; gap:5px; }
  .maze-rules svg{ width:0.16in; height:0.16in; flex-shrink:0; }
  .maze-svg{ position:absolute; top:0; left:0; width:100%; height:100%; }
  .maze-end{ font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:11px; letter-spacing:1px; fill:#0a0a0a; }
  .ws-theme{ margin:0; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:11pt; line-height:1.05; letter-spacing:1px; text-transform:uppercase; }
  .ws{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; gap:0.16in; }
  .ws-svg{ display:block; flex-shrink:0; max-height:100%; height:auto; }
  .ws-l{ font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:700; font-size:12.5px; fill:#0a0a0a; }
  .ws-bank{ margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:3px; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:700; font-size:9.5pt; line-height:1.1; letter-spacing:.5px; }
  .ws-bank li{ display:flex; align-items:center; gap:5px; white-space:nowrap; }
  .ws-bank li::before{ content:""; flex-shrink:0; width:0.09in; height:0.09in; border:1.2px solid #0a0a0a; }
  .ph{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; border:1.5px dashed #b5b0a6; text-align:center; color:#6b665d; font-size:10pt; }
  .ph b{ font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:14pt; color:#0a0a0a; text-transform:uppercase; }

  /* ── PAGE 8 · BACK COVER: the old welcome panel, sized up for the page ── */
  .w-head{ font-size:46px; margin:16px 0 0; }
  .w-body{ margin:16px 0 0; }
  .w-body p,.w-body ul{ font-size:13.5px; line-height:1.6; margin:0 0 9px; }
  .w-body ul{ padding-left:1.2em; }
  .w-body > :last-child{ margin-bottom:0; }
  .qr-hymnal-block{ margin:auto 0; align-self:center; }
  .w-foot .verse-ref{ font-size:34px; margin:0 0 6px; text-transform:none; }
  .w-foot .verse-txt{ font-size:14px; line-height:1.5; }

  /* PRINT. Each side prints inside an 11.75in-wide strip with the 11in sheet
     centred in it, and the browser does the sizing - no zoom knob:
     - Safari ignores @page{size} (so LANDSCAPE is picked in the dialog) and
       prints inside the printer's own margins; anything wider than that
       printable width it shrinks to fit the width.
     - A bare 11 x 8.5in sheet shrunk to the width is still a hair too tall
       (the margins take a bigger bite out of 8.5in than out of 11in), so its
       last sliver spilled onto a blank page - the 2-sheets-become-4-pages
       bug. The strip's extra 0.75in makes it wider-shaped than any printable
       area, so once the width fits the height fits too, on any printer.
     - The booklet folds down the middle and the strip is centred on the
       paper, so the fold lands in the middle whatever the shrink. Checked
       through WebKit's print engine: one page per side and the fold at
       5.50in, with printer margins anywhere from 0 to 0.5in.
     The on-screen transform:scale() is cancelled: it only shrinks the paint,
     not the layout. Chrome/Firefox get @page{size} from the script and fit
     the width the same way. */
  @media print{
    body{ background:#fff; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
    .chrome,.sheet-label,.fold,.z-hint,.cf-hint{ display:none!important; }
    .stage{ padding:0; }
    .sheet-wrap{ width:11.75in!important; height:8.5in!important; margin:0 auto!important;
                 overflow:hidden!important; break-inside:avoid; page-break-inside:avoid;
                 page-break-after:always; break-after:page; }
    .sheet-wrap:last-of-type{ page-break-after:auto; break-after:auto; }
    .sheet{ transform:none!important; margin:0 auto!important; box-shadow:none!important; }
  }
"""

JS = r"""/* Printing: ask for landscape Letter, but never set an @page margin — Safari
   and every iOS browser shove the whole sheet up and clip it when a page margin
   is set (the trap the kids sheet hit). The print CSS fits each side inside the
   printer's own margins instead. */
(function(){
  var pr=document.createElement('style');
  pr.textContent='@page{ size:11in 8.5in; }';
  document.head.appendChild(pr);
  window.addEventListener('beforeprint',function(){ try{window.scrollTo(0,0);}catch(e){} });
})();


    var KEY='__KEY__';
    var loc=document.location.href.split('#')[0].split('?')[0];
    var i=loc.indexOf('/'+KEY+'/');
    var ROOT=(i>=0)?loc.slice(0,i+KEY.length+2):loc.replace(/[^/]*$/,'');
    var ZINE_URL=ROOT+'zine/', PRAYER_URL=ROOT+'prayer-list/', HYMNAL_URL=ROOT+'hymnal/', EVENTS_URL=ROOT+'events/';
    var _bl=document.getElementById("bulletin-back"); if(_bl) _bl.href=ROOT+"resources/";

    /* cover date = the coming Sunday */
    (function(){
      var M=['January','February','March','April','May','June','July','August','September','October','November','December'];
      var n=new Date(), add=(7-n.getDay())%7;
      var s=new Date(n.getFullYear(),n.getMonth(),n.getDate()+add);
      var t=M[s.getMonth()]+' '+s.getDate();
      document.querySelectorAll('.cover [data-date]').forEach(function(e){e.textContent=t;});
    })();

    /* random back-cover verse (from bulletin-verses.txt) */
    (function(){
      var VERSES=__VERSES_JSON__;
      var v=VERSES[Math.floor(Math.random()*VERSES.length)];
      document.getElementById('v-ref').textContent=v.ref;
      document.getElementById('v-txt').textContent='“'+v.text+'”';
    })();

    /* QR codes: drawn at 300px and shown at about an inch, so they print crisp */
    function qr(id,url){ try{ new QRCode(document.getElementById(id),{text:url,width:300,height:300,correctLevel:QRCode.CorrectLevel.M}); }catch(e){} }
    function makeQRs(){ qr('qr-hymnal',HYMNAL_URL); qr('qr-zine',ZINE_URL); qr('qr-prayer',PRAYER_URL); qr('qr-events',EVENTS_URL); }
    if(window.QRCode) makeQRs(); else window.addEventListener('load',makeQRs);

    /* Zine: fills page 4, then page 5 (the center spread), and a long week
       carries on at the top of page 6. All three are editable. Whole blocks
       move on first; then the next paragraph is split at a word boundary so
       each page fills to the bottom. A heading is kept with at least the first
       line of its paragraph so it never strands alone. While someone types,
       only whole blocks move (so the caret's own text is never rebuilt and can
       be put straight back); the full pass with splits runs when they click
       away. */
    var Z=[document.getElementById('zine'), document.getElementById('zine5'), document.getElementById('zine6')];
    var A=[document.getElementById('z-area4'), document.getElementById('z-area5'), document.getElementById('z-area6')];
    var overBox=document.getElementById('z-over'), warn=document.getElementById('zine-warn');
    var ZINE_DEFAULT=Z[0].innerHTML;
    function fits(k){ return Z[k].scrollHeight<=A[k].clientHeight; }
    function zineHost(n){ for(var k=0;k<Z.length;k++){ if(n && Z[k].contains(n)) return Z[k]; } return null; }
    function fill(k, light){
      var cur=Z[k], next=Z[k+1];
      /* 1) move whole trailing blocks on until this page fits */
      var guard=0;
      while(cur.children.length>1 && !fits(k) && guard<400){
        next.insertBefore(cur.lastElementChild, next.firstChild); guard++;
      }
      if(light) return;
      /* 2) fill the leftover gap by splitting the next block across */
      var cand=next.firstElementChild, movedHeading=null, split=false;
      if(cand && cand.tagName==="H4"){
        cur.appendChild(cand);
        if(!fits(k)){ next.insertBefore(cand, next.firstChild); cand=null; }
        else { movedHeading=cand; cand=next.firstElementChild; }
      }
      if(cand && cand.tagName==="P"){
        var words=(cand.textContent||"").trim().split(" ").filter(Boolean);
        if(words.length>1){
          var hp=document.createElement("p");
          hp.setAttribute("data-frag","head");
          cur.appendChild(hp);
          var lo=1, hi=words.length-1, best=0;
          while(lo<=hi){ var m=(lo+hi)>>1; hp.textContent=words.slice(0,m).join(" "); if(fits(k)){ best=m; lo=m+1; } else { hi=m-1; } }
          /* no lone line on either side of the break: carry at least two lines
             over, and if that leaves one line behind, move the whole paragraph */
          var lh=parseFloat(getComputedStyle(cand).lineHeight)||18;
          function cut(n){ hp.textContent=words.slice(0,n).join(" "); cand.textContent=words.slice(n).join(" "); }
          if(best>0){
            cut(best);
            while(best>0 && cand.offsetHeight<lh*1.5){ best--; cut(best); }
            if(best>0 && hp.offsetHeight<lh*1.5) best=0;
          }
          if(best>0){
            cand.setAttribute("data-frag","tail");
            split=true;
          } else { cur.removeChild(hp); cand.textContent=words.join(" "); }
        }
      }
      if(movedHeading && !split) next.insertBefore(movedHeading, next.firstChild);
      /* never end a page on a heading */
      while(cur.children.length>1 && cur.lastElementChild.tagName==="H4" && next.firstElementChild){
        next.insertBefore(cur.lastElementChild, next.firstChild);
      }
    }
    function flowZine(light){
      var sel=window.getSelection(), an=null, ao=0;
      if(light && sel.rangeCount && zineHost(sel.anchorNode)){ an=sel.anchorNode; ao=sel.anchorOffset; }
      /* pull everything back to page 4; a full pass also undoes earlier splits */
      for(var k=1;k<Z.length;k++){ while(Z[k].firstChild) Z[0].appendChild(Z[k].firstChild); }
      if(!light){
        [].forEach.call(Z[0].querySelectorAll("[data-frag=head]"),function(hd){
          var tl=hd.nextElementSibling;
          if(tl && tl.getAttribute("data-frag")==="tail" && tl.tagName===hd.tagName){
            hd.textContent=(hd.textContent.trim()+" "+tl.textContent.trim()).trim();
            tl.parentNode.removeChild(tl);
          }
        });
        [].forEach.call(Z[0].querySelectorAll("[data-frag]"),function(e){ e.removeAttribute("data-frag"); });
      }
      overBox.hidden=false;                       /* page 6 has to be laid out to be measured */
      for(var k=0;k<Z.length-1;k++) fill(k, light);
      overBox.hidden=!Z[2].textContent.trim() && zineHost(an)!==Z[2];
      if(warn) warn.hidden=overBox.hidden || fits(2);
      /* the end that didn't fit: a QR code to the whole zine instead */
      document.getElementById('z-more').hidden=overBox.hidden || fits(2);
      if(an && document.contains(an)){ zineHost(an).focus({preventScroll:true}); sel.collapse(an, ao); }
    }
    function resetZine(){ Z.forEach(function(z){ z.innerHTML=''; }); Z[0].innerHTML=ZINE_DEFAULT; flowZine(); }
    var t;
    Z.forEach(function(z){
      z.addEventListener('input',function(){ clearTimeout(t); t=setTimeout(function(){ flowZine(true); },350); });
      /* clicked away from the zine (not just onto another of its pages): full pass */
      z.addEventListener('blur',function(){ setTimeout(function(){ if(!zineHost(document.activeElement)){ clearTimeout(t); flowZine(); } },0); });
    });

    /* Events: show only those from the coming Sunday (the cover date) up to,
       but not including, the next Sunday. ISO date strings compare directly. */
    (function(){
      var box=document.getElementById("be-list"); if(!box) return;
      var n=new Date(), add=(7-n.getDay())%7;
      var start=new Date(n.getFullYear(),n.getMonth(),n.getDate()+add);
      var end=new Date(start.getFullYear(),start.getMonth(),start.getDate()+7);
      function k(d){ return d.getFullYear()+"-"+("0"+(d.getMonth()+1)).slice(-2)+"-"+("0"+d.getDate()).slice(-2); }
      var s=k(start), e=k(end), shown=0;
      var items=box.querySelectorAll(".be-item");
      for(var i=0;i<items.length;i++){
        var d=items[i].getAttribute("data-when");
        var inWin=(d>=s && d<e);
        items[i].hidden=!inWin; if(inWin) shown++;
      }
      /* Nothing this week? Scan forward from the cover Sunday to the next event
         (never earlier than the cover Sunday; rows are in date order). */
      if(shown===0){
        for(var j=0;j<items.length;j++){
          if(items[j].getAttribute("data-when")>=s){ items[j].hidden=false; shown=1; break; }
        }
      }
      var none=document.getElementById("be-none"); if(none) none.hidden=shown>0;
      var ttl=document.getElementById("be-title");
      if(ttl && shown>0) ttl.textContent = (function(){
        /* label the fallback so it does not read as this week */
        for(var j=0;j<items.length;j++){ if(!items[j].hidden){ return items[j].getAttribute("data-when")<e ? "Coming Up" : "Next Up"; } }
        return "Coming Up";
      })();
    })();

    document.getElementById('flip').addEventListener('change',function(e){
      document.querySelectorAll('.sheet.backside').forEach(function(sh){ sh.classList.toggle('flip',e.target.checked); });
    });

    /* Prayer list and events: if they run out of room, cut rows from the end
       and show a QR code to the full list in their place. The prayer list's
       write-in lines go first. */
    function fitList(list, rowSel, more, extra){
      if(!list) return;
      var rows=list.querySelectorAll(rowSel);
      [].forEach.call(rows,function(r){ r.classList.remove('cut'); });
      more.hidden=true; if(extra) extra.hidden=false;
      function over(){ return list.scrollHeight>list.clientHeight+1; }
      if(!over()) return;
      if(extra){ extra.hidden=true; if(!over()) return; }
      more.hidden=false;
      for(var i=rows.length-1;i>0 && over();i--){ if(!rows[i].hidden) rows[i].classList.add('cut'); }
    }
    function fitLists(){
      fitList(document.querySelector('.pr-list'),'.pr-row',document.getElementById('pr-more'),document.querySelector('.pr-fill'));
      fitList(document.getElementById('be-list'),'.be-item',document.getElementById('be-more'));
    }

    /* Page 7, the kids activity page. The makers are kids.py's own (its
       KIDS_JS engine, dropped in at render time), sized for a half page.
       Tap a box on screen for a new one; the code's answer shows above. */
    var remakeKids=function(){};
    (function(){
      var root=document.getElementById('kidp'); if(!root) return;
      __KIDS_ENGINE__
      if(typeof secretCode!=='function') return;
      function read(a){ try{ return JSON.parse(root.getAttribute(a))||[]; }catch(e){ return []; } }
      var REFS=read('data-verses'), THEMES=read('data-words');
      /* The coded verse and its key are wider than this half page can always
         fit, so each shrinks (symbols, blanks and letters together) until it
         fits on one line. */
      function shrinkToFit(el, box, prop){
        for(var k=1; box.scrollWidth>box.clientWidth+1 && k>0.5; ){ k-=0.03; el.style.setProperty(prop,k); }
      }
      function fitCode(body){
        var msg=body.querySelector('.code-msg'), key=body.querySelector('.code-key');
        if(msg) shrinkToFit(msg, msg, '--ms');
        if(!key) return;
        var wrap=document.createElement('div'); wrap.className='kp-wrap';
        [].slice.call(key.querySelectorAll('.kp,.kp-gap')).forEach(function(k){ wrap.appendChild(k); });
        key.appendChild(wrap);
        shrinkToFit(key, wrap, '--ks');
      }
      var MAKERS={
        verse:function(body,rng){
          var ref=pick(REFS.length?REFS:['John 3:16'],rng);
          body.innerHTML=secretCode(ref,rng);
          fitCode(body);
          var ans=document.getElementById('kids-answer'); if(ans) ans.textContent=ref;
        },
        words:function(body,rng,box){
          var th=pick(THEMES,rng);
          box.querySelector('.ws-theme').textContent=th[0];
          wordSearch(body,pickWords(th[1],rng,8),rng);
        },
        maze:function(body,rng){
          var C=Math.max(8,Math.min(18,Math.floor((body.clientWidth-4)/CELL)));
          var R=Math.max(6,Math.min(30,Math.floor((body.clientHeight-34)/CELL)));
          body.innerHTML=drawMaze(makeMaze(R,C,rng));
        }
      };
      var boxes=root.querySelectorAll('.act[data-act]');
      function make(box,seed){
        box.setAttribute('data-seed',seed);
        MAKERS[box.getAttribute('data-act')](box.querySelector('.act-body'),makeRng(seed),box);
      }
      [].forEach.call(boxes,function(box){
        make(box,newSeed());
        box.addEventListener('click',function(){ make(box,newSeed()); });
      });
      /* sizes depend on the fonts: once they're in, lay the same puzzles out again */
      remakeKids=function(){ [].forEach.call(boxes,function(box){ make(box,+box.getAttribute('data-seed')); }); };
    })();

    /* order of service: the largest text (8 to 15px) that still fits page 2 */
    function fitOrder(){
      var el=document.querySelector('.pad-order'); if(!el) return;
      function fits(f){ el.style.fontSize=f+'px'; return el.scrollHeight<=el.clientHeight+1; }
      var lo=8, hi=15;
      if(fits(hi)) return;
      while(hi-lo>0.2){ var m=(lo+hi)/2; if(fits(m)) lo=m; else hi=m; }
      fits(lo);
    }

    function scale(){
      var avail=document.querySelector('.stage').clientWidth-36;   /* minus the stage padding */
      var s=Math.min(1, avail/(11*96));
      document.querySelectorAll('.sheet').forEach(function(sh){ sh.style.transform='scale('+s+')'; });
      document.querySelectorAll('.sheet-wrap').forEach(function(w){ w.style.height=(8.5*96*s)+'px'; w.style.width=(11*96*s)+'px'; });
    }
    /* page 6's notes: no room for even a couple of lines (a long zine and a busy week)? drop the heading too */
    function fitNotes(){
      var nt=document.querySelector('.notes-title'), nl=document.querySelector('.notes-lines'); if(!nt||!nl) return;
      nt.hidden=nl.hidden=false;
      if(nl.clientHeight<60) nt.hidden=nl.hidden=true;
    }
    /* Everything that measures runs again whenever fonts finish loading (a
       measurement taken with a fallback font is wrong), but never while the
       page is being printed: the print layout isn't the one to measure. */
    function printing(){ return window.matchMedia && window.matchMedia('print').matches; }
    function fitAll(){ if(printing()) return; scale(); fitOrder(); fitLists(); flowZine(); fitNotes(); }
    window.addEventListener('resize',fitAll);
    if(document.fonts&&document.fonts.ready){ document.fonts.ready.then(function(){ fitAll(); remakeKids(); }); }
    if(document.fonts&&document.fonts.addEventListener){ document.fonts.addEventListener('loadingdone',function(){ fitAll(); remakeKids(); }); }
    window.addEventListener('load',function(){ fitAll(); setTimeout(fitAll,400); });
  """

_MARK = ('GRACE&nbsp;H<svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="43" fill="none" stroke="#000" stroke-width="6.5"/>'
         '<g stroke="#000" stroke-width="5.5"><line x1="50" y1="7" x2="50" y2="93"/><line x1="7" y1="50" x2="93" y2="50"/>'
         '<line x1="19.6" y1="19.6" x2="80.4" y2="80.4"/><line x1="80.4" y1="19.6" x2="19.6" y2="80.4"/></g>'
         '<circle cx="50" cy="50" r="7.5" fill="#000"/></svg>USE')

BODY = r"""  <div class="chrome">
    <a class="btn back" id="bulletin-back" href="../resources/">&larr; Resources</a>
    <h1>Grace House — Sunday bulletin</h1>
    <p>An 8-page booklet from two sheets of paper. Edit the zine (click it and type) &mdash; it runs across the center spread, and a long week carries on at the top of page 6. This week&rsquo;s events fill in on their own. Print: <b>Landscape, double-sided, Short-edge binding</b>, 100%; for more than one copy, turn on <b>Collate</b>. Slip sheet 2 inside sheet 1, fold them in half together and staple on the fold. Long-edge printer? Tick the box so the backs line up.</p>
    <div class="bar">
      <button class="btn primary" onclick="window.print()">Print</button>
      <label class="chk"><input type="checkbox" id="flip"> My printer flips on the long edge</label>
      <button class="btn" onclick="resetZine()">Reset zine text</button>
      <span class="hint">Four pages = both sides of two sheets.</span>
      <span class="hint">Kids page verse: <b id="kids-answer"></b></span>
      <span class="warn" id="zine-warn" hidden>The zine is too long for the booklet &mdash; its end is cut off on page 6, with a QR code to the rest.</span>
    </div>
  </div>

  <div class="stage">
    <div class="sheet-label">Sheet 1, outside &mdash; back cover + cover (prints first)</div>
    <div class="sheet-wrap"><div class="sheet" id="side1"><div class="flipwrap">
      <div class="page"><div class="pad">
        <div class="brandmark">__MARK__</div>
        <h2 class="h-stencil w-head">__HEAD__</h2>
        <div class="w-body">__WELCOME__</div>
        <div class="qr-block qr-hymnal-block"><div class="qr" id="qr-hymnal"></div><div class="qr-cap">Hymnal</div></div>
        <div class="w-foot">
          <div class="verse-ref" id="v-ref">__V_REF__</div>
          <p class="verse-txt" id="v-txt">__V_TXT__</p>
        </div>
      </div></div>

      <div class="page cover">
        __COVER_INNER__
        <span class="date" data-date>September 20</span>
      </div>
      <div class="fold"></div>
    </div></div></div>

    <div class="sheet-label">Sheet 1, inside &mdash; pages 2 + 7 (prints on the back)</div>
    <div class="sheet-wrap"><div class="sheet backside" id="side2"><div class="flipwrap">
      <div class="page"><div class="pad pad-order">
        __ORDER__
      </div></div>

      <div class="page"><div class="pad kidp" id="kidp" data-verses="__KID_REFS__" data-words="__KID_WORDS__">
        __KIDS_PAGE__
      </div></div>
      <div class="fold"></div>
    </div></div></div>

    <div class="sheet-label">Sheet 2, outside &mdash; pages 6 + 3</div>
    <div class="sheet-wrap"><div class="sheet" id="side3"><div class="flipwrap">
      <div class="page"><div class="pad">
        <div class="z-over" id="z-over" hidden>
          <div class="z-over-label">The zine, continued</div>
          <div class="z-over-area" id="z-area6"><div class="zine" id="zine6" contenteditable="true"></div></div>
          <div class="more-qr" id="z-more" hidden><div class="qr" id="qr-zine"></div><div class="qr-cap">Read the rest<br>of the zine</div></div>
        </div>
        <h2 class="h-stencil be-title" id="be-title">Coming Up</h2>
        <div class="be-list" id="be-list">__EVENTS__</div>
        <div class="more-qr" id="be-more" hidden><div class="qr" id="qr-events"></div><div class="qr-cap">More coming up:<br>all events</div></div>
        <p class="be-none" id="be-none" hidden>Nothing coming up, what&rsquo;s up?</p>
        <h3 class="h-stencil notes-title">Notes</h3>
        <div class="notes-lines"></div>
      </div></div>

      <div class="page"><div class="pad">
        <h2 class="h-stencil p-title">Prayer List</h2>
        <div class="pr-list">
          __PRAYER_ROWS__
          <div class="pr-fill"></div>
        </div>
        <div class="more-qr" id="pr-more" hidden><div class="qr" id="qr-prayer"></div><div class="qr-cap">See the full<br>prayer list</div></div>
      </div></div>
      <div class="fold"></div>
    </div></div></div>

    <div class="sheet-label">Sheet 2, inside &mdash; pages 4 + 5, the center spread (prints on the back)</div>
    <div class="sheet-wrap"><div class="sheet backside" id="side4"><div class="flipwrap">
      <div class="page"><div class="pad">
        <h2 class="h-stencil z-title">__ZINE_TITLE__</h2>
        <div class="z-area" id="z-area4"><div class="zine" id="zine" contenteditable="true">__ZINE__</div></div>
      </div></div>

      <div class="page"><div class="pad">
        <div class="z-area" id="z-area5"><div class="zine" id="zine5" contenteditable="true"></div></div>
      </div></div>
      <div class="z-hint">Tap the zine to edit</div>
      <div class="fold"></div>
    </div></div></div>
  </div>"""

_HEAD = (
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
    '<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    '<title>Grace House — bulletin</title>\n'
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Stencil+Display:wght@800;900&family=Big+Shoulders+Stencil+Text:wght@600;700;800&family=Special+Elite&family=Montserrat:wght@400&display=swap" rel="stylesheet">\n'
    '<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>\n'
    '<style>'
)


def render_bulletin(key: str, zine_data=None, who_data=None,
                    prayer_data=None, verses=None, events_data=None,
                    today: datetime.date | None = None) -> str:
    """Full standalone HTML for the printable bulletin booklet.

    key         access key (for the QR targets)
    zine_data   server.parse_zine()                    -> (title, sections) | None
    who_data    who.parse_who()                        -> (headline, welcome, sections) | None
    prayer_data prayer.parse_prayers(parse_event_date) -> {"days": [...]} | None
    verses      parse_bulletin_verses()                -> [(text, ref), ...]  (optional)
    events_data server.parse_events()[0]               -> [(date, lines), ...] | None
    """
    today = today or datetime.date.today()
    if verses is None:
        verses = parse_bulletin_verses()
    if not verses:
        verses = [_FALLBACK_VERSE]

    head_html, welcome_html = _welcome_html(who_data)
    zine_title = escape(zine_data[0]) if (zine_data and zine_data[0]) else "The Sunday Zine"
    v0_text, v0_ref = verses[0]

    body = BODY.replace("__MARK__", _MARK)
    body = body.replace("__PRAYER_ROWS__", _prayer_rows(prayer_data, today))
    body = body.replace("__HEAD__", head_html or "Welcome")
    body = body.replace("__WELCOME__", welcome_html)
    body = body.replace("__ORDER__", _order_html(who_data))
    body = body.replace("__ZINE_TITLE__", zine_title)      # before __ZINE__
    body = body.replace("__ZINE__", _zine_html(zine_data))
    body = body.replace("__EVENTS__", _events_html(events_data))
    cover = _cover_data_uri()
    if cover:
        cover_inner = f'<img src="{cover}" alt="Grace House cover" decoding="sync">'
    else:
        cover_inner = ('<div class="cover-fallback" aria-label="Grace House">'
                       '<div class="cf-mark">GRACE<br>HOUSE</div>'
                       '<div class="cf-hint">GraceHouseCover.png not found in the repo root</div>'
                       '</div>')
    body = body.replace("__COVER_INNER__", cover_inner)
    body = body.replace("__V_REF__", escape(v0_ref))
    body = body.replace("__V_TXT__", "“" + escape(v0_text) + "”")
    kids_inner, kid_refs, kid_words, kids_engine = _kids_page(verses)
    body = body.replace("__KIDS_PAGE__", kids_inner)
    body = body.replace("__KID_REFS__", kid_refs)
    body = body.replace("__KID_WORDS__", kid_words)

    verses_json = json.dumps([{"ref": r, "text": t} for (t, r) in verses],
                             ensure_ascii=False)
    script = (JS.replace("__KEY__", key).replace("__VERSES_JSON__", verses_json)
              .replace("__KIDS_ENGINE__", kids_engine))

    return (_HEAD + CSS + "</style>\n</head>\n<body>\n"
            + body + "\n<script>" + script + "</script>\n</body>\n</html>\n")
