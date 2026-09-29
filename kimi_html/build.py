#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 docs/interview_prep 下的 Markdown 面试资料生成纯离线静态站点。

用法（在仓库根目录）:
    python kimi_html/build.py

产物：kimi_html/ 下与源目录同层级的 .html 文件 + 总览页 kimi.html。
全部内联 CSS/JS，零 CDN、零网络依赖，file:// 双击可用。
"""

import json
import posixpath
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, unquote

import markdown
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "interview_prep"
OUT = ROOT / "kimi_html"

MD_EXTENSIONS = ["extra", "codehilite", "sane_lists", "toc"]
MD_CONFIGS = {
    "codehilite": {"guess_lang": False, "css_class": "codehilite"},
}

# 方向配色：00_导航靛蓝灰、01_AI 蓝、02_后端 橙、03_系统设计 绿、04_算法 金、05_项目表达 粉
DIRECTIONS = [
    ("00_导航", "导航", "#64748b"),
    ("01_AI", "AI", "#3b82f6"),
    ("02_后端", "后端", "#f97316"),
    ("03_系统设计", "系统设计", "#22c55e"),
    ("04_算法", "算法", "#eab308"),
    ("05_项目表达", "项目表达", "#ec4899"),
    ("", "资料总入口", "#8b5cf6"),
]


def direction_of(rel_posix):
    first = rel_posix.split("/")[0] if "/" in rel_posix else ""
    for key, label, color in DIRECTIONS:
        if key == first:
            return key, label, color
    return "", "资料总入口", "#8b5cf6"


# ---------------------------------------------------------------------------
# Markdown 源预处理：相对 .md 链接改写成对应 .html 相对路径
# ---------------------------------------------------------------------------
LINK_RE = re.compile(r"(\]\()([^)\s]+?\.md)((?:#[^)\s]*)?)(\))")


def rewrite_md_links(text, md_path):
    src_dir_rel = md_path.parent.relative_to(SRC).as_posix()

    def repl(m):
        href = m.group(2)
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href):
            return m.group(0)
        target = (md_path.parent / unquote(href)).resolve()
        try:
            rel = target.relative_to(SRC.resolve()).with_suffix(".html").as_posix()
        except ValueError:
            return m.group(0)
        new_href = posixpath.relpath(rel, src_dir_rel)
        new_href = "/".join(quote(seg) for seg in new_href.split("/"))
        return m.group(1) + new_href + (m.group(3) or "") + m.group(4)

    return LINK_RE.sub(repl, text)


# ---------------------------------------------------------------------------
# HTML 后处理
# ---------------------------------------------------------------------------
HEADING_RE = re.compile(r'<h([23])\s+id="([^"]+)"[^>]*>(.*?)</h\1>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def wrap_qa(html):
    """按 h2（无 h2 时按 h3）把正文切成可折叠的 <section class="qa">。"""
    level = 2 if "<h2 " in html else 3
    if not re.search(r"<h%d " % level, html):
        return html
    parts = re.split(
        r"(<h%d\s[^>]*>.*?</h%d>)" % (level, level), html, flags=re.S
    )
    out = [parts[0]]
    i = 1
    qn = 0
    while i + 1 < len(parts):
        head, body = parts[i], parts[i + 1]
        qn += 1
        mid = re.search(r'id="([^"]+)"', head)
        qid = mid.group(1) if mid else "q%d" % qn
        out.append(
            '<section class="qa" data-qid="'
            + qid
            + '"><div class="qa-head">'
            + head
            + '<span class="qa-mark" aria-hidden="true"></span>'
            + '<span class="qa-caret" aria-hidden="true">▾</span></div>'
            + '<div class="qa-body"><div class="qa-inner">'
            + body
            + '<div class="qa-rate">'
            '<button type="button" data-r="known">✓ 会了</button>'
            '<button type="button" data-r="learning">↺ 再看</button>'
            "</div></div></div></section>"
        )
        i += 2
    return "".join(out)


def extract_toc(html):
    toc = []
    for m in HEADING_RE.finditer(html):
        label = TAG_RE.sub("", m.group(3)).strip()
        toc.append({"level": int(m.group(1)), "id": m.group(2), "label": label})
    return toc


def extract_title(md_text, fallback):
    for line in md_text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


# ---------------------------------------------------------------------------
# Pygments 样式（明暗两套）
# ---------------------------------------------------------------------------
def scope_css(css, scope):
    out = []
    for line in css.splitlines():
        if "{" in line:
            sel, rest = line.split("{", 1)
            sels = ", ".join(scope + " " + s.strip() for s in sel.split(",") if s.strip())
            out.append(sels + " {" + rest)
        else:
            out.append(line)
    return "\n".join(out)


LIGHT_CODE_CSS = HtmlFormatter(style="default").get_style_defs(".codehilite")
DARK_CODE_CSS = scope_css(
    HtmlFormatter(style="monokai").get_style_defs(".codehilite"),
    'html[data-theme="dark"]',
)


# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------
COMMON_CSS = """
:root{
  --bg:#f7f8fa; --panel:#ffffff; --text:#1f2328; --muted:#6b7280;
  --border:#e5e7eb; --code-bg:#f5f5f0; --link:#2563eb; --accent:#8b5cf6;
  --quote-bg:#f1f5f9; --quote-border:#cbd5e1;
  --shadow:0 1px 3px rgba(0,0,0,.08);
}
html[data-theme="dark"]{
  --bg:#0f1115; --panel:#181b22; --text:#e6e8eb; --muted:#9aa1ab;
  --border:#2b3038; --code-bg:#282828; --link:#7aa2f7;
  --quote-bg:#1e2430; --quote-border:#374151;
  --shadow:0 1px 3px rgba(0,0,0,.4);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:76px}
