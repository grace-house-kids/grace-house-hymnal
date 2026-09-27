#!/usr/bin/env python3
"""Grace House — edit a hymn from the musician page, saved to the songbook.

Two things the musician can change on /musician/hymn/N/ and have saved
back to the hymn file for everyone — the same way the events form saves
an event (eventform.py + .github/workflows/events.yml):

    CAPO    the [Capo:X] line in the hymn file (0 = no capo line)
    CHORD   one chord marker [X], nudged up or down a half step

How it works: the musician page sends a workflow_dispatch to
.github/workflows/songedit.yml, which runs "python3 songedit.py set",
edits hymns/NNN-*.txt, commits to main, and kicks off the site build.
It's live a minute or two later. Uses the SAME PRAYER_TOKEN secret the
events/prayer forms use. Without that token (e.g. on your own computer,
or any build with no secret) there's nothing to save to, so the CAPO
button falls back to a private per-device reminder and chords aren't
editable — no button or behavior disappears, it just can't write.

Why chord edits are safe: every chord the musician sees carries a
data-ci — its position in the FILE, counted the same way this file
counts (skipping [Speed]/[Key]/[Capo] lines, the title, and the Notes
block, and NOT double-counting a repeated chorus). Before replacing a
marker, the Action checks the chord still reads what the page thought it
was (ED_FROM). If the file moved on, it refuses instead of editing the
wrong chord. Worst case is a declined save, never a scrambled song.

server.py needs, in the musician branch of render_hymn_page:
    from songedit import render_song_editor
    ... render_player(...) + render_song_editor(number, meta.get("capo", "")) + ...
and META_RE widened to (speed|key|capo) so [Capo:X] is read, not shown.

The Action passes everything through env (never the command line), so
nothing anyone types can run as a command:
    ED_ACTION   "capo" or "chord"
    ED_HYMN     hymn number
    ED_CAPO     0..7                         (capo)
    ED_CI       chord index (data-ci)        (chord)
    ED_FROM     chord as the page saw it     (chord, the guard)
    ED_TO       new chord to write           (chord)
"""
from __future__ import annotations

import os
import re
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
HYMNS_DIR = HERE / "hymns"
BRANCH = "main"
MAX_CAPO = 7
MAX_MOVE = 40          # most characters a chord can be nudged in one save

# Kept in step with server.py. CHORD_RE matches any [..]; the real
# chords are picked out by chord_spans() below, which excludes the same
# things parse_hymn / render_hymn_page do.
CHORD_RE = re.compile(r"\[([^\]]+)\]")
META_RE = re.compile(r"^\s*\[\s*(speed|key|capo)\s*:\s*([^\]]*?)\s*\]\s*$", re.IGNORECASE)
CAPO_LINE_RE = re.compile(r"^\s*\[\s*capo\s*:\s*[^\]]*\]\s*$", re.IGNORECASE)


# ─────────────────────────────────────────────────────────────
# Finding the hymn file (same rule as server.load_hymns / find_audio)

def find_hymn(number: int) -> Path | None:
    if not HYMNS_DIR.is_dir():
        return None
    for path in sorted(HYMNS_DIR.glob("*.txt")):
        m = re.match(r"(\d+)[-_ ](.+)\.txt$", path.name)
        if m and int(m.group(1)) == number:
            return path
    return None


def _valid_chord(text: str) -> bool:
    """A chord token that's safe to drop between [ and ]: not empty, no
    bracket or newline that would break the marker, not absurdly long."""
    if not text or len(text) > 16:
        return False
    return not any(c in text for c in "[]\r\n")


# ─────────────────────────────────────────────────────────────
# Locating real chord markers in the raw file
#
# A chord's data-ci on the page is its index here: every [..] in file
# order, EXCLUDING [Speed]/[Key]/[Capo] lines, the title line, and the
# Notes/Note block — mirroring parse_hymn + render_hymn_page's notes
# filter. A repeated chorus is NOT counted twice: the file has the
# chorus once, and the page gives every rendered copy the same data-ci.

