"""The "Add a poem" form on the Poetry page.

Works like the prayer, event and recipe forms. When the PRAYER_TOKEN
repository secret is set (the same token those forms use), the Poetry
page gets an "+ Add a poem" button. It starts the "Add poem" GitHub
Action (.github/workflows/poems.yml), which runs "python3 poemform.py
add" to put the poem into poems.txt, saves it, and rebuilds the site.
It's on the page a minute or two later. The phone that sent it shows it
right away, marked "Adding", until the real one arrives. Without the
secret (like on your own computer), there's no button.

New poems go at the TOP of poems.txt (newest first), under any # notes
up there. Set NEW_POEMS_AT_TOP to False to put them at the bottom
instead. Each poem's link is made from its title, so either way no
existing poem's link changes.

The form writes the poem in the same layout as the example at the top
of poetry.py: title, [By: ...], [Date: ...], a blank line, then the
stanzas, with a --- line between it and the next poem. Blank lines
between stanzas and spaces at the start of a line are kept as typed.

Anything typed that poems.txt would misread is quietly defused: a line
of dashes would split the poem in two, so it becomes em dashes (— — —
reads the same); a line starting with # would vanish, so that # becomes
a look-alike (＃); a line like [By: Name] inside the poem would become
the signature, so its brackets become parentheses.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from html import escape

NEW_POEMS_AT_TOP = True

MAX_TITLE = 100
MAX_BY = 40
MAX_DATE = 40
MAX_BODY = 6000      # characters of poem
MAX_LINES = 200      # lines of poem
MAX_LINE = 300       # characters in one line
BRANCH = "main"
BREAK = "---"

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# Line breaks that Python's splitlines() honors but a plain "\n" split
# doesn't. Left in, they'd sneak extra lines into poems.txt.
_ODD_BREAKS = re.compile(r"[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")


# ─────────────────────────────────────────────────────────────
# Writing a poem into poems.txt (run by the "Add poem" Action)

def _one(value, limit: int) -> str:
    """One line: control characters and runs of spaces squashed."""
    s = _ODD_BREAKS.sub(" ", str(value or ""))
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:limit].strip()


def _defuse(line: str) -> str:
    """A line of the poem, made sure it reads as a line of the poem."""
    from poetry import POEM_BREAK_RE, POEM_META_RE
    if POEM_BREAK_RE.match(line):
        return line.replace("-", "—")                  # --- -> ———
    if line.strip().startswith("#"):
        line = line.replace("#", "＃", 1)              # a look-alike, so it isn't a comment
    if POEM_META_RE.match(line):
        line = line.replace("[", "(").replace("]", ")")
    return line


def _meta(value, limit: int) -> str:
    return _one(value, limit).replace("[", "(").replace("]", ")")


def poem_body(value) -> list[str]:
    """The poem's lines: stanzas split by single blank lines, leading
    spaces kept, trailing spaces trimmed, blank lines at the start and
    end dropped, runs of blank lines squashed to one."""
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
        out.append(line)
        total += len(line)
        if total >= MAX_BODY or len(out) >= MAX_LINES:
            break
    return out


def poem_lines(data: dict) -> list[str] | None:
    """The poem as poems.txt lines, or None if the title or the poem
    itself is missing."""
    title = _defuse(_one(data.get("title"), MAX_TITLE))
    body = poem_body(data.get("body"))
    if not title or not body:
        return None
    lines = [title]
    by = _meta(data.get("by"), MAX_BY)
    date = _meta(data.get("date"), MAX_DATE)
    if by:
        lines.append(f"[By: {by}]")
    if date:
        lines.append(f"[Date: {date}]")
    return lines + [""] + body


def insert_poem(current: str, lines: list[str], at_top: bool = NEW_POEMS_AT_TOP) -> str:
    """poems.txt with the poem added, with a --- line between it and
    its neighbor. At the top it goes under any # notes up there."""
    from poetry import POEM_BREAK_RE
    text = current.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").rstrip()
    if not text.strip():
        return "\n".join(lines) + "\n"
    all_lines = text.split("\n")
    if not at_top:
        real = [ln for ln in all_lines if ln.strip() and not ln.strip().startswith("#")]
        sep = [] if (real and POEM_BREAK_RE.match(real[-1])) else [BREAK, ""]
        return "\n".join(all_lines + [""] + sep + lines).rstrip() + "\n"
    i = 0
    while i < len(all_lines) and (not all_lines[i].strip() or all_lines[i].strip().startswith("#")):
        i += 1
    head, rest = all_lines[:i], all_lines[i:]
    if not rest:                     # only # notes so far
        gap = [""] if head and head[-1].strip() else []
        return "\n".join(head + gap + lines) + "\n"
    sep = [""] if POEM_BREAK_RE.match(rest[0]) else ["", BREAK, ""]
    return "\n".join(head + lines + sep + rest).rstrip() + "\n"