body{margin:0;background:var(--bg);color:var(--text);
  font:16px/1.8 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
  "Hiragino Sans GB","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:var(--link);text-decoration:none}
a:hover{text-decoration:underline}
"""

CHAPTER_CSS = (
    COMMON_CSS
    + LIGHT_CODE_CSS
    + DARK_CODE_CSS
    + """
/* 顶部固定栏 */
#topbar{position:fixed;top:0;left:0;right:0;z-index:100;height:56px;
  display:flex;align-items:center;gap:12px;padding:0 16px;
  background:var(--panel);border-bottom:1px solid var(--border);box-shadow:var(--shadow)}
#topbar .back{flex:none;color:var(--muted);font-size:14px;white-space:nowrap}
#topbar .back:hover{color:var(--text)}
#topbar .dir-badge{flex:none;display:inline-flex;align-items:center;gap:6px;
  font-size:12px;color:var(--muted);white-space:nowrap}
#topbar .dir-badge .dot{width:10px;height:10px;border-radius:50%;background:var(--dir-color,#888)}
#topbar h1{flex:1;min-width:0;margin:0;font-size:15px;font-weight:600;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#topbar .meta{flex:none;font-size:12px;color:var(--muted);white-space:nowrap}
#read-badge{flex:none;display:none;font-size:12px;color:#16a34a;
  border:1px solid #16a34a;border-radius:10px;padding:1px 8px;white-space:nowrap}
#read-badge.show{display:inline-block}
#theme-btn,#expand-btn,#collapse-btn,#mode-btn,#random-btn{flex:none;cursor:pointer;font-size:13px;
  color:var(--text);background:transparent;border:1px solid var(--border);
  border-radius:6px;padding:3px 10px;white-space:nowrap;
  transition:transform .1s ease,border-color .15s,background-color .15s}
#theme-btn:hover,#expand-btn:hover,#collapse-btn:hover,#mode-btn:hover,#random-btn:hover{border-color:var(--muted)}
#theme-btn:active,#expand-btn:active,#collapse-btn:active,#mode-btn:active,#random-btn:active{transform:scale(.96)}
#mode-btn.on{color:var(--dir-color,#3b82f6);border-color:var(--dir-color,#3b82f6);font-weight:600}
#mastery{flex:none;font-size:12px;color:var(--muted);white-space:nowrap;
  border:1px solid var(--border);border-radius:10px;padding:1px 9px}
#mastery.full{color:#16a34a;border-color:#16a34a;font-weight:600}
#ace-badge{flex:none;display:none;font-size:15px}
#ace-badge.show{display:inline-block}
#progress{position:fixed;top:56px;left:0;height:2px;width:0;z-index:101;
  background:linear-gradient(90deg,var(--dir-color,#3b82f6),var(--accent,#8b5cf6));
  transition:width .12s linear}

/* 布局 */
.layout{max-width:1240px;margin:0 auto;padding:76px 20px 60px;
  display:flex;gap:32px;align-items:flex-start}
.content{flex:1;min-width:0;max-width:860px;margin:0 auto}
article{background:var(--panel);border:1px solid var(--border);
  border-radius:10px;padding:28px 36px;box-shadow:var(--shadow)}

/* 章内目录 */
#toc{position:sticky;top:76px;flex:none;width:220px;max-height:calc(100vh - 96px);
  overflow:auto;font-size:13px;padding:12px 0}
#toc .toc-title{font-weight:600;color:var(--muted);margin:0 0 8px;font-size:12px;
  letter-spacing:.08em}
#toc a{display:block;color:var(--muted);padding:3px 10px;
  border-left:2px solid var(--border);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
#toc a.toc-h3{padding-left:24px;font-size:12px}
#toc a:hover{color:var(--text);text-decoration:none}
#toc a.active{color:var(--dir-color,#3b82f6);border-left-color:var(--dir-color,#3b82f6);
  font-weight:600}