def _line_spans(raw: str) -> list[tuple[int, int, str]]:
    """(start, end, text) for every physical line; end excludes the \\n."""
    spans, pos = [], 0
    for line in raw.split("\n"):
        spans.append((pos, pos + len(line), line))
        pos += len(line) + 1
    return spans


def _excluded_ranges(raw: str) -> list[tuple[int, int]]:
    """Char ranges to skip: meta lines, the title, and any Notes block."""
    spans = _line_spans(raw)
    excluded: list[tuple[int, int]] = []
    structural: list[tuple[int, int, str]] = []
    for s, e, text in spans:
        if META_RE.match(text):
            excluded.append((s, e))           # [Speed]/[Key]/[Capo]
        else:
            structural.append((s, e, text))
    # First non-blank structural line is the title (parse_hymn).
    idx = 0
    while idx < len(structural) and not structural[idx][2].strip():
        idx += 1
    if idx >= len(structural):
        return excluded
    excluded.append((structural[idx][0], structural[idx][1]))   # title
    body = structural[idx + 1:]
    # Split the body into blank-line-separated blocks, keeping char refs.
    blocks, cur = [], []
    for s, e, text in body:
        if not text.strip():
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append((s, e, text))
    if cur:
        blocks.append(cur)
    for block in blocks:
        first = block[0][2].strip()
        is_label = (len(first) <= 6 and " " not in first and len(block) > 1)
        label = first if is_label else ""
        if label.strip().lower().rstrip(":").strip() in ("notes", "note"):
            for s, e, _ in block:
                excluded.append((s, e))       # the whole Notes block
    return excluded


def chord_spans(raw: str) -> list[tuple[int, int, str]]:
    """(start, end, inner) for each real chord marker, in file order.
    The ci-th entry is the marker that data-ci=ci points at."""
    excluded = _excluded_ranges(raw)

    def hidden(pos: int) -> bool:
        return any(s <= pos < e for s, e in excluded)

    return [(m.start(), m.end(), m.group(1))
            for m in CHORD_RE.finditer(raw) if not hidden(m.start())]


# ─────────────────────────────────────────────────────────────
# The edits themselves (pure string in, string out — easy to test)

def set_chord(raw: str, ci: int, frm: str, to: str, offset: int = 0) -> str:
    """Replace the ci-th real chord marker (only if it still reads [frm] —
    the guard), and optionally slide it `offset` characters along its own
    line: >0 right, <0 left. The marker never crosses another chord marker
    or the ends of its line; it just stops there. Lyrics are untouched —
    only where the invisible [..] sits moves."""
    spans = chord_spans(raw)
    if ci < 0 or ci >= len(spans):
        raise ValueError(f"there's no chord #{ci} (the song has {len(spans)}).")
    s, e, inner = spans[ci]
    if inner != frm:
        raise ValueError(f"chord #{ci} now reads [{inner}], not [{frm}] — "
                         "the song changed since the page loaded, so nothing was touched.")
    if not _valid_chord(to):
        raise ValueError(f"[{to}] isn't a chord I'll write into the file.")
    try:
        off = max(-MAX_MOVE, min(MAX_MOVE, int(offset)))
    except (TypeError, ValueError):
        off = 0
    marker = "[" + to + "]"
    ls = raw.rfind("\n", 0, s) + 1          # start of this line
    le = raw.find("\n", e)                   # end of this line
    if le == -1:
        le = len(raw)
    if off > 0:
        right = raw[e:le]
        take = 0
        while take < off and take < len(right) and right[take] != "[":
            take += 1
        return raw[:s] + right[:take] + marker + raw[e + take:]
    if off < 0:
        left = raw[ls:s]
        take = 0
        while take < -off and take < len(left) and left[len(left) - 1 - take] != "]":
            take += 1
        return raw[:s - take] + marker + raw[s - take:s] + raw[e:]
    return raw[:s] + marker + raw[e:]


