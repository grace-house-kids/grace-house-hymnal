"""The hidden "Add a letter" form on the Letters page.

A maintainer tool, like removing prayer requests: long-press the
8-spoke wheel in the logo on /{key}/letters/ and a form opens above
the list. Long-press again (or Cancel) to put it away. Sending starts
the "Add letter" GitHub Action (.github/workflows/letters.yml), which
runs "python3 letterform.py add" to put the letter into letters.txt,
saves it, and rebuilds the site. It's on the page a minute or two
later. The phone that sent it shows it at the top of the list right
away, marked "adding…", until the real one arrives.

Uses the same PRAYER_TOKEN secret as the other forms. Without it (like
on your own computer) the long-press does nothing. It isn't advertised
on the page, so it's only hidden, not locked — but every letter is an
ordinary git commit, so one that shouldn't be there can be taken out of
letters.txt or brought back from the repo's history.

New letters go at the TOP of letters.txt (newest first), under the #
notes up there, written the way letters.py expects:

    List title
    Page heading               <- the list title again if left blank
    [Date: October 2026]       <- only if a date was typed

    The letter...

    ---

Anything typed that letters.txt would misread is quietly defused: a
line of dashes would split the letter in two, so it becomes spaced em
dashes (— — —); a line starting with # would vanish, so that # becomes
a look-alike (＃); a [Date: ...] line at the very top of the letter
would be taken as its date, so its brackets become parentheses.

While a letter is being typed it's kept on that phone as a draft, so a
dropped connection or a closed tab doesn't lose it. The draft is
cleared once the letter is sent.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from html import escape

MAX_TITLE = 100
MAX_DATE = 40
MAX_BODY = 20000     # characters of letter (GitHub caps a dispatch at 65,535)
MAX_LINES = 800      # lines of letter
MAX_LINE = 2000      # characters in one line (a whole paragraph can be one line)
BRANCH = "main"
BREAK = "---"

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# Line breaks that Python's splitlines() honors but a plain "\n" split
# doesn't. Left in, they'd sneak extra lines into letters.txt.
_ODD_BREAKS = re.compile(r"[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")


# ─────────────────────────────────────────────────────────────
# Writing a letter into letters.txt (run by the "Add letter" Action)

def _one(value, limit: int) -> str:
    """One line: control characters and runs of spaces squashed."""
    s = _ODD_BREAKS.sub(" ", str(value or ""))
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:limit].strip()


def _defuse(line: str) -> str:
    """A line made sure it reads as a line of the letter."""
    from letters import SEPARATOR_RE
    if SEPARATOR_RE.match(line):
        # letters.py splits on runs of dashes (em dashes too), so space
        # them out: --- -> — — —, which reads the same.
        return " ".join("—" * min(len(line.strip()), 7))
    if line.lstrip().startswith("#"):
        line = line.replace("#", "＃", 1)              # a look-alike, so it isn't a note
    return line


def letter_body(value) -> list[str]:
    """The letter's lines: paragraphs split by single blank lines,
    trailing spaces trimmed, blank lines at the start and end dropped,
    runs of blank lines squashed to one."""
    from letters import DATE_RE
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _ODD_BREAKS.sub("\n", text).expandtabs(4)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    out, gap, total = [], False, 0
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            gap = bool(out)
            continue
        if gap:
            out.append("")
            gap = False
        line = _defuse(line[:MAX_LINE].rstrip())
        if not out and DATE_RE.match(line):
            line = line.replace("[", "(").replace("]", ")")
        out.append(line)
        total += len(line)
        if total >= MAX_BODY or len(out) >= MAX_LINES:
            break
    return out


def letter_lines(data: dict) -> list[str] | None:
    """The letter as letters.txt lines, or None if the title or the
    letter itself is missing. Both title lines are always written:
    letters.py reads the second non-blank line as the page heading."""
    title = _defuse(_one(data.get("title"), MAX_TITLE))
    body = letter_body(data.get("body"))
    if not title or not body:
        return None
    heading = _defuse(_one(data.get("heading"), MAX_TITLE)) or title
    lines = [title, heading]
    date = _one(data.get("date"), MAX_DATE).replace("[", "(").replace("]", ")")
    if date:
        lines.append(f"[Date: {date}]")
    return lines + [""] + body


def insert_letter(current: str, lines: list[str]) -> str:
    """letters.txt with the letter added at the top, under any # notes,
    with a --- line between it and the next letter."""
    from letters import SEPARATOR_RE
    text = current.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").rstrip()
    if not text.strip():
        return "\n".join(lines) + "\n"
    all_lines = text.split("\n")
    i = 0
    while i < len(all_lines) and (not all_lines[i].strip() or all_lines[i].lstrip().startswith("#")):
        i += 1
    head, rest = all_lines[:i], all_lines[i:]
    if not rest:                     # only # notes so far
        gap = [""] if head and head[-1].strip() else []
        return "\n".join(head + gap + lines) + "\n"
    sep = [""] if SEPARATOR_RE.match(rest[0]) else ["", BREAK, ""]
    return "\n".join(head + lines + sep + rest).rstrip() + "\n"


def add_letter_from_env() -> int:
    """"python3 letterform.py add": adds the letter in LT_LETTER (the
    form's boxes, as JSON) to the top of letters.txt."""
    from letters import LETTERS_PATH
    try:
        data = json.loads(os.environ.get("LT_LETTER") or "")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        print("::error::The letter didn't come through. Nothing added.")
        return 1
    lines = letter_lines(data)
    if lines is None:
        print("::error::The letter needs a title and some words. Nothing added.")
        return 1
    current = LETTERS_PATH.read_text(encoding="utf-8-sig") if LETTERS_PATH.exists() else ""
    LETTERS_PATH.write_text(insert_letter(current, lines), encoding="utf-8")
    print(f"Added a letter: {lines[0]}")
    return 0


# ─────────────────────────────────────────────────────────────
# The form

def _token() -> str:
    return os.environ.get("PRAYER_TOKEN", "").strip()


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "grace-house-kids/grace-house-hymnal")


