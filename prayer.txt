"""Prayer list page for Grace House.

Reads ./prayer.txt and builds the middle of /{key}/prayer-list/.
server.py wraps it in the usual page (HOME tag, logo, title tag).

File format (lines starting with # are ignored):

    September 27 2026                      <- the date, on its own line
    Healing for Sarah after surgery (Mike) <- one request per line;
    Dave's dad in the hospital (Dave)         who asked goes in ( ) at
    Peace at home                             the end (leave it off if
                                              they'd rather not be named)
    September 20 2026
    + Mike's new job (Mike)                <- a + in front = answered

Put a blank line between gatherings. The year is optional ("Sep 27"
works; it takes the most recent Sep 27). Dates can be written any way
events.txt accepts them.

Each gathering's requests drop off the page one month after its date
(Sep 20 -> gone on Oct 20). That's worked out in the visitor's browser,
like the events page, so the list stays right without a rebuild.
build.py tells you which blocks have dropped off so you can delete them.

Answered requests (a + at the start of the line) move to an Answered
section and drop off on the same schedule.

Private checks: tapping a request marks it prayed for, on that phone
only. Nothing is sent anywhere. A check clears itself after CHECK_HOURS.
"""
from __future__ import annotations

import calendar
import datetime
import hashlib
import re
from html import escape
from pathlib import Path

PRAYER_PATH = Path(__file__).resolve().parent / "prayer.txt"

CHECK_HOURS = 4   # a private check clears itself after this long
NEW_DAYS = 7      # requests this recent get a "New" tag

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
        "Saturday", "Sunday"]   # same order as date.weekday()

ANSWERED_RE = re.compile(r"^\s*[+✓✔]\s*")
# The last (…) on a line is who asked: "Healing for Sarah (Mike)"
ASKER_RE = re.compile(r"^(.*\S)\s*\(([^()]+)\)\s*$")


def _read_day(line: str, read_date, today: datetime.date):
    """A date line, with or without the year. With no year, it's the most
    recent one (a few days ahead is allowed, for lists typed early)."""
    when = read_date(line)
    if when is None and not re.search(r"\d{4}", line):
        when = read_date(f"{line} {today.year}")
        if when is not None and when > today + datetime.timedelta(days=7):
            try:
                when = when.replace(year=when.year - 1)
            except ValueError:   # Feb 29
                when = None
    return when


def _dateish(line: str) -> bool:
    """Probably meant as a date (so don't file it as a request)."""
    low = line.lower()
    if re.search(r"\d\s*/\s*\d", low):
        return True
    return bool(re.search(r"\d", low)) and any(
        re.search(rf"\b{m[:3].lower()}", low) for m in MONTHS)


def _ends(when: datetime.date) -> datetime.date:
    """The day a request drops off: one month after its date."""
    y, m = when.year + when.month // 12, when.month % 12 + 1
    return datetime.date(y, m, min(when.day, calendar.monthrange(y, m)[1]))


def _item(when: datetime.date, line: str):
    answered = bool(ANSWERED_RE.match(line))
    text = ANSWERED_RE.sub("", line, count=1).strip()
    asker = ""
    m = ASKER_RE.match(text)
    if m:
        text, asker = m.group(1).strip(), m.group(2).strip()
    if not text:
        return None
    uid = hashlib.sha1(f"{when.isoformat()}|{text}|{asker}".encode("utf-8")).hexdigest()[:10]
    return {"text": text, "asker": asker, "answered": answered, "id": uid}


def parse_prayers(read_date, path: Path = PRAYER_PATH, today: datetime.date | None = None):
    """Return {"days": [(date, [items])], "problems": [str]}, newest day
    first, or None if the file is missing or has nothing but comments.

    read_date is server.parse_event_date, so dates work the same as in
    events.txt. A block that doesn't start with a date is more requests
    for the day above it, so a stray blank line inside a list is fine.
    """
    if not path.exists():
        return None
    today = today or datetime.date.today()
    raw = path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("#")]

    days: dict[datetime.date, list] = {}
    problems: list[str] = []
    current = None
    for block in re.split(r"\n\s*\n", "\n".join(lines)):
        block_lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not block_lines:
            continue
        when = _read_day(block_lines[0], read_date, today)
        if when is not None:
            current = when
            rest = block_lines[1:]
            days.setdefault(when, [])
        elif _dateish(block_lines[0]):
            problems.append(f'"{block_lines[0]}" looks like a date but can\'t be read. '
                            "The requests under it were left out.")
            current = None
            continue
        elif current is not None:
            rest = block_lines
        else:
            problems.append(f'"{block_lines[0]}" needs a date line above it, like '
                            '"September 27 2026". It was left out.')
            continue
        for ln in rest:
            item = _item(current, ln)
            if item:
                days[current].append(item)

    if not days and not problems:
        return None
    ordered = sorted(((d, items) for d, items in days.items() if items),
                     key=lambda d: d[0], reverse=True)
    return {"days": ordered, "problems": problems}


