"""bulletin.py — the printable tri-fold Sunday bulletin.

Renders a two-sided, three-fold LANDSCAPE bulletin from the site's own
files and serves it at /{key}/bulletin. Print double-sided (short-edge
binding) and fold in thirds.

Pulls at render time from: GraceHouseCover.png (repo root, embedded; the
live "coming Sunday" date is drawn over it in the browser), who-we-are.txt
(the "Know Grace / Live Grace / Share Grace" headline + welcome, and the
timed order-of-service sections), prayer.txt (the prayer list, with the
same one-month drop-off applied here at print time), zine.txt (this
week's zine, editable on the page; long weeks spill onto the last panel),
and bulletin-verses.txt (the back-panel verse, chosen at random).

QR codes point at the site's zine / prayer-list / hymnal pages, worked
out in the browser from this page's own address, so they always match the
current access key. Everything interactive runs in the browser, so it
works on the static GitHub Pages build too (JavaScript required).

server.py wiring:
    from bulletin import render_bulletin, parse_bulletin_verses
    ... plus a /bulletin route that calls render_bulletin(key, ...).
resources.py gets the button that opens it.
"""
from __future__ import annotations

import base64
import calendar
import datetime
import json
import re
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
COVER_PATH = HERE / "GraceHouseCover.png"
BVERSES_PATH = HERE / "bulletin-verses.txt"


def parse_bulletin_verses(path: Path = BVERSES_PATH):
    """[(text, reference), ...] from bulletin-verses.txt (same shape as
    quote.txt: verse text, then a dash line with the reference). Lines
    starting with # are ignored. Missing/empty file -> []."""
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("#")]
    out = []
    for block in re.split(r"\n\s*\n", "\n".join(lines)):
        text_lines, ref = [], ""
        for ln in (l.strip() for l in block.splitlines()):
            if not ln:
                continue
            if ln[0] in "-—–" and text_lines:
                ref = ln.lstrip("-—– ").strip()
            else:
                text_lines.append(ln)
        text = " ".join(text_lines).strip().strip('"“”').strip()
        if text:
            out.append((text, ref))
    return out


def _cover_data_uri() -> str:
    if not COVER_PATH.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(COVER_PATH.read_bytes()).decode()


def _ends(when: datetime.date) -> datetime.date:
    """One month after a date — when its prayer requests drop off
    (same rule as prayer.py)."""
    y, m = when.year + when.month // 12, when.month % 12 + 1
    return datetime.date(y, m, min(when.day, calendar.monthrange(y, m)[1]))


def _para(lines) -> str:
    """Paragraphs; runs of "- "/"* " lines become a list."""
    parts, bullets = [], []

    def flush():
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{escape(b)}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith(("- ", "* ")):
            bullets.append(s[2:].strip())
        else:
            flush()
            parts.append(f"<p>{escape(s)}</p>")
    flush()
    return "\n".join(parts)


def _prayer_rows(prayer_data, today: datetime.date) -> str:
    """Open requests from gatherings still inside their month, newest
    first — each request line with the asker as a name chip."""
    if not prayer_data:
        return ""
    rows = []
    for when, items in prayer_data["days"]:
        if _ends(when) <= today:
            continue
        for it in items:
            if it.get("answered"):
                continue
            chip = (f'<span class="tag pr-chip">{escape(it["asker"])}</span>'
                    if it.get("asker") else "")
            rows.append(f'<div class="pr-row"><span class="pr-req">{escape(it["text"])}</span>{chip}</div>')
    return "\n".join(rows)


def _welcome_html(who_data):
    """(headline_html, welcome_html) for the welcome panel."""
    if not who_data:
        return "", ""
    headline, welcome, _sections = who_data
    head = "<br>".join(escape(l) for l in headline) if headline else ""
    return head, _para(welcome)


def _order_html(who_data) -> str:
    """Order-of-service blocks from who-we-are.txt sections."""
    if not who_data:
        return ""
    _headline, _welcome, sections = who_data
    blocks = []
    for name, time, names, body in sections:
        time_html = f'<div class="svc-time">{escape(time)}</div>' if time else ""
        tags = "".join(f'<span class="tag">{escape(n)}</span>' for n in names)
        text = " ".join(l.strip() for l in body if l.strip())
        blocks.append(
            '<div class="svc"><div class="svc-top"><div>'
            f'{time_html}<h3>{escape(name)}</h3></div>{tags}</div>'
            f'<p>{escape(text)}</p></div>'
        )
    return "\n".join(blocks)