def set_capo(raw: str, value: int) -> str:
    """value 0 removes any [Capo:X] line; 1..7 inserts or replaces it,
    tucked into the meta cluster under the title (next to Speed/Key)."""
    nl = "\n"
    lines = raw.split(nl)
    keep = [ln for ln in lines if not CAPO_LINE_RE.match(ln)]
    if value <= 0:
        return nl.join(keep)
    # Title = first non-blank, non-meta line; sit below it and any
    # Speed/Key lines already there.
    ti = 0
    while ti < len(keep) and (not keep[ti].strip() or META_RE.match(keep[ti])):
        ti += 1
    j = ti + 1
    while j < len(keep) and META_RE.match(keep[j]):
        j += 1
    keep.insert(j, f"[Capo:{value}]")
    return nl.join(keep)


# ─────────────────────────────────────────────────────────────
# The Action entry point ("python3 songedit.py set")

def _apply_from_env() -> int:
    action = (os.environ.get("ED_ACTION") or "").strip().lower()
    num_raw = (os.environ.get("ED_HYMN") or "").strip()
    if not num_raw.isdigit():
        print("::error::Missing or bad hymn number.")
        return 1
    number = int(num_raw)
    path = find_hymn(number)
    if path is None:
        print(f"::error::No hymn file for #{number}.")
        return 1
    raw = path.read_text(encoding="utf-8")

    if action == "capo":
        cr = (os.environ.get("ED_CAPO") or "").strip()
        if not cr.isdigit() or not (0 <= int(cr) <= MAX_CAPO):
            print(f"::error::Capo must be a whole number 0-{MAX_CAPO}.")
            return 1
        new = set_capo(raw, int(cr))
        what = f"capo set to {int(cr)}" if int(cr) else "capo removed"
    elif action == "chord":
        cir = (os.environ.get("ED_CI") or "").strip()
        frm = (os.environ.get("ED_FROM") or "").strip()
        to = (os.environ.get("ED_TO") or "").strip()
        off_raw = (os.environ.get("ED_OFFSET") or "0").strip()
        try:
            off = int(off_raw)
        except ValueError:
            off = 0
        if not cir.isdigit():
            print("::error::Missing or bad chord index.")
            return 1
        if not _valid_chord(frm) or not _valid_chord(to):
            print("::error::Missing or bad chord text.")
            return 1
        try:
            new = set_chord(raw, int(cir), frm, to, off)
        except ValueError as e:
            print(f"::error::{e}")
            return 1
        what = f"chord #{cir}: [{frm}] to [{to}]" + (f", moved {off:+d}" if off else "")
    else:
        print('::error::Unknown action (want "capo" or "chord").')
        return 1

    if new == raw:
        print(f"{path.name}: nothing to change.")
        return 0
    path.write_text(new, encoding="utf-8")
    print(f"{path.name}: {what}.")
    return 0


# ─────────────────────────────────────────────────────────────
# The musician-page control (chord popup + capo/chord save wiring)

def _token() -> str:
    return os.environ.get("PRAYER_TOKEN", "").strip()


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "grace-house-kids/grace-house-hymnal")


