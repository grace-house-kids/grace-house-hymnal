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

Adding requests from the page: when the PRAYER_TOKEN repository
secret is set, the page gets an "Add a request" button. It starts the
"Add prayer request" GitHub Action (.github/workflows/prayer.yml),
which runs "python3 prayer.py add" to put the request at the top of
prayer.txt under that day's date, saves it, and rebuilds the site. It's
on the page a minute or two later. The phone that sent it shows it
right away, marked "Adding", until the real one arrives. Without the
secret (like on your own computer), there's no button.

PRAYER_TOKEN is a fine-grained GitHub token that can do one thing:
Actions (read and write) on this repo. It can't change files or see
secrets. It sits in the prayer page, so anyone with the site link could
dig it out; if it's ever misused, delete it on GitHub (the button just
stops working) and make a new one. Because the website edits prayer.txt
now too, run "git pull" before you edit it on your computer.
"""
from __future__ import annotations

import calendar
import datetime
import hashlib
import os
import re
import sys
from html import escape
from pathlib import Path

PRAYER_PATH = Path(__file__).resolve().parent / "prayer.txt"

CHECK_HOURS = 4   # a private check clears itself after this long
NEW_DAYS = 7      # requests this recent get a "New" tag

MAX_TEXT = 300    # longest request people can send, in characters
MAX_NAME = 40     # longest name
BRANCH = "main"   # the branch the Add prayer request Action saves to

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


# ─────────────────────────────────────────────────────────────
# Adding a request (run by the "Add prayer request" GitHub Action)

def _clean(value, limit: int) -> str:
    s = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))   # line breaks, tabs, etc.
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit].strip()


def request_line(text, name) -> str:
    """One line of prayer.txt, like "Healing for Sarah (Mike)". Empty if
    there's no request."""
    # A leading + or ✓ would mark it answered, and # would hide it.
    t = re.sub(r"^[\s+#✓✔]+", "", _clean(text, MAX_TEXT)).strip()
    n = _clean(name, MAX_NAME).replace("(", "").replace(")", "").strip()
    if not t:
        return ""
    if n:
        return f"{t} ({n})"
    # "(…)" at the very end of a line means who asked. With no name
    # given, a period keeps "Surgery (knee)" from being read that way.
    return t + "." if t.endswith(")") else t


def date_line(sent, today: datetime.date) -> str:
    """"September 23 2026". Uses the date on the visitor's phone (sent as
    2026-09-23), so a Tuesday-night request is filed under Tuesday even
    though GitHub's clock is on UTC, as long as it's within a day."""
    when = today
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(sent or "").strip())
    if m:
        try:
            d = datetime.date(int(m[1]), int(m[2]), int(m[3]))
            if abs((d - today).days) <= 1:
                when = d
        except ValueError:
            pass
    return f"{MONTHS[when.month - 1]} {when.day} {when.year}"


def insert_request(current: str, date: str, line: str) -> str:
    """prayer.txt with the request added. The newest list goes at the
    top (after any # notes up there); if the top list already has this
    date, the request joins the end of it."""
    text = current.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").rstrip()
    if not text.strip():
        return f"{date}\n{line}\n"
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith("#")):
        i += 1
    if i < len(lines) and lines[i].strip() == date:
        j = i + 1
        while j < len(lines) and lines[j].strip():
            j += 1
        lines[j:j] = [line]
    else:
        lines[i:i] = [date, line, ""]
    return "\n".join(lines).rstrip() + "\n"


def add_request_from_env(path: Path = PRAYER_PATH) -> int:
    """"python3 prayer.py add": adds the request in PR_TEXT / PR_NAME /
    PR_DATE to prayer.txt. Prints only the date, never the request, since
    Action logs on a public repo are public."""
    line = request_line(os.environ.get("PR_TEXT"), os.environ.get("PR_NAME"))
    if not line:
        print("The request was empty; nothing added.")
        return 1
    today = datetime.datetime.now(datetime.timezone.utc).date()
    date = date_line(os.environ.get("PR_DATE"), today)
    current = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    path.write_text(insert_request(current, date, line), encoding="utf-8")
    print(f"Added a request under {date}.")
    return 0


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