def add_poem_from_env() -> int:
    """"python3 poemform.py add": adds the poem in PM_POEM (the form's
    boxes, as JSON) to poems.txt."""
    from poetry import POEMS_PATH
    try:
        data = json.loads(os.environ.get("PM_POEM") or "")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        print("::error::The poem didn't come through. Nothing added.")
        return 1
    lines = poem_lines(data)
    if lines is None:
        print("::error::The poem needs a title and at least one line. Nothing added.")
        return 1
    current = POEMS_PATH.read_text(encoding="utf-8-sig") if POEMS_PATH.exists() else ""
    POEMS_PATH.write_text(insert_poem(current, lines), encoding="utf-8")
    print("Added a poem.")
    return 0


# ─────────────────────────────────────────────────────────────
# The form

def _token() -> str:
    return os.environ.get("PRAYER_TOKEN", "").strip()


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "grace-house-kids/grace-house-hymnal")


def render_poem_form() -> str:
    """The "+ Add a poem" button, its form, styles and script. Empty
    when there's no token. Borrows the prayer form's look (the pr-
    classes in prayer.py's CSS)."""
    if not _token():
        return ""
    from poetry import WHEEL_BREAK
    js = (POEMFORM_JS.replace("__MAX_TITLE__", str(MAX_TITLE))
                     .replace("__MONTHS__", json.dumps(MONTHS)))
    return (
        f"<style>{POEMFORM_CSS}</style>\n"
        f'<div class="pr-add" id="pf-add" data-repo="{escape(_repo())}" '
        f'data-branch="{escape(BRANCH)}" data-top="{"1" if NEW_POEMS_AT_TOP else ""}" '
        f'data-t="{escape(_token()[::-1])}">'
        '<button type="button" class="pr-add-open" id="pf-open" '
        'aria-expanded="false" aria-controls="pf-form">+ Add a poem</button>'
        '<form class="pr-form" id="pf-form" hidden>'
        '<label class="pr-label" for="pf-title">Title</label>'
        f'<input id="pf-title" type="text" maxlength="{MAX_TITLE}" required autocapitalize="words">'
        '<label class="pr-label" for="pf-body">The poem '
        "<span>A blank line between stanzas. Spaces at the start of a line are kept.</span></label>"
        f'<textarea id="pf-body" class="pf-body" rows="10" maxlength="{MAX_BODY}" required '
        'autocapitalize="sentences" spellcheck="true"></textarea>'
        '<div class="pf-meta">'
        '<div><label class="pr-label" for="pf-by">By <span>optional</span></label>'
        f'<input id="pf-by" type="text" maxlength="{MAX_BY}" autocapitalize="words"></div>'
        '<div><label class="pr-label" for="pf-date">Date <span>optional</span></label>'
        f'<input id="pf-date" type="text" maxlength="{MAX_DATE}"></div>'
        "</div>"
        '<p class="pr-form-note">It goes on the Poetry page in a couple of minutes, '
        "where anyone with the site link can see it.</p>"
        '<div class="pr-form-row">'
        '<button type="submit" class="pr-send" id="pf-send">Add poem</button>'
        '<button type="button" class="pr-cancel" id="pf-cancel">Cancel</button>'
        "</div>"
        "</form>"
        '<p class="pr-status" id="pf-status" role="status" aria-live="polite"></p>'
        f'<template id="pf-break">{WHEEL_BREAK}</template>'
        "</div>\n"
        f"<script>{js}</script>"
    )