SONGEDIT_CSS = r"""
.se-modal .listen-box { max-width: 300px; text-align: center; }
.se-chordwrap { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 18px 0 6px; }
.se-chord {
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900; font-size: 56px; line-height: 0.9; color: #f01a8b;
  min-width: 96px; font-variant-numeric: tabular-nums;
}
.se-moverow { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 4px 0 2px; }
.se-pos {
  min-width: 96px; font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 12px; letter-spacing: 1px; color: #0a0a0a; opacity: 0.7;
}
html.dark .se-pos { color: #f5f5f5; }
.se-hint {
  font-family: 'Special Elite', 'Courier New', monospace; font-size: 11px;
  line-height: 1.5; color: #0a0a0a; opacity: 0.7; margin: 6px 0 14px;
}
.se-actions { justify-content: center; gap: 10px; }
.se-actions .se-cancel { width: auto; padding: 0 16px; height: 40px; font-size: 13px; }
.se-toast {
  position: fixed; left: 50%; transform: translateX(-50%);
  bottom: calc(150px + env(safe-area-inset-bottom)); z-index: 65;
  max-width: calc(100% - 32px);
  background: #0a0a0a; color: #f2ede4; padding: 10px 16px;
  font-family: 'Special Elite', 'Courier New', monospace; font-size: 12px;
  line-height: 1.4; box-shadow: 4px 4px 0 #f01a8b;
}
.se-toast[hidden] { display: none; }
.se-toast, .se-toast *, .se-modal, .se-modal * {
  -webkit-text-stroke-width: 0 !important;
  -webkit-text-stroke-color: transparent !important;
  paint-order: normal !important;
}
/* When saving is on, show chords are tappable. */
html.se-on .v-body .chord {
  cursor: pointer; text-decoration: underline; text-decoration-style: dotted;
  text-underline-offset: 3px; text-decoration-color: rgba(240, 26, 139, 0.5);
}
html.se-on .v-body .chord:focus-visible { outline: 2px solid #f01a8b; outline-offset: 2px; }
html.dark .se-hint { color: #f5f5f5; }
"""