def _zine_html(zine_data) -> str:
    """Zine sections as editable heading + paragraph blocks."""
    if not zine_data:
        return ""
    _title, sections = zine_data
    out = []
    for heading, body_lines in sections:
        out.append(f"<h4>{escape(heading)}</h4>")
        out.append(_para(body_lines))
    return "\n".join(out)


_EV_DAYS3 = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_EV_MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
            "Sep", "Oct", "Nov", "Dec"]


def _events_html(events_data) -> str:
    """One <div class="be-item"> per event (date chip + title). The browser
    shows only those in the coming-Sunday-to-next-Sunday window; the rest
    stay hidden. events_data is server.parse_events()[0], newest last."""
    if not events_data:
        return ""
    rows = []
    for when, details in events_data:
        title = next((ln.strip() for ln in details if ln.strip()), "")
        if not title:
            continue
        label = f"{_EV_DAYS3[when.weekday()]} {_EV_MON3[when.month - 1]} {when.day}"
        rows.append(
            f'<div class="be-item" data-date="{when.isoformat()}">'
            f'<div class="be-when">{escape(label)}</div>'
            f'<div class="be-what">{escape(title)}</div>'
            f'</div>'
        )
    return "\n".join(rows)


_FALLBACK_VERSE = ("For God so loved the world, that he gave his only Son, "
                   "that whoever believes in him should not perish but have "
                   "eternal life.", "John 3:16")