def render_letter_form() -> str:
    """The hidden form, its styles and script. Empty when there's no
    token. Borrows the prayer form's look (the pr- classes in prayer.py's
    CSS, which is on every page)."""
    if not _token():
        return ""
    js = (LETTERFORM_JS.replace("__MAX_TITLE__", str(MAX_TITLE))
                       .replace("__MONTHS__", json.dumps(MONTHS)))
    return (
        f"<style>{LETTERFORM_CSS}</style>\n"
        f'<div class="pr-add lf-add" id="lf-add" hidden data-repo="{escape(_repo())}" '
        f'data-branch="{escape(BRANCH)}" data-t="{escape(_token()[::-1])}">'
        '<div class="pr-admin-bar lf-bar">'
        '<span class="pr-admin-tag">New letter</span>'
        '<span class="pr-admin-say">Goes at the top of the list. '
        'Long-press the wheel again to put this away.</span>'
        '</div>'
        '<form class="pr-form" id="lf-form">'
        '<label class="pr-label" for="lf-title">Title '
        '<span>How it shows in the list.</span></label>'
        f'<input id="lf-title" type="text" maxlength="{MAX_TITLE}" required autocapitalize="words">'
        '<label class="pr-label" for="lf-heading">Page heading '
        '<span>Optional. Leave blank to use the title.</span></label>'
        f'<input id="lf-heading" type="text" maxlength="{MAX_TITLE}" autocapitalize="words">'
        '<label class="pr-label" for="lf-date">Date <span>Optional, any words you like.</span></label>'
        f'<input id="lf-date" type="text" maxlength="{MAX_DATE}">'
        '<label class="pr-label" for="lf-body">The letter '
        '<span>A blank line starts a new paragraph. &ldquo;- &rdquo; makes a bullet, '
        '&ldquo;&gt; &rdquo; an indented quote.</span></label>'
        f'<textarea id="lf-body" class="lf-body" rows="14" maxlength="{MAX_BODY}" required '
        'autocapitalize="sentences" spellcheck="true"></textarea>'
        '<p class="pr-form-note">It goes on the Letters page in a couple of minutes, '
        'where anyone with the site link can read it.</p>'
        '<div class="pr-form-row">'
        '<button type="submit" class="pr-send" id="lf-send">Add letter</button>'
        '<button type="button" class="pr-cancel" id="lf-cancel">Cancel</button>'
        '</div>'
        '</form>'
        '</div>'
        '<p class="pr-status lf-status" id="lf-status" role="status" aria-live="polite"></p>\n'
        f"<script>{js}</script>"
    )


