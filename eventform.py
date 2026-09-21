"""The "Add an event" form on the Events page.

Works like the prayer list's "Add a request" form. When the
PRAYER_TOKEN repository secret is set (the same token the prayer form
uses), the Events page gets an "+ Add an event" button. It starts the
"Add event" GitHub Action (.github/workflows/events.yml), which runs
"python3 eventform.py add" to put the event into events.txt, saves it,
and rebuilds the site. It's on the page a minute or two later. The
phone that sent it shows it right away, marked "Adding", until the
real one arrives. Without the secret (like on your own computer),
there's no button.

What the form writes into events.txt, in date order:

    September 27 2026          <- the date
    Fall potluck               <- what's happening (the big heading)
    12 PM                      <- the time, if they gave one
    Bring a dish to share.     <- details, if any ("- " lines = bullets)

server.py needs two lines for this (see the note in its events part):
    from eventform import render_event_form
and render_event_form() in render_events_page's body.
"""
from __future__ import annotations

import datetime
import os
import re
import sys
from html import escape
from pathlib import Path

EVENTS_PATH = Path(__file__).resolve().parent / "events.txt"

MAX_TITLE = 80        # longest event name, in characters
MAX_DETAILS = 600     # most characters of details
MAX_LINES = 12        # most lines of details
MAX_AHEAD_DAYS = 3 * 366   # furthest ahead an event can be added
BRANCH = "main"

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


# ─────────────────────────────────────────────────────────────
# Adding an event (run by the "Add event" GitHub Action)

def _clean_line(value, limit: int) -> str:
    s = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit].strip()


def clean_title(value) -> str:
    # A leading # would hide it, and - or * would make it a bullet.
    return re.sub(r"^[\s#*\-–—•]+", "", _clean_line(value, MAX_TITLE)).strip()


def clean_details(value) -> list[str]:
    """Detail lines: blank lines dropped (a blank line would end the
    event), # at the start removed (it would hide the line)."""
    out, total = [], 0
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    for raw in text.split("\n"):
        line = re.sub(r"^#+\s*", "", _clean_line(raw, MAX_DETAILS)).strip()
        if not line:
            continue
        line = line[:MAX_DETAILS - total].strip()
        if line:
            out.append(line)
            total += len(line)
        if total >= MAX_DETAILS or len(out) >= MAX_LINES:
            break
    return out


def time_label(value) -> str:
    """"19:30" -> "7:30 PM", "12:00" -> "12 PM". Empty if not a time."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?", str(value or "").strip())
    if not m:
        return ""
    h, mi = int(m[1]), int(m[2])
    if h > 23 or mi > 59:
        return ""
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12} {suffix}" if mi == 0 else f"{h12}:{mi:02d} {suffix}"


def event_date(value, today: datetime.date) -> datetime.date | None:
    """The date from the form (2026-09-27), if it's usable: not already
    past (a day of leeway, since GitHub's clock is on UTC) and not more
    than about three years ahead."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(value or "").strip())
    if not m:
        return None
    try:
        d = datetime.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
    if d < today - datetime.timedelta(days=1):
        return None
    if d > today + datetime.timedelta(days=MAX_AHEAD_DAYS):
        return None
    return d


def date_line(d: datetime.date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day} {d.year}"


def insert_event(current: str, when: datetime.date, block: list[str], read_date=None) -> str:
    """events.txt with the event added, in date order: just before the
    first event that's later (after any others on the same day). Without
    read_date, it goes at the end. Only ever lands just above a line
    that starts an event, so it can't split an event from its details."""
    text = current.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").rstrip()
    if not text.strip():
        return "\n".join(block) + "\n"
    lines = text.split("\n")
    at = None
    if read_date is not None:
        after_blank = True
        for j, ln in enumerate(lines):
            s = ln.strip()
            if s.startswith("#"):
                continue              # comments don't count either way
            if not s:
                after_blank = True
                continue
            if after_blank:
                try:
                    d = read_date(s)
                except Exception:
                    d = None
                if d is not None and d > when:
                    at = j
                    break
            after_blank = False
    if at is None:
        return text + "\n\n" + "\n".join(block) + "\n"
    # Keep a # note that sits right on top of an event with that event.
    k = at
    while k > 0 and lines[k - 1].strip().startswith("#"):
        k -= 1
    lines[k:k] = block + [""]
    return "\n".join(lines).rstrip() + "\n"


def add_event_from_env(path: Path = EVENTS_PATH) -> int:
    """"python3 eventform.py add": adds the event in EV_DATE / EV_TIME /
    EV_TITLE / EV_DETAILS to events.txt."""
    today = datetime.datetime.now(datetime.timezone.utc).date()
    when = event_date(os.environ.get("EV_DATE"), today)
    title = clean_title(os.environ.get("EV_TITLE"))
    if when is None:
        print("::error::The date is missing, already past, or too far ahead. Nothing added.")
        return 1
    if not title:
        print("::error::The event needs a name. Nothing added.")
        return 1
    block = [date_line(when), title]
    t = time_label(os.environ.get("EV_TIME"))
    if t:
        block.append(t)
    block += clean_details(os.environ.get("EV_DETAILS"))
    try:   # read dates exactly the way the events page does
        from server import parse_event_date as read_date
    except Exception:
        read_date = None   # still works; the event just goes at the end
    current = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    path.write_text(insert_event(current, when, block, read_date), encoding="utf-8")
    print(f"Added an event on {date_line(when)}.")
    return 0


# ─────────────────────────────────────────────────────────────
# The form

def _token() -> str:
    return os.environ.get("PRAYER_TOKEN", "").strip()


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "grace-house-kids/grace-house-hymnal")


