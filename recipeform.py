"""The "Add a recipe" form on the Community Cookbook page.

Works like the prayer and event forms. When the PRAYER_TOKEN
repository secret is set (the same token those forms use), the
cookbook page gets an "+ Add a recipe" button. It starts the
"Add recipe" GitHub Action (.github/workflows/recipes.yml), which runs
"python3 recipeform.py add" to put the recipe at the END of
cookbook.txt (so no existing recipe's address changes), saves it, and
rebuilds the site. It's in the cookbook a minute or two later. The
phone that sent it shows it in the list right away, marked "Adding",
until the real one arrives. Without the secret (like on your own
computer), there's no button.

The form has everything cookbook.txt understands: name, who it's from,
prep / cook / total time, serves, an icon (or "pick for me"), a short
intro, ingredients, directions and notes. It writes the recipe in the
same layout as the example at the top of cookbook.py.

Anything typed that cookbook.txt would misread is quietly defused:
a line like "Bake: 350 for 30 minutes" in the directions would be read
as the Cook time, so it's written "Bake - 350 for 30 minutes"; a line
that's just "Notes" would start a Notes section, so it gets a period;
a line of dashes would split the recipe in two, so it's dropped; a #
at the start of a line would hide it, so it's removed.

cookbook.py needs two lines for this (see its render_cookbook):
    from recipeform import render_recipe_form
and render_recipe_form() just under the count strip.
"""
from __future__ import annotations

import json
import os
import re
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent

MAX_NAME = 80        # recipe name
MAX_FROM = 40        # who it's from
MAX_STAT = 30        # prep / cook / total / serves
MAX_INTRO = 400
MAX_INGREDIENTS = 2000
MAX_DIRECTIONS = 4000
MAX_NOTES = 800
MAX_LINES = 60       # most lines in any one box
BRANCH = "main"
SEPARATOR = "-" * 60


# ─────────────────────────────────────────────────────────────
# Writing a recipe into cookbook.txt (run by the "Add recipe" Action)

def _one(value, limit: int) -> str:
    """One line: control characters and runs of spaces squashed."""
    s = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return re.sub(r"\s+", " ", s).strip()[:limit].strip()


def _safe(line: str) -> str:
    """A line of the recipe, made sure it reads as plain content."""
    from cookbook import SEP_RE, _field, _section
    line = re.sub(r"^#+\s*", "", line).strip()
    if not line or SEP_RE.match(line):
        return ""
    if _section(line):
        return line.rstrip(":").strip() + "."        # "Notes" -> "Notes."
    fld = _field(line)
    if fld and fld[0]:
        return re.sub(r"\s*:\s*", " - ", line, count=1).strip()   # "Bake: 350" -> "Bake - 350"
    return line


def _many(value, limit: int) -> list[str]:
    """A box of lines: blank lines dropped, each line made safe."""
    out, total = [], 0
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    for raw in text.split("\n"):
        line = _safe(_one(raw, limit))
        if not line:
            continue
        line = line[:limit - total].strip()
        if line:
            out.append(line)
            total += len(line)
        if total >= limit or len(out) >= MAX_LINES:
            break
    return out


def recipe_lines(data: dict) -> list[str] | None:
    """The recipe as cookbook.txt lines, or None if the name,
    ingredients or directions are missing."""
    from cookbook import ICONS
    name = _safe(_one(data.get("name"), MAX_NAME))
    ingredients = _many(data.get("ingredients"), MAX_INGREDIENTS)
    directions = _many(data.get("directions"), MAX_DIRECTIONS)
    if not name or not ingredients or not directions:
        return None
    # The name twice: the link text, then the page title.
    lines = [name, name]
    for label, key, limit in (("From", "from", MAX_FROM), ("Prep", "prep", MAX_STAT),
                              ("Cook", "cook", MAX_STAT), ("Total", "total", MAX_STAT),
                              ("Serves", "serves", MAX_STAT)):
        value = _one(data.get(key), limit)
        if value:
            lines.append(f"{label}: {value}")
    icon = re.sub(r"[^a-z]", "", str(data.get("icon") or "").lower())
    if icon in ICONS:
        lines.append(f"Icon: {icon}")
    intro = _many(data.get("intro"), MAX_INTRO)
    if intro:
        lines += [""] + intro
    lines += ["", "Ingredients"] + ingredients
    lines += ["", "Directions"] + directions
    notes = _many(data.get("notes"), MAX_NOTES)
    if notes:
        lines += ["", "Notes"] + notes
    return lines