CSS = "\n  :root{ color-scheme:light; box-sizing:border-box; --pw:3.667in; --ph:8.5in; }\n  *,*::before,*::after{ box-sizing:inherit; }\n  html,body{ margin:0; padding:0; }\n  body{ background:#5f5f5f; color:#eee; font-family:'Special Elite','Courier New',monospace; -webkit-font-smoothing:antialiased; }\n\n  .chrome{ max-width:1056px; margin:0 auto; padding:22px 18px 6px; }\n  .chrome h1{ font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; letter-spacing:1px; font-size:22px; margin:0 0 8px; }\n  .chrome p{ margin:0 0 14px; font-size:13px; line-height:1.55; opacity:.85; max-width:80ch; }\n  .bar{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:6px; }\n  .btn{ font-family:'Special Elite',monospace; font-size:13px; letter-spacing:.5px; padding:9px 14px; border:2px solid #eee; background:transparent; color:#eee; cursor:pointer; border-radius:0; }\n  .btn.primary{ background:#eee; color:#111; }\n  .btn:active{ transform:translateY(1px); }\n  .chk{ display:flex; align-items:center; gap:7px; font-size:13px; opacity:.9; }\n  .hint{ font-size:12px; opacity:.6; }\n  .kctl{ gap:9px; }\n  .kctl input[type=range]{ width:120px; accent-color:#eee; cursor:pointer; vertical-align:middle; }\n  .kval{ font-size:12px; opacity:.85; min-width:34px; text-align:right; }\n\n  .stage{ padding:14px 18px 60px; }\n  .sheet-wrap{ margin:0 auto 26px; }\n  .sheet-label{ max-width:1056px; margin:0 auto 6px; font-size:11px; letter-spacing:2px; text-transform:uppercase; opacity:.6; }\n\n  .sheet{ width:11in; height:8.5in; background:#fff; color:#000; display:flex; transform-origin:top left; position:relative; box-shadow:0 10px 34px rgba(0,0,0,.4); }\n  .panel{ flex:1 1 0; min-width:0; height:100%; position:relative; overflow:hidden; }\n  .fold{ position:absolute; top:0; bottom:0; width:0; border-left:1px dashed #cfcfcf; pointer-events:none; }\n  .fold.f1{ left:33.333%; } .fold.f2{ left:66.667%; }\n  .pad{ position:absolute; top:0.34in; right:0.30in; bottom:0.34in; left:0.30in; display:flex; flex-direction:column; }\n\n  .h-stencil{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; text-transform:uppercase; line-height:.92; color:#000; margin:0; }\n  .body{ font-family:'Special Elite','Courier New',monospace; color:#000; }\n\n  /* shared name chip (order of service + prayer) */\n  .tag{ background:#000; color:#fff; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; white-space:nowrap; }\n\n  /* QR blocks */\n  .qr-block{ display:flex; flex-direction:column; align-items:center; gap:5px; }\n  .qr-cap{ font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:700; font-size:14px; letter-spacing:1px; text-transform:uppercase; }\n\n  /* ── PRAYER panel ──────────────────────────────────── */\n  .p-title{ font-size:34px; letter-spacing:.5px; }\n  .pr-list{ margin-top:12px; display:flex; flex-direction:column; flex:1; min-height:5in; }\n  .pr-row{ display:flex; align-items:center; gap:8px; min-height:27px; padding:5px 1px 6px; border-bottom:1px solid #000; }\n  .pr-req{ flex:1; min-width:0; font-family:'Special Elite',monospace; font-size:12px; line-height:1.15; }\n  .pr-chip{ font-size:12px; padding:1px 8px 2px; transform:rotate(-2deg); }\n  .pr-row:nth-child(even) .pr-chip{ transform:rotate(2deg); }\n  /* ruled write-in lines filling the leftover space */\n  .pr-fill{ flex:1; min-height:0.9in; background-color:#fff; background-image:repeating-linear-gradient(to bottom, #fff 0, #fff 26px, #000 26px, #000 27px); }\n  .qr-more-block{ margin-top:12px; }\n  .qr-more-block .qr,.qr-more-block .qr img,.qr-more-block .qr canvas{ width:80px!important; height:80px!important; }\n\n  /* ── WELCOME panel ─────────────────────────────────── */\n  .brandmark{ display:flex; align-items:center; gap:2px; font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:15px; letter-spacing:2px; }\n  .brandmark svg{ width:16px; height:16px; }\n  .w-head{ font-size:33px; margin:14px 0 0; }\n  .w-body{ margin:12px 0 0; }\n  .w-body p{ font-size:12px; line-height:1.5; margin:0 0 8px; }\n  .w-body p:last-child{ margin-bottom:0; }\n  .qr-hymnal-block{ margin-top:60px; }              /* moved down ~60px */\n  .qr-hymnal-block .qr,.qr-hymnal-block .qr img,.qr-hymnal-block .qr canvas{ width:84px!important; height:84px!important; }  /* ~20% smaller */\n  .verse-ref{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; font-size:26px; margin:8px 0 4px; }\n  .verse-txt{ font-size:11.5px; line-height:1.45; font-style:italic; }\n  .w-foot{ margin-top:auto; }\n\n  /* ── COVER panel ───────────────────────────────────── */\n  .cover img{ position:absolute; inset:0; width:100%; height:100%; display:block; }\n  .cover .date{ position:absolute; left:88%; top:19.36%; transform:translate(-50%,-50%) rotate(90deg); transform-origin:center; white-space:nowrap; font-family:'Nunito','Segoe UI',sans-serif; font-weight:500; font-size:21px; letter-spacing:.5px; color:#111; }\n\n  /* ── ORDER OF SERVICE panel ────────────────────────── */\n  .o-title{ font-size:30px; margin-bottom:4px; }\n  .pad-order{ justify-content:space-between; }\n  .svc{ padding:10px 0 12px; border-top:2px solid #000; }\n  .svc:first-of-type{ border-top:0; }\n  .svc-top{ display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }\n  .svc-time{ font-family:'Special Elite',monospace; font-size:12px; letter-spacing:.5px; }\n  .svc h3{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; text-transform:uppercase; font-size:24px; line-height:.9; margin:1px 0 0; }\n  .svc .tag{ padding:2px 8px 3px; font-size:14px; transform:rotate(3deg); }\n  .svc:nth-of-type(even) .tag{ transform:rotate(-3deg); }\n  .svc p{ font-family:'Special Elite',monospace; font-size:10.5px; line-height:1.4; margin:7px 0 0; }\n\n  /* ── ZINE (middle) + overflow (right) ──────────────── */\n  .z-title{ font-size:28px; margin-bottom:2px; }\n  .z-sub{ font-size:9px; letter-spacing:2px; text-transform:uppercase; opacity:.55; margin-bottom:6px; }\n  .z-area{ flex:1; min-height:6in; overflow:hidden; }\n  .z-over-area{ max-height:3.3in; overflow:hidden; }\n  .zine{ outline:none; }\n  .zine h4{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; text-transform:uppercase; font-size:1.32em; line-height:1; margin:.7em 0 .28em; }\n  .zine h4:first-child{ margin-top:0; }\n  .zine p{ font-family:'Special Elite',monospace; line-height:1.4; margin:0 0 .5em; }\n  .zine{ font-size:12.5px; }\n  .z-edit-hint{ font-size:10px; opacity:.5; margin-top:6px; }\n  .z-over-label{ font-size:9px; letter-spacing:2px; text-transform:uppercase; opacity:.45; margin-bottom:4px; }\n\n  /* ── UPLOAD (square) + zine QR ─────────────────────── */\n  .upload{ position:absolute; left:50%; top:5.19in; transform:translateX(-50%); width:2.97in; height:2.97in; border:2px dashed #000; display:flex; align-items:center; justify-content:center; text-align:center; cursor:pointer; overflow:hidden; position:relative; }\n  .upload span{ font-family:'Special Elite',monospace; font-size:11px; opacity:.55; padding:0 12px; line-height:1.5; }\n  .upload img{ width:100%; height:100%; object-fit:cover; }\n  .upload input{ display:none; }\n  .upload.has-img{ border:0; }\n  /* events block (replaces the upload square, bottom of the third panel) */\n  .bul-events{ position:absolute; left:0.30in; right:0.30in; top:5.19in; bottom:0.34in; display:flex; flex-direction:column; }\n  .be-title{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; text-transform:uppercase; font-size:26px; line-height:.9; margin:0 0 6px; color:#000; }\n  .be-list{ flex:1; min-height:0; overflow:hidden; }\n  .be-item{ padding:5px 0 6px; border-top:1px solid #000; }\n  .be-item:first-child{ border-top:0; }\n  .be-item[hidden]{ display:none; }\n  .be-when{ font-family:'Big Shoulders Stencil Text','Impact',sans-serif; font-weight:800; font-size:12px; letter-spacing:.5px; text-transform:uppercase; }\n  .be-what{ font-family:'Special Elite',monospace; font-size:12px; line-height:1.25; }\n  .be-none{ font-family:'Special Elite',monospace; font-size:12px; opacity:.7; margin:6px 0 0; }\n  .qr-ev-block{ margin-top:8px; align-self:center; }\n  .qr-ev-block .qr,.qr-ev-block .qr img,.qr-ev-block .qr canvas{ width:80px!important; height:80px!important; }\n  .qr-zine-block{ margin-top:12px; }\n  .qr-zine-block .qr,.qr-zine-block .qr img,.qr-zine-block .qr canvas{ width:86px!important; height:86px!important; }\n\n  /* long-edge flip */\n  .flipwrap{ display:flex; width:100%; height:100%; }\n  .sheet.inside.flip .flipwrap{ transform:rotate(180deg); transform-origin:center; }\n\n  /* PRINT */\n  \n  @media print{\n    body{ background:#fff; -webkit-print-color-adjust:exact; print-color-adjust:exact; }\n    .chrome,.sheet-label{ display:none!important; }\n    .stage{ padding:0; }\n    /* Scale to fit with ZOOM, not transform. Two confirmed Safari facts drive\n       this: (1) Safari ignores @page{size} (incl. orientation), so LANDSCAPE\n       must be picked in the print dialog - the injected @page is only for\n       Chrome/Firefox; (2) transform:scale() shrinks only the PAINT, so the\n       sheet still occupied its full 11 x 8.5in in the flow - taller than the\n       printable area - and the overflow paginated onto a blank page after every\n       sheet (the 2-sheets-become-4-pages bug). CSS zoom scales the LAYOUT box\n       itself (Baseline since 2024, supported in Safari), so the sheet genuinely\n       becomes 11k x 8.5k in the flow and fits on one page. The on-screen\n       scale()'s inline transform is cancelled (transform:none) so it can't\n       multiply with zoom. Print dialog: LANDSCAPE, US Letter, 100%. If a blank\n       page ever returns on some printer, either lower --k a notch or set the\n       dialog's Scaling to ~90%. Knob: --k - raise toward 0.95 for a bigger\n       print, lower if an edge clips. */\n    :root{ --k:0.80; }\n    .sheet-wrap{ width:auto!important; height:auto!important; margin:0 auto!important;\n                 overflow:visible!important; break-inside:avoid; page-break-inside:avoid;\n                 page-break-after:always; break-after:page; }\n    .sheet-wrap:last-of-type{ page-break-after:auto; break-after:auto; }\n    .sheet{ transform:none!important; zoom:var(--k)!important;\n            margin:0 auto!important; box-shadow:none!important; }\n    .fold{ display:none; }\n    .z-sub,.z-edit-hint,.upload span,.cf-hint{ display:none!important; }\n  }\n\n.cover-fallback{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; text-align:center; padding:0.4in; }\n.cf-mark{ font-family:'Big Shoulders Stencil Display','Impact',sans-serif; font-weight:900; font-size:54px; line-height:.82; letter-spacing:1px; color:#000; }\n.cf-hint{ font-family:'Special Elite',monospace; font-size:11px; line-height:1.4; color:#b00; }\n"

