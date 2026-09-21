#!/usr/bin/env python3
"""Grace House — Community Cookbook.

Every recipe lives in ONE file: ./cookbook.txt. Recipes are separated by
a line of three or more dashes. Here's a whole recipe:

    Mike's Awesome Burritos
    Mike's Awesome Burritos
    From: Mike
    Prep: 10 min
    Cook: 20 min
    Serves: 4

    Ingredients
    Frozen waffles, a cup of frozen bananas, a splash of pickle juice

    Directions
    1. Smash bananas
    2. Reconstitute smashed bananas
    3. Make burrito

    Notes
    Mike swears by the pickle juice. We have questions.

    ------------------------------------------------------------

    (the next recipe starts here)

THE TWO TITLE LINES
    Line 1 is the LINK TEXT on the cookbook index page.
    Line 2 is the TITLE at the top of the recipe's own page.
    Type the same thing twice if you want them the same. Use two
    different lines when the short one reads better in a list:

        Mike's Burritos
        Mike's Awesome Late-Night Burritos

    If line 2 is a field ("From: Mike") or a section heading
    ("Ingredients"), the link text is used as the page title too.

FIELDS — one per line, in any order, anywhere before the sections:
    From:    who gave us the recipe      (also: By)
    Prep:    prep time                   (also: Prep time)
    Cook:    cook or bake time           (also: Cook time, Bake)
    Total:   total time                  (optional)
    Serves:  how many it feeds           (also: Servings, Makes, Yield)
    Icon:    which food icon to use      (see the list below)
    Write the times however you like: "20 min", "1 hr 15", "overnight".

SECTIONS — a heading alone on its own line, colon optional:
    Ingredients   (also: Ingredient)
    Directions    (also: Instructions, Steps, Method)
    Notes         (also: Note, Tips)
    Any lines before the first section heading become a short
    introduction under the title — good for a sentence of story.

INGREDIENTS can be one per line, with or without "- " in front. If
you put them all on ONE line with commas, the commas become the list:
    Frozen waffles, a cup of frozen bananas, a splash of pickle juice
One per line gives you exact control (use it when an ingredient has a
comma of its own, like "1 cup flour, sifted").

DIRECTIONS get numbered automatically. "1." "2)" "- " at the start of
a line are stripped, so you can number them yourself in the file and
they won't end up doubled.

SUB-HEADINGS: inside Ingredients or Directions, a short line ending
in a colon becomes a sub-heading — handy for "For the sauce:".

ICONS. Each recipe gets a little food icon on the index page and a
big one on its own page. It's picked automatically from the recipe's
name and ingredients (chili gets a pot, pie gets a pie). To choose it
yourself, add an Icon line. Names you can use:

    apple  bowl  bread  burrito  cake  cheese  chicken  coffee
    cookie  corn  dish  drink  egg  fish  icecream  jar  muffin
    noodles  pancakes  pepper  pie  pizza  pot  roast  salad
    sandwich  skillet  taco  waffle  fork

The order recipes appear in cookbook.txt is the order they appear on
the page, and it's also their address: the third recipe in the file
lives at /{key}/cookbook/3/. Moving a recipe changes its address, so
don't reorder the file right after texting someone a link to one.
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path
from recipeform import render_recipe_form

HERE = Path(__file__).resolve().parent
COOKBOOK_PATH = HERE / "cookbook.txt"


# ─────────────────────────────────────────────────────────────
# Food icons
#
# Each one is the inside of a 24x24 SVG, drawn in single strokes so it
# matches the hand-inked look of the rest of the site. They use
# currentColor, so they turn pink or black along with the text.

ICONS: dict[str, str] = {
    "pot": """<path d="M4 10h16v5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4Z"/>
<path d="M2.5 10h19"/>
<path d="M4 12H2.6a1.4 1.4 0 0 0 0 2.8H4"/>
<path d="M20 12h1.4a1.4 1.4 0 0 1 0 2.8H20"/>
<path d="M9 7.6c0-1.2 1.2-1.4 1.2-2.6"/>
<path d="M13.8 7.6c0-1.2 1.2-1.4 1.2-2.6"/>""",

    "bowl": """<path d="M3 11.5h18a9 9 0 0 1-18 0Z"/>
<path d="M7.5 20.2h9"/>
<path d="M9 8.6c0-1.2 1.2-1.4 1.2-2.6"/>
<path d="M13.8 8.6c0-1.2 1.2-1.4 1.2-2.6"/>""",

    "bread": """<path d="M3.5 12.5A4.5 4.5 0 0 1 8 8h8a4.5 4.5 0 0 1 4.5 4.5V18a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1Z"/>