def append_recipe(current: str, lines: list[str]) -> str:
    """cookbook.txt with the recipe added at the end, after a line of
    dashes (unless the file already ends with one)."""
    from cookbook import SEP_RE
    text = current.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").rstrip()
    block = "\n".join(lines) + "\n"
    if not text.strip():
        return block
    real = [ln for ln in text.split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    if real and SEP_RE.match(real[-1]):
        return text + "\n\n" + block
    return text + "\n\n" + SEPARATOR + "\n\n" + block


def add_recipe_from_env() -> int:
    """"python3 recipeform.py add": adds the recipe in RC_RECIPE (the
    form's boxes, as JSON) to the end of cookbook.txt."""
    from cookbook import COOKBOOK_PATH, parse_recipes
    try:
        data = json.loads(os.environ.get("RC_RECIPE") or "")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        print("::error::The recipe didn't come through. Nothing added.")
        return 1
    lines = recipe_lines(data)
    if lines is None:
        print("::error::The recipe needs a name, ingredients and directions. Nothing added.")
        return 1
    current = COOKBOOK_PATH.read_text(encoding="utf-8-sig") if COOKBOOK_PATH.exists() else ""
    COOKBOOK_PATH.write_text(append_recipe(current, lines), encoding="utf-8")
    count = len(parse_recipes() or [])
    print(f"Added recipe #{count}.")
    return 0


# ─────────────────────────────────────────────────────────────
# The form

def _token() -> str:
    return os.environ.get("PRAYER_TOKEN", "").strip()


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "grace-house-kids/grace-house-hymnal")