def prayer_notes(data, today: datetime.date | None = None):
    """[(level, message)] for build.py: lines to fix, and blocks that have
    dropped off the page and can be deleted from prayer.txt."""
    if not data:
        return []
    today = today or datetime.date.today()
    notes = [("warning", p) for p in data["problems"]]
    for when, _items in reversed(data["days"]):
        ends = _ends(when)
        if ends <= today:
            notes.append(("notice",
                          f"The {MONTHS[when.month - 1]} {when.day} {when.year} requests "
                          f"dropped off on {MONTHS[ends.month - 1][:3]} {ends.day}. "
                          "You can delete that block."))
    return notes


def _short(d: datetime.date) -> str:
    return f"{MONTHS[d.month - 1][:3]} {d.day}"


def _text_html(item) -> str:
    who = f'<span class="pr-who">asked by {escape(item["asker"])}</span>' if item["asker"] else ""
    return f'<span class="pr-text"><span class="pr-req">{escape(item["text"])}</span>{who}</span>'


def render_prayers(data, today: datetime.date | None = None) -> str:
    """The page's middle: count strip, one group per gathering (newest
    first), then Answered. Anything already past its month at build time
    is left out; the browser hides the rest as their day comes."""
    today = today or datetime.date.today()
    groups, answered = [], []
    for when, items in (data["days"] if data else []):
        ends = _ends(when)
        if ends <= today:
            continue
        open_items = [i for i in items if not i["answered"]]
        if open_items:
            groups.append((when, ends, open_items))
        answered += [(ends, i) for i in items if i["answered"]]

    count = sum(len(g[2]) for g in groups)
    count_txt = f"{count} request{'' if count == 1 else 's'}" if count else "nothing right now"

    parts = [
        '<div class="meta-strip">'
        f'<span class="count-tag" id="pr-count">{count_txt}</span>'
        '<div class="dash-rule"></div>'
        '<span class="hint">↓ tap as you pray</span>'
        "</div>",
        f'<p class="pr-hint">Only you see your checks. They clear after {CHECK_HOURS} hours.</p>',
    ]
    for when, ends, items in groups:
        last = ends - datetime.timedelta(days=1)
        buttons = "".join(
            f'<button type="button" class="pr-item" data-id="{i["id"]}" aria-pressed="false">'
            '<span class="pr-check" aria-hidden="true">✓</span>'
            f"{_text_html(i)}</button>"
            for i in items
        )
        parts.append(
            f'<section class="pr-day" data-date="{when.isoformat()}" data-expires="{ends.isoformat()}">'
            '<div class="pr-head">'
            f'<h2 class="pr-date">{DAYS[when.weekday()]} {_short(when)}</h2>'
            '<span class="count-tag pr-new" hidden>New</span>'
            f'<span class="pr-thru">through {_short(last)}</span>'
            "</div>"
            f"{buttons}</section>"
        )
    if answered:
        done = "".join(
            f'<div class="pr-done" data-expires="{ends.isoformat()}">'
            '<span class="pr-check on" aria-hidden="true">✓</span>'
            f"{_text_html(i)}</div>"
            for ends, i in answered
        )
        parts.append(
            '<section class="pr-answered" id="pr-answered">'
            '<div class="pr-head"><h2 class="pr-date">Answered</h2></div>'
            f"{done}</section>"
        )
    parts.append(
        f'<p class="ev-none" id="pr-none"{" hidden" if (groups or answered) else ""}>'
        "Nothing on the list right now.</p>"
    )
    script = PRAYER_JS.replace("__HOURS__", str(CHECK_HOURS)).replace("__NEW__", str(NEW_DAYS))
    return ('<div class="pr-list" id="pr-list">\n' + "\n".join(parts)
            + f"\n</div>\n<script>{script}</script>")


