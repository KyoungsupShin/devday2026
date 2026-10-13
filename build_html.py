#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
교재/문서 마크다운을 스타일 적용 HTML로 변환한다.
  pip install markdown pygments
  python build_html.py
- 실습자용/ 강사용/ 의 *.md → 같은 폴더에 *.html
- 루트의 *.md(검증·설계 문서) → 루트에 *.html
- index.html 생성 (목차 + 링크)
"""
import re
from pathlib import Path
import markdown
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parent
FOLDERS = ["실습자용", "강사용"]

light_css = HtmlFormatter(style="default").get_style_defs(".codehilite")
dark_css = HtmlFormatter(style="monokai").get_style_defs(".codehilite")

CSS = """
:root { --bg:#fff; --fg:#1a1a1a; --muted:#5b6671; --border:#e3e8ee; --accent:#0a6ed1;
  --accent-soft:#eaf3fb; --code-bg:#f6f8fa; --th-bg:#f2f5f8; --quote-bg:#f7f9fb; --quote-bar:#0a6ed1; }
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#0f1115; --fg:#e6e8eb; --muted:#9aa4af; --border:#2a2f37; --accent:#4aa3ff;
  --accent-soft:#15202b; --code-bg:#161a20; --th-bg:#1a1f27; --quote-bg:#151a21; --quote-bar:#4aa3ff; } }
:root[data-theme="dark"]{ --bg:#0f1115; --fg:#e6e8eb; --muted:#9aa4af; --border:#2a2f37; --accent:#4aa3ff;
  --accent-soft:#15202b; --code-bg:#161a20; --th-bg:#1a1f27; --quote-bg:#151a21; --quote-bar:#4aa3ff; }
*{box-sizing:border-box;} html{-webkit-text-size-adjust:100%;}
body{background:var(--bg);color:var(--fg);margin:0;font-size:16px;line-height:1.7;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",Roboto,sans-serif;}
.wrap{max-width:860px;margin:0 auto;padding:24px 16px 96px;}
.topbar{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--border);padding:10px 16px;
  display:flex;gap:12px;align-items:center;font-size:13px;color:var(--muted);z-index:10;}
.topbar a{color:var(--accent);text-decoration:none;}
.topbar .crumb{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;} .topbar .spacer{flex:1;}
h1,h2,h3,h4{line-height:1.3;font-weight:700;} h1{font-size:1.8rem;margin:.2em 0 .6em;}
h2{font-size:1.35rem;margin:1.8em 0 .5em;padding-top:.6em;border-top:1px solid var(--border);}
h3{font-size:1.12rem;margin:1.3em 0 .4em;color:var(--accent);} h4{font-size:1rem;margin:1.1em 0 .3em;}
p,li{font-size:1rem;} a{color:var(--accent);text-decoration:underline;text-underline-offset:2px;overflow-wrap:anywhere;word-break:break-word;}
a:hover{text-decoration:underline;opacity:.85;}
td a,th a{overflow-wrap:anywhere;word-break:break-all;}
code{font-family:"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;background:var(--code-bg);
  padding:.12em .38em;border-radius:5px;font-size:.9em;}
pre{background:var(--code-bg);border:1px solid var(--border);border-radius:10px;padding:14px 16px;
  overflow-x:auto;font-size:.82rem;line-height:1.45;} pre code{background:none;padding:0;}
.codehilite{background:var(--code-bg);border:1px solid var(--border);border-radius:10px;padding:2px 14px;overflow-x:auto;margin:1em 0;}
.codehilite pre{border:none;background:none;padding:12px 0;margin:0;}
table{border-collapse:collapse;width:100%;margin:1em 0;font-size:.93rem;display:block;overflow-x:auto;}
th,td{border:1px solid var(--border);padding:8px 12px;text-align:left;vertical-align:top;} th{background:var(--th-bg);font-weight:600;}
blockquote{margin:1em 0;padding:10px 16px;background:var(--quote-bg);border-left:4px solid var(--quote-bar);border-radius:0 8px 8px 0;}
blockquote p{margin:.3em 0;} hr{border:none;border-top:1px solid var(--border);margin:2em 0;}
ul,ol{padding-left:1.5em;} li{margin:.25em 0;}
li.task{list-style:none;margin-left:-1.3em;} li.task input{margin-right:.5em;}
.theme-toggle{cursor:pointer;background:none;border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:3px 10px;font-size:12px;}
""" + light_css + "\n@media (prefers-color-scheme: dark){:root:not([data-theme=\"light\"]) {" + dark_css + "}}\n[data-theme=\"dark\"] {" + dark_css + "}\n"

PAGE = """<!DOCTYPE html>
<html lang="ko" data-theme="">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body>
<div class="topbar"><a href="{home}">⌂ 인덱스</a><span class="crumb">{crumb}</span>
<span class="spacer"></span><button class="theme-toggle" onclick="tog()">◐ 테마</button></div>
<div class="wrap">
{body}
</div>
<script>
function tog(){{var r=document.documentElement;var c=r.getAttribute('data-theme');
var n=c==='dark'?'light':(c==='light'?'':'dark');r.setAttribute('data-theme',n);
try{{localStorage.setItem('codejam-theme',n)}}catch(e){{}}}}
try{{var s=localStorage.getItem('codejam-theme');if(s)document.documentElement.setAttribute('data-theme',s)}}catch(e){{}}
</script>
</body></html>
"""

def md_to_html(md_text):
    md = markdown.Markdown(extensions=["fenced_code","tables","sane_lists","codehilite","toc"],
                           extension_configs={"codehilite":{"guess_lang":False,"css_class":"codehilite"}})
    html = md.convert(md_text)
    html = re.sub(r"<li>\s*\[ \]\s*", '<li class="task"><input type="checkbox" disabled> ', html)
    html = re.sub(r"<li>\s*\[[xX]\]\s*", '<li class="task"><input type="checkbox" checked disabled> ', html)
    html = re.sub(r'(href="[^"]*?)\.md(")', r"\1.html\2", html)
    return html

def first_title(md_text, fallback):
    for line in md_text.splitlines():
        if line.startswith("# "): return line[2:].strip()
    return fallback

def render(mdfile, home, crumb):
    text = mdfile.read_text(encoding="utf-8")
    title = first_title(text, mdfile.stem)
    (mdfile.parent / (mdfile.stem + ".html")).write_text(
        PAGE.format(title=title, css=CSS, body=md_to_html(text), home=home, crumb=crumb), encoding="utf-8")
    print("wrote", mdfile.relative_to(ROOT).with_suffix(".html"))
    return title

def links_for(folder):
    items = []
    for mdfile in sorted((ROOT/folder).glob("*.md")):
        t = first_title(mdfile.read_text(encoding="utf-8"), mdfile.stem)
        items.append(f'<li><a href="{folder}/{mdfile.stem}.html">{t}</a></li>')
    return "\n".join(items)

# 폴더 문서
for folder in FOLDERS:
    for mdfile in sorted((ROOT/folder).glob("*.md")):
        render(mdfile, "../index.html", f"{folder} / {mdfile.stem}")

# 루트 문서(설계·검증)
top = [(render(m, "index.html", m.stem), m.stem + ".html")
       for m in sorted(ROOT.glob("*.md"))]
top_links = "\n".join(f'<li><a href="{href}">{t}</a></li>' for t, href in top)

index_body = f"""<h1>SAP Generative AI Hub 핸즈온 — 4시간</h1>
<p>단일 공유 AI Core · SDK 코딩 중심 · Document Grounding + 에이전트 캅스톤.</p>
<p><a href="handson.html" style="display:inline-block;background:var(--accent);color:#fff;
  padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600;">📑 통합 보기 (탭) 열기</a></p>
{('<h2>설계 · 검증</h2><ul>' + top_links + '</ul>') if top_links else ''}
<h2>실습자용</h2><ul>
{links_for("실습자용")}
</ul>
<h2>강사용</h2><ul>
{links_for("강사용")}
</ul>
<hr><p style="color:var(--muted);font-size:.9rem">기반: SAP-samples/generative-ai-codejam</p>"""
(ROOT/"index.html").write_text(
    PAGE.format(title="Gen AI Hub 핸즈온 인덱스", css=CSS, body=index_body, home="index.html", crumb="인덱스"),
    encoding="utf-8")
print("wrote index.html")

# =====================================================================
# 통합 탭 단일 페이지 (handson.html)
#   - 상위 탭: 실습자용 / 강사용
#   - 하위 탭(사이드): 각 폴더의 모듈(00~07 등)
#   - 모든 본문을 한 파일에 포함(오프라인). iframe 없음.
# =====================================================================
import html as _html

def _module_label(stem: str) -> str:
    """'00-환경-준비' → '00 · 환경 준비' 형태의 짧은 탭 라벨."""
    s = stem
    if "-" in s and s.split("-", 1)[0].isdigit():
        num, rest = s.split("-", 1)
        return f"{num} · {rest.replace('-', ' ')}"
    return s.replace("-", " ")

def build_combined():
    groups = []  # [(folder, [(stem, title, body_html), ...]), ...]
    for folder in FOLDERS:
        docs = []
        for mdfile in sorted((ROOT / folder).glob("*.md")):
            text = mdfile.read_text(encoding="utf-8")
            title = first_title(text, mdfile.stem)
            body = md_to_html(text)
            # 통합 페이지 내부에서는 .html 링크(상대)를 자체 탭 전환으로 돌리기 어렵고,
            # 외부 개별 파일로 열리는 것도 유효하므로 그대로 둔다.
            docs.append((mdfile.stem, title, body))
        if docs:
            groups.append((folder, docs))

    # 네비 + 패널 생성
    group_btns = []
    panels = []
    first_group = True
    for gi, (folder, docs) in enumerate(groups):
        gid = f"g{gi}"
        group_btns.append(
            f'<button class="gtab{" active" if first_group else ""}" '
            f'data-g="{gid}" onclick="selGroup(\'{gid}\')">{_html.escape(folder)}</button>')
        # 사이드 모듈 목록
        side_items = []
        content_items = []
        first_doc = True
        for di, (stem, title, body) in enumerate(docs):
            pid = f"{gid}_d{di}"
            label = _module_label(stem)
            side_items.append(
                f'<li><button class="mtab{" active" if first_doc else ""}" '
                f'data-p="{pid}" onclick="selDoc(\'{gid}\',\'{pid}\')" '
                f'title="{_html.escape(title)}">{_html.escape(label)}</button></li>')
            content_items.append(
                f'<article class="doc{" active" if first_doc else ""}" id="{pid}">{body}</article>')
            first_doc = False
        panels.append(
            f'<section class="panel{" active" if first_group else ""}" id="{gid}">'
            f'<nav class="side"><ul>{"".join(side_items)}</ul></nav>'
            f'<div class="content">{"".join(content_items)}</div>'
            f'</section>')
        first_group = False

    body = f"""<div class="combined">
  <div class="gtabs">{"".join(group_btns)}</div>
  {"".join(panels)}
</div>
<script>
function selGroup(gid){{
  document.querySelectorAll('.combined .gtab').forEach(b=>b.classList.toggle('active', b.dataset.g===gid));
  document.querySelectorAll('.combined .panel').forEach(p=>p.classList.toggle('active', p.id===gid));
}}
function selDoc(gid, pid){{
  var panel=document.getElementById(gid);
  panel.querySelectorAll('.mtab').forEach(b=>b.classList.toggle('active', b.dataset.p===pid));
  panel.querySelectorAll('.doc').forEach(d=>d.classList.toggle('active', d.id===pid));
  panel.querySelector('.content').scrollTop=0;
}}
</script>"""

    combined_css = CSS + """
.combined{max-width:none;}
.gtabs{display:flex;gap:8px;margin:0 0 14px;flex-wrap:wrap;}
.gtabs .gtab{cursor:pointer;border:1px solid var(--border);background:var(--code-bg);color:var(--fg);
  border-radius:8px 8px 0 0;padding:8px 18px;font-size:15px;font-weight:600;}
.gtabs .gtab.active{background:var(--accent);color:#fff;border-color:var(--accent);}
.panel{display:none;gap:18px;}
.panel.active{display:flex;}
.side{flex:0 0 220px;position:sticky;top:60px;align-self:flex-start;max-height:calc(100vh - 80px);overflow-y:auto;}
.side ul{list-style:none;padding:0;margin:0;}
.side li{margin:.2em 0;}
.side .mtab{display:block;width:100%;text-align:left;cursor:pointer;border:1px solid transparent;
  background:none;color:var(--fg);border-radius:7px;padding:7px 10px;font-size:13.5px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.side .mtab:hover{background:var(--code-bg);}
.side .mtab.active{background:var(--accent-soft);color:var(--accent);border-color:var(--border);font-weight:600;}
.content{flex:1;min-width:0;border-left:1px solid var(--border);padding-left:22px;}
.content .doc{display:none;}
.content .doc.active{display:block;animation:fadein .15s ease;}
.content .doc h1{margin-top:0;}
@keyframes fadein{from{opacity:0}to{opacity:1}}
@media(max-width:720px){.panel.active{flex-direction:column;}
  .side{position:static;flex-basis:auto;max-height:none;}
  .content{border-left:none;padding-left:0;border-top:1px solid var(--border);padding-top:16px;}}
"""
    page = PAGE.format(title="Gen AI Hub 핸즈온 — 통합", css=combined_css,
                       body=body, home="index.html", crumb="통합 보기 (탭)")
    (ROOT / "handson.html").write_text(page, encoding="utf-8")
    print("wrote handson.html")

build_combined()