def render_recipe_form() -> str:
    """The "+ Add a recipe" button, its form, styles and script. Empty
    when there's no token. Borrows the prayer form's look (the pr-
    classes in prayer.py's CSS)."""
    if not _token():
        return ""
    from cookbook import ICON_NAMES, ICON_WORDS, icon_svg

    tiles = "".join(
        f'<label class="rf-ico" title="{escape(n)}">'
        f'<input type="radio" name="icon" value="{escape(n)}">'
        f'<span class="rf-ico-box">{icon_svg(n)}</span>'
        f'<span class="rf-sr">{escape(n)}</span></label>'
        for n in ICON_NAMES
    )
    auto = (
        '<label class="rf-ico rf-auto" title="Pick for me">'
        '<input type="radio" name="icon" value="" checked>'
        f'<span class="rf-ico-box"><span id="rf-auto-svg">{icon_svg("fork")}</span>'
        "<span>Pick for me</span></span></label>"
    )

    def box(id_, label, hint, rows, limit, required=False):
        hint_html = f" <span>{hint}</span>" if hint else ""
        req = " required" if required else ""
        return (f'<label class="pr-label" for="{id_}">{label}{hint_html}</label>'
                f'<textarea id="{id_}" rows="{rows}" maxlength="{limit}"{req}></textarea>')

    def stat(id_, label, placeholder):
        return (f'<div><label class="pr-label" for="{id_}">{label}</label>'
                f'<input id="{id_}" type="text" maxlength="{MAX_STAT}" '
                f'placeholder="{escape(placeholder)}"></div>')

    js = (RECIPEFORM_JS
          .replace("__ICON_WORDS__", json.dumps(ICON_WORDS))
          .replace("__MAX_NAME__", str(MAX_NAME))
          .replace("__MAX_FROM__", str(MAX_FROM)))
    return (
        f"<style>{RECIPEFORM_CSS}</style>\n"
        f'<div class="pr-add" id="rf-add" data-repo="{escape(_repo())}" '
        f'data-branch="{escape(BRANCH)}" data-t="{escape(_token()[::-1])}">'
        '<button type="button" class="pr-add-open" id="rf-open" '
        'aria-expanded="false" aria-controls="rf-form">+ Add a recipe</button>'
        '<form class="pr-form" id="rf-form" hidden>'
        '<label class="pr-label" for="rf-name">Recipe name</label>'
        f'<input id="rf-name" type="text" maxlength="{MAX_NAME}" required autocapitalize="words">'
        '<label class="pr-label" for="rf-from">From <span>optional. Your name, or whose recipe it is.</span></label>'
        f'<input id="rf-from" type="text" maxlength="{MAX_FROM}" autocapitalize="words">'
        '<div class="rf-stats">'
        + stat("rf-prep", "Prep", "15 min") + stat("rf-cook", "Cook", "1 hr")
        + stat("rf-total", "Total", "optional") + stat("rf-serves", "Serves", "6")
        + "</div>"
        '<fieldset class="rf-icons"><legend class="pr-label">Icon</legend>'
        f'<div class="rf-grid">{auto}{tiles}</div></fieldset>'
        + box("rf-intro", "Intro", "optional. A sentence or two of story.", 2, MAX_INTRO)
        + box("rf-ing", "Ingredients",
              'One per line. A line ending in a colon, like "For the sauce:", starts a group.',
              5, MAX_INGREDIENTS, required=True)
        + box("rf-dir", "Directions", "One step per line. They get numbered for you.",
              5, MAX_DIRECTIONS, required=True)
        + box("rf-notes", "Notes", "optional. Tips, swaps, stories.", 2, MAX_NOTES)
        + '<p class="pr-form-note">It goes in the cookbook in a couple of minutes, '
        "where anyone with the site link can see it.</p>"
        '<div class="pr-form-row">'
        '<button type="submit" class="pr-send" id="rf-send">Add recipe</button>'
        '<button type="button" class="pr-cancel" id="rf-cancel">Cancel</button>'
        "</div>"
        "</form>"
        '<p class="pr-status" id="rf-status" role="status" aria-live="polite"></p>'
        "</div>\n"
        f"<script>{js}</script>"
    )