@media (max-width:980px){#toc{display:none}.layout{padding-left:14px;padding-right:14px}}

/* 正文排版 */
article h1{font-size:26px;line-height:1.4;margin:0 0 18px;padding-bottom:14px;
  border-bottom:1px solid var(--border)}
article h2{font-size:20px;margin:0;font-weight:600}
article h3{font-size:17px;margin:22px 0 10px}
article h4{font-size:15px;margin:18px 0 8px}
article p{margin:10px 0}
article img{max-width:100%}
article blockquote{margin:12px 0;padding:8px 16px;background:var(--quote-bg);
  border-left:3px solid var(--quote-border);border-radius:0 6px 6px 0;color:var(--muted)}
article blockquote p{margin:4px 0}
article code{font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;
  font-size:13.5px;background:var(--code-bg);border-radius:4px;padding:1px 5px}
article pre code{background:transparent;padding:0}
.table-wrap{overflow-x:auto;margin:12px 0}
article table{border-collapse:collapse;width:100%;font-size:14px}
article th,article td{border:1px solid var(--border);padding:7px 12px;text-align:left}
article th{background:var(--quote-bg)}
article hr{border:none;border-top:1px solid var(--border);margin:20px 0}

/* 问答折叠 */
.qa{margin:14px 0;border:1px solid var(--border);border-left:3px solid var(--border);
  border-radius:8px;overflow:hidden;transition:border-color .3s}
.qa-head{display:flex;align-items:center;gap:10px;cursor:pointer;
  padding:10px 16px;background:var(--quote-bg);user-select:none}
.qa-head h2,.qa-head h3{flex:1;min-width:0;margin:0;font-size:16px}
.qa-head .qa-caret{flex:none;color:var(--muted);font-size:13px;transition:transform .3s ease}
.qa-head:hover{background:var(--border)}
.qa-body{display:grid;grid-template-rows:1fr;transition:grid-template-rows .3s ease}
.qa-inner{overflow:hidden;min-height:0;padding:4px 16px 14px}
.qa.collapsed .qa-body{grid-template-rows:0fr}
.qa.collapsed .qa-caret{transform:rotate(-90deg)}

/* 自测模式：答案模糊揭示 */
@keyframes kf-reveal{from{filter:blur(14px);opacity:.15}to{filter:blur(0);opacity:1}}
body.quiz .qa:not(.collapsed) .qa-inner{animation:kf-reveal .45s ease}

/* 自评标记 */
.qa-mark{flex:none;font-size:12px;font-weight:600;white-space:nowrap}
.qa.m-known{border-left-color:#16a34a}
.qa.m-known .qa-mark{color:#16a34a}
.qa.m-known .qa-mark::before{content:"✓ 会了"}
.qa.m-learning{border-left-color:#f59e0b}
.qa.m-learning .qa-mark{color:#f59e0b}
.qa.m-learning .qa-mark::before{content:"↺ 再看"}
.qa-rate{margin-top:14px;padding-top:10px;border-top:1px dashed var(--border);
  display:flex;gap:10px}
.qa-rate button{cursor:pointer;font-size:12.5px;color:var(--muted);
  background:transparent;border:1px solid var(--border);border-radius:6px;
  padding:3px 12px;transition:transform .1s ease,border-color .15s,color .15s}
.qa-rate button:hover{border-color:var(--muted);color:var(--text)}
.qa-rate button:active{transform:scale(.96)}
.qa.m-known .qa-rate button[data-r="known"]{color:#16a34a;border-color:#16a34a}
.qa.m-learning .qa-rate button[data-r="learning"]{color:#f59e0b;border-color:#f59e0b}

/* 随机一问高亮闪烁 */
@keyframes kf-flash{0%,100%{box-shadow:0 0 0 0 transparent}
  30%,70%{box-shadow:0 0 0 3px var(--dir-color,#3b82f6)}}
.qa.flash{animation:kf-flash 1.2s ease 2}

/* 滚动渐入（JS 控制初始态，禁用 JS 时不隐藏内容） */
.reveal-on{opacity:0;transform:translateY(12px);
  transition:opacity .5s ease,transform .5s ease}
.reveal-on.in{opacity:1;transform:none}

@media (prefers-reduced-motion:reduce){
  .qa-body{transition:none}
  .qa-head .qa-caret{transition:none}
  #progress{transition:none}
  .reveal-on{opacity:1;transform:none;transition:none}
  .qa.flash{animation:none}
}

/* 代码块 */
.codehilite{position:relative;margin:12px 0;border-radius:8px;overflow:hidden;
  border:1px solid var(--border)}
.codehilite pre{margin:0;padding:14px;overflow-x:auto;font-size:13.5px;line-height:1.6}
html[data-theme="dark"] .codehilite{background:#282828}
.copy-btn{position:absolute;top:8px;right:8px;cursor:pointer;font-size:12px;
  color:var(--muted);background:var(--panel);border:1px solid var(--border);
  border-radius:5px;padding:2px 9px;opacity:0;transition:opacity .15s;z-index:2}
.codehilite:hover .copy-btn{opacity:1}
.copy-btn.ok{color:#16a34a;border-color:#16a34a;opacity:1}
@media (hover:none){.copy-btn{opacity:.8}}

/* 上下章导航 */
.pager{display:flex;justify-content:space-between;gap:16px;max-width:860px;
  margin:20px auto 0;font-size:14px}
.pager a{flex:1;min-width:0;padding:12px 16px;background:var(--panel);
  border:1px solid var(--border);border-radius:8px;color:var(--text);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pager a:hover{border-color:var(--dir-color,#3b82f6);text-decoration:none;
  color:var(--dir-color,#3b82f6)}
.pager .next{text-align:right}
.pager .disabled{visibility:hidden}

/* 回到顶部 */
#to-top{position:fixed;right:24px;bottom:28px;z-index:90;width:42px;height:42px;
  border-radius:50%;border:1px solid var(--border);background:var(--panel);
  color:var(--muted);font-size:18px;cursor:pointer;display:none;
  align-items:center;justify-content:center;box-shadow:var(--shadow)}
#to-top.show{display:flex}
#to-top:hover{color:var(--text)}
@media (max-width:640px){
  article{padding:18px 16px}
  #topbar h1{font-size:13px}
  #topbar .meta,#expand-btn,#collapse-btn{display:none}
}
"""
)

THEME_INIT_JS = """<script>(function(){var t=null;try{t=localStorage.getItem('kimi-theme');}catch(e){}if(!t){t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';}document.documentElement.setAttribute('data-theme',t);})();</script>"""

CHAPTER_JS = """
(function(){
  'use strict';
  var REL = '__REL_PATH__';
  var reduced = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- 主题 ---------- */
  function applyTheme(t){
    document.documentElement.setAttribute('data-theme', t);
    var b = document.getElementById('theme-btn');
    if (b) b.textContent = (t === 'dark') ? '\u2600' : '\u263E';
  }
  var theme = document.documentElement.getAttribute('data-theme') || 'light';
  var themeBtn = document.getElementById('theme-btn');
  if (themeBtn) themeBtn.textContent = (theme === 'dark') ? '\u2600' : '\u263E';
  if (themeBtn) themeBtn.addEventListener('click', function(){
    theme = (theme === 'dark') ? 'light' : 'dark';
    applyTheme(theme);
    try { localStorage.setItem('kimi-theme', theme); } catch(e){}
  });

  /* ---------- 折叠 ---------- */
  function setCaret(sec){
    var caret = sec.querySelector('.qa-caret');
    if (caret) caret.textContent = sec.classList.contains('collapsed') ? '\u25B8' : '\u25BE';
  }
  document.querySelectorAll('.qa-head').forEach(function(head){
    head.addEventListener('click', function(e){
      if (e.target.closest('.qa-rate')) return;
      var sec = head.parentElement;
      sec.classList.toggle('collapsed');
      sec.classList.add('seen');
      setCaret(sec);
    });
  });
  function setAll(collapsed){
    document.querySelectorAll('.qa').forEach(function(sec){
      sec.classList.toggle('collapsed', collapsed);
      if (!collapsed) sec.classList.add('seen');
      setCaret(sec);
    });
  }
  var eBtn = document.getElementById('expand-btn');
  var cBtn = document.getElementById('collapse-btn');
  if (eBtn) eBtn.addEventListener('click', function(){ setAll(false); });
  if (cBtn) cBtn.addEventListener('click', function(){ setAll(true); });

  /* ---------- 自测模式 ---------- */
  var modeBtn = document.getElementById('mode-btn');
  var quizMode = false;
  try { quizMode = localStorage.getItem('kimi-quiz-mode') === 'quiz'; } catch(e){}
  function applyMode(){
    document.body.classList.toggle('quiz', quizMode);
    if (modeBtn) {
      modeBtn.textContent = quizMode ? '\u81EA\u6D4B\u6A21\u5F0F' : '\u9605\u8BFB\u6A21\u5F0F';
      modeBtn.classList.toggle('on', quizMode);
    }
    setAll(!quizMode);
  }
  if (modeBtn) modeBtn.addEventListener('click', function(){
    quizMode = !quizMode;
    try { localStorage.setItem('kimi-quiz-mode', quizMode ? 'quiz' : 'read'); } catch(e){}
    applyMode();
  });

  /* ---------- 自评标记 + 掌握度 ---------- */
  var MARK_KEY = 'kimi-mark:' + REL;
  var marks = {};
  try { marks = JSON.parse(localStorage.getItem(MARK_KEY) || '{}') || {}; } catch(e){ marks = {}; }
  var masteryEl = document.getElementById('mastery');
  var aceEl = document.getElementById('ace-badge');

  function confetti(){
    if (reduced) return;
    var canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:300';
    document.body.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth; canvas.height = window.innerHeight;
    var colors = ['#3b82f6','#f97316','#22c55e','#eab308','#ec4899','#8b5cf6'];
    var parts = [];
    for (var i = 0; i < 140; i++) {
      parts.push({
        x: Math.random() * canvas.width, y: -Math.random() * canvas.height,
        w: 6 + Math.random() * 6, h: 8 + Math.random() * 8,
        vy: 2 + Math.random() * 3, vx: -1 + Math.random() * 2,
        rot: Math.random() * Math.PI, vr: -0.1 + Math.random() * 0.2,
        color: colors[i % colors.length]
      });
    }
    var start = Date.now();
    (function tick(){
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (var j = 0; j < parts.length; j++) {
        var p = parts[j];
        p.y += p.vy; p.x += p.vx; p.rot += p.vr;
        if (p.y > canvas.height + 20) { p.y = -20; p.x = Math.random() * canvas.width; }
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      }
      if (Date.now() - start < 3000) requestAnimationFrame(tick);
      else canvas.remove();
    })();
  }

  function refreshMastery(celebrate){
    var secs = document.querySelectorAll('.qa');
    var known = 0;
    secs.forEach(function(sec){
      if (marks[sec.getAttribute('data-qid')] === 'known') known++;
    });
    if (masteryEl) {
      masteryEl.textContent = '\u638C\u63E1 ' + known + '/' + secs.length;
      masteryEl.classList.toggle('full', secs.length > 0 && known === secs.length);
    }
    var aced = false;
    try { aced = !!localStorage.getItem('kimi-aced:' + REL); } catch(e){}
    if (secs.length > 0 && known === secs.length && !aced) {
      try { localStorage.setItem('kimi-aced:' + REL, '1'); } catch(e){}
      if (aceEl) aceEl.classList.add('show');
      if (celebrate) confetti();
    } else if (aced && aceEl) {
      aceEl.classList.add('show');
    }
  }

  function applyMarks(){
    document.querySelectorAll('.qa').forEach(function(sec){
      var st = marks[sec.getAttribute('data-qid')];
      sec.classList.toggle('m-known', st === 'known');
      sec.classList.toggle('m-learning', st === 'learning');
    });
  }
  document.querySelectorAll('.qa-rate button').forEach(function(btn){
    btn.addEventListener('click', function(e){
      e.stopPropagation();
      var sec = btn.closest('.qa');
      var qid = sec.getAttribute('data-qid');
      var val = btn.getAttribute('data-r');
      if (marks[qid] === val) delete marks[qid];
      else marks[qid] = val;
      try { localStorage.setItem(MARK_KEY, JSON.stringify(marks)); } catch(e){}
      applyMarks();
      refreshMastery(true);
    });
  });
  applyMarks();
  refreshMastery(false);

  /* ---------- 随机一问 ---------- */
  var randBtn = document.getElementById('random-btn');
  var lastPick = -1;
  if (randBtn) randBtn.addEventListener('click', function(){
    var secs = Array.prototype.slice.call(document.querySelectorAll('.qa'));
    if (!secs.length) return;
    setAll(true);
    var i = Math.floor(Math.random() * secs.length);
    if (secs.length > 1) { while (i === lastPick) i = Math.floor(Math.random() * secs.length); }
    lastPick = i;
    var sec = secs[i];
    sec.classList.remove('collapsed');
    sec.classList.add('seen');
    setCaret(sec);
    sec.scrollIntoView({behavior: reduced ? 'auto' : 'smooth', block: 'start'});
    sec.classList.remove('flash');
    void sec.offsetWidth;
    sec.classList.add('flash');
    setTimeout(function(){ sec.classList.remove('flash'); }, 2600);
  });

  /* ---------- 代码复制 ---------- */
  function markCopied(btn){
    btn.textContent = '\u5DF2\u590D\u5236';
    btn.classList.add('ok');
    setTimeout(function(){ btn.textContent = '\u590D\u5236'; btn.classList.remove('ok'); }, 1500);
  }
  function copyText(text, btn){
    function fallback(){
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); markCopied(btn); }
      catch(e){ btn.textContent = '\u5931\u8D25'; setTimeout(function(){ btn.textContent='\u590D\u5236'; }, 1500); }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function(){ markCopied(btn); }, fallback);
    } else { fallback(); }
  }
  document.querySelectorAll('.codehilite').forEach(function(el){
    var pre = el.querySelector('pre');
    if (!pre) return;
    var text = pre.innerText;
    var btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.type = 'button';
    btn.textContent = '\u590D\u5236';
    btn.addEventListener('click', function(){ copyText(text, btn); });
    el.appendChild(btn);
  });

  /* ---------- 表格横向滚动 ---------- */
  document.querySelectorAll('article table').forEach(function(tb){
    var w = document.createElement('div');
    w.className = 'table-wrap';
    tb.parentNode.insertBefore(w, tb);
    w.appendChild(tb);
  });

  /* ---------- 滚动渐入 ---------- */
  if (!reduced && 'IntersectionObserver' in window) {
    var revEls = document.querySelectorAll('.qa, article > h1, article > blockquote');
    revEls.forEach(function(el){ el.classList.add('reveal-on'); });
    var stagger = 0;
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(en){
        if (en.isIntersecting) {
          en.target.style.transitionDelay = Math.min(stagger++ * 40, 240) + 'ms';
          en.target.classList.add('in');
          io.unobserve(en.target);
        }
      });
    }, {rootMargin: '0px 0px -40px 0px'});
    revEls.forEach(function(el){ io.observe(el); });
  }

  /* ---------- 阅读进度条 / 回到顶部 / 已读标记 ---------- */
  var progress = document.getElementById('progress');
  var toTop = document.getElementById('to-top');
  var readDone = false;
  function markRead(){
    if (readDone) return;
    readDone = true;
    try { localStorage.setItem('kimi-read:' + REL, '1'); } catch(e){}
    var badge = document.getElementById('read-badge');
    if (badge) badge.classList.add('show');
  }
  try {
    if (localStorage.getItem('kimi-read:' + REL)) {
      readDone = true;
      var b0 = document.getElementById('read-badge');
      if (b0) b0.classList.add('show');
    }
  } catch(e){}

  /* 章内目录 scroll-spy */
  var tocLinks = [];
  document.querySelectorAll('#toc a').forEach(function(a){
    var t = document.getElementById(a.getAttribute('data-target'));
    if (t) tocLinks.push({link: a, target: t});
  });

  var ticking = false;
  function onScroll(){
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function(){
      ticking = false;
      var st = window.pageYOffset || document.documentElement.scrollTop;
      var sh = document.documentElement.scrollHeight - window.innerHeight;
      var pct = sh > 0 ? Math.min(100, st / sh * 100) : 100;
      if (progress) progress.style.width = pct + '%';
      if (toTop) toTop.classList.toggle('show', st > window.innerHeight);
      if (sh > 0 && st / sh >= 0.9) markRead();
      var current = null;
      for (var i = 0; i < tocLinks.length; i++) {
        if (tocLinks[i].target.getBoundingClientRect().top <= 90) current = tocLinks[i];
        else break;
      }
      tocLinks.forEach(function(it){ it.link.classList.toggle('active', it === current); });
    });
  }
  window.addEventListener('scroll', onScroll, {passive: true});
  window.addEventListener('resize', onScroll);

  /* 自测模式初始化（读完标记后应用默认收起/展开） */
  applyMode();
  onScroll();

  if (toTop) toTop.addEventListener('click', function(){
    window.scrollTo({top: 0, behavior: reduced ? 'auto' : 'smooth'});
  });
})();
"""

CHAPTER_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · Agent Offer</title>
__THEME_INIT__
<style>__CSS__</style>
</head>
<body style="--dir-color:__DIR_COLOR__">
<header id="topbar">
  <a class="back" href="__HOME_LINK__">&#8592; 返回总览</a>
  <span class="dir-badge"><span class="dot"></span>__DIR_LABEL__</span>
  <h1>__TITLE__</h1>
  <span id="read-badge">&#10003; 已读</span>
  <span id="ace-badge" title="本章全部掌握">&#127942;</span>
  <span id="mastery">掌握 0/0</span>
  <span class="meta">约 __MINUTES__ 分钟 · __CHARS_FMT__ 字</span>
  <button id="mode-btn" type="button">阅读模式</button>
  <button id="random-btn" type="button">&#127922; 随机一问</button>
  <button id="expand-btn" type="button">全部展开</button>
  <button id="collapse-btn" type="button">全部收起</button>
  <button id="theme-btn" type="button" aria-label="切换主题"></button>
</header>
<div id="progress"></div>
<div class="layout">
  <div class="content">
    <article>
__BODY__
    </article>
    <nav class="pager">
      __PREV__
      __NEXT__
    </nav>
  </div>
  __TOC__
</div>
<button id="to-top" type="button" aria-label="回到顶部">&#8593;</button>
<script>__JS__</script>
</body>
</html>
"""

OVERVIEW_CSS = (
    COMMON_CSS
    + """
.page{max-width:1200px;margin:0 auto;padding:0 20px 60px}
#obar{position:sticky;top:0;z-index:100;display:flex;align-items:center;gap:12px;
  padding:12px 0;background:var(--bg)}
#obar h1{margin:0;font-size:18px;flex:1}
#obar button{cursor:pointer;font-size:13px;color:var(--text);background:transparent;
  border:1px solid var(--border);border-radius:6px;padding:4px 12px;
  transition:transform .1s ease,border-color .15s}
#obar button:hover{border-color:var(--muted)}
#obar button:active{transform:scale(.96)}
.hero{background:var(--panel);border:1px solid var(--border);border-radius:12px;
  padding:28px 32px;margin:8px 0 24px;box-shadow:var(--shadow)}
.hero h2{margin:0 0 6px;font-size:26px}
.hero .sub{color:var(--muted);font-size:14px;margin-bottom:16px}
.hero .stats{display:flex;flex-wrap:wrap;gap:20px;font-size:14px;color:var(--muted);
  margin-bottom:14px}
.hero .stats b{color:var(--text);font-size:18px;margin-right:4px}
.bar{height:8px;background:var(--border);border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,#3b82f6,#22c55e);
  border-radius:4px;transition:width .5s}
.hero .actions{margin-top:16px;display:flex;gap:10px;flex-wrap:wrap}
.btn{display:inline-block;padding:8px 18px;border-radius:8px;font-size:14px;
  background:#3b82f6;color:#fff;border:none;cursor:pointer}
.btn:hover{text-decoration:none;background:#2563eb}
.btn.ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}
.btn.ghost:hover{color:var(--text);background:transparent}
#filter{width:100%;margin:0 0 20px;padding:10px 14px;font-size:15px;
  color:var(--text);background:var(--panel);border:1px solid var(--border);
  border-radius:8px;outline:none}
#filter:focus{border-color:#3b82f6}
.dir-group{margin-bottom:28px}
.dir-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.dir-head .dot{width:12px;height:12px;border-radius:3px}
.dir-head h3{margin:0;font-size:17px}
.dir-head .cnt{font-size:12px;color:var(--muted)}
.dir-head .mini{flex:1;max-width:220px;margin-left:auto}
.dir-head .mini .bar{height:5px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.card{display:block;background:var(--panel);border:1px solid var(--border);
  border-left:4px solid var(--c,#888);border-radius:8px;padding:12px 16px;
  color:var(--text);box-shadow:var(--shadow);
  transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease}
.card:hover{text-decoration:none;border-color:var(--c,#888);
  transform:translateY(-2px);box-shadow:0 6px 18px rgba(0,0,0,.14)}
html[data-theme="dark"] .card:hover{box-shadow:0 6px 18px rgba(0,0,0,.5)}
.card.aced{border-color:#eab308;
  box-shadow:0 0 0 1px rgba(234,179,8,.35),0 2px 10px rgba(234,179,8,.18)}
.card.aced:hover{box-shadow:0 0 0 1px rgba(234,179,8,.5),0 6px 18px rgba(234,179,8,.28)}
.card .t{font-size:14.5px;font-weight:600;margin-bottom:6px;
  display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.card .t .done{color:#16a34a;flex:none;font-size:13px}
.card .t .trophy{flex:none;font-size:15px}
.card .m{font-size:12px;color:var(--muted)}
.card .m2{font-size:12px;color:#16a34a;margin-top:3px}
#confetti{position:fixed;inset:0;pointer-events:none;z-index:200}
.hidden{display:none !important}
@media (prefers-reduced-motion:reduce){
  .card{transition:none}
  .card:hover{transform:none}
  .bar>i{transition:none !important}
  #obar button{transition:none}
}
"""
)

OVERVIEW_JS = """
(function(){
  'use strict';
  var DATA = __DATA_JSON__;

  /* 主题 */
  var theme = document.documentElement.getAttribute('data-theme') || 'light';
  var themeBtn = document.getElementById('theme-btn');
  function applyTheme(t){
    document.documentElement.setAttribute('data-theme', t);
    if (themeBtn) themeBtn.textContent = (t === 'dark') ? '\\u2600' : '\\u263E';
  }
  applyTheme(theme);
  if (themeBtn) themeBtn.addEventListener('click', function(){
    theme = (theme === 'dark') ? 'light' : 'dark';
    applyTheme(theme);
    try { localStorage.setItem('kimi-theme', theme); } catch(e){}
  });

  /* 已读状态 */
  function isRead(p){
    try { return !!localStorage.getItem('kimi-read:' + p); } catch(e){ return false; }
  }
  var readCount = 0, firstUnread = null;
  DATA.chapters.forEach(function(ch){
    ch.read = isRead(ch.path);
    if (ch.read) readCount++;
    else if (!firstUnread) firstUnread = ch;
  });

  /* Hero 统计 count-up */
  var reduced = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function countUp(el, target, fmt){
    if (!el) return;
    if (reduced || target <= 0) { el.textContent = fmt(target); return; }
    var dur = 800, t0 = performance.now();
    (function step(now){
      var k = Math.min(1, (now - t0) / dur);
      var e = 1 - Math.pow(1 - k, 3);
      el.textContent = fmt(Math.round(target * e));
      if (k < 1) requestAnimationFrame(step);
      else el.textContent = fmt(target);
    })(t0);
  }
  function fmtPlain(n){ return String(n); }
  function fmtComma(n){ return n.toLocaleString('en-US'); }
  var totalChars = 0;
  DATA.chapters.forEach(function(c){ totalChars += c.chars; });
  countUp(document.getElementById('stat-count'), DATA.chapters.length, fmtPlain);
  countUp(document.getElementById('stat-total'), totalChars, fmtComma);
  countUp(document.getElementById('stat-read'), readCount, fmtPlain);
  requestAnimationFrame(function(){
    document.getElementById('all-bar').style.width =
      Math.round(readCount / DATA.chapters.length * 100) + '%';
  });

  var cont = document.getElementById('continue-btn');
  if (firstUnread) {
    cont.href = firstUnread.path;
    cont.textContent = '\\u7EE7\\u7EED\\u5B66\\u4E60\\uFF1A' + firstUnread.title;
  } else {
    cont.style.display = 'none';
  }

  /* 渲染方向分组 */
  var host = document.getElementById('groups');
  DATA.directions.forEach(function(dir){
    var chs = DATA.chapters.filter(function(c){ return c.dir === dir.key; });
    if (!chs.length) return;
    var g = document.createElement('div');
    g.className = 'dir-group';
    g.setAttribute('data-dir', dir.key);
    var dRead = chs.filter(function(c){ return c.read; }).length;
    g.innerHTML =
      '<div class="dir-head"><span class="dot" style="background:' + dir.color + '"></span>' +
      '<h3>' + dir.label + '</h3>' +
      '<span class="cnt">' + chs.length + ' \\u7AE0 \\u00B7 \\u5DF2\\u8BFB ' + dRead + '</span>' +
      '<span class="mini"><span class="bar"><i class="anim-bar" data-w="' +
        Math.round(dRead / chs.length * 100) + '" style="width:0;background:' + dir.color + '"></i></span></span>' +
      '</div>';
    var grid = document.createElement('div');
    grid.className = 'grid';
    chs.forEach(function(ch){
      var a = document.createElement('a');
      a.className = 'card';
      a.href = ch.path;
      a.style.setProperty('--c', dir.color);
      a.setAttribute('data-title', (ch.title + ' ' + ch.path).toLowerCase());
      /* 掌握度/奖杯 */
      var markInfo = '';
      var aced = false;
      try {
        var mk = JSON.parse(localStorage.getItem('kimi-mark:' + ch.path) || '{}') || {};
        var known = 0, total = 0;
        for (var k in mk) {
          if (!Object.prototype.hasOwnProperty.call(mk, k)) continue;
          total++;
          if (mk[k] === 'known') known++;
        }
        if (total > 0 && ch.qas > 0) {
          markInfo = '<div class="m2">\\u4F1A\\u4E86 ' + known + '/' + ch.qas + '</div>';
        }
        aced = !!localStorage.getItem('kimi-aced:' + ch.path);
      } catch(e){}
      if (aced) a.classList.add('aced');
      a.innerHTML =
        '<div class="t"><span>' + ch.title + '</span>' +
        (aced ? '<span class="trophy">\\uD83C\\uDFC6</span>' :
          (ch.read ? '<span class="done">\\u2713 \\u5DF2\\u8BFB</span>' : '')) + '</div>' +
        '<div class="m">' + ch.chars_fmt + ' \\u5B57 \\u00B7 \\u7EA6 ' + ch.minutes + ' \\u5206\\u949F</div>' +
        markInfo;
      grid.appendChild(a);
    });
    g.appendChild(grid);
    host.appendChild(g);
  });

  /* 方向进度条首次进入视口时从 0 动画到目标值 */
  var bars = document.querySelectorAll('.anim-bar');
  if (reduced || !('IntersectionObserver' in window)) {
    bars.forEach(function(b){ b.style.width = b.getAttribute('data-w') + '%'; });
  } else {
    var bio = new IntersectionObserver(function(entries){
      entries.forEach(function(en){
        if (en.isIntersecting) {
          en.target.style.width = en.target.getAttribute('data-w') + '%';
          bio.unobserve(en.target);
        }
      });
    }, {rootMargin: '0px 0px -30px 0px'});
    bars.forEach(function(b){ bio.observe(b); });
  }

  /* 过滤 */
  var input = document.getElementById('filter');
  input.addEventListener('input', function(){
    var q = input.value.trim().toLowerCase();
    document.querySelectorAll('.dir-group').forEach(function(g){
      var visible = 0;
      g.querySelectorAll('.card').forEach(function(c){
        var show = !q || c.getAttribute('data-title').indexOf(q) >= 0;
        c.classList.toggle('hidden', !show);
        if (show) visible++;
      });
      g.classList.toggle('hidden', visible === 0);
    });
  });

  /* 清除阅读记录 */
  document.getElementById('clear-btn').addEventListener('click', function(){
    if (!window.confirm('\\u786E\\u5B9A\\u6E05\\u9664\\u5168\\u90E8\\u9605\\u8BFB\\u8BB0\\u5F55\\uFF1F')) return;
    try {
      var keys = [];
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && k.indexOf('kimi-read:') === 0) keys.push(k);
      }
      keys.forEach(function(k){ localStorage.removeItem(k); });
    } catch(e){}
    location.reload();
  });

  /* 全部读完的彩带庆祝 */
  if (readCount === DATA.chapters.length && DATA.chapters.length > 0 && !reduced) {
    var canvas = document.createElement('canvas');
    canvas.id = 'confetti';
    document.body.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    var W, H;
    function resize(){
      W = canvas.width = window.innerWidth;
      H = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);
    var colors = ['#3b82f6', '#f97316', '#22c55e', '#eab308', '#ec4899', '#8b5cf6'];
    var parts = [];
    for (var i = 0; i < 160; i++) {
      parts.push({
        x: Math.random() * W,
        y: -Math.random() * H,
        w: 6 + Math.random() * 6,
        h: 8 + Math.random() * 8,
        vy: 2 + Math.random() * 3,
        vx: -1 + Math.random() * 2,
        rot: Math.random() * Math.PI,
        vr: -0.1 + Math.random() * 0.2,
        color: colors[i % colors.length]
      });
    }
    var start = Date.now();
    (function tick(){
      ctx.clearRect(0, 0, W, H);
      for (var j = 0; j < parts.length; j++) {
        var p = parts[j];
        p.y += p.vy; p.x += p.vx; p.rot += p.vr;
        if (p.y > H + 20) { p.y = -20; p.x = Math.random() * W; }
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      }
      if (Date.now() - start < 3500) requestAnimationFrame(tick);
      else canvas.remove();
    })();
  }
})();
"""


def esc(s):
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    sys.stdout.reconfigure(encoding="utf-8")
    md_files = sorted(
        SRC.rglob("*.md"), key=lambda p: p.relative_to(SRC).as_posix()
    )
    if not md_files:
        print("未找到源文件: %s" % SRC, file=sys.stderr)
        sys.exit(1)

    # 清空再生成（保留 build.py 自身）
    if OUT.exists():
        for child in OUT.iterdir():
            if child.name == "build.py":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    OUT.mkdir(exist_ok=True)

    rel_paths = [p.relative_to(SRC).as_posix() for p in md_files]
    html_paths = [posixpath.splitext(r)[0] + ".html" for r in rel_paths]

    # 先收集全部标题，供上一章/下一章导航使用
    titles = []
    for md_path in md_files:
        titles.append(
            extract_title(md_path.read_text(encoding="utf-8"), md_path.stem)
        )

    chapters = []
    total_chars = 0

    for idx, md_path in enumerate(md_files):
        rel_posix = rel_paths[idx]
        out_rel = html_paths[idx]
        text = md_path.read_text(encoding="utf-8")
        chars = len(text)
        total_chars += chars
        minutes = max(1, round(chars / 500))
        title = titles[idx]
        dir_key, dir_label, dir_color = direction_of(rel_posix)
        depth = out_rel.count("/")

        html_body = markdown.markdown(
            rewrite_md_links(text, md_path),
            extensions=MD_EXTENSIONS,
            extension_configs=MD_CONFIGS,
        )
        html_body = wrap_qa(html_body)
        toc = extract_toc(html_body)

        def pager_link(j, cls, arrow):
            if j < 0 or j >= len(md_files):
                return '<a class="%s disabled" href="#"></a>' % cls
            href = posixpath.relpath(html_paths[j], posixpath.dirname(out_rel) or ".")
            href = "/".join(quote(seg) for seg in href.split("/"))
            return '<a class="%s" href="%s">%s %s</a>' % (
                cls, href, arrow, esc(titles[j])
            )

        toc_html = ""
        if toc:
            items = [
                '<a href="#%s" data-target="%s" class="toc-h%d">%s</a>'
                % (it["id"], it["id"], it["level"], esc(it["label"]))
                for it in toc
            ]
            toc_html = (
                '<nav id="toc"><p class="toc-title">章内目录</p>'
                + "".join(items)
                + "</nav>"
            )

        page = (
            CHAPTER_TEMPLATE.replace("__TITLE__", esc(title))
            .replace("__THEME_INIT__", THEME_INIT_JS)
            .replace("__CSS__", CHAPTER_CSS)
            .replace("__DIR_COLOR__", dir_color)
            .replace("__DIR_LABEL__", esc(dir_label))
            .replace("__HOME_LINK__", "../" * depth + "kimi.html")
            .replace("__MINUTES__", str(minutes))
            .replace("__CHARS_FMT__", "{:,}".format(chars))
            .replace("__BODY__", html_body)
            .replace("__TOC__", toc_html)
            .replace("__PREV__", pager_link(idx - 1, "prev", "&#8592;"))
            .replace("__NEXT__", pager_link(idx + 1, "next", "&#8594;"))
            .replace(
                "__JS__",
                CHAPTER_JS.replace("__REL_PATH__", out_rel).replace(
                    "__DIR_COLOR__", dir_color
                ),
            )
        )
        dest = OUT / out_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page, encoding="utf-8")
        chapters.append(
            {
                "path": out_rel,
                "title": title,
                "dir": dir_key,
                "chars": chars,
                "minutes": minutes,
                "qas": html_body.count('<section class="qa"'),
            }
        )

    # 总览页 kimi.html
    dirs_used = [
        {"key": key, "label": label, "color": color}
        for key, label, color in DIRECTIONS
        if any(c["dir"] == key for c in chapters)
    ]
    data = {
        "directions": dirs_used,
        "chapters": [
            {
                "path": c["path"],
                "title": c["title"],
                "dir": c["dir"],
                "chars": c["chars"],
                "chars_fmt": "{:,}".format(c["chars"]),
                "minutes": c["minutes"],
                "qas": c["qas"],
            }
            for c in chapters
        ],
    }
    total_fmt = "{:,}".format(total_chars)
    overview = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Offer · Kimi 教程</title>
__THEME_INIT__
<style>__CSS__</style>
</head>
<body>
<div class="page">
  <div id="obar">
    <h1>Agent Offer · Kimi 教程</h1>
    <button id="clear-btn" type="button">清除阅读记录</button>
    <button id="theme-btn" type="button" aria-label="切换主题"></button>
  </div>
  <section class="hero">
    <h2>面试复习总览</h2>
    <p class="sub">Agent Offer 面试资料静态教程站 · 纯离线 · 双击即用</p>
    <div class="stats">
      <span><b id="stat-count">__COUNT__</b>章节</span>
      <span><b id="stat-total">__TOTAL__</b>总字数</span>
      <span>已读 <b id="stat-read">0</b> / __COUNT__</span>
    </div>
    <div class="bar"><i id="all-bar"></i></div>
    <div class="actions"><a id="continue-btn" class="btn" href="#">继续学习</a></div>
  </section>
  <input id="filter" type="search" placeholder="按章节标题过滤…">
  <div id="groups"></div>
</div>
<script>__JS__</script>
</body>
</html>
"""
    overview = (
        overview.replace("__THEME_INIT__", THEME_INIT_JS)
        .replace("__CSS__", OVERVIEW_CSS)
        .replace("__COUNT__", str(len(chapters)))
        .replace("__TOTAL__", total_fmt)
        .replace(
            "__JS__",
            OVERVIEW_JS.replace(
                "__DATA_JSON__", json.dumps(data, ensure_ascii=False)
            ),
        )
    )
    (OUT / "kimi.html").write_text(overview, encoding="utf-8")

    html_count = len(list(OUT.rglob("*.html")))
    print("源 Markdown 章节数: %d" % len(md_files))
    print("生成 HTML 文件数:  %d (含 kimi.html)" % html_count)
    print("总字符数:          %s" % total_fmt)
    print("输出目录:          %s" % OUT)
    assert len(md_files) == 52, "章节数应为 52，实际 %d" % len(md_files)
    print("断言通过: 章节数 == 52")


if __name__ == "__main__":
    main()