def render_event_form() -> str:
    """The "+ Add an event" button, its form, styles and script. Empty
    when there's no token. Borrows the prayer form's look (the pr-
    classes in prayer.py's CSS) so the two match."""
    if not _token():
        return ""
    js = (EVENTFORM_JS.replace("__MAX_TITLE__", str(MAX_TITLE))
                      .replace("__MAX_DETAILS__", str(MAX_DETAILS))
                      .replace("__MAX_LINES__", str(MAX_LINES)))
    return (
        f"<style>{EVENTFORM_CSS}</style>\n"
        f'<div class="pr-add" id="ef-add" data-repo="{escape(_repo())}" '
        f'data-branch="{escape(BRANCH)}" data-t="{escape(_token()[::-1])}">'
        '<button type="button" class="pr-add-open" id="ef-open" '
        'aria-expanded="false" aria-controls="ef-form">+ Add an event</button>'
        '<form class="pr-form" id="ef-form" hidden>'
        '<div class="ef-when">'
        '<div><label class="pr-label" for="ef-date">Date</label>'
        '<input id="ef-date" name="date" type="date" required></div>'
        '<div><label class="pr-label" for="ef-time">Time <span>optional</span></label>'
        '<input id="ef-time" name="time" type="time"></div>'
        "</div>"
        '<label class="pr-label" for="ef-title">What\'s happening?</label>'
        f'<input id="ef-title" name="title" type="text" maxlength="{MAX_TITLE}" required '
        'autocapitalize="sentences">'
        '<label class="pr-label" for="ef-details">Details '
        "<span>optional. Where, what to bring. Start a line with - for a bullet.</span></label>"
        f'<textarea id="ef-details" name="details" rows="4" maxlength="{MAX_DETAILS}"></textarea>'
        '<p class="pr-form-note">It goes on the calendar in a couple of minutes, '
        "where anyone with the site link can see it.</p>"
        '<div class="pr-form-row">'
        '<button type="submit" class="pr-send" id="ef-send">Add event</button>'
        '<button type="button" class="pr-cancel" id="ef-cancel">Cancel</button>'
        "</div>"
        "</form>"
        '<p class="pr-status" id="ef-status" role="status" aria-live="polite"></p>'
        "</div>\n"
        f"<script>{js}</script>"
    )


