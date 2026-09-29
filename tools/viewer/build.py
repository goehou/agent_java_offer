"""把 docs/interview_prep 下的 Markdown 打包进单文件 HTML 可视化页面。

用法（仓库根目录执行）：
    python tools/viewer/build.py
产物：tools/viewer/index.html（离线可用，双击即可打开）
"""
import datetime
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
PREP = ROOT / "docs" / "interview_prep"
HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE / "template.html"
OUTPUT = HERE / "index.html"
PLACEHOLDER = "__AGENT_OFFER_DATA__"
ROOT_FILES = ["README.md", "DISCLAIMER.md"]  # 仓库根目录下需要一并展示的文件

PREFIX = re.compile(r"^\d+_")


def strip_prefix(name: str) -> str:
    return PREFIX.sub("", name)


def title_of(md: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+?)\s*$", md, re.M)
    return m.group(1) if m else fallback


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def snapshot() -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h %cd", "--date=short"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out
    except (OSError, subprocess.CalledProcessError):
        pass
    return datetime.date.today().isoformat()


def collect():
    docs = {}
    for f in sorted(PREP.rglob("*.md")):
        rel = f.relative_to(PREP).as_posix()
        md = read(f)
        docs[rel] = {"md": md, "title": title_of(md, f.stem)}
    for name in ROOT_FILES:
        f = ROOT / name
        if f.exists():
            md = read(f)
            docs["@root/" + name] = {"md": md, "title": title_of(md, f.stem)}

    directions = []
    for d in sorted(p for p in PREP.iterdir() if p.is_dir() and PREFIX.match(p.name)):
        if d.name.startswith("00_"):  # 导航目录单独处理，不算方向
            continue
        topics = [
            {"path": f"{d.name}/{t.name}/01_核心问答.md", "name": strip_prefix(t.name)}
            for t in sorted(p for p in d.iterdir() if p.is_dir())
            if (t / "01_核心问答.md").exists()
        ]
        readme = f"{d.name}/README.md"
        directions.append({
            "key": d.name,
            "name": strip_prefix(d.name),
            "readme": readme if readme in docs else None,
            "topics": topics,
        })
    return {"generatedAt": snapshot(), "directions": directions, "docs": docs}


def main():
    data = collect()
    # 防止正文里的 "</script>" 提前闭合数据块
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = read(TEMPLATE)
    if PLACEHOLDER not in html:
        raise SystemExit(f"模板中缺少占位符 {PLACEHOLDER}")
    OUTPUT.write_text(html.replace(PLACEHOLDER, payload), encoding="utf-8", newline="\n")
    topics = sum(len(d["topics"]) for d in data["directions"])
    print(f"OK: {len(data['docs'])} docs, {len(data['directions'])} directions, {topics} topics "
          f"-> {OUTPUT.relative_to(ROOT).as_posix()} ({OUTPUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