JS = '/* Printing: ask for landscape Letter, but never set an @page margin \\u2014 Safari\n   and every iOS browser shove the whole sheet up and clip it when a page margin\n   is set (the trap the kids sheet hit). The print CSS zooms the sheet to fit\n   inside the printer\'s own margins instead. */\n(function(){\n  var pr=document.createElement(\'style\');\n  pr.textContent=\'@page{ size:11in 8.5in; }\';\n  document.head.appendChild(pr);\n  window.addEventListener(\'beforeprint\',function(){ try{window.scrollTo(0,0);}catch(e){} });\n})();\n\n\n    var KEY=\'__KEY__\';\n    var loc=document.location.href.split(\'#\')[0].split(\'?\')[0];\n    var i=loc.indexOf(\'/\'+KEY+\'/\');\n    var ROOT=(i>=0)?loc.slice(0,i+KEY.length+2):loc.replace(/[^/]*$/,\'\');\n    var ZINE_URL=ROOT+\'zine/\', PRAYER_URL=ROOT+\'prayer-list/\', HYMNAL_URL=ROOT+\'hymnal/\', EVENTS_URL=ROOT+\'events/\';\n\n    (function(){\n      var M=[\'January\',\'February\',\'March\',\'April\',\'May\',\'June\',\'July\',\'August\',\'September\',\'October\',\'November\',\'December\'];\n      var n=new Date(), add=(7-n.getDay())%7;\n      var s=new Date(n.getFullYear(),n.getMonth(),n.getDate()+add);\n      var t=M[s.getMonth()]+\' \'+s.getDate();\n      document.querySelectorAll(\'[data-date]\').forEach(function(e){e.textContent=t;});\n    })();\n\n    /* random back-page verse (from bulletin-verses.txt) */\n    (function(){\n      var VERSES=__VERSES_JSON__;\n      var v=VERSES[Math.floor(Math.random()*VERSES.length)];\n      document.getElementById(\'v-ref\').textContent=v.ref;\n      document.getElementById(\'v-txt\').textContent=\'\\u201C\'+v.text+\'\\u201D\';\n    })();\n\n    function qr(id,url,size){ try{ new QRCode(document.getElementById(id),{text:url,width:size,height:size,correctLevel:QRCode.CorrectLevel.M}); }catch(e){} }\n    function makeQRs(){ qr(\'qr-more\',PRAYER_URL,80); qr(\'qr-hymnal\',HYMNAL_URL,84); qr(\'qr-zine\',ZINE_URL,86); qr(\'qr-events\',EVENTS_URL,80); }\n    if(window.QRCode) makeQRs(); else window.addEventListener(\'load\',makeQRs);\n\n    /* zine flows middle -> right overflow panel */\n    var zine=document.getElementById(\'zine\'), over=document.getElementById(\'zine-over\');\n    var midArea=document.querySelector(\'.z-area\');\n    var ZINE_DEFAULT=zine.innerHTML;\n    /* Fill the middle panel completely, then spill the rest to the right. Moves\n       whole blocks first; when the next block only partly fits, it SPLITS that\n       paragraph at a word boundary so the left column fills to the bottom and\n       the remainder continues on the right. A heading is kept with at least the\n       first line of its paragraph so it never strands alone. */\n    function flowZine(){\n      var H=midArea.clientHeight;\n      /* 1) pull everything back and undo any earlier split */\n      while(over.firstChild) zine.appendChild(over.firstChild);\n      var hd=zine.querySelector("[data-frag=head]");\n      if(hd){\n        var tl=hd.nextElementSibling;\n        if(tl && tl.getAttribute("data-frag")==="tail" && tl.tagName===hd.tagName){\n          hd.textContent=(hd.textContent.trim()+" "+tl.textContent.trim()).trim();\n          tl.parentNode.removeChild(tl);\n        }\n        hd.removeAttribute("data-frag");\n      }\n      var st=zine.querySelector("[data-frag=tail]"); if(st) st.removeAttribute("data-frag");\n      /* 2) all fits? done */\n      if(zine.scrollHeight<=H) return;\n      /* 3) move whole trailing blocks out until the middle fits */\n      var guard=0;\n      while(zine.children.length>1 && zine.scrollHeight>H && guard<400){\n        over.insertBefore(zine.lastElementChild, over.firstChild); guard++;\n      }\n      /* 4) fill the leftover gap by splitting the next block across the fold */\n      var cand=over.firstElementChild, movedHeading=null;\n      if(cand && cand.tagName==="H4"){\n        zine.appendChild(cand);\n        if(zine.scrollHeight>H){ over.insertBefore(cand, over.firstChild); return; }\n        movedHeading=cand; cand=over.firstElementChild;\n      }\n      if(cand && cand.tagName==="P"){\n        var words=(cand.textContent||"").trim().split(" ").filter(Boolean);\n        if(words.length>1){\n          var hp=document.createElement("p");\n          hp.setAttribute("data-frag","head");\n          zine.appendChild(hp);\n          var lo=1, hi=words.length-1, best=0;\n          while(lo<=hi){ var m=(lo+hi)>>1; hp.textContent=words.slice(0,m).join(" "); if(zine.scrollHeight<=H){ best=m; lo=m+1; } else { hi=m-1; } }\n          if(best>0){\n            hp.textContent=words.slice(0,best).join(" ");\n            cand.textContent=words.slice(best).join(" ");\n            cand.setAttribute("data-frag","tail");\n          } else {\n            zine.removeChild(hp);\n            if(movedHeading) over.insertBefore(movedHeading, over.firstChild);\n          }\n        } else if(movedHeading){ over.insertBefore(movedHeading, over.firstChild); }\n      } else if(movedHeading){ over.insertBefore(movedHeading, over.firstChild); }\n    }\n    function resetZine(){ zine.innerHTML=ZINE_DEFAULT; flowZine(); }\n    var t; zine.addEventListener(\'input\',function(){ clearTimeout(t); t=setTimeout(flowZine,350); });\n\n    /* Events: show only those from the coming Sunday (the cover date) up to,\n       but not including, the next Sunday. ISO date strings compare directly. */\n    (function(){\n      var box=document.getElementById("be-list"); if(!box) return;\n      var n=new Date(), add=(7-n.getDay())%7;\n      var start=new Date(n.getFullYear(),n.getMonth(),n.getDate()+add);\n      var end=new Date(start.getFullYear(),start.getMonth(),start.getDate()+7);\n      function k(d){ return d.getFullYear()+"-"+("0"+(d.getMonth()+1)).slice(-2)+"-"+("0"+d.getDate()).slice(-2); }\n      var s=k(start), e=k(end), today=k(n), shown=0;\n      var items=box.querySelectorAll(".be-item");\n      for(var i=0;i<items.length;i++){\n        var d=items[i].getAttribute("data-date");\n        var inWin=(d>=s && d<e);\n        items[i].hidden=!inWin; if(inWin) shown++;\n      }\n      /* Nothing in the week window? Scan forward from today to the very next\n         event (rows are already in date order). */\n      if(shown===0){\n        for(var j=0;j<items.length;j++){\n          if(items[j].getAttribute("data-date")>=today){ items[j].hidden=false; shown=1; break; }\n        }\n      }\n      var none=document.getElementById("be-none"); if(none) none.hidden=shown>0;\n      var ttl=document.getElementById("be-title");\n      if(ttl && shown>0) ttl.textContent = (function(){\n        /* label the fallback so it does not read as this week */\n        for(var j=0;j<items.length;j++){ if(!items[j].hidden){ return items[j].getAttribute("data-date")<e ? "Coming Up" : "Next Up"; } }\n        return "Coming Up";\n      })();\n    })();\n\n    document.getElementById(\'flip\').addEventListener(\'change\',function(e){\n      document.getElementById(\'sheet2\').classList.toggle(\'flip\',e.target.checked);\n    });\n\n    /* Print-size slider -> live --k. Set inline on <html>, which beats the\n       @media print :root{--k} default, so the dialog needs no fiddling. */\n    (function(){\n      var KKEY="gh-bulletin-k";\n      var slider=document.getElementById("ksize"), out=document.getElementById("kval");\n      function apply(v){\n        v=Math.max(0.70,Math.min(0.98,parseFloat(v)||0.80));\n        document.documentElement.style.setProperty("--k",String(v));\n        if(out) out.textContent=Math.round(v/0.80*100)+"%";\n        if(slider) slider.value=v;\n      }\n      var saved=null; try{ saved=localStorage.getItem(KKEY); }catch(e){}\n      apply(saved!=null?saved:0.80);\n      if(slider) slider.addEventListener("input",function(){\n        apply(slider.value);\n        try{ localStorage.setItem(KKEY,slider.value); }catch(e){}\n      });\n    })();\n\n    function scale(){\n      var avail=document.querySelector(\'.stage\').clientWidth;\n      var s=Math.min(1, avail/(11*96));\n      document.querySelectorAll(\'.sheet\').forEach(function(sh){ sh.style.transform=\'scale(\'+s+\')\'; });\n      document.querySelectorAll(\'.sheet-wrap\').forEach(function(w){ w.style.height=(8.5*96*s)+\'px\'; w.style.width=(11*96*s)+\'px\'; });\n    }\n    window.addEventListener(\'resize\',function(){ scale(); flowZine(); });\n    if(document.fonts&&document.fonts.ready){ document.fonts.ready.then(function(){ scale(); flowZine(); }); }\n    window.addEventListener(\'load\',function(){ scale(); flowZine(); setTimeout(function(){ scale(); flowZine(); },400); });\n  '