# Starts the "Add event" Action, then shows the event on this phone
# straight away (list + calendar circle), marked "Adding", until the
# page loads with the real one. Gives up on it after 20 minutes. It
# waits for the page to finish loading, so the events script has
# already drawn the calendar and hidden past days.
EVENTFORM_JS = r"""
(function () {
  var box = document.getElementById('ef-add');
  if (!box) return;
  var token = box.getAttribute('data-t').split('').reverse().join('');
  var url = 'https://api.github.com/repos/' + box.getAttribute('data-repo') +
            '/actions/workflows/events.yml/dispatches';
  var branch = box.getAttribute('data-branch') || 'main';
  var form = document.getElementById('ef-form');
  var open = document.getElementById('ef-open');
  var send = document.getElementById('ef-send');
  var status = document.getElementById('ef-status');
  var fDate = document.getElementById('ef-date');
  var fTime = document.getElementById('ef-time');
  var fTitle = document.getElementById('ef-title');
  var fDetails = document.getElementById('ef-details');

  var PENDING = 'gh-event-pending', PENDING_LIFE = 20 * 60 * 1000;
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function iso(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function fromIso(s) { var p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function ordinal(n) {
    var s = ['th', 'st', 'nd', 'rd'], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }
  // "Sunday September 27th 2026", like server.py's event_date_label.
  function dayLabel(date) {
    var d = fromIso(date);
    return DAYS[d.getDay()] + ' ' + MONTHS[d.getMonth()] + ' ' + ordinal(d.getDate()) + ' ' + d.getFullYear();
  }

  // The same tidy-up the Action does (eventform.py), so the copy shown
  // here matches what lands on the calendar.
  function line(s, max) {
    return String(s || '').replace(/[\u0000-\u001f\u007f]/g, ' ')
      .replace(/\s+/g, ' ').trim().slice(0, max).trim();
  }
  function cleanTitle(s) { return line(s, __MAX_TITLE__).replace(/^[\s#*\-\u2013\u2014\u2022]+/, '').trim(); }
  function cleanDetails(s) {
    var out = [], total = 0, raw = String(s || '').replace(/\r\n?/g, '\n').split('\n');
    for (var i = 0; i < raw.length; i++) {
      var ln = line(raw[i], __MAX_DETAILS__).replace(/^#+\s*/, '').trim();
      if (!ln) continue;
      ln = ln.slice(0, __MAX_DETAILS__ - total).trim();
      if (ln) { out.push(ln); total += ln.length; }
      if (total >= __MAX_DETAILS__ || out.length >= __MAX_LINES__) break;
    }
    return out;
  }
  function timeLabel(s) {
    var m = /^(\d{1,2}):(\d{2})/.exec(String(s || ''));
    if (!m) return '';
    var h = +m[1], mi = +m[2], suffix = h < 12 ? 'AM' : 'PM', h12 = h % 12 || 12;
    return mi ? h12 + ':' + pad(mi) + ' ' + suffix : h12 + ' ' + suffix;
  }
  function norm(s) { return String(s).toLowerCase().replace(/[^0-9a-z\u00c0-\u024f]+/g, ''); }

  function loadPending() { try { return JSON.parse(localStorage.getItem(PENDING)) || []; } catch (e) { return []; } }
  function savePending(list) { try { localStorage.setItem(PENDING, JSON.stringify(list)); } catch (e) {} }

  // How many real events that day have the same name.
  function matches(p) {
    var sec = document.querySelector('.ev-day[data-date="' + p.date + '"]:not(.ef-made)');
    if (!sec) return 0;
    var names = sec.querySelectorAll('.ev-item:not(.ev-pending) > p:first-child'), n = 0;
    for (var i = 0; i < names.length; i++) if (norm(names[i].textContent) === norm(p.title)) n++;
    return n;
  }

  // A day heading the page doesn't have yet, in date order (soonest first).
  function makeDay(date) {
    var list = document.querySelector('.ev-list');
    var sec = document.createElement('section');
    sec.className = 'zine-section ev-day ef-made';
    sec.setAttribute('data-date', date);
    sec.innerHTML = '<h2 class="zine-heading"></h2><div class="zine-body"></div>';
    sec.querySelector('.zine-heading').textContent = dayLabel(date);
    var days = list.querySelectorAll('.ev-day'), before = null;
    for (var i = 0; i < days.length; i++) {
      if (days[i].getAttribute('data-date') > date) { before = days[i]; break; }
    }
    list.insertBefore(sec, before);
    return sec;
  }

  // Laid out like server.py's render_zine_body: "- " lines are bullets.
  function makeItem(p) {
    var el = document.createElement('div'), ul = null;
    el.className = 'ev-item ev-pending';
    el.setAttribute('data-pending', p.id);
    [p.title].concat(p.time ? [p.time] : [], p.details || []).forEach(function (ln) {
      var m = /^[-*] (.*)$/.exec(ln);
      if (m) {
        if (!ul) { ul = document.createElement('ul'); el.appendChild(ul); }
        var li = document.createElement('li');
        li.textContent = m[1].trim();
        ul.appendChild(li);
      } else {
        ul = null;
        var para = document.createElement('p');
        para.textContent = ln;
        el.appendChild(para);
      }
    });
    var note = document.createElement('p');
    note.className = 'ev-adding';
    note.textContent = 'Adding. Only you can see this until the calendar updates.';
    el.appendChild(note);
    return el;
  }

  // Pink circles on this month's calendar for waiting events.
  function paint(list) {
    var now = new Date(), month = now.getFullYear() + '-' + pad(now.getMonth() + 1);
    var cells = document.querySelectorAll('#cal-days .cal-day');
    list.forEach(function (p) {
      if (p.date.slice(0, 7) !== month) return;
      for (var i = 0; i < cells.length; i++) {
        var span = cells[i].querySelector('span');
        if (span && +span.textContent === +p.date.slice(8)) cells[i].classList.add('event');
      }
    });
  }

  // The "N coming up" tag and the "Nothing on the calendar" line,
  // counted the way the events script counts them.
  function recount() {
    var n = 0, days = document.querySelectorAll('.ev-day[data-date]');
    for (var i = 0; i < days.length; i++) {
      if (!days[i].hidden) n += days[i].querySelectorAll('.ev-item').length;
    }
    var none = document.getElementById('ev-none'), count = document.getElementById('ev-count');
    if (none) none.hidden = n > 0;
    if (count) count.textContent = n ? n + ' coming up' : 'nothing yet';
  }

  function showPending() {
    var i, old = document.querySelectorAll('.ev-pending');
    for (i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    var now = Date.now(), today = iso(new Date()), keep = [];
    loadPending().forEach(function (p) {
      if (!p || !p.title || !p.date || p.date < today || now - p.sent > PENDING_LIFE) return;
      if (matches(p) > (p.before || 0)) return;
      keep.push(p);
      var sec = document.querySelector('.ev-day[data-date="' + p.date + '"]') || makeDay(p.date);
      sec.querySelector('.zine-body').appendChild(makeItem(p));
    });
    var made = document.querySelectorAll('.ef-made');
    for (i = 0; i < made.length; i++) {
      if (!made[i].querySelector('.ev-pending')) made[i].parentNode.removeChild(made[i]);
    }
    savePending(keep);
    paint(keep);
    recount();
  }

  function show(on) {
    form.hidden = !on;
    open.hidden = on;
    open.setAttribute('aria-expanded', String(on));
    if (on) {
      status.textContent = '';
      fDate.min = iso(new Date());
      if (!fDate.value) fDate.value = fDate.min;
      fTitle.focus();
    }
  }
  open.onclick = function () { show(true); };
  document.getElementById('ef-cancel').onclick = function () { show(false); open.focus(); };

  form.onsubmit = function (e) {
    e.preventDefault();
    var p = { id: String(Date.now()), date: fDate.value, time: timeLabel(fTime.value),
              title: cleanTitle(fTitle.value), details: cleanDetails(fDetails.value), sent: Date.now() };
    if (!/^\d{4}-\d{2}-\d{2}$/.test(p.date) || p.date < iso(new Date())) {
      status.textContent = 'Pick today or a day after it.';
      fDate.focus();
      return;
    }
    if (!p.title) { fTitle.focus(); return; }
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
        inputs: { date: p.date, time: fTime.value, title: fTitle.value, details: fDetails.value }
      })
    }).then(function (r) {
      if (r.ok) return;
      return r.json().catch(function () { return {}; }).then(function (j) {
        var err = new Error((j && j.message) || '');
        err.status = r.status;
        throw err;
      });
    }).then(function () {
      fTitle.value = ''; fTime.value = ''; fDetails.value = '';
      show(false);
      p.before = matches(p);      // same name already on that day (rare)
      var list = loadPending();
      list.push(p);
      savePending(list);
      showPending();
      status.textContent = 'Added. Everyone else will see it in a couple of minutes.';
      var el = document.querySelector('[data-pending="' + p.id + '"]');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }).catch(function (err) {
      status.textContent = (err && err.status)
        ? 'That didn\u2019t go through. GitHub said: ' + err.status +
          (err.message ? ' ' + err.message : '') +
          '. Please let whoever looks after the site know.'
        : 'That didn\u2019t go through. Check your connection and tap Add event again.';
    }).then(function () {
      send.disabled = false;
      send.textContent = 'Add event';
    });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showPending);
  else showPending();
  // The events script redraws the calendar at midnight; put circles back.
  setInterval(function () { paint(loadPending()); }, 60 * 1000);
})();
"""