<path d="M8.4 8.2V19M12 8V19M15.6 8.2V19"/>""",

    "cake": """<path d="M4 19.5v-6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v6Z"/>
<path d="M4 16.2c1.6 0 1.6 1.4 3.2 1.4s1.6-1.4 3.2-1.4 1.6 1.4 3.2 1.4 1.6-1.4 3.2-1.4 1.6 1.4 3.2 1.4"/>
<path d="M12 11.5V8.6"/>
<path d="M12 7.6c.9-1 0-2.2 0-2.2s-.9 1.2 0 2.2Z"/>
<path d="M2.8 19.5h18.4"/>""",

    "pie": """<path d="M2.6 13.4a9.4 9.4 0 0 1 18.8 0Z"/>
<path d="M2 13.4h20v1.9a2.4 2.4 0 0 1-2.4 2.4H4.4A2.4 2.4 0 0 1 2 15.3Z"/>
<path d="M7.2 10.9 9 7.6M12 9.7V6.2M16.8 10.9 15 7.6"/>""",

    "cookie": """<circle cx="12" cy="12" r="8.6"/>
<circle cx="9.4" cy="9.8" r="1.05" fill="currentColor" stroke="none"/>
<circle cx="14.2" cy="9.6" r="1.05" fill="currentColor" stroke="none"/>
<circle cx="12.4" cy="14.2" r="1.05" fill="currentColor" stroke="none"/>
<circle cx="8.6" cy="14.4" r="1.05" fill="currentColor" stroke="none"/>
<circle cx="16" cy="13.6" r="1.05" fill="currentColor" stroke="none"/>""",

    "skillet": """<circle cx="10" cy="13" r="6.6"/>
<path d="M16.5 12.2 22 10.3" stroke-width="2.2"/>
<ellipse cx="10" cy="13" rx="3.1" ry="2.5"/>
<circle cx="10" cy="13" r="0.9" fill="currentColor" stroke="none"/>""",

    "burrito": """<rect x="3.5" y="8" width="17" height="8" rx="4"/>
<path d="M8.2 8.2 6.6 15.8M12.6 8 11 16M17 8.2 15.4 15.8"/>""",

    "taco": """<path d="M2.6 16.4a9.4 9.4 0 0 1 18.8 0Z"/>
<path d="M2.6 16.4h18.8"/>
<path d="M5.8 13.2c1.5-1.1 2.7 1 4.2 0s2.7 1 4.2 0 2.7 1 4.2 0"/>""",

    "pizza": """<path d="M12 3.4 4 19.8a20 20 0 0 1 16 0Z"/>
<path d="M5.4 16.6a15 15 0 0 1 13.2 0"/>
<circle cx="12" cy="10.4" r="1.1" fill="currentColor" stroke="none"/>
<circle cx="9.6" cy="15" r="1.1" fill="currentColor" stroke="none"/>
<circle cx="14.4" cy="14.7" r="1.1" fill="currentColor" stroke="none"/>""",

    "chicken": """<path d="M19.2 4.8a4.2 4.2 0 0 0-5.9 0L9 9.1l5.9 5.9 4.3-4.3a4.2 4.2 0 0 0 0-5.9Z"/>
<path d="M9 9.1 5.7 12.4"/>
<circle cx="4.7" cy="15.3" r="2.3"/>
<circle cx="7.8" cy="18.4" r="2.3"/>""",

    "fish": """<ellipse cx="13" cy="12" rx="7.4" ry="5"/>
<path d="M5.6 12 1.6 8.4v7.2Z"/>
<circle cx="16.4" cy="10.4" r="0.9" fill="currentColor" stroke="none"/>
<path d="M11.5 8.4c1.2 2.4 1.2 4.8 0 7.2"/>""",

    "egg": """<path d="M12 3.4c3.6 0 6.6 5.1 6.6 9.1a6.6 6.6 0 0 1-13.2 0c0-4 3-9.1 6.6-9.1Z"/>""",

    "salad": """<path d="M3 12.5h18a9 9 0 0 1-18 0Z"/>
<path d="M8.2 12.5c-1.5-2.2-.7-4.5 1.6-5.6.5 2.5-.1 4.4-1.6 5.6Z"/>
<path d="M13.4 12.5c-2.2-1.3-2.6-3.7-1.2-5.8 1.9 1.6 2.4 3.7 1.2 5.8Z"/>
<circle cx="16.8" cy="10.2" r="2"/>""",

    "coffee": """<path d="M4 8.6h13v6.6a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4Z"/>