BODY = '  <div class="chrome">\n    <h1>Grace House — Sunday bulletin</h1>\n    <p>Edit the zine (click it and type) &mdash; long weeks spill onto the last panel on their own. This week&rsquo;s events fill in under the zine automatically. Then Print: <b>Landscape, double-sided, Short-edge binding</b>, 100%. Long-edge printer? Tick the box so the back lines up.</p>\n    <div class="bar">\n      <button class="btn primary" onclick="window.print()">Print</button>\n      <label class="chk"><input type="checkbox" id="flip"> My printer flips on the long edge</label>\n      <label class="chk kctl" title="Shrinks the printout so it fits on one page. Raise it until an edge clips; lower it if a blank page appears.">Print size <input type="range" id="ksize" min="0.70" max="0.98" step="0.01" value="0.80"> <span class="kval" id="kval">100%</span></label>\n      <button class="btn" onclick="resetZine()">Reset zine text</button>\n      <span class="hint">Two pages = the two sides of one sheet.</span>\n    </div>\n  </div>\n\n  <div class="stage">\n    <div class="sheet-label">Sheet 1 — outside (prints first)</div>\n    <div class="sheet-wrap"><div class="sheet outside" id="sheet1">\n      <div class="fold f1"></div><div class="fold f2"></div>\n\n      <div class="panel"><div class="pad">\n        <h2 class="h-stencil p-title">Prayer List</h2>\n        <div class="pr-list">\n          __PRAYER_ROWS__\n          <div class="pr-fill"></div>\n        </div>\n        <div class="qr-block qr-more-block">\n          <div class="qr" id="qr-more"></div>\n          <div class="qr-cap">More</div>\n        </div>\n      </div></div>\n\n      <div class="panel"><div class="pad">\n        <div class="brandmark">GRACE&nbsp;H<svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="43" fill="none" stroke="#000" stroke-width="6.5"/><g stroke="#000" stroke-width="5.5"><line x1="50" y1="7" x2="50" y2="93"/><line x1="7" y1="50" x2="93" y2="50"/><line x1="19.6" y1="19.6" x2="80.4" y2="80.4"/><line x1="80.4" y1="19.6" x2="19.6" y2="80.4"/></g><circle cx="50" cy="50" r="7.5" fill="#000"/></svg>USE</div>\n        <h2 class="h-stencil w-head">__HEAD__</h2>\n        <div class="w-body">__WELCOME__</div>\n        <div class="qr-block qr-hymnal-block">\n          <div class="qr" id="qr-hymnal"></div>\n          <div class="qr-cap">Hymnal</div>\n        </div>\n        <div class="w-foot">\n          <div class="verse-ref" id="v-ref">__V_REF__</div>\n          <p class="verse-txt" id="v-txt">__V_TXT__</p>\n        </div>\n      </div></div>\n\n      <div class="panel cover">\n        __COVER_INNER__\n        <span class="date" data-date>September 20</span>\n      </div>\n    </div></div>\n\n    <div class="sheet-label">Sheet 2 — inside (prints on the back)</div>\n    <div class="sheet-wrap"><div class="sheet inside" id="sheet2"><div class="flipwrap">\n      <div class="fold f1"></div><div class="fold f2"></div>\n\n      <div class="panel"><div class="pad pad-order">\n        __ORDER__\n      </div></div>\n\n      <div class="panel"><div class="pad">\n        <h2 class="h-stencil z-title">__ZINE_TITLE__</h2>\n        <div class="z-sub">tap to edit</div>\n        <div class="z-area"><div class="zine" id="zine" contenteditable="true">__ZINE__</div></div>\n        <div class="z-edit-hint">Overflow spills onto the next panel &rarr;</div>\n      </div></div>\n\n      <div class="panel">\n        <div class="pad">\n          <div class="z-over-area"><div class="zine" id="zine-over"></div></div>\n          <div class="qr-block qr-zine-block">\n            <div class="qr" id="qr-zine"></div>\n            <div class="qr-cap">See what you&rsquo;re missing</div>\n          </div>\n        </div>\n        <div class="bul-events" id="bul-events">\n          <h3 class="be-title" id="be-title">Coming Up</h3>\n          <div class="be-list" id="be-list">__EVENTS__</div>\n          <p class="be-none" id="be-none" hidden>Nothing coming up, what&rsquo;s up?</p>\n          <div class="qr-block qr-ev-block">\n            <div class="qr" id="qr-events"></div>\n            <div class="qr-cap">All events</div>\n          </div>\n        </div>\n      </div>\n    </div></div></div>\n  </div>'