# Starts the "Add poem" Action, then shows the poem on this phone
# straight away (at the top, or the bottom if NEW_POEMS_AT_TOP is off),
# marked "Adding", until the page loads with the real one. Gives up on
# it after 20 minutes.
POEMFORM_JS = r"""
(function () {
  var box = document.getElementById('pf-add');
  if (!box) return;
  var token = box.getAttribute('data-t').split('').reverse().join('');
  var url = 'https://api.github.com/repos/' + box.getAttribute('data-repo') +
            '/actions/workflows/poems.yml/dispatches';
  var branch = box.getAttribute('data-branch') || 'main';
  var atTop = box.getAttribute('data-top') === '1';
  function $(id) { return document.getElementById(id); }
  var form = $('pf-form'), open = $('pf-open'), send = $('pf-send'), status = $('pf-status');
  var fTitle = $('pf-title'), fBody = $('pf-body'), fBy = $('pf-by'), fDate = $('pf-date');
  var MONTHS = __MONTHS__;
  var PENDING = 'gh-poem-pending', PENDING_LIFE = 20 * 60 * 1000;

  function line(s, max) {
    return String(s || '').replace(/[\u0000-\u001f\u007f\u0085\u2028\u2029]/g, ' ')
      .replace(/\s+/g, ' ').trim().slice(0, max).trim();
  }
  function norm(s) { return String(s).toLowerCase().replace(/[^0-9a-z\u00c0-\u024f]+/g, ''); }

  // Stanzas the way poems.txt will have them: blank lines split them,
  // leading spaces stay.
  function stanzas(text) {
    var out = [], cur = [];
    String(text || '').replace(/\r\n?|[\u0085\u2028\u2029]/g, '\n').replace(/\t/g, '    ')
      .split('\n').forEach(function (ln) {
        ln = ln.replace(/\s+$/, '');
        // The same defusing the Action does (see _defuse).
        if (/^\s*-{3,}\s*$/.test(ln)) ln = ln.replace(/-/g, '\u2014');
        else {
          if (/^\s*#/.test(ln)) ln = ln.replace('#', '\uff03');
          if (/^\s*\[\s*(by|date)\s*:[^\]]*\]\s*$/i.test(ln)) ln = ln.replace(/\[/g, '(').replace(/\]/g, ')');
        }
        if (ln.trim()) cur.push(ln);
        else if (cur.length) { out.push(cur); cur = []; }
      });
    if (cur.length) out.push(cur);
    return out;
  }

  function loadPending() { try { return JSON.parse(localStorage.getItem(PENDING)) || []; } catch (e) { return []; } }
  function savePending(list) { try { localStorage.setItem(PENDING, JSON.stringify(list)); } catch (e) {} }

  function realPoems() { return document.querySelectorAll('section.poem:not(.poem-pending)'); }
  function matches(p) {
    var t = document.querySelectorAll('section.poem:not(.poem-pending) .poem-title'), n = 0;
    for (var i = 0; i < t.length; i++) if (norm(t[i].textContent) === norm(p.title)) n++;
    return n;
  }
  function wheel() {
    var tpl = $('pf-break');
    return tpl && tpl.content ? tpl.content.firstElementChild.cloneNode(true) : document.createElement('div');
  }

  // Laid out like poetry.py's render_poetry, plus the "Adding" note.
  function makePoem(p) {
    var wrap = document.createElement('div');
    wrap.className = 'poem-pending-wrap';
    wrap.setAttribute('data-pending', p.id);
    wrap.appendChild(wheel());
    var sec = document.createElement('section');
    sec.className = 'poem poem-pending';
    var h = document.createElement('h2');
    h.className = 'poem-title';
    h.textContent = p.title;
    sec.appendChild(h);
    var body = document.createElement('div');
    body.className = 'poem-body';
    stanzas(p.body).forEach(function (st) {
      var s = document.createElement('div');
      s.className = 'stanza';
      st.forEach(function (ln) {
        var d = document.createElement('div');
        d.className = 'poem-line';
        d.textContent = ln;
        s.appendChild(d);
      });
      body.appendChild(s);
    });
    sec.appendChild(body);
    var bits = [p.by, p.date].filter(Boolean);
    if (bits.length) {
      var sign = document.createElement('p');
      sign.className = 'poem-sign';
      sign.textContent = (p.by ? '\u2014 ' : '') + bits.join(', ');
      var foot = document.createElement('div');
      foot.className = 'poem-foot';
      foot.appendChild(sign);
      sec.appendChild(foot);
    }
    var note = document.createElement('p');
    note.className = 'poem-adding';
    note.textContent = 'Adding. Only you can see this until the Poetry page updates.';
    sec.appendChild(note);
    wrap.appendChild(sec);
    return wrap;
  }

  function tocItem(p) {
    var li = document.createElement('li');
    li.className = 'poem-toc-pending';
    li.setAttribute('data-pending', p.id);
    li.innerHTML = '<span class="poem-toc-title"></span><span class="poem-toc-date">adding\u2026</span>';
    li.querySelector('.poem-toc-title').textContent = p.title;
    return li;
  }

  function recount() {
    var tag = document.querySelector('.meta-strip .count-tag');
    if (!tag) return;
    var n = document.querySelectorAll('section.poem').length;
    tag.textContent = n + (n === 1 ? ' poem' : ' poems');
  }

  // Newest on top: above any other waiting poems, else above the first
  // real poem. At the bottom: after everything.
  function place(el) {
    var poems = realPoems(), waiting = document.querySelectorAll('.poem-pending-wrap');
    if (atTop) {
      if (waiting.length) { waiting[0].parentNode.insertBefore(el, waiting[0]); return; }
      if (!poems.length) { box.parentNode.insertBefore(el, box.nextSibling); return; }
      var first = poems[0], prev = first.previousElementSibling;
      var anchor = (prev && prev.classList.contains('poem-break')) ? prev : first;
      anchor.parentNode.insertBefore(el, anchor);
      // A poem with no wheel above it (the only poem) needs one now.
      if (anchor === first) el.appendChild(wheel());
    } else {
      var after = waiting.length ? waiting[waiting.length - 1] : (poems.length ? poems[poems.length - 1] : box);
      after.parentNode.insertBefore(el, after.nextSibling);
    }
  }

  function showPending() {
    var i, old = document.querySelectorAll('[data-pending]');
    for (i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    var now = Date.now(), keep = [], toc = $('contents');
    loadPending().forEach(function (p) {      // oldest first; each new one lands on top
      if (!p || !p.title || now - p.sent > PENDING_LIFE) return;
      if (matches(p) > (p.before || 0)) return;
      keep.push(p);
      place(makePoem(p));
      if (toc) {
        if (atTop) toc.insertBefore(tocItem(p), toc.firstChild);
        else toc.appendChild(tocItem(p));
      }
    });
    savePending(keep);
    recount();
  }

  function thisMonth() { var d = new Date(); return MONTHS[d.getMonth()] + ' ' + d.getFullYear(); }
  function show(on) {
    form.hidden = !on;
    open.hidden = on;
    open.setAttribute('aria-expanded', String(on));
    if (on) {
      status.textContent = '';
      if (!fDate.value) fDate.value = thisMonth();
      fTitle.focus();
    }
  }
  open.onclick = function () { show(true); };
  $('pf-cancel').onclick = function () { show(false); open.focus(); };

  form.onsubmit = function (e) {
    e.preventDefault();
    var p = { id: String(Date.now()), title: line(fTitle.value, __MAX_TITLE__).replace(/^#/, '\uff03'),
              body: fBody.value, by: line(fBy.value, 40), date: line(fDate.value, 40), sent: Date.now() };
    if (!p.title) { fTitle.focus(); return; }
    if (!stanzas(p.body).length) { fBody.focus(); return; }
    send.disabled = true;
    send.textContent = 'Adding\u2026';
    status.textContent = '';
    var poem = { title: fTitle.value, body: fBody.value, by: fBy.value, date: fDate.value };
    fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ref: branch, inputs: { poem: JSON.stringify(poem) } })
    }).then(function (r) {
      if (r.ok) return;
      return r.json().catch(function () { return {}; }).then(function (j) {
        var err = new Error((j && j.message) || '');
        err.status = r.status;
        throw err;
      });
    }).then(function () {
      fTitle.value = ''; fBody.value = '';      // "by" and the date stay, for the next one
      show(false);
      p.before = matches(p);      // a poem with the same title already (rare)
      var list = loadPending();
      list.push(p);
      savePending(list);
      showPending();
      status.textContent = 'Added. Everyone else will see it in a couple of minutes.';
      var el = document.querySelector('.poem-pending-wrap[data-pending="' + p.id + '"]');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }).catch(function (err) {
      status.textContent = (err && err.status)
        ? 'That didn\u2019t go through. GitHub said: ' + err.status +
          (err.message ? ' ' + err.message : '') +
          '. Please let whoever looks after the site know.'
        : 'That didn\u2019t go through. Check your connection and tap Add poem again.';
    }).then(function () {
      send.disabled = false;
      send.textContent = 'Add poem';
    });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showPending);
  else showPending();
})();
"""


# Only what the prayer form's styles (prayer.py) don't already cover.
POEMFORM_CSS = r"""
.pr-form textarea.pf-body { min-height: 220px; line-height: 1.6; }
.pf-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 0 10px; }
.pf-meta > div { min-width: 0; }
.pf-meta .pr-label span { display: inline; margin: 0 0 0 4px; }

/* A poem this phone just sent, until the real one arrives. */
.poem.poem-pending {
  border-left: 3px dashed #f01a8b;
  margin-left: -13px;
  padding-left: 10px;
}
.poem-adding {
  margin: 16px 0 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.5;
  opacity: 0.6;
}
.poem-toc li.poem-toc-pending {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 6px;
}
"""


if __name__ == "__main__":
    if sys.argv[1:] == ["add"]:
        sys.exit(add_poem_from_env())
    print("Usage: python3 poemform.py add   (reads PM_POEM)")
    sys.exit(2)