<path d="M17 10.2h1.8a2.6 2.6 0 0 1 0 5.2H17"/>
<path d="M3 21.4h15"/>
<path d="M8 5.6c0-1.2 1.2-1.4 1.2-2.6M12.6 5.6c0-1.2 1.2-1.4 1.2-2.6"/>""",

    "drink": """<path d="M6.4 5.4h11.2l-1.4 14a1.6 1.6 0 0 1-1.6 1.4H9.4a1.6 1.6 0 0 1-1.6-1.4Z"/>
<path d="M6.8 9.6h10.4"/>
<path d="M14.6 5.4 17.8 2"/>""",

    "apple": """<path d="M12 8.3c1-1.3 2.6-1.9 4.1-1.5 2.6.7 4 3.7 3 7-.9 3-3 6.5-5.1 6.5-1 0-1.4-.5-2-.5s-1 .5-2 .5c-2.1 0-4.2-3.5-5.1-6.5-1-3.3.4-6.3 3-7 1.5-.4 3.1.2 4.1 1.5Z"/>
<path d="M12 8.3V5.2"/>
<path d="M12 5.4c1.7-.4 2.9-1.7 3.1-3.3-1.9.1-3.1 1.4-3.1 3.3Z"/>""",

    "cheese": """<path d="M3 11.5 13.4 5.4 21 9.4V16a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 16Z"/>
<circle cx="8" cy="14" r="1.4"/>
<circle cx="14" cy="12.6" r="1.1"/>
<circle cx="17.4" cy="15" r="1"/>""",

    "corn": """<path d="M12 3c3.4 0 5.6 3.4 5.6 8s-2.2 9-5.6 9-5.6-4.4-5.6-9S8.6 3 12 3Z"/>
<path d="M12 4.6v14.2"/>
<path d="M8.6 7.9c2.2.8 4.6.8 6.8 0M8 11.1c2.6.9 5.4.9 8 0M8.4 14.4c2.4.8 4.8.8 7.2 0"/>""",

    "pepper": """<path d="M17.2 9.2c0 5.6-4.6 10.2-10.2 10.2-1.7 0-3-1.4-3-3 0-5.1 4.1-9.2 9.2-9.2Z"/>
<path d="M13.2 5.6c1.9 0 3.5 1.5 4 3.6"/>
<path d="M13.6 5.7c-1-.6-2.3-.4-3.1.6 1.2.8 2.5.6 3.1-.6Z"/>""",

    "icecream": """<circle cx="12" cy="8.6" r="4.6"/>
<path d="M7.8 10.7 12 21l4.2-10.3"/>
<path d="M9.3 14.4h5.4"/>""",

    "dish": """<path d="M5 10.6h14v5a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2Z"/>
<path d="M3 10.6h18"/>
<path d="M3 12.3h2M19 12.3h2"/>
<path d="M8.6 7.9c0-1 1-1.3 1-2.4M14.4 7.9c0-1 1-1.3 1-2.4"/>""",

    "sandwich": """<path d="M3.6 9.6A3.5 3.5 0 0 1 7.1 6h9.8a3.5 3.5 0 0 1 3.5 3.6Z"/>
<path d="M3.6 9.6h16.8"/>
<path d="M3.2 12.2c2.4 1.2 4.3-.7 6.5.3s3.6 1 5.4 0 3.6.9 6.1-.3"/>
<path d="M4 15.4h16a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3Z"/>
<path d="M4 15.4h16"/>""",

    "waffle": """<rect x="3.6" y="5.6" width="16.8" height="12.8" rx="2"/>
<path d="M8.2 5.6v12.8M12 5.6v12.8M15.8 5.6v12.8"/>
<path d="M3.6 9.8h16.8M3.6 14.2h16.8"/>""",

    "pancakes": """<ellipse cx="12" cy="8.6" rx="8" ry="3"/>
<path d="M4 8.6v2.6c0 1.7 3.6 3 8 3s8-1.3 8-3V8.6"/>
<path d="M4 13.4V16c0 1.7 3.6 3 8 3s8-1.3 8-3v-2.6"/>
<path d="M10.4 6.6c.9-1 2.3-1 3.2 0"/>""",

    "muffin": """<path d="M6 11.2h12l-1.2 7.5a1.5 1.5 0 0 1-1.5 1.3H8.7a1.5 1.5 0 0 1-1.5-1.3Z"/>