_HEAD = (
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
    '<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    '<title>Grace House — bulletin</title>\n'
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Stencil+Display:wght@800;900&family=Big+Shoulders+Stencil+Text:wght@600;700;800&family=Special+Elite&family=Nunito:wght@500;600&display=swap" rel="stylesheet">\n'
    '<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>\n'
    '<style>'
)


def render_bulletin(key: str, zine_data=None, who_data=None,
                    prayer_data=None, verses=None, events_data=None,
                    today: datetime.date | None = None) -> str:
    """Full standalone HTML for the printable bulletin.

    key         access key (for the QR targets)
    zine_data   server.parse_zine()                    -> (title, sections) | None
    who_data    who.parse_who()                        -> (headline, welcome, sections) | None
    prayer_data prayer.parse_prayers(parse_event_date) -> {"days": [...]} | None
    verses      parse_bulletin_verses()                -> [(text, ref), ...]  (optional)
    """
    today = today or datetime.date.today()
    if verses is None:
        verses = parse_bulletin_verses()
    if not verses:
        verses = [_FALLBACK_VERSE]

    head_html, welcome_html = _welcome_html(who_data)
    zine_title = escape(zine_data[0]) if (zine_data and zine_data[0]) else "The Sunday Zine"
    v0_text, v0_ref = verses[0]

    body = BODY
    body = body.replace("__PRAYER_ROWS__", _prayer_rows(prayer_data, today))
    body = body.replace("__HEAD__", head_html or "Welcome")
    body = body.replace("__WELCOME__", welcome_html)
    body = body.replace("__ORDER__", _order_html(who_data))
    body = body.replace("__ZINE_TITLE__", zine_title)      # before __ZINE__
    body = body.replace("__ZINE__", _zine_html(zine_data))
    body = body.replace("__EVENTS__", _events_html(events_data))
    cover = _cover_data_uri()
    if cover:
        cover_inner = f'<img src="{cover}" alt="Grace House cover">'
    else:
        cover_inner = ('<div class="cover-fallback" aria-label="Grace House">'
                       '<div class="cf-mark">GRACE<br>HOUSE</div>'
                       '<div class="cf-hint">GraceHouseCover.png not found in the repo root</div>'
                       '</div>')
    body = body.replace("__COVER_INNER__", cover_inner)
    body = body.replace("__V_REF__", escape(v0_ref))
    body = body.replace("__V_TXT__", "“" + escape(v0_text) + "”")

    verses_json = json.dumps([{"ref": r, "text": t} for (t, r) in verses],
                             ensure_ascii=False)
    script = JS.replace("__KEY__", key).replace("__VERSES_JSON__", verses_json)

    return (_HEAD + CSS + "</style>\n</head>\n<body>\n"
            + body + "\n<script>" + script + "</script>\n</body>\n</html>\n")