# Plain string (not an f-string) so the JavaScript braces are left alone.
SONGEDIT_JS = r"""
(function () {
  var se = document.getElementById('se');
  if (!se) return;
  function $(id) { return document.getElementById(id); }
  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function save(k, v) { try { localStorage.setItem(k, String(v)); } catch (e) {} }

  var num = se.getAttribute('data-num') || '';
  var repo = se.getAttribute('data-repo') || '';
  var branch = se.getAttribute('data-branch') || 'main';
  var tok = se.getAttribute('data-t');
  tok = tok ? tok.split('').reverse().join('') : '';
  var canSave = !!(tok && repo && num);
  var api = 'https://api.github.com/repos/' + repo + '/actions/workflows/songedit.yml/dispatches';

  function dispatch(inputs) {
    return fetch(api, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + tok,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ref: branch, inputs: inputs })
    }).then(function (r) {
      if (r.ok) return;
      return r.json().catch(function () { return {}; }).then(function (j) {
        var e = new Error((j && j.message) || ''); e.status = r.status; throw e;
      });
    });
  }

  var toastEl = $('se-toast'), toastTimer = 0;
  function toast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg; toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.hidden = true; }, 6000);
  }

  /* ── Capo ─────────────────────────────────────────────────
     With a token, the button saves the [Capo:X] line to the songbook
     (debounced, so a quick 0→1→2→3 sends one save). Without a token
     it's just a private per-device reminder, like it was before. */
  var capoBtn = $('ctl-capo'), capoVal = $('ctl-capo-val');
  var localKey = 'gh-capo-' + num;
  var startCapo = parseInt(se.getAttribute('data-capo'), 10);
  if (!(startCapo >= 0 && startCapo <= 7)) startCapo = 0;
  var capo;
  if (canSave) {
    capo = startCapo;                       // the file value is the truth
  } else {
    var lv = parseInt(load(localKey), 10);
    capo = (lv >= 0 && lv <= 7) ? lv : startCapo;
  }
  var capoTimer = 0;
  function showCapo() {
    capoVal.textContent = capo === 0 ? 'OFF' : String(capo);
    capoBtn.classList.toggle('on', capo !== 0);
    capoBtn.setAttribute('aria-pressed', String(capo !== 0));
  }
  capoBtn.onclick = function () {
    capo = (capo + 1 > 7) ? 0 : capo + 1;
    showCapo();
    if (canSave) {
      clearTimeout(capoTimer);
      toast('Saving capo…');
      capoTimer = setTimeout(function () {
        var v = capo;
        dispatch({ action: 'capo', hymn: num, capo: String(v) })
          .then(function () {
            toast((v === 0 ? 'Capo off' : 'Capo ' + v) +
                  ' — everyone sees it after the site rebuilds (about a minute).');
          })
          .catch(function (err) {
            toast('Capo didn’t save' + (err && err.status ? ' (' + err.status + ')' : '') +
                  '. Tap it again in a moment.');
          });
      }, 1200);
    } else {
      save(localKey, capo);
    }
  };
  showCapo();

  /* ── Chord editing (only when it can save) ────────────────── */
  if (canSave) {
    document.documentElement.classList.add('se-on');
    var modal = $('se-modal'), disp = $('se-chord'), stat = $('se-status'), saveBtn = $('se-save');
    var posEl = $('se-pos'), moveOffset = 0, MAXMOVE = 40;
    function showPos() {
      posEl.textContent = moveOffset === 0 ? 'in place'
        : (moveOffset < 0 ? '◄ ' + (-moveOffset) : moveOffset + ' ►');
    }
    // Slide a chord span one character along its line, across the lyric
    // text but never past another chord or the line's edge (matching the
    // file-side move). Cosmetic only — the saved file is the source of truth.
    function domMove(span, steps) {
      var dir = steps < 0 ? -1 : 1, n = Math.abs(steps);
      for (var k = 0; k < n; k++) {
        if (dir > 0) {
          var nx = span.nextSibling;
          if (!nx || nx.nodeType !== 3 || !nx.textContent.length) break;
          span.parentNode.insertBefore(document.createTextNode(nx.textContent[0]), span);
          nx.textContent = nx.textContent.slice(1);
        } else {
          var pv = span.previousSibling;
          if (!pv || pv.nodeType !== 3 || !pv.textContent.length) break;
          span.parentNode.insertBefore(
            document.createTextNode(pv.textContent[pv.textContent.length - 1]), span.nextSibling);
          pv.textContent = pv.textContent.slice(0, -1);
        }
      }
    }

    var SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
    var FLAT  = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B'];
    var PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
    var NOTE_RE = /(^|[\/(\s])([A-G])([#b♯♭]?)/g;
    function pcOf(l, a) {
      var p = PC[l];
      if (a === '#' || a === '♯') p += 1;
      else if (a === 'b' || a === '♭') p -= 1;
      return (p + 12) % 12;
    }
    // Nudge a written chord a half step: sharps going up, flats going down,
    // so G+1 = G#, A-1 = Ab. Suffixes and slash notes are kept (Gm7, G/B).
    function move(chord, step) {
      var names = step < 0 ? FLAT : SHARP;
      return chord.replace(NOTE_RE, function (m, pre, l, a) {
        return pre + names[((pcOf(l, a) + step) % 12 + 12) % 12];
      });
    }

    var curEl = null, fromChord = '', working = '';
    function open(el) {
      curEl = el;
      fromChord = el.getAttribute('data-chord');
      working = fromChord;
      disp.textContent = working;
      moveOffset = 0;
      showPos();
      stat.textContent = '';
      saveBtn.disabled = false;
      modal.hidden = false;
    }
    function close() { modal.hidden = true; curEl = null; }
    function nudge(step) { working = move(working, step); disp.textContent = working; }

    var spans = document.querySelectorAll('.v-body .chord[data-ci]');
    for (var i = 0; i < spans.length; i++) {
      var sp = spans[i];
      sp.setAttribute('role', 'button');
      sp.setAttribute('tabindex', '0');
      sp.addEventListener('click', function () { open(this); });
      sp.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(this); }
      });
    }
    $('se-up').onclick = function () { nudge(1); };
    $('se-dn').onclick = function () { nudge(-1); };
    $('se-right').onclick = function () { if (moveOffset < MAXMOVE) { moveOffset++; showPos(); } };
    $('se-left').onclick = function () { if (moveOffset > -MAXMOVE) { moveOffset--; showPos(); } };
    $('se-x').onclick = close;
    $('se-cancel').onclick = close;
    document.addEventListener('keydown', function (e) {
      if (!modal.hidden && e.key === 'Escape') close();
    });

    saveBtn.onclick = function () {
      if (working === fromChord && moveOffset === 0) { close(); return; }
      var ci = curEl.getAttribute('data-ci');
      var to = working, off = moveOffset;
      saveBtn.disabled = true;
      stat.textContent = 'Saving…';
      dispatch({ action: 'chord', hymn: num, ci: String(ci), from: fromChord,
                 to: to, offset: String(off) })
        .then(function () {
          // Update every copy that shares this ci (a repeated chorus)
          // so the page matches what will come back after the rebuild.
          var twins = document.querySelectorAll('.v-body .chord[data-ci="' + ci + '"]');
          for (var j = 0; j < twins.length; j++) {
            twins[j].setAttribute('data-chord', to);
            twins[j].textContent = '[' + to + ']';
            if (off) domMove(twins[j], off);
          }
          close();
          toast('Chord saved — everyone sees it after the site rebuilds (about a minute).');
        })
        .catch(function (err) {
          stat.textContent = 'Didn’t save' + (err && err.status ? ' (' + err.status + ')' : '') +
                             '. Try again.';
          saveBtn.disabled = false;
        });
    };
  }
})();
"""