def _token() -> str:
    return os.environ.get("PRAYER_TOKEN", "").strip()


def _repo() -> str:
    # GitHub fills this in during the build ("owner/repo-name").
    return os.environ.get("GITHUB_REPOSITORY", "grace-house-kids/grace-house-hymnal")


def _form_html() -> str:
    """The "Add a request" button and the form it opens (PRAYER_FORM_JS
    sends it). The token is stored backwards so automatic token scanners
    don't recognize it if the page ever ends up somewhere public."""
    return (
        f'<div class="pr-add" id="pr-add" data-repo="{escape(_repo())}" '
        f'data-branch="{escape(BRANCH)}" data-t="{escape(_token()[::-1])}">'
        '<button type="button" class="pr-add-open" id="pr-add-open" '
        'aria-expanded="false" aria-controls="pr-form">+ Add a request</button>'
        '<form class="pr-form" id="pr-form" hidden>'
        '<label class="pr-label" for="pr-f-text">What can we pray for?</label>'
        f'<textarea id="pr-f-text" name="text" rows="3" maxlength="{MAX_TEXT}" required></textarea>'
        '<label class="pr-label" for="pr-f-name">Your name '
        "<span>optional. Leave it blank to stay unnamed.</span></label>"
        f'<input id="pr-f-name" name="name" type="text" maxlength="{MAX_NAME}" '
        'autocomplete="given-name" autocapitalize="words">'
        '<p class="pr-form-note">It shows up on the list in a couple of minutes, '
        "where anyone with the site link can see it.</p>"
        '<div class="pr-form-row">'
        '<button type="submit" class="pr-send" id="pr-send">Add request</button>'
        '<button type="button" class="pr-cancel" id="pr-cancel">Cancel</button>'
        "</div>"
        "</form>"
        '<p class="pr-status" id="pr-status" role="status" aria-live="polite"></p>'
        "</div>"
    )