# Runs in the visitor's browser: drops requests whose month is up, tags
# the last week's as New, and keeps this phone's private checks. Checks
# are stored on the phone only (localStorage) and clear after __HOURS__
# hours. Rechecks every minute and when the tab comes back.
PRAYER_JS = r"""
(function () {
  var root = document.getElementById('pr-list');
  if (!root) return;
  var KEY = 'gh-prayed', LIFE = __HOURS__ * 3600 * 1000, NEW_DAYS = __NEW__;
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function dayKey(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
  function save(m) { try { localStorage.setItem(KEY, JSON.stringify(m)); } catch (e) {} }

  function refresh() {
    var now = new Date(), today = dayKey(now), i;
    var newSince = dayKey(new Date(now.getFullYear(), now.getMonth(), now.getDate() - (NEW_DAYS - 1)));
    var open = 0, done = 0;

    var days = root.querySelectorAll('.pr-day');
    for (i = 0; i < days.length; i++) {
      var gone = days[i].getAttribute('data-expires') <= today;
      days[i].hidden = gone;
      var tag = days[i].querySelector('.pr-new');
      if (tag) tag.hidden = gone || days[i].getAttribute('data-date') < newSince;
      if (!gone) open += days[i].querySelectorAll('.pr-item').length;
    }
    var ans = root.querySelectorAll('.pr-done');
    for (i = 0; i < ans.length; i++) {
      var over = ans[i].getAttribute('data-expires') <= today;
      ans[i].hidden = over;
      if (!over) done++;
    }
    var box = document.getElementById('pr-answered');
    if (box) box.hidden = done === 0;
    document.getElementById('pr-none').hidden = open + done > 0;
    document.getElementById('pr-count').textContent =
      open ? open + (open === 1 ? ' request' : ' requests') : 'nothing right now';

    // Private checks: keep the fresh ones, forget anything older.
    var marks = load(), keep = {}, t = Date.now();
    for (var k in marks) if (t - marks[k] < LIFE) keep[k] = marks[k];
    save(keep);
    var items = root.querySelectorAll('.pr-item');
    for (i = 0; i < items.length; i++)
      items[i].setAttribute('aria-pressed', keep[items[i].getAttribute('data-id')] ? 'true' : 'false');
  }

  root.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.pr-item') : null;
    if (!btn) return;
    var id = btn.getAttribute('data-id'), marks = load();
    if (marks[id]) delete marks[id]; else marks[id] = Date.now();
    save(marks);
    refresh();
  });

  refresh();
  setInterval(refresh, 60 * 1000);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') refresh();
  });
})();
"""


# Added onto server.py's CSS.
PRAYER_CSS = r"""
/* ────────────────────────────────────────────────────────────
   PRAYER LIST — one group per gathering, newest first, then
   Answered. Tapping a request checks it on this phone only.
   ──────────────────────────────────────────────────────────── */
.pr-hint {
  margin: 10px 0 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.5;
  opacity: 0.6;
}
.pr-day, .pr-answered { padding-top: 28px; }
.pr-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 2px solid #0a0a0a;
}
.pr-date {
  margin: 0;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 28px;
  line-height: 0.95;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.pr-new { transform: rotate(-3deg); }
.pr-thru {
  margin-left: auto;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 12px;
  white-space: nowrap;
  color: #f01a8b;
}

/* Each request is one big tap target. */
.pr-item {
  -webkit-appearance: none;
  appearance: none;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  width: 100%;
  margin: 0;
  padding: 14px 2px;
  background: none;
  border: 0;
  border-radius: 0;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.pr-done {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 2px;
}
.pr-item + .pr-item,
.pr-done + .pr-done { border-top: 1.5px dashed rgba(10, 10, 10, 0.35); }
.pr-item:focus-visible { outline: 3px solid #f01a8b; outline-offset: 2px; }

.pr-check {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-top: -2px;
  border: 2px solid #0a0a0a;
  border-radius: 50%;
  background: #f2ede4;
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 15px;
  font-weight: 700;
  line-height: 1;
  color: transparent;
  transition: background 0.12s, border-color 0.12s;
}
.pr-item[aria-pressed="true"] .pr-check,
.pr-check.on {
  background: #f01a8b;
  border-color: #f01a8b;
  color: #0a0a0a;
}
@media (hover: hover) {
  .pr-item:hover .pr-check { border-color: #f01a8b; }
}
.pr-text { flex: 1; min-width: 0; transition: opacity 0.12s; }
.pr-item[aria-pressed="true"] .pr-text { opacity: 0.45; }
.pr-req {
  display: block;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 16px;
  line-height: 1.45;
}
.pr-who {
  display: block;
  margin-top: 4px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: #f01a8b;
}

.pr-day[hidden], .pr-answered[hidden], .pr-done[hidden], .pr-new[hidden] {
  display: none !important;
}

/* The check circle has its own background, so no beige halo (see the
   NO HALO note in server.py's CSS). */
.pr-check {
  -webkit-text-stroke-width: 0 !important;
  -webkit-text-stroke-color: transparent !important;
  paint-order: normal !important;
}
"""