<path d="M5.5 11.2c0-3 2.4-3.2 2.9-4.4C9 5.1 10.4 4 12 4s3 1.1 3.6 2.8c.5 1.2 2.9 1.4 2.9 4.4Z"/>""",

    "jar": """<rect x="6" y="8.2" width="12" height="11.8" rx="2"/>
<path d="M7.4 4.8h9.2v3.4H7.4Z"/>
<path d="M6 11.4h12"/>
<circle cx="10" cy="14.6" r="1.2"/>
<circle cx="14" cy="16.8" r="1.2"/>""",

    "roast": """<path d="M4 15.2a8 8 0 0 1 16 0Z"/>
<path d="M2.5 15.2h19"/>
<path d="M4.4 17.8h15.2"/>
<path d="M12 7.2V5.4"/>""",

    "noodles": """<path d="M3.4 12.5h17.2a8.6 8.6 0 0 1-17.2 0Z"/>
<path d="M6.2 12.5c0-3 1.6-4.7 3.6-4.7M10.2 12.5c0-3.6 1.8-5.5 4-5.5M14.2 12.5c0-2.8 1.4-4.4 3.2-4.4"/>
<path d="M7.6 20.2h8.8"/>""",

    "fork": """<path d="M7 3v5.2a2.5 2.5 0 0 0 5 0V3"/>
<path d="M9.5 10.7V21"/>
<ellipse cx="17" cy="6.6" rx="2.5" ry="3.6"/>
<path d="M17 10.2V21"/>""",
}

ICON_NAMES = sorted(ICONS)
DEFAULT_ICON = "fork"

# Which words point at which icon. Checked in order, so the fussier
# entries go first (chili -> pot, before jalapeno -> pepper).
ICON_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("pot", ("soup", "stew", "chili", "chile con carne", "chowder", "broth",
             "gumbo", "bisque", "stock", "beans", "crockpot", "crock pot",
             "slow cooker", "simmer")),
    ("noodles", ("pasta", "spaghetti", "noodle", "noodles", "ramen",
                 "macaroni", "mac and cheese", "alfredo", "fettuccine",
                 "linguine", "orzo")),
    ("pizza", ("pizza", "calzone", "flatbread", "stromboli")),
    ("burrito", ("burrito", "burritos", "wrap", "wraps", "enchilada",
                 "enchiladas", "quesadilla", "tortilla", "tortillas")),
    ("taco", ("taco", "tacos", "nacho", "nachos", "fajita", "fajitas")),
    ("bread", ("bread", "loaf", "roll", "rolls", "biscuit", "biscuits",
               "bun", "buns", "sourdough", "cornbread", "focaccia",
               "dough", "banana bread", "zucchini bread")),
    ("pie", ("pie", "cobbler", "tart", "crisp", "crumble", "quiche",
             "galette", "turnover")),
    ("cake", ("cake", "cupcake", "cupcakes", "frosting", "icing",
              "brownie", "brownies", "birthday")),
    ("cookie", ("cookie", "cookies", "snickerdoodle", "shortbread",
                "macaroon", "gingersnap", "biscotti")),
    ("muffin", ("muffin", "muffins", "scone", "scones")),
    ("waffle", ("waffle", "waffles")),
    ("pancakes", ("pancake", "pancakes", "flapjack", "flapjacks",
                  "french toast", "crepe", "crepes")),
    ("dish", ("casserole", "hotdish", "hot dish", "gratin", "lasagna",
              "bake", "baked", "scalloped", "au gratin")),
    ("skillet", ("skillet", "fried", "fry", "hash", "scramble", "saute",
                 "sauteed", "omelet", "omelette", "stir fry", "stir-fry",
                 "pan-fried")),
    ("egg", ("egg", "eggs", "deviled", "frittata", "custard", "meringue",
             "quiche lorraine")),
    ("chicken", ("chicken", "wing", "wings", "drumstick", "drumsticks",
                 "turkey", "poultry")),
    ("roast", ("roast", "brisket", "ham", "meatloaf", "meat loaf", "pork",
               "beef", "steak", "ribs", "pot roast", "prime rib")),
    ("fish", ("fish", "salmon", "tuna", "shrimp", "tilapia", "catfish",
              "seafood", "crab", "clam", "chowder fish")),
    ("salad", ("salad", "slaw", "coleslaw", "greens", "kale", "lettuce",
               "spinach", "veggie", "vegetable", "vegetables")),
    ("cheese", ("cheese", "queso", "cheesy", "fondue")),
    ("corn", ("corn", "elote", "maize", "grits")),
    ("pepper", ("pepper", "peppers", "spicy", "hot sauce", "salsa",
                "jalapeno", "jalapeño", "chipotle", "cayenne")),
    ("apple", ("apple", "apples", "fruit", "peach", "peaches", "pear",
               "berry", "berries", "strawberry", "blueberry", "cherry")),
    ("icecream", ("ice cream", "sundae", "gelato", "sorbet", "popsicle",
                  "milkshake", "float")),
    ("coffee", ("coffee", "tea", "cocoa", "chai", "latte", "cider",
                "mocha", "espresso")),
    ("drink", ("punch", "lemonade", "smoothie", "juice", "soda", "drink",
               "shake", "agua fresca")),
    ("jar", ("jam", "jelly", "pickle", "pickles", "pickled", "preserve",
             "preserves", "canning", "relish", "sauce", "dressing",
             "marinade", "butter", "syrup", "chutney")),
    ("sandwich", ("sandwich", "sandwiches", "sub", "blt", "grilled cheese",
                  "burger", "burgers", "sloppy joe", "panini", "melt")),
    ("bowl", ("rice", "oatmeal", "porridge", "cereal", "granola", "bowl",
              "dip", "hummus", "guacamole", "pudding", "risotto",
              "casserole bowl")),
    ("bread", ("toast",)),
]


def icon_svg(name: str) -> str:
    """One food icon, ready to drop into the page."""
    inner = ICONS.get(name, ICONS[DEFAULT_ICON])
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true" focusable="false">' + inner + "</svg>"
    )


def _pick_icon(title: str, everything: str) -> str:
    """Guess an icon from the recipe's name, then from the whole recipe."""
    for haystack in (title.lower(), everything.lower()):
        for name, words in ICON_WORDS:
            for word in words:
                if re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", haystack):
                    return name
    return DEFAULT_ICON


