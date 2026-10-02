#!/usr/bin/env python3
"""Grace House — edit a hymn from the musician page, saved to the songbook.

Three things the musician can change on /musician/hymn/N/ and have saved
back to the hymn file for everyone — the same way the events form saves
an event (eventform.py + .github/workflows/events.yml):

    CAPO    the [Capo:X] line in the hymn file (0 = no capo line)
    CHORD   one chord marker [X], nudged up or down a half step
    TEXT    the whole hymn file, edited as plain text ("✎ Edit song")

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

Why text edits are safe: the page sends ED_BASE, a SHA-256 of the file
as the page loaded it. If the file changed since (another save landed
first), the Action refuses rather than overwrite it. The page keeps her
edit on the device as a draft until a reloaded page shows it really
made it into the songbook, so a refused save is never lost work — the
next time she opens the editor she's offered "Load it".

RESTORE ORIGINAL: the "↺ Restore original" button puts a hymn back the
way YOU last saved it, undoing every chord/capo change made from the
website since. Nothing extra is stored: every website save is committed
by the Action as BOT_EMAIL, so "your original" is simply the newest
commit of that hymn file made by anybody else (you uploading or editing
it on GitHub, or pushing from your computer). Edit a hymn yourself and
that becomes the new original. The Action needs the full history for
this (fetch-depth: 0 in songedit.yml).

server.py needs, in the musician branch of render_hymn_page:
    from songedit import render_song_editor
    ... render_player(...) + render_song_editor(number, meta.get("capo", "")) + ...
and META_RE widened to (speed|key|capo) so [Capo:X] is read, not shown.

The Action passes everything through env (never the command line), so
nothing anyone types can run as a command:
    ED_ACTION   "capo", "chord", "text" or "revert"
    ED_HYMN     hymn number
    ED_CAPO     0..7                         (capo)
    ED_CI       chord index (data-ci)        (chord)
    ED_FROM     chord as the page saw it     (chord, the guard)
    ED_TO       new chord to write           (chord)
    ED_OFFSET   characters to slide it       (chord, optional)
    ED_TEXT     the whole new hymn file      (text)
    ED_BASE     sha256 of the file the page loaded (text, the guard)
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
HYMNS_DIR = HERE / "hymns"
BRANCH = "main"
MAX_CAPO = 7
MAX_MOVE = 40          # most characters a chord can be nudged in one save
MAX_TEXT = 30000       # biggest hymn file the editor will save (GitHub caps
                       # all dispatch inputs together at 65,535 characters)
# Who the website's saves are committed as (songedit.yml's git config).
# Any commit NOT by this address counts as one of yours.
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"

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


def normalize_text(text: str) -> str:
    """How a hymn file is written after a text edit: \\n line endings,
    no trailing blank lines or spaces at the very end, one final \\n.
    SONGEDIT_JS's norm() does exactly the same, so both sides hash the
    same bytes."""
    return re.sub(r"\r\n?", "\n", text).rstrip(" \t\n") + "\n"


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def set_text(raw: str, text: str, base: str) -> str:
    """Replace the whole file with `text` — only if the file is still the
    one the page loaded (sha256 `base`, the guard)."""
    base = (base or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", base):
        raise ValueError("missing the page's version check, so nothing was touched.")
    if text_hash(raw) != base:
        raise ValueError("the song changed since the page loaded (another save landed "
                         "first), so nothing was touched. Her edit is still saved on "
                         "her device; reloading the page offers it back.")
    new = normalize_text(text)
    if len(new) > MAX_TEXT:
        raise ValueError(f"the song is {len(new)} characters; the most I'll save is {MAX_TEXT}.")
    if "\x00" in new:
        raise ValueError("the text has a stray null character in it.")
    if not any(ln.strip() and not META_RE.match(ln) for ln in new.split("\n")):
        raise ValueError("the song needs at least a title line.")
    return new


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=HERE, check=True,
                          capture_output=True).stdout


def original_text(path: Path) -> str:
    """The hymn file as of the newest commit to it NOT made by the
    website (BOT_EMAIL) — i.e. the way you last saved it."""
    if _git("rev-parse", "--is-shallow-repository").strip() == b"true":
        raise ValueError("the Action only has the latest commit, not the history "
                         "(songedit.yml's checkout needs fetch-depth: 0).")
    rel = path.relative_to(HERE).as_posix()
    log = _git("log", "--format=%H%x09%ae", "--", rel).decode("utf-8")
    for line in log.splitlines():
        sha, _, email = line.partition("\t")
        if email.strip().lower() != BOT_EMAIL:
            try:
                return _git("show", f"{sha}:{rel}").decode("utf-8")
            except subprocess.CalledProcessError:
                break     # file had another name back then
    raise ValueError(f"couldn't find your own saved version of {rel} in the history.")


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
    elif action == "text":
        try:
            new = set_text(raw, os.environ.get("ED_TEXT") or "",
                           os.environ.get("ED_BASE") or "")
        except ValueError as e:
            print(f"::error::{e}")
            return 1
        what = "song text edited"
    elif action == "revert":
        try:
            new = original_text(path)
        except (ValueError, subprocess.CalledProcessError) as e:
            print(f"::error::Couldn't restore the original: {e}")
            return 1
        what = "restored to the original"
    else:
        print('::error::Unknown action (want "capo", "chord", "text" or "revert").')
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
  bottom: calc(150px + env(safe-area-inset-bottom)); z-index: 85;
  max-width: calc(100% - 32px);
  background: #0a0a0a; color: #f2ede4; padding: 10px 16px;
  font-family: 'Special Elite', 'Courier New', monospace; font-size: 12px;
  line-height: 1.4; box-shadow: 4px 4px 0 #f01a8b;
}
.se-toast[hidden] { display: none; }
/* Edit song + Restore original: moved above the PREV / INDEX / NEXT
   row by the script, where the fixed control bar can't cover them.
   Restore is outlined, not pink, so it doesn't look like an everyday
   button. */
.se-tools {
  margin-top: 26px; display: flex; justify-content: flex-end;
  align-items: center; flex-wrap: wrap; gap: 12px;
}
.se-tools[hidden] { display: none; }
.se-editbtn { border: 0; cursor: pointer; touch-action: manipulation; }
.se-revert {
  font-family: 'Special Elite', 'Courier New', monospace; font-size: 11px;
  letter-spacing: 1.5px; text-transform: uppercase;
  padding: 4px 10px 5px; border: 1.5px dashed #0a0a0a; border-radius: 0;
  background: transparent; color: #0a0a0a; cursor: pointer;
  touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.se-revert:active { transform: translateY(1px); }
.se-revert:disabled { opacity: 0.45; cursor: default; }
html.dark .se-revert { border-color: #f5f5f5; color: #f5f5f5; }

/* Full-screen plain-text editor. */
.se-text {
  position: fixed; inset: 0; z-index: 80;
  display: flex; flex-direction: column; gap: 8px;
  background: #f2ede4;
  padding: 12px 12px calc(12px + env(safe-area-inset-bottom));
}
.se-text[hidden] { display: none; }
.se-text > * { width: 100%; max-width: 48rem; margin: 0 auto; }
.se-text-head { display: flex; align-items: center; justify-content: space-between; }
.se-draft {
  display: flex; align-items: center; gap: 10px;
  background: #f01a8b; color: #0a0a0a; padding: 8px 10px;
  font-family: 'Special Elite', 'Courier New', monospace; font-size: 12px; line-height: 1.4;
}
.se-draft[hidden] { display: none; }
.se-draft span { flex: 1; }
.se-draft .p-btn { flex-shrink: 0; height: 32px; }
.se-help {
  font-family: 'Special Elite', 'Courier New', monospace; font-size: 12px;
  line-height: 1.5; color: #0a0a0a;
}
.se-help summary { cursor: pointer; color: #f01a8b; letter-spacing: 1px; }
.se-help ul { margin: 6px 0 2px; padding-left: 20px; }
.se-help code { font-family: inherit; color: #f01a8b; }
.se-ta {
  flex: 1; min-height: 0; resize: none;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 16px;            /* 16px+ keeps iPhones from zooming in */
  line-height: 1.55;
  padding: 10px 12px;
  border: 3px solid #0a0a0a; border-radius: 0;
  background: #fffdf8; color: #0a0a0a;
  -webkit-appearance: none; appearance: none;
}
.se-ta:focus { outline: 3px solid #f01a8b; outline-offset: 0; }
.se-text-foot { display: flex; align-items: center; gap: 10px; }
.se-text-status {
  flex: 1; font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 12px; line-height: 1.4; color: #0a0a0a;
}
.se-text-foot .se-cancel { width: auto; padding: 0 16px; height: 40px; font-size: 13px; }
html.dark .se-text { background: #000000; }
html.dark .se-ta { background: #0d0d0d; color: #f5f5f5; border-color: #f5f5f5; }
html.dark .se-help, html.dark .se-text-status { color: #f5f5f5; }
html.dark .se-text .listen-x { border-color: #f5f5f5; color: #f5f5f5; }
html.dark .se-text .listen-play { background: #f5f5f5; color: #000000; border-color: #f5f5f5; }

.se-toast, .se-toast *, .se-modal, .se-modal *, .se-tools, .se-tools *,
.se-text, .se-text * {
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
            fileChanged = true;
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

  // After any save, the text editor's copy of the song is out of date
  // (its save would be refused), so it asks for a reload first. After a
  // text save or a restore, the chord positions are out of date too.
  var fileChanged = false, chordsStale = false;

  /* ── Edit song / Restore original row ─────────────────────── */
  var tools = $('se-tools');
  if (canSave && tools) {
    var foot = document.querySelector('nav.foot');
    if (foot) foot.parentNode.insertBefore(tools, foot);
    tools.hidden = false;
  }

  /* ── Restore original (only when it can save) ─────────────
     Puts the hymn file back the way the site owner last saved it
     (songedit.py original_text), undoing every website edit. */
  var revBtn = $('se-revert');
  if (canSave && revBtn) {
    revBtn.onclick = function () {
      if (!confirm('Put song #' + num + ' back to the original?\n\n' +
                   'This undoes every change made to it from this website, ' +
                   'for everyone.')) return;
      revBtn.disabled = true;
      toast('Restoring the original…');
      dispatch({ action: 'revert', hymn: num })
        .then(function () {
          fileChanged = chordsStale = true;
          toast('Restored — reload in a minute or two to see the original.');
        })
        .catch(function (err) {
          revBtn.disabled = false;
          toast('Didn’t restore' + (err && err.status ? ' (' + err.status + ')' : '') +
                '. Try again in a moment.');
        });
    };
  }

  /* ── Edit the whole song as text (only when it can save) ──────
     The textarea holds the hymn file exactly as it is in the songbook.
     Save sends the new text plus a fingerprint (sha256) of the text the
     page loaded; the Action refuses if the file changed in between.
     Her edit is kept on this device as a draft (autosaved while she
     types) until a reloaded page shows it made it in, so a refused or
     interrupted save is never lost — the editor offers "Load it". */
  var tx = $('se-text'), ta = $('se-ta');
  if (canSave && tx && ta) {
    var original = ta.value;
    var maxText = parseInt(se.getAttribute('data-maxtext'), 10) || 30000;
    var draftKey = 'gh-draft-' + num, draftTimer = 0;
    var txStat = $('se-text-status'), txSave = $('se-text-save'), draftBar = $('se-draft');
    var META = /^\s*\[\s*(speed|key|capo)\s*:[^\]]*\]\s*$/i;

    // Same as songedit.normalize_text in Python — both hash these bytes.
    function norm(t) { return t.replace(/\r\n?/g, '\n').replace(/[ \t\n]+$/, '') + '\n'; }
    function sha(t) {
      return crypto.subtle.digest('SHA-256', new TextEncoder().encode(norm(t)))
        .then(function (b) {
          return Array.prototype.map.call(new Uint8Array(b), function (x) {
            return ('0' + x.toString(16)).slice(-2);
          }).join('');
        });
    }
    function readDraft() {
      try { var d = JSON.parse(load(draftKey)); return d && d.text ? d : null; }
      catch (e) { return null; }
    }
    function dropDraft() { try { localStorage.removeItem(draftKey); } catch (e) {} }
    function keepDraft(text) { save(draftKey, JSON.stringify({ t: Date.now(), text: text })); }
    function dirty() { return norm(ta.value) !== norm(original); }

    // A draft that matches what the songbook now says = that save landed.
    var d0 = readDraft();
    if (d0 && norm(d0.text) === norm(original)) dropDraft();

    function txOpen() {
      if (fileChanged) {
        toast('Reload the page first — this song was just changed.');
        return;
      }
      var pb = $('ctl-play');
      if (pb && pb.classList.contains('on')) pb.click();     // stop auto-scroll
      var d = readDraft();
      var pending = d && norm(d.text) !== norm(ta.value);
      if (pending) {
        $('se-draft-msg').textContent = 'You have an edit from ' +
          new Date(d.t).toLocaleString([], { month: 'short', day: 'numeric',
            hour: 'numeric', minute: '2-digit' }) +
          ' that isn’t on this page. If you just saved it, it may still be on its way ' +
          '(reload in a minute) — or it didn’t go through.';
      }
      draftBar.hidden = !pending;
      txStat.textContent = '';
      txSave.disabled = false;
      tx.hidden = false;
      document.documentElement.style.overflow = 'hidden';
    }
    function txClose() {
      tx.hidden = true;
      document.documentElement.style.overflow = '';
    }
    function txCancel() {
      if (dirty()) {
        if (!confirm('Throw away your changes to this song?')) return;
        ta.value = original;
        dropDraft();
      }
      txClose();
    }

    $('se-edit').onclick = txOpen;
    $('se-text-x').onclick = txCancel;
    $('se-text-cancel').onclick = txCancel;
    $('se-draft-load').onclick = function () {
      var d = readDraft();
      if (d) ta.value = d.text;
      draftBar.hidden = true;
    };
    ta.addEventListener('input', function () {
      clearTimeout(draftTimer);
      draftTimer = setTimeout(function () {
        if (dirty()) keepDraft(ta.value);
      }, 600);
    });
    document.addEventListener('keydown', function (e) {
      if (!tx.hidden && e.key === 'Escape') txCancel();
    });

    txSave.onclick = function () {
      if (!dirty()) { txClose(); return; }
      var text = norm(ta.value);
      var hasTitle = text.split('\n').some(function (l) { return l.trim() && !META.test(l); });
      if (!hasTitle) { txStat.textContent = 'The first line should be the song title.'; return; }
      if (text.length > maxText) {
        txStat.textContent = 'That’s too long to save (' + text.length + ' of ' + maxText + ' characters).';
        return;
      }
      if (!(window.crypto && crypto.subtle && window.TextEncoder)) {
        txStat.textContent = 'This browser can’t save here — open the site’s https address.';
        return;
      }
      clearTimeout(draftTimer);
      keepDraft(text);
      txSave.disabled = true;
      txStat.textContent = 'Saving…';
      sha(original).then(function (base) {
        return dispatch({ action: 'text', hymn: num, text: text, base: base });
      }).then(function () {
        original = text;
        ta.value = text;
        fileChanged = chordsStale = true;
        txClose();
        toast('Song saved — reload in a minute or two to see it.');
      }).catch(function (err) {
        txStat.textContent = 'Didn’t save' + (err && err.status ? ' (' + err.status + ')' : '') +
                             '. Your edit is kept on this device — try again.';
        txSave.disabled = false;
      });
    };
  }

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
      // After a text save or restore the chord positions on this page no
      // longer match the file, so a chord save could land on the wrong one.
      if (chordsStale) { toast('Reload the page first — this song was just changed.'); return; }
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
          fileChanged = true;
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


def _render_tools(number, raw: str | None) -> str:
    """The Edit song / Restore original row, plus the full-screen text
    editor (left out if the hymn file couldn't be read)."""
    edit_btn = editor = ""
    if raw is not None:
        edit_btn = ('<button id="se-edit" class="foot-link se-editbtn" type="button">'
                    '&#9998; Edit song</button>')
        editor = (
            '<div id="se-text" class="se-text" hidden role="dialog" aria-modal="true" '
            'aria-label="Edit song">'
            '<div class="se-text-head">'
            f'<span class="listen-title">Edit song #{escape(str(number))}</span>'
            '<button id="se-text-x" class="listen-x" type="button" aria-label="Close">&times;</button>'
            '</div>'
            '<div id="se-draft" class="se-draft" hidden>'
            '<span id="se-draft-msg"></span>'
            '<button id="se-draft-load" class="p-btn" type="button">LOAD IT</button>'
            '</div>'
            '<details class="se-help"><summary>How the text works</summary><ul>'
            '<li>First line is the song title.</li>'
            '<li><code>[G]</code> goes right before the syllable the chord lands on.</li>'
            '<li>A blank line starts a new verse.</li>'
            '<li>A short label alone at the top of a verse: <code>1</code>, <code>2</code>, '
            '<code>C</code> (chorus), <code>B</code> (bridge).</li>'
            '<li>A last verse labeled <code>Notes</code> is for musicians only.</li>'
            '<li><code>[Speed:4]</code> <code>[Key:G]</code> <code>[Capo:3]</code> '
            'go on their own lines under the title.</li>'
            '<li>Made a mess? <b>Restore original</b> puts the song back.</li>'
            '</ul></details>'
            # The newline right after <textarea> is eaten by the browser, so
            # a file that starts with a blank line keeps it.
            '<textarea id="se-ta" class="se-ta" spellcheck="false" autocapitalize="off" '
            'autocomplete="off" autocorrect="off" aria-label="Song text">\n'
            f'{escape(raw)}</textarea>'
            '<div class="se-text-foot">'
            '<span id="se-text-status" class="se-text-status" role="status" aria-live="polite"></span>'
            '<button id="se-text-cancel" class="listen-x se-cancel" type="button">Cancel</button>'
            '<button id="se-text-save" class="listen-play" type="button">Save</button>'
            '</div>'
            '</div>'
        )
    return (
        '<div id="se-tools" class="se-tools" hidden>'
        f'{edit_btn}'
        '<button id="se-revert" class="se-revert" type="button">&#8634; Restore original</button>'
        '</div>'
        f'{editor}'
    )


def render_song_editor(number, capo_meta: str = "") -> str:
    """Chord-edit popup, whole-song text editor, Restore original, and
    the save wiring for all of them, for the musician page. Always
    returned (so the capo reminder works offline); the save wiring and
    the Edit song / Restore original buttons only appear when
    PRAYER_TOKEN is set, exactly like the events form's button."""
    try:
        capo = int(str(capo_meta).strip())
    except (TypeError, ValueError):
        capo = 0
    if not (0 <= capo <= MAX_CAPO):
        capo = 0
    tok = _token()
    attrs = (f'data-num="{escape(str(number))}" data-capo="{capo}" '
             f'data-branch="{escape(BRANCH)}" data-maxtext="{MAX_TEXT}"')
    tools = ""
    if tok:
        attrs += f' data-repo="{escape(_repo())}" data-t="{escape(tok[::-1])}"'
        raw = None
        path = find_hymn(int(number))
        if path is not None:
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                pass
        tools = _render_tools(number, raw)
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
        f'{tools}' +
        '<div id="se-toast" class="se-toast" role="status" aria-live="polite" hidden></div>'
        '</div>\n'
        f"<script>{SONGEDIT_JS}</script>"
    )


if __name__ == "__main__":
    if sys.argv[1:2] == ["set"]:
        sys.exit(_apply_from_env())
    print("Usage: python3 songedit.py set   "
          "(reads ED_ACTION, ED_HYMN, ED_CAPO | ED_CI/ED_FROM/ED_TO | ED_TEXT/ED_BASE)")
    sys.exit(2)
