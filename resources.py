"""resources.py — downloadable files, grouped into categories.

Drop files into ./resources/<category>/ and they show up under the
Resources section: the Resources page lists each category, and each
category page lists its files with a download link (image files also
get a small preview).

    resources/
      tracts/
        01-the-gospel.pdf
        02-who-is-jesus.pdf
      shirt-designs/
        wheel-front.png
        wheel-back.png

Adding a category is just making a new folder — no code changes, same
as dropping a hymn in ./hymns.

Names: category folders and file names both take an OPTIONAL "NN-"
number prefix that sets their order and is stripped from what's shown.
The rest of the name becomes a title (dashes/underscores -> spaces,
Title Case). So "01-the-gospel.pdf" is shown as "The Gospel", and the
folder "02-shirt designs" is shown as "Shirt Designs" at the address
/resources/shirt-designs/.

Optional blurb: put an "about.txt" in a category folder. Its first
line is shown as a one-line description under the category. It is not
listed as a downloadable file.
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
RESOURCES_DIR = HERE / "resources"

# Never listed as downloadable files.
_HIDDEN = {"about.txt", ".ds_store", "thumbs.db"}
# Files we show a thumbnail for instead of a type badge.
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
# Leading "01-", "02_", "3 " ... used for ordering, stripped from display.
_NUM_PREFIX = re.compile(r"^\s*(\d+)\s*[-_. ]\s*(.+)$")


def _split_order(name: str) -> tuple[int, str]:
    """'01-the-gospel' -> (1, 'the-gospel'). No prefix -> (big, name)."""
    m = _NUM_PREFIX.match(name)
    if m:
        return int(m.group(1)), m.group(2)
    return 10 ** 9, name


def _titleize(stem: str) -> str:
    words = re.split(r"[-_ ]+", stem.strip())
    return " ".join(w[:1].upper() + w[1:] for w in words if w) or stem


def _slugify(stem: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f}".rstrip("0").rstrip(".") + f" {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def parse_resources():
    """Return [category, ...] or None if there's nothing to show.

    Each category is a dict:
        slug   URL segment ("shirt-designs")
        folder on-disk folder name (used to find files, never in a URL)
        title  display name ("Shirt Designs")
        desc   one-line blurb from about.txt, or ""
        files  [file, ...]
    Each file is a dict:
        name     on-disk filename ("01-the-gospel.pdf")
        title    display title ("The Gospel")
        ext      lowercase extension without dot ("pdf")
        size     human size ("1.2 MB") or ""
        is_image whether to show a preview thumbnail
    """
    if not RESOURCES_DIR.is_dir():
        return None
    categories = []
    for folder in RESOURCES_DIR.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        desc = ""
        about = folder / "about.txt"
        if about.exists():
            try:
                lines = about.read_text(encoding="utf-8").strip().splitlines()
                desc = lines[0].strip() if lines else ""
            except OSError:
                desc = ""

        files = []
        for f in folder.iterdir():
            if (not f.is_file() or f.name.startswith(".")
                    or f.name.lower() in _HIDDEN):
                continue
            order, stem_name = _split_order(f.stem)
            try:
                size = _human_size(f.stat().st_size)
            except OSError:
                size = ""
            files.append({
                "name": f.name,
                "title": _titleize(stem_name),
                "ext": f.suffix.lower().lstrip("."),
                "size": size,
                "is_image": f.suffix.lower() in _IMAGE_EXTS,
                "_order": (order, f.name.lower()),
            })
        if not files:
            continue
        files.sort(key=lambda d: d["_order"])

        order, slug_stem = _split_order(folder.name)
        categories.append({
            "slug": _slugify(slug_stem),
            "folder": folder.name,
            "title": _titleize(slug_stem),
            "desc": desc,
            "files": files,
            "_order": (order, folder.name.lower()),
        })
    if not categories:
        return None
    categories.sort(key=lambda c: c["_order"])
    return categories


def find_category(categories, slug):
    return next((c for c in categories if c["slug"] == slug), None)


def find_resource_file(categories, slug, filename):
    """The Path to a file, or None. Only returns files that are actually
    listed (a whitelist match on the exact name), so a crafted URL can't
    reach outside the category folder — no path traversal is possible."""
    cat = find_category(categories, slug)
    if cat is None:
        return None
    for f in cat["files"]:
        if f["name"] == filename:
            p = RESOURCES_DIR / cat["folder"] / f["name"]
            if p.is_file():
                return p
    return None


# ─────────────────────────────────────────────────────────────
# Rendering  (returns the inner body; server.py wraps it with the
# brand mark + page() shell, same as the other sections.)
def render_resources(categories) -> str:
    """The Resources index: the bulletin button, then one card per category."""
    bulletin = (
        '<ul class="sections bulletin-cta">\n'
        '<li><a class="sec" href="bulletin">'
        '<span><span class="sec-name">Print the Bulletin</span>'
        "<span class=\"sec-sub\">This week's tri-fold, ready to fold &amp; print</span>"
        '</span><span class="sec-arrow" aria-hidden="true">→</span></a></li>\n'
        "</ul>\n"
    )
    if not categories:
        return (bulletin
                + '<p class="res-empty">Nothing here yet. Make a folder under '
                "./resources (like resources/tracts) and drop files in.</p>")
    total = sum(len(c["files"]) for c in categories)
    items = []
    for c in categories:
        n = len(c["files"])
        sub = c["desc"] or f"{n} file" + ("" if n == 1 else "s")
        items.append(
            f'<li><a class="sec" href="resources/{quote(c["slug"])}/">'
            f'<span><span class="sec-name">{escape(c["title"])}</span>'
            f'<span class="sec-sub">{escape(sub)}</span></span>'
            f'<span class="sec-arrow" aria-hidden="true">→</span></a></li>'
        )
    plural = "" if total == 1 else "s"
    meta = (
        '<div class="meta-strip">'
        f'<span class="count-tag">{total} file{plural}</span>'
        '<div class="dash-rule"></div>'
        '<span class="hint">↓ pick one</span>'
        "</div>\n"
    )
    return bulletin + meta + '<ul class="sections">\n' + "\n".join(items) + "\n</ul>"

def render_resource_category(category) -> str:
    """One category: its own title tag, an optional blurb, then the
    file list. Images get a preview; everything else a type badge."""
    files = category["files"]
    n = len(files)
    count = f"{n} file" + ("" if n == 1 else "s")

    rows = []
    for f in files:
        href = ("resources/" + quote(category["slug"]) + "/" + quote(f["name"]))
        if f["is_image"]:
            left = (f'<img class="res-thumb" src="{escape(href)}" alt="" '
                    'loading="lazy">')
        else:
            left = f'<span class="res-icon">{escape(f["ext"].upper() or "FILE")}</span>'
        sub = escape(" · ".join(b for b in (f["ext"].upper(), f["size"]) if b))
        rows.append(
            f'<li><a class="res-file" href="{escape(href)}" download>'
            f"{left}"
            '<span class="res-meta">'
            f'<span class="res-name">{escape(f["title"])}</span>'
            f'<span class="res-sub">{sub}</span></span>'
            '<span class="res-dl" aria-hidden="true">↓</span>'
            "</a></li>"
        )

    desc_html = (f'<p class="res-desc">{escape(category["desc"])}</p>'
                 if category["desc"] else "")
    meta = (
        '<div class="meta-strip">'
        f'<span class="count-tag">{count}</span>'
        '<div class="dash-rule"></div>'
        '<span class="hint">↓ tap to save</span>'
        "</div>\n"
    )
    return (
        f'<div class="title-tag"><h1>{escape(category["title"].upper())}</h1></div>\n'
        f"{meta}"
        f"{desc_html}"
        '<ul class="res-files">\n' + "\n".join(rows) + "\n</ul>"
    )


# ─────────────────────────────────────────────────────────────
# Styles  (server.py does:  CSS += RESOURCES_CSS)

RESOURCES_CSS = r"""
/* The bulletin button sits below the title tag and above the file
   categories, with a little air on both sides so it doesn't jam up
   under the RESOURCES chip. */