# Starts the "Add recipe" Action with the whole form as one JSON box,
# then shows the recipe at the end of this phone's list straight away,
# marked "Adding", until the page loads with the real one. Gives up on
# it after 20 minutes. "Pick for me" shows the icon the site will pick,
# using the same word list as cookbook.py.
RECIPEFORM_JS = r"""
(function () {
  var box = document.getElementById('rf-add');
  if (!box) return;
  var token = box.getAttribute('data-t').split('').reverse().join('');
  var url = 'https://api.github.com/repos/' + box.getAttribute('data-repo') +
            '/actions/workflows/recipes.yml/dispatches';
  var branch = box.getAttribute('data-branch') || 'main';
  function $(id) { return document.getElementById(id); }
  var form = $('rf-form'), open = $('rf-open'), send = $('rf-send'), status = $('rf-status');
  var f = { name: $('rf-name'), from: $('rf-from'), prep: $('rf-prep'), cook: $('rf-cook'),
            total: $('rf-total'), serves: $('rf-serves'), intro: $('rf-intro'),
            ingredients: $('rf-ing'), directions: $('rf-dir'), notes: $('rf-notes') };
  var WORDS = __ICON_WORDS__;
  var PENDING = 'gh-recipe-pending', PENDING_LIFE = 20 * 60 * 1000;

  function line(s, max) {
    return String(s || '').replace(/[\u0000-\u001f\u007f]/g, ' ')
      .replace(/\s+/g, ' ').trim().slice(0, max).trim();
  }
  function norm(s) { return String(s).toLowerCase().replace(/[^0-9a-z\u00c0-\u024f]+/g, ''); }
  function esc(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  // Same guess as cookbook.py's _pick_icon: the name first, then the
  // name and ingredients together.
  function guess() {
    var name = f.name.value.toLowerCase();
    var all = (f.name.value + ' ' + f.name.value + ' ' + f.ingredients.value.replace(/\n/g, ' ')).toLowerCase();
    var hays = [name, all];
    for (var h = 0; h < hays.length; h++) {
      for (var i = 0; i < WORDS.length; i++) {
        for (var j = 0; j < WORDS[i][1].length; j++) {
          if (new RegExp('(^|[^a-z])' + esc(WORDS[i][1][j]) + '(?![a-z])').test(hays[h])) return WORDS[i][0];
        }
      }
    }
    return 'fork';
  }
  function svgFor(name) {
    var el = form.querySelector('.rf-ico input[value="' + name + '"] + .rf-ico-box svg');
    return el ? el.cloneNode(true) : null;
  }
  function chosen() {
    var c = form.querySelector('input[name="icon"]:checked');
    return c ? c.value : '';
  }
  function showGuess() {
    var holder = $('rf-auto-svg'), svg = svgFor(guess());
    if (holder && svg) { holder.innerHTML = ''; holder.appendChild(svg); }
  }
  f.name.addEventListener('input', showGuess);
  f.ingredients.addEventListener('input', showGuess);

  function loadPending() { try { return JSON.parse(localStorage.getItem(PENDING)) || []; } catch (e) { return []; } }
  function savePending(list) { try { localStorage.setItem(PENDING, JSON.stringify(list)); } catch (e) {} }
  function list() { return document.querySelector('.rc-list'); }

  // How many real recipes in the list have the same name.
  function matches(p) {
    var names = document.querySelectorAll('.rc-list li:not(.rc-pending) .rc-name'), n = 0;
    for (var i = 0; i < names.length; i++) if (norm(names[i].textContent) === norm(p.name)) n++;
    return n;
  }

  function makeItem(p) {
    var li = document.createElement('li');
    li.className = 'rc-pending';
    li.setAttribute('data-pending', p.id);
    li.innerHTML = '<div class="rc-row"><span class="rc-ico"></span><span class="rc-txt">' +
      '<span class="rc-name"></span><span class="rc-by"></span>' +
      '<span class="rc-adding">Adding. Only you can see this until the cookbook updates.</span>' +
      '</span></div>';
    var svg = svgFor(p.icon) || svgFor('fork');
    if (svg) li.querySelector('.rc-ico').appendChild(svg);
    li.querySelector('.rc-name').textContent = p.name;
    var by = li.querySelector('.rc-by');
    if (p.from) by.textContent = 'From ' + p.from; else by.parentNode.removeChild(by);
    return li;
  }

  function recount() {
    var tag = document.querySelector('.meta-strip .count-tag'), l = list();
    if (!tag || !l) return;
    var n = l.querySelectorAll('li').length;
    tag.textContent = n + (n === 1 ? ' recipe' : ' recipes');
  }

  function showPending() {
    var l = list();
    if (!l) return;
    var i, old = l.querySelectorAll('.rc-pending');
    for (i = 0; i < old.length; i++) l.removeChild(old[i]);
    var now = Date.now(), keep = [];
    loadPending().forEach(function (p) {
      if (!p || !p.name || now - p.sent > PENDING_LIFE) return;
      if (matches(p) > (p.before || 0)) return;
      keep.push(p);
      l.appendChild(makeItem(p));
    });
    savePending(keep);
    recount();
  }

  function show(on) {
    form.hidden = !on;
    open.hidden = on;
    open.setAttribute('aria-expanded', String(on));
    if (on) { status.textContent = ''; showGuess(); f.name.focus(); }
  }
  open.onclick = function () { show(true); };
  $('rf-cancel').onclick = function () { show(false); open.focus(); };

  form.onsubmit = function (e) {
    e.preventDefault();
    var p = { id: String(Date.now()), name: line(f.name.value, __MAX_NAME__).replace(/^#+\s*/, ''),
              from: line(f.from.value, __MAX_FROM__), icon: chosen() || guess(), sent: Date.now() };
    if (!p.name) { f.name.focus(); return; }
    if (!f.ingredients.value.trim()) { f.ingredients.focus(); return; }
    if (!f.directions.value.trim()) { f.directions.focus(); return; }
    var recipe = { icon: chosen() };
    for (var k in f) recipe[k] = f[k].value;
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
      body: JSON.stringify({ ref: branch, inputs: { recipe: JSON.stringify(recipe) } })
    }).then(function (r) {
      if (r.ok) return;
      return r.json().catch(function () { return {}; }).then(function (j) {
        var err = new Error((j && j.message) || '');
        err.status = r.status;
        throw err;
      });
    }).then(function () {
      for (var k in f) if (k !== 'from') f[k].value = '';   // "from" stays, for the next one
      var autoBox = form.querySelector('input[name="icon"][value=""]');
      if (autoBox) autoBox.checked = true;
      show(false);
      p.before = matches(p);      // a recipe with the same name already (rare)
      var pending = loadPending();
      pending.push(p);
      savePending(pending);
      showPending();
      status.textContent = 'Added. Everyone else will see it in a couple of minutes.';
      var el = document.querySelector('[data-pending="' + p.id + '"]');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }).catch(function (err) {
      status.textContent = (err && err.status)
        ? 'That didn\u2019t go through. GitHub said: ' + err.status +
          (err.message ? ' ' + err.message : '') +
          '. Please let whoever looks after the site know.'
        : 'That didn\u2019t go through. Check your connection and tap Add recipe again.';
    }).then(function () {
      send.disabled = false;
      send.textContent = 'Add recipe';
    });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showPending);
  else showPending();
})();
"""