# Long-press the wheel to open/close the form (same hold as the prayer
# list's Edit mode). Sending starts the "Add letter" Action, then shows
# the letter at the top of the list on this phone, marked "adding…",
# until the page loads with the real one. Gives up on it after 20
# minutes.
LETTERFORM_JS = r"""
(function () {
  var box = document.getElementById('lf-add');
  var wheel = document.querySelector('.brand svg[aria-label="wheel"]');
  if (!box || !wheel) return;
  var token = box.getAttribute('data-t').split('').reverse().join('');
  var url = 'https://api.github.com/repos/' + box.getAttribute('data-repo') +
            '/actions/workflows/letters.yml/dispatches';
  var branch = box.getAttribute('data-branch') || 'main';
  function $(id) { return document.getElementById(id); }
  var form = $('lf-form'), send = $('lf-send'), status = $('lf-status');
  var fTitle = $('lf-title'), fHead = $('lf-heading'), fDate = $('lf-date'), fBody = $('lf-body');
  var MONTHS = __MONTHS__;
  var PENDING = 'gh-letter-pending', PENDING_LIFE = 20 * 60 * 1000;
  var DRAFT = 'gh-letter-draft';

  function load(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } }
  function store(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function drop(k) { try { localStorage.removeItem(k); } catch (e) {} }
  function line(s, max) {
    return String(s || '').replace(/[\u0000-\u001f\u007f\u0085\u2028\u2029]/g, ' ')
      .replace(/\s+/g, ' ').trim().slice(0, max).trim();
  }
  function norm(s) { return String(s).toLowerCase().replace(/[^0-9a-z\u00c0-\u024f]+/g, ''); }

  /* ── Draft: kept on this phone while typing ─────────────── */
  var draftTimer = 0;
  function saveDraft() {
    clearTimeout(draftTimer);
    draftTimer = setTimeout(function () {
      if (fTitle.value || fBody.value)
        store(DRAFT, { title: fTitle.value, heading: fHead.value, date: fDate.value, body: fBody.value });
      else drop(DRAFT);
    }, 500);
  }
  [fTitle, fHead, fDate, fBody].forEach(function (el) { el.addEventListener('input', saveDraft); });
  var d = load(DRAFT);
  if (d) {
    fTitle.value = d.title || ''; fHead.value = d.heading || '';
    fDate.value = d.date || ''; fBody.value = d.body || '';
  }

  /* ── Letters this phone sent, until the real ones arrive ── */
  // The form sits above the list, so this script runs before the list
  // exists: look it up each time instead of once.
  function letterList() { return document.querySelector('ul.letter-list'); }
  function realCount(title) {
    var n = 0, names = document.querySelectorAll('ul.letter-list li:not(.lf-pending) .letter-name');
    for (var i = 0; i < names.length; i++) if (norm(names[i].textContent) === norm(title)) n++;
    return n;
  }
  function recount() {
    var tag = document.querySelector('.meta-strip .count-tag'), list = letterList();
    if (!tag || !list) return;
    var n = list.querySelectorAll('li').length;
    tag.textContent = n + (n === 1 ? ' letter' : ' letters');
  }
  function showPending() {
    var list = letterList();
    if (!list) return;
    var old = list.querySelectorAll('li.lf-pending');
    for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    var now = Date.now(), keep = [];
    (load(PENDING) || []).forEach(function (p) {   // oldest first; each lands on top
      if (!p || !p.title || now - p.sent > PENDING_LIFE) return;
      if (realCount(p.title) > (p.before || 0)) return;      // the real one is here
      keep.push(p);
      var li = document.createElement('li');
      li.className = 'lf-pending';
      li.innerHTML = '<span class="lf-row"><span class="letter-mark" aria-hidden="true">&#10022;</span>' +
                     '<span class="letter-name"></span><span class="letter-date">adding…</span></span>';
      li.querySelector('.letter-name').textContent = p.title;
      list.insertBefore(li, list.firstChild);
    });
    store(PENDING, keep);
    recount();
  }

  /* ── Open / close ───────────────────────────────────────── */
  function thisMonth() { var t = new Date(); return MONTHS[t.getMonth()] + ' ' + t.getFullYear(); }
  function setOpen(on) {
    box.hidden = !on;
    if (on) {
      status.textContent = '';
      if (!fDate.value) fDate.value = thisMonth();
      if (box.scrollIntoView) box.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  }
  $('lf-cancel').onclick = function () { setOpen(false); };

  form.onsubmit = function (e) {
    e.preventDefault();
    var title = line(fTitle.value, __MAX_TITLE__);
    if (!title) { fTitle.focus(); return; }
    if (!fBody.value.trim()) { fBody.focus(); return; }
    send.disabled = true;
    send.textContent = 'Adding…';
    status.textContent = '';
    var letter = { title: fTitle.value, heading: fHead.value, date: fDate.value, body: fBody.value };
    fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ref: branch, inputs: { letter: JSON.stringify(letter) } })
    }).then(function (r) {
      if (r.ok) return;
      return r.json().catch(function () { return {}; }).then(function (j) {
        var err = new Error((j && j.message) || '');
        err.status = r.status;
        throw err;
      });
    }).then(function () {
      var pending = load(PENDING) || [];
      pending.push({ title: title, sent: Date.now(), before: realCount(title) });
      store(PENDING, pending);
      fTitle.value = ''; fHead.value = ''; fDate.value = ''; fBody.value = '';
      clearTimeout(draftTimer);
      drop(DRAFT);
      setOpen(false);
      showPending();
      status.textContent = 'Added. Everyone will see it in a couple of minutes.';
    }).catch(function (err) {
      // The boxes keep what was typed (and the draft is saved), so
      // nothing is lost — just tap Add letter again.
      status.textContent = (err && err.status)
        ? 'That didn’t go through. GitHub said: ' + err.status +
          (err.message ? ' ' + err.message : '') + '. Your letter is still here; try again.'
        : 'That didn’t go through. Check your connection and tap Add letter again.';
    }).then(function () {
      send.disabled = false;
      send.textContent = 'Add letter';
    });
  };

  /* ── Long-press the wheel to open / close ───────────────── */
  var timer = null, sx = 0, sy = 0, HOLD = 550, MOVE = 10;
  function clearHold() { if (timer) { clearTimeout(timer); timer = null; } }
  function startHold(x, y) {
    sx = x; sy = y; clearHold();
    timer = setTimeout(function () { timer = null; setOpen(box.hidden); }, HOLD);
  }
  function moveHold(x, y) {
    if (timer && (Math.abs(x - sx) > MOVE || Math.abs(y - sy) > MOVE)) clearHold();
  }
  wheel.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  if (window.PointerEvent) {
    wheel.addEventListener('pointerdown', function (e) { startHold(e.clientX, e.clientY); });
    wheel.addEventListener('pointermove', function (e) { moveHold(e.clientX, e.clientY); });
    wheel.addEventListener('pointerup', clearHold);
    wheel.addEventListener('pointercancel', clearHold);
    wheel.addEventListener('pointerleave', clearHold);
  } else {
    wheel.addEventListener('touchstart', function (e) {
      var t = e.touches && e.touches[0]; if (t) startHold(t.clientX, t.clientY);
    }, { passive: true });
    wheel.addEventListener('touchmove', function (e) {
      var t = e.touches && e.touches[0]; if (t) moveHold(t.clientX, t.clientY);
    }, { passive: true });
    wheel.addEventListener('touchend', clearHold);
    wheel.addEventListener('touchcancel', clearHold);
    wheel.addEventListener('mousedown', function (e) { startHold(e.clientX, e.clientY); });
    wheel.addEventListener('mousemove', function (e) { moveHold(e.clientX, e.clientY); });
    wheel.addEventListener('mouseup', clearHold);
    wheel.addEventListener('mouseleave', clearHold);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showPending);
  else showPending();
})();
"""


# Only what the prayer form's styles (prayer.py) don't already cover.
LETTERFORM_CSS = r"""
.lf-add[hidden] { display: none !important; }
.lf-bar { margin: 0 0 14px; }
.pr-form textarea.lf-body { min-height: 300px; line-height: 1.6; }
.lf-status { margin-top: 14px; }
/* A letter this phone just sent, until the real one arrives. */
ul.letter-list li.lf-pending { border-left: 3px dashed #f01a8b; }
ul.letter-list .lf-row {
  display: flex; align-items: baseline; gap: 14px;
  padding: 12px 6px; opacity: 0.7;
}
"""


if __name__ == "__main__":
    if sys.argv[1:] == ["add"]:
        sys.exit(add_letter_from_env())
    print("Usage: python3 letterform.py add   (reads LT_LETTER)")
    sys.exit(2)