# ─────────────────────────────────────────────────────────────
# Reading cookbook.txt

SEP_RE = re.compile(r"^\s*[-=~_*]{3,}\s*$")
FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ]{0,14}?)\s*:\s*(.*)$")
SECTION_RE = re.compile(r"^\s*([A-Za-z]{4,12})\s*:?\s*$")
SUBHEAD_RE = re.compile(r"^\s*(.{2,40}?)\s*:\s*$")
STEP_RE = re.compile(r"^\s*(?:step\s*)?\(?\d{1,2}\s*[.):]\s*|^\s*[-*\u2022]\s+", re.I)
BULLET_RE = re.compile(r"^\s*[-*\u2022]\s+")

FIELD_KEYS = {
    "from": "from", "by": "from", "submitted by": "from", "recipe from": "from",
    "prep": "prep", "prep time": "prep", "preptime": "prep",
    "cook": "cook", "cook time": "cook", "cooktime": "cook",
    "bake": "cook", "bake time": "cook",
    "total": "total", "total time": "total",
    "serves": "serves", "servings": "serves", "makes": "serves",
    "yield": "serves", "feeds": "serves",
    "icon": "icon",
}

SECTION_KEYS = {
    "ingredients": "ingredients", "ingredient": "ingredients",
    "directions": "directions", "direction": "directions",
    "instructions": "directions", "instruction": "directions",
    "steps": "directions", "method": "directions",
    "notes": "notes", "note": "notes", "tips": "notes", "tip": "notes",
}


def _field(line: str):
    """('prep', '10 min') if this line is a field, else None."""
    m = FIELD_RE.match(line)
    if not m:
        return None
    key = FIELD_KEYS.get(re.sub(r"\s+", " ", m.group(1)).strip().lower())
    return (key, m.group(2).strip()) if key else None


def _section(line: str):
    """'ingredients' / 'directions' / 'notes' if this line is a heading."""
    m = SECTION_RE.match(line)
    return SECTION_KEYS.get(m.group(1).lower()) if m else None