def render_prayers(data, today: datetime.date | None = None) -> str:
    """The page's middle: count strip, the Add a request button (when
    PRAYER_TOKEN is set), one group per gathering (newest first), then
    Answered. Anything already past its month at build time is left
    out; the browser hides the rest as their day comes."""
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
    if _token():
        parts.append(_form_html())
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
    if _token():
        script += (PRAYER_FORM_JS.replace("__MAX_TEXT__", str(MAX_TEXT))
                                 .replace("__MAX_NAME__", str(MAX_NAME)))
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
      if (!gone) open += days[i].querySelectorAll('.pr-item, .pr-pending').length;
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

  root.addEventListener('pr-changed', refresh);   // the form drew something in
  refresh();
  setInterval(refresh, 60 * 1000);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') refresh();
  });
})();
"""


# The "Add a request" form. Starts the "Add prayer request" Action on
# GitHub with the request, the name and the date on this phone. GitHub
# answers 204 when the Action has been started.
#
# The request then takes a minute or two to reach the page, so the phone
# that sent it draws it into the list straight away, marked "Adding",
# and remembers it (localStorage, this phone only). Once the page loads
# with the real one on it, the phone forgets its copy. If the real one
# never shows up, the copy goes away after PENDING_LIFE.
PRAYER_FORM_JS = r"""
(function () {
  var box = document.getElementById('pr-add');
  var root = document.getElementById('pr-list');
  if (!box || !root) return;
  var token = box.getAttribute('data-t').split('').reverse().join('');
  var url = 'https://api.github.com/repos/' + box.getAttribute('data-repo') +
            '/actions/workflows/prayer.yml/dispatches';
  var branch = box.getAttribute('data-branch') || 'main';
  var form = document.getElementById('pr-form');
  var open = document.getElementById('pr-add-open');
  var send = document.getElementById('pr-send');
  var status = document.getElementById('pr-status');
  var text = document.getElementById('pr-f-text');
  var name = document.getElementById('pr-f-name');

  var PENDING = 'gh-prayer-pending', PENDING_LIFE = 20 * 60 * 1000;
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function iso(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function fromIso(s) { var p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  // One month after the date, like prayer.py's _ends.
  function ends(d) {
    var y = d.getFullYear(), m = d.getMonth() + 1;
    return new Date(y, m, Math.min(d.getDate(), new Date(y, m + 1, 0).getDate()));
  }

  // The same tidy-up the Action does (prayer.py request_line), so the
  // copy shown here matches what lands on the list.
  function tidy(s, max) {
    return String(s || '').replace(/[\u0000-\u001f\u007f]/g, ' ')
      .replace(/\s+/g, ' ').trim().slice(0, max).trim();
  }
  function cleanText(s) { return tidy(s, __MAX_TEXT__).replace(/^[\s+#\u2713\u2714]+/, '').trim(); }
  function cleanName(s) { return tidy(s, __MAX_NAME__).replace(/[()]/g, '').trim(); }
  // For spotting the real request on the page: letters and numbers only.
  function norm(s) { return String(s).toLowerCase().replace(/[^0-9a-z\u00c0-\u024f]+/g, ''); }

  function loadPending() { try { return JSON.parse(localStorage.getItem(PENDING)) || []; } catch (e) { return []; } }
  function savePending(list) { try { localStorage.setItem(PENDING, JSON.stringify(list)); } catch (e) {} }

  // How many real (built) requests on that day read the same.
  function matches(p) {
    var sec = root.querySelector('.pr-day[data-date="' + p.date + '"]:not(.pr-made)');
    if (!sec) return 0;
    var reqs = sec.querySelectorAll('.pr-item .pr-req'), n = 0;
    for (var i = 0; i < reqs.length; i++) if (norm(reqs[i].textContent) === norm(p.text)) n++;
    return n;
  }

  // A day heading for a date the page doesn't have yet, put in date
  // order (newest first).
  function makeDay(date) {
    var d = fromIso(date), end = ends(d), last = new Date(end);
    last.setDate(last.getDate() - 1);
    var sec = document.createElement('section');
    sec.className = 'pr-day pr-made';
    sec.setAttribute('data-date', date);
    sec.setAttribute('data-expires', iso(end));
    sec.innerHTML = '<div class="pr-head"><h2 class="pr-date"></h2>' +
      '<span class="count-tag pr-new" hidden>New</span><span class="pr-thru"></span></div>';
    sec.querySelector('.pr-date').textContent = DAYS[d.getDay()] + ' ' + MON[d.getMonth()] + ' ' + d.getDate();
    sec.querySelector('.pr-thru').textContent = 'through ' + MON[last.getMonth()] + ' ' + last.getDate();
    var days = root.querySelectorAll('.pr-day'), before = null;
    for (var i = 0; i < days.length; i++) {
      if (days[i].getAttribute('data-date') < date) { before = days[i]; break; }
    }
    root.insertBefore(sec, before || document.getElementById('pr-answered') || document.getElementById('pr-none'));
    return sec;
  }

  function makeItem(p) {
    var el = document.createElement('div');
    el.className = 'pr-pending';
    el.setAttribute('data-pending', p.id);
    el.innerHTML = '<span class="pr-check pr-wait" aria-hidden="true"></span>' +
      '<span class="pr-text"><span class="pr-req"></span><span class="pr-who"></span>' +
      '<span class="pr-adding">Adding. Only you can see this until the list updates.</span></span>';
    el.querySelector('.pr-req').textContent = p.text;
    var who = el.querySelector('.pr-who');
    if (p.name) who.textContent = 'asked by ' + p.name;
    else who.parentNode.removeChild(who);
    return el;
  }

  // Draw this phone's waiting requests into the list. Drops any whose
  // real copy has arrived, or that have waited too long.
  function showPending() {
    var i, old = root.querySelectorAll('.pr-pending');
    for (i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    var now = Date.now(), keep = [];
    loadPending().forEach(function (p) {
      if (!p || !p.text || !p.date || now - p.sent > PENDING_LIFE) return;
      if (matches(p) > (p.before || 0)) return;
      keep.push(p);
      var sec = root.querySelector('.pr-day[data-date="' + p.date + '"]') || makeDay(p.date);
      sec.appendChild(makeItem(p));
    });
    var made = root.querySelectorAll('.pr-made');
    for (i = 0; i < made.length; i++) {
      if (!made[i].querySelector('.pr-pending')) made[i].parentNode.removeChild(made[i]);
    }
    savePending(keep);
    var ev;
    try { ev = new Event('pr-changed'); } catch (e) { ev = document.createEvent('Event'); ev.initEvent('pr-changed', false, false); }
    root.dispatchEvent(ev);
  }

  function show(on) {
    form.hidden = !on;
    open.hidden = on;
    open.setAttribute('aria-expanded', String(on));
    if (on) { status.textContent = ''; text.focus(); }
  }
  open.onclick = function () { show(true); };
  document.getElementById('pr-cancel').onclick = function () { show(false); open.focus(); };

  form.onsubmit = function (e) {
    e.preventDefault();
    var p = { id: String(Date.now()), text: cleanText(text.value), name: cleanName(name.value),
              date: iso(new Date()), sent: Date.now() };
    if (!p.text) { text.focus(); return; }
    send.disabled = true;
    send.textContent = 'Adding\u2026';
    status.textContent = '';
    fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        ref: branch,
        inputs: { text: text.value, name: name.value, date: p.date }
      })
    }).then(function (r) {
      if (r.ok) return;
      // Keep GitHub's reason ("Not Found", "Bad credentials"...) so the
      // message says what went wrong.
      return r.json().catch(function () { return {}; }).then(function (j) {
        var err = new Error((j && j.message) || '');
        err.status = r.status;
        throw err;
      });
    }).then(function () {
      text.value = '';            // the name stays, for the next one
      show(false);
      p.before = matches(p);      // same words already on that day (rare)
      var list = loadPending();
      list.push(p);
      savePending(list);
      showPending();
      status.textContent = 'Added. Everyone else will see it in a couple of minutes.';
      var el = root.querySelector('[data-pending="' + p.id + '"]');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }).catch(function (err) {
      status.textContent = (err && err.status)
        ? 'That didn\u2019t go through. GitHub said: ' + err.status +
          (err.message ? ' ' + err.message : '') +
          '. Please let whoever looks after the site know.'
        : 'That didn\u2019t go through. Check your connection and tap Add request again.';
    }).then(function () {
      send.disabled = false;
      send.textContent = 'Add request';
    });
  };

  showPending();
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
.pr-done + .pr-done,
.pr-item + .pr-pending,
.pr-pending + .pr-pending { border-top: 1.5px dashed rgba(10, 10, 10, 0.35); }
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

/* A request this phone just sent, shown until the real one arrives.
   Same shape as a request, with a slowly turning dashed circle. */
.pr-pending {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 2px;
}
.pr-check.pr-wait {
  border-style: dashed;
  border-color: #f01a8b;
  animation: pr-turn 4s linear infinite;
}
@keyframes pr-turn { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .pr-check.pr-wait { animation: none; }
}
.pr-adding {
  display: block;
  margin-top: 6px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.5;
  opacity: 0.6;
}

.pr-day[hidden], .pr-answered[hidden], .pr-done[hidden], .pr-new[hidden] {
  display: none !important;
}

/* ── Add a request ─────────────────────────────────────────
   Same chunky bordered look as the front page buttons. The
   button swaps for the form when tapped. */
.pr-add { margin-top: 22px; }
.pr-add [hidden] { display: none !important; }
.pr-add-open {
  -webkit-appearance: none;
  appearance: none;
  display: block;
  width: 100%;
  margin: 0;
  padding: 12px 16px 13px 18px;
  background: #f2ede4;
  border: 3px solid #0a0a0a;
  border-radius: 0;
  box-shadow: 5px 5px 0 #0a0a0a;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 28px;
  line-height: 0.95;
  text-transform: uppercase;
  text-align: left;
  color: #0a0a0a;
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.08s, box-shadow 0.08s;
  position: relative;       /* keeps its shadow above the status line's halo */
  z-index: 1;
}
.pr-add-open:active {
  transform: translate(3px, 3px);
  box-shadow: 2px 2px 0 #0a0a0a;
  background: #f01a8b;
}
@media (hover: hover) {
  .pr-add-open:hover { background: #f01a8b; }
}
.pr-add-open:focus-visible { outline: 3px solid #f01a8b; outline-offset: 4px; }

.pr-form {
  margin: 0;
  padding: 16px 16px 18px;
  background: #f2ede4;
  border: 3px solid #0a0a0a;
  box-shadow: 5px 5px 0 #0a0a0a;
  position: relative;
  z-index: 1;
}
.pr-label {
  display: block;
  margin: 0 0 6px;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 18px;
  line-height: 1.1;
  text-transform: uppercase;
}
.pr-label span {
  display: block;
  margin-top: 2px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-weight: 400;
  font-size: 11px;
  text-transform: none;
  opacity: 0.65;
}
.pr-form textarea,
.pr-form input[type="text"] {
  -webkit-appearance: none;
  appearance: none;
  display: block;
  width: 100%;
  margin: 0 0 16px;
  padding: 10px 12px;
  background: #fffdf8;
  border: 2px solid #0a0a0a;
  border-radius: 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 16px;          /* 16px or more keeps iPhones from zooming in */
  line-height: 1.45;
  color: #0a0a0a;
}
.pr-form textarea { min-height: 88px; resize: vertical; }
.pr-form textarea:focus,
.pr-form input[type="text"]:focus {
  outline: none;
  border-color: #f01a8b;
  box-shadow: 0 0 0 2px #f01a8b;
}
.pr-form-note {
  margin: -6px 0 14px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.5;
  opacity: 0.65;
}
.pr-form-row { display: flex; gap: 10px; }
.pr-send,
.pr-cancel {
  -webkit-appearance: none;
  appearance: none;
  height: 42px;
  padding: 0 16px;
  border: 2px solid #0a0a0a;
  border-radius: 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 13px;
  letter-spacing: 1px;
  text-transform: uppercase;
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.pr-send { flex: 1; background: #0a0a0a; color: #f2ede4; }
.pr-send:disabled { opacity: 0.6; cursor: default; }
.pr-cancel { background: transparent; color: #0a0a0a; }
.pr-send:active, .pr-cancel:active { transform: translateY(1px); }
.pr-send:focus-visible, .pr-cancel:focus-visible { outline: 3px solid #f01a8b; outline-offset: 2px; }
.pr-status {
  margin: 18px 0 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #f01a8b;
}
.pr-status:empty { display: none; }

/* The check circle, the add button and the form have their own
   backgrounds, so no beige halo (see the NO HALO note in server.py's
   CSS). The status line sits on the paper, so it keeps its halo. */
.pr-check,
.pr-add-open,
.pr-form, .pr-form * {
  -webkit-text-stroke-width: 0 !important;
  -webkit-text-stroke-color: transparent !important;
  paint-order: normal !important;
}
"""


if __name__ == "__main__":
    if sys.argv[1:] == ["add"]:
        sys.exit(add_request_from_env())
    print("Usage: python3 prayer.py add   (reads PR_TEXT, PR_NAME, PR_DATE)")
    sys.exit(2)