def render_song_editor(number, capo_meta: str = "") -> str:
    """Chord-edit popup + the capo/chord save wiring, for the musician
    page. Always returned (so the capo reminder works offline); the save
    wiring only activates when PRAYER_TOKEN is set, exactly like the
    events form's button."""
    try:
        capo = int(str(capo_meta).strip())
    except (TypeError, ValueError):
        capo = 0
    if not (0 <= capo <= MAX_CAPO):
        capo = 0
    tok = _token()
    attrs = (f'data-num="{escape(str(number))}" data-capo="{capo}" '
             f'data-branch="{escape(BRANCH)}"')
    if tok:
        attrs += f' data-repo="{escape(_repo())}" data-t="{escape(tok[::-1])}"'
    return (
        f"<style>{SONGEDIT_CSS}</style>\n"
        f'<div id="se" {attrs}>'
        '<div id="se-modal" class="listen se-modal" hidden role="dialog" '
        'aria-modal="true" aria-label="Edit chord">'
        '<div class="listen-box">'
        '<div class="listen-head">'
        '<span class="listen-title">Edit chord</span>'
        '<button id="se-x" class="listen-x" type="button" aria-label="Close">&times;</button>'
        '</div>'
        '<div class="se-chordwrap">'
        '<button id="se-dn" class="p-btn p-sq" type="button" aria-label="Down a half step">&minus;</button>'
        '<b id="se-chord" class="se-chord">&nbsp;</b>'
        '<button id="se-up" class="p-btn p-sq" type="button" aria-label="Up a half step">+</button>'
        '</div>'
        '<div class="se-moverow">'
        '<button id="se-left" class="p-btn p-sq" type="button" aria-label="Move chord left">&#9664;</button>'
        '<span id="se-pos" class="se-pos">in place</span>'
        '<button id="se-right" class="p-btn p-sq" type="button" aria-label="Move chord right">&#9654;</button>'
        '</div>'
        '<p class="se-hint">&minus; / + change the chord; &#9664; &#9654; slide it '
        'to another syllable. Saved for everyone; the page updates after the '
        'site rebuilds (about a minute).</p>'
        '<div class="listen-row se-actions">'
        '<button id="se-save" class="listen-play" type="button">Save</button>'
        '<button id="se-cancel" class="listen-x se-cancel" type="button">Cancel</button>'
        '</div>'
        '<div id="se-status" class="listen-time" role="status" aria-live="polite"></div>'
        '</div></div>'
        '<div id="se-toast" class="se-toast" role="status" aria-live="polite" hidden></div>'
        '</div>\n'
        f"<script>{SONGEDIT_JS}</script>"
    )


if __name__ == "__main__":
    if sys.argv[1:2] == ["set"]:
        sys.exit(_apply_from_env())
    print("Usage: python3 songedit.py set   "
          "(reads ED_ACTION, ED_HYMN, ED_CAPO | ED_CI/ED_FROM/ED_TO)")
    sys.exit(2)