def _parse_one(lines: list[str], n: int) -> dict | None:
    body = [ln.strip() for ln in lines if ln.strip()]
    if not body:
        return None

    label = body[0]
    rest = body[1:]
    title = label
    # Line 2 is the page title — unless it's already a field or a heading.
    if rest and not _field(rest[0]) and not _section(rest[0]):
        title = rest[0]
        rest = rest[1:]

    r: dict = {
        "n": n, "label": label, "title": title,
        "from": "", "prep": "", "cook": "", "total": "", "serves": "",
        "icon": "", "icon_given": "",
        "lead": [], "ingredients": [], "directions": [], "notes": [],
    }

    where = "lead"
    for line in rest:
        sec = _section(line)
        if sec:
            where = sec
            continue
        fld = _field(line)
        if fld and fld[0]:
            key, value = fld
            if key == "icon":
                r["icon_given"] = re.sub(r"[^a-z0-9]", "", value.lower())
            else:
                r[key] = value
            continue
        if where in ("ingredients", "directions"):
            sub = SUBHEAD_RE.match(line)
            if sub:
                r[where].append(("head", sub.group(1)))
                continue
            text = (STEP_RE.sub("", line) if where == "directions"
                    else BULLET_RE.sub("", line)).strip()
            if text:
                r[where].append(("item", text))
        elif where == "notes":
            r["notes"].append(line)
        else:
            r["lead"].append(line)

    # "flour, sugar, two eggs" on one line becomes three ingredients.
    items = r["ingredients"]
    if len(items) == 1 and items[0][0] == "item" and "," in items[0][1]:
        r["ingredients"] = [("item", part.strip())
                            for part in items[0][1].split(",") if part.strip()]

    everything = " ".join(
        [title, label, " ".join(t for _, t in r["ingredients"])])
    r["icon"] = (r["icon_given"] if r["icon_given"] in ICONS
                 else _pick_icon(title, everything))
    return r


def parse_recipes(path: Path | None = None) -> list[dict] | None:
    """Every recipe in cookbook.txt, in file order. None if there's no
    file (or nothing in it), which is how the front page knows to keep
    showing "coming soon"."""
    path = path or COOKBOOK_PATH
    if not path.exists():
        return None
    lines = [ln.rstrip() for ln in path.read_text(encoding="utf-8").splitlines()
             if not ln.lstrip().startswith("#")]
    chunks: list[list[str]] = [[]]
    for line in lines:
        if SEP_RE.match(line):
            chunks.append([])
        else:
            chunks[-1].append(line)
    recipes = []
    for chunk in chunks:
        r = _parse_one(chunk, len(recipes) + 1)
        if r:
            recipes.append(r)
    return recipes or None


def cookbook_notes(recipes: list[dict] | None) -> list[tuple[str, str]]:
    """Plain-English notes for the build log: bad icon names, recipes
    missing their ingredients or directions."""
    out: list[tuple[str, str]] = []
    if not recipes:
        return out
    for r in recipes:
        who = f'"{r["label"]}"'
        if r["icon_given"] and r["icon_given"] not in ICONS:
            out.append(("warning", f'{who}: there\'s no icon called '
                                   f'"{r["icon_given"]}". Picked one from the '
                                   f'recipe instead ({r["icon"]}). '
                                   f"Names: {', '.join(ICON_NAMES)}."))
        if not r["ingredients"]:
            out.append(("warning", f"{who} has no ingredients. Add a line that "
                                   'says "Ingredients" and list them under it.'))
        if not r["directions"]:
            out.append(("warning", f"{who} has no directions. Add a line that "
                                   'says "Directions" and list the steps under it.'))
    return out


# ─────────────────────────────────────────────────────────────
# Look