# Only what the prayer form's styles (prayer.py) don't already cover.
EVENTFORM_CSS = r"""
.ef-when { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ef-when > div { min-width: 0; }
.ef-when .pr-label span { display: inline; margin: 0 0 0 4px; }
.pr-form input[type="date"],
.pr-form input[type="time"] {
  -webkit-appearance: none;
  appearance: none;
  display: block;
  width: 100%;
  min-height: 46px;         /* iPhones shrink empty date boxes otherwise */
  margin: 0 0 16px;
  padding: 10px 12px;
  background: #fffdf8;
  border: 2px solid #0a0a0a;
  border-radius: 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 16px;
  line-height: 1.45;
  color: #0a0a0a;
}
.pr-form input[type="date"]::-webkit-date-and-time-value,
.pr-form input[type="time"]::-webkit-date-and-time-value { text-align: left; }
.pr-form input[type="date"]:focus,
.pr-form input[type="time"]:focus {
  outline: none;
  border-color: #f01a8b;
  box-shadow: 0 0 0 2px #f01a8b;
}

/* An event this phone just sent, until the real one arrives. */
.ev-pending {
  border-left: 3px dashed #f01a8b;
  margin-left: -13px;
  padding-left: 10px;
}
.zine-body .ev-item.ev-pending > p.ev-adding {
  margin: 8px 0 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.5;
  letter-spacing: 0;
  text-transform: none;
  opacity: 0.6;
}
"""


if __name__ == "__main__":
    if sys.argv[1:] == ["add"]:
        sys.exit(add_event_from_env())
    print("Usage: python3 eventform.py add   (reads EV_DATE, EV_TIME, EV_TITLE, EV_DETAILS)")
    sys.exit(2)