# Only what the prayer form's styles (prayer.py) don't already cover.
RECIPEFORM_CSS = r"""
.rf-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 0 10px; }
.rf-stats > div { min-width: 0; }

/* Icon picker: "Pick for me" plus every food icon, as tiles. */
.rf-icons { margin: 0 0 16px; padding: 0; border: 0; min-width: 0; }
.rf-icons legend { padding: 0; }
.rf-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(44px, 1fr));
  gap: 6px;
}
.rf-ico { position: relative; display: block; cursor: pointer; -webkit-tap-highlight-color: transparent; }
.rf-ico input { position: absolute; opacity: 0; width: 1px; height: 1px; margin: 0; }
.rf-ico-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 44px;
  border: 2px solid #0a0a0a;
  background: #fffdf8;
  color: #0a0a0a;
}
.rf-ico-box svg { display: block; width: 26px; height: 26px; }
#rf-auto-svg { display: block; }
.rf-auto { grid-column: span 3; }
.rf-auto .rf-ico-box {
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.rf-ico input:checked + .rf-ico-box { background: #f01a8b; border-color: #f01a8b; }
.rf-ico input:focus-visible + .rf-ico-box { outline: 3px solid #f01a8b; outline-offset: 2px; }
@media (hover: hover) {
  .rf-ico:hover .rf-ico-box { border-color: #f01a8b; }
}
.rf-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

/* A recipe this phone just sent, until the real one arrives. */
.rc-list li.rc-pending {
  border-left: 3px dashed #f01a8b;
  margin-left: -13px;
  padding-left: 10px;
}
.rc-pending .rc-row { display: flex; align-items: center; gap: 14px; padding: 11px 6px; }
.rc-adding {
  display: block;
  margin-top: 6px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.5;
  opacity: 0.6;
}
"""


if __name__ == "__main__":
    if sys.argv[1:] == ["add"]:
        sys.exit(add_recipe_from_env())
    print("Usage: python3 recipeform.py add   (reads RC_RECIPE)")
    sys.exit(2)