COOKBOOK_CSS = r"""
/* ────────────────────────────────────────────────────────────
   COMMUNITY COOKBOOK — the index of recipes, then a page each.
   ──────────────────────────────────────────────────────────── */

/* The index: a food icon, the recipe name, who sent it in. */
.rc-list {
  list-style: none;
  margin: 22px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.rc-list li { border-bottom: 1.5px solid #0a0a0a; }
.rc-list li:last-child { border-bottom: none; }
.rc-list a {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 6px;
  color: inherit;
}
.rc-list a:active { opacity: 0.6; }
.rc-list a:focus-visible { outline: 3px solid #f01a8b; outline-offset: 2px; }
.rc-ico {
  display: block;
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  color: #f01a8b;
}
.rc-ico svg { display: block; width: 100%; height: 100%; }
.rc-txt { flex: 1; min-width: 0; }
.rc-name {
  display: block;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 700;
  font-size: 20px;
  letter-spacing: 0.5px;
  line-height: 1.05;
  text-transform: uppercase;
}
.rc-by {
  display: block;
  margin-top: 4px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 11px;
  color: #3a3a3a;
}
.rc-go {
  flex-shrink: 0;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 26px;
  color: #f01a8b;
}
.rc-empty {
  margin: 0;
  padding: 26px 0 6px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.55;
}

/* A recipe's own page. The title block reuses <article> from the hymn
   pages, so it prints the same way. */
.rc-titlewrap { display: flex; align-items: flex-start; gap: 14px; }
.rc-titlewrap h1 { flex: 1; min-width: 0; }
.rc-bigico {
  display: block;
  flex-shrink: 0;
  width: 62px;
  height: 62px;
  margin-top: 4px;
  color: #f01a8b;
}
.rc-bigico svg { display: block; width: 100%; height: 100%; }
.rc-from {
  margin: 12px 0 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 12px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: #f01a8b;
}

/* Prep / cook / serves, in one boxed strip. */
.rc-meta {
  display: flex;
  flex-wrap: wrap;
  margin: 18px 0 0;
  border: 3px solid #0a0a0a;
  background: #f2ede4;
}
.rc-stat {
  flex: 1 1 88px;
  padding: 9px 8px 10px;
  text-align: center;
  border-right: 1.5px dashed rgba(10, 10, 10, 0.35);
}
.rc-stat:last-child { border-right: none; }
.rc-stat small {
  display: block;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 9px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: #5a5a5a;
}
.rc-stat b {
  display: block;
  margin-top: 4px;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 19px;
  line-height: 1.05;
}

.rc-lead {
  margin: 18px 0 0;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
}
.rc-lead p { margin: 0 0 10px; }
.rc-lead p:last-child { margin-bottom: 0; }

.rc-sec { padding: 24px 0 2px; }
.rc-head {
  margin: 0 0 12px;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 28px;
  line-height: 0.95;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.rc-sub {
  margin: 14px 0 8px;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 15px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: #f01a8b;
}

/* Ingredients — a little pink box to tick off as you go. */
.rc-ing { list-style: none; margin: 0; padding: 0; }
.rc-ing li {
  position: relative;
  padding: 7px 0 7px 26px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.5;
  border-bottom: 1.5px dashed rgba(10, 10, 10, 0.25);
}
.rc-ing li:last-child { border-bottom: none; }
.rc-ing li::before {
  content: "";
  position: absolute;
  left: 2px;
  top: 12px;
  width: 10px;
  height: 10px;
  border: 2px solid #f01a8b;
}

/* Directions — big stencil numbers, same as the verse labels. */
.rc-steps { list-style: none; counter-reset: rcstep; margin: 0; padding: 0; }
.rc-steps li {
  counter-increment: rcstep;
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 9px 0;
}
.rc-steps li::before {
  content: counter(rcstep);
  flex-shrink: 0;
  min-width: 34px;
  text-align: right;
  font-family: 'Big Shoulders Stencil Display', 'Impact', sans-serif;
  font-weight: 900;
  font-size: 34px;
  line-height: 0.8;
  color: #f01a8b;
  font-variant-numeric: tabular-nums;
}
.rc-steps .rc-step-body {
  flex: 1;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
  padding-top: 2px;
}

/* Notes — the black tape strip, like the front page quote. */
.rc-notes {
  margin: 30px 0 0;
  padding: 16px 20px 18px;
  background: #0a0a0a;
  color: #f2ede4;
  transform: rotate(-0.8deg);
}
.rc-notes-label {
  margin: 0 0 8px;
  font-family: 'Big Shoulders Stencil Text', 'Impact', sans-serif;
  font-weight: 800;
  font-size: 14px;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: #f01a8b;
}
.rc-notes p {
  margin: 0 0 8px;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.55;
}
.rc-notes p:last-child { margin-bottom: 0; }

/* Chips and boxes with their own background don't want the beige halo. */
.rc-meta, .rc-meta *,
.rc-notes, .rc-notes * {
  -webkit-text-stroke-width: 0 !important;
  -webkit-text-stroke-color: transparent !important;
  paint-order: normal !important;
}

@media print {
  .rc-notes {
    background: #ffffff !important;
    color: #000000 !important;
    border: 1.5pt solid #000;
    transform: none;
    margin-top: 20pt;
    break-inside: avoid-page;
  }
  .rc-notes-label { color: #000 !important; }
  .rc-meta { border-width: 1.5pt; background: #fff !important; }
  .rc-stat b, .rc-stat small { color: #000 !important; }
  .rc-bigico { width: 44px; height: 44px; color: #000 !important; }
  .rc-from { color: #000 !important; }
  .rc-ico { color: #000 !important; }
  .rc-sec { break-inside: avoid-page; padding-top: 14pt; }
  .rc-steps li::before { color: #000 !important; font-size: 24pt; }
  .rc-ing li::before { border-color: #000 !important; }
  .rc-ing li, .rc-steps .rc-step-body, .rc-lead { font-size: 11pt; }
}
"""


# ─────────────────────────────────────────────────────────────
# Building the pages

def _paras(lines: list[str]) -> str:
    return "\n".join(f"<p>{escape(ln)}</p>" for ln in lines if ln.strip())