.bulletin-cta { margin: 124px 0 22px; }
/* ────────────────────────────────────────────────────────────
   RESOURCES — category cards reuse .sec; per-category file lists
   get their own rows with an image preview or a type badge.
   ──────────────────────────────────────────────────────────── */
.res-files {
  list-style: none;
  margin: 20px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.res-file {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  background: #f2ede4;
  border: 3px solid #0a0a0a;
  box-shadow: 4px 4px 0 #0a0a0a;
  color: #0a0a0a !important;
  transition: transform 0.08s, box-shadow 0.08s;
}
.res-file:active { transform: translate(3px, 3px); box-shadow: 1px 1px 0 #0a0a0a; }
.res-file:active { background: #f01a8b; }
@media (hover: hover) { .res-file:hover { background: #f01a8b; } }
.res-file:focus-visible { outline: 3px solid #f01a8b; outline-offset: 4px; }

.res-thumb {
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  object-fit: cover;
  background: #ffffff;
  border: 2px solid #0a0a0a;
}
.res-icon {
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a0a0a;
  color: #f2ede4;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 14px;
  letter-spacing: 1px;
}
.res-meta { flex: 1; min-width: 0; }
.res-name {
  display: block;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 700;
  font-size: 20px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  line-height: 1.05;
  word-break: break-word;
}
.res-sub {
  display: block;
  margin-top: 4px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 12px;
  color: #3a3a3a;
}
.res-dl {
  flex-shrink: 0;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 30px;
  color: #f01a8b;
}
.res-file:active .res-dl,
.res-file:active .res-name,
.res-file:active .res-sub { color: #0a0a0a; }
@media (hover: hover) {
  .res-file:hover .res-dl,
  .res-file:hover .res-name,
  .res-file:hover .res-sub { color: #0a0a0a; }
}

.res-desc {
  margin: 8px 0 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.55;
  color: #3a3a3a;
}
.res-empty {
  margin: 26px 0 6px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.55;
}

/* These rows have their own solid background, so kill the beige halo
   inherited from body (same reason the other chips/cards do). */
.res-file, .res-file *,
.res-icon {
  -webkit-text-stroke-width: 0 !important;
  -webkit-text-stroke-color: transparent !important;
  paint-order: normal !important;
}
"""