def render_cookbook(recipes: list[dict] | None) -> str:
    """The index: every recipe as an icon you can tap."""
    if not recipes:
        return ('<p class="rc-empty">No recipes yet. '
                "Add the first one to cookbook.txt.</p>")
    items = []
    for r in recipes:
        who = f'From {r["from"]}' if r["from"] else ""
        by = f'<span class="rc-by">{escape(who)}</span>' if who else ""
        items.append(
            f'<li><a href="cookbook/{r["n"]}/">'
            f'<span class="rc-ico">{icon_svg(r["icon"])}</span>'
            f'<span class="rc-txt"><span class="rc-name">{escape(r["label"])}</span>{by}</span>'
            f'<span class="rc-go" aria-hidden="true">&rarr;</span>'
            f"</a></li>"
        )
    count = f'{len(recipes)} recipe{"" if len(recipes) == 1 else "s"}'
    return (
        '<div class="meta-strip">'
        f'<span class="count-tag">{count}</span>'
        '<div class="dash-rule"></div>'
        '<span class="hint">↓ tap one</span>'
        "</div>\n"
        f"{render_recipe_form()}\n"
        f'<ul class="rc-list">\n' + "\n".join(items) + "\n</ul>"
    )


def _list_html(rows: list[tuple[str, str]], kind: str) -> str:
    """Ingredients or directions, splitting at any sub-headings."""
    out, group = [], []
    tag = "ul" if kind == "ing" else "ol"
    cls = "rc-ing" if kind == "ing" else "rc-steps"

    def flush():
        if group:
            body = "".join(
                f"<li>{escape(t)}</li>" if kind == "ing"
                else f'<li><span class="rc-step-body">{escape(t)}</span></li>'
                for t in group
            )
            out.append(f'<{tag} class="{cls}">{body}</{tag}>')
            group.clear()

    for role, text in rows:
        if role == "head":
            flush()
            out.append(f'<p class="rc-sub">{escape(text)}</p>')
        else:
            group.append(text)
    flush()
    return "\n".join(out)


def render_recipe(recipe: dict, prev: dict | None, nxt: dict | None) -> str:
    """One recipe's page — everything under the brand logo."""
    r = recipe
    stats = [(lbl, r[k]) for k, lbl in
             (("prep", "Prep"), ("cook", "Cook"),
              ("total", "Total"), ("serves", "Serves")) if r[k]]
    meta_html = ""
    if stats:
        meta_html = '<div class="rc-meta">' + "".join(
            f'<div class="rc-stat"><small>{lbl}</small><b>{escape(val)}</b></div>'
            for lbl, val in stats
        ) + "</div>\n"

    from_html = (f'<p class="rc-from">From {escape(r["from"])}</p>'
                 if r["from"] else "")
    lead_html = (f'<div class="rc-lead">{_paras(r["lead"])}</div>\n'
                 if r["lead"] else "")

    sections = ""
    if r["ingredients"]:
        sections += ('<section class="rc-sec">'
                     '<h2 class="rc-head">Ingredients</h2>'
                     f'{_list_html(r["ingredients"], "ing")}</section>\n')
    if r["directions"]:
        sections += ('<section class="rc-sec">'
                     '<h2 class="rc-head">Directions</h2>'
                     f'{_list_html(r["directions"], "step")}</section>\n')
    notes_html = ""
    if r["notes"]:
        notes_html = ('<section class="rc-notes">'
                      '<h3 class="rc-notes-label">Notes</h3>'
                      f'{_paras(r["notes"])}</section>\n')

    prev_link = (f'<a class="nav-prev" href="cookbook/{prev["n"]}/">← PREV</a>'
                 if prev else "<span></span>")
    next_link = (f'<a class="nav-next" href="cookbook/{nxt["n"]}/">NEXT →</a>'
                 if nxt else "<span></span>")

    return (
        '<article class="rc-title">\n'
        f'<span class="print-slug">Recipe #{r["n"]}</span>'
        '<div class="rc-titlewrap">'
        f'<h1>{escape(r["title"])}</h1>'
        f'<span class="rc-bigico">{icon_svg(r["icon"])}</span>'
        "</div>\n"
        f"{from_html}\n"
        "</article>\n"
        f"{meta_html}"
        f"{lead_html}"
        f"{sections}"
        f"{notes_html}"
        '<nav class="foot">\n'
        f"{prev_link}\n"
        '<a class="home" href="cookbook/">ALL RECIPES</a>\n'
        f"{next_link}\n"
        "</nav>"
    )
