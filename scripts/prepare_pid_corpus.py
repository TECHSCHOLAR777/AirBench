"""Build the desktop app's P&ID showcase corpus from demo_showcase/PID.

The source drawings are 7168x4562 PNGs (~6MB each) with a matching
ground-truth .graphml. This script writes web-sized JPEG derivatives into
apps/desktop/public/pid-corpus/ and copies the GraphML into
apps/desktop/src/assets/pid-corpus/ (where Vite can lazily import it as raw
text, so the frontend never needs a fetch call for it). Bounding boxes in
the GraphML stay in original pixel space, so the rendered topology still
lines up with the full-resolution drawing.

Run from the repo root:  python scripts/prepare_pid_corpus.py
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_ROOT / "demo_showcase" / "PID"
TARGET_DIR = REPO_ROOT / "apps" / "desktop" / "public" / "pid-corpus"
GRAPHML_DIR = REPO_ROOT / "apps" / "desktop" / "src" / "assets" / "pid-corpus"

THUMB_WIDTH = 900
DISPLAY_WIDTH = 2600

DRAWINGS = [
    ("0", "PID-101", "Crude feed and preheat train", "Unit 100 - Crude distillation"),
    ("1", "PID-102", "Atmospheric column overhead", "Unit 100 - Crude distillation"),
    ("2", "PID-103", "Debutanizer reflux loop", "Unit 200 - Light ends recovery"),
    ("3", "PID-104", "Hydrotreater reactor loop", "Unit 300 - Distillate hydrotreating"),
    ("4", "PID-105", "Product rundown and storage", "Unit 400 - Rundown and tankage"),
]


def graph_counts(graphml: str) -> tuple[int, int, dict[str, int]]:
    nodes = re.findall(r'<node id="([^"]+)">(.*?)</node>', graphml, re.S)
    edges = re.findall(r'<edge source="([^"]+)" target="([^"]+)"', graphml)
    labels: dict[str, int] = {}
    for _, body in nodes:
        found = re.search(r'key="d0">([^<]*)<', body)
        label = found.group(1) if found else "unknown"
        labels[label] = labels.get(label, 0) + 1
    return len(nodes), len(edges), labels


def write_jpeg(source: Path, target: Path, width: int) -> None:
    with Image.open(source) as image:
        height = round(image.height * (width / image.width))
        resized = image.convert("RGB").resize((width, height), Image.LANCZOS)
        resized.save(target, "JPEG", quality=85, optimize=True, progressive=True)


def main() -> int:
    if not SOURCE_DIR.is_dir():
        print(f"Source corpus not found: {SOURCE_DIR}")
        return 1
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    GRAPHML_DIR.mkdir(parents=True, exist_ok=True)

    entries = []
    for stem, tag, title, unit in DRAWINGS:
        png = SOURCE_DIR / f"{stem}.png"
        graphml = SOURCE_DIR / f"{stem}.graphml"
        if not png.exists() or not graphml.exists():
            print(f"Skipping {stem}: missing source files")
            continue

        write_jpeg(png, TARGET_DIR / f"{stem}-thumb.jpg", THUMB_WIDTH)
        write_jpeg(png, TARGET_DIR / f"{stem}-display.jpg", DISPLAY_WIDTH)
        shutil.copyfile(graphml, GRAPHML_DIR / f"{stem}.graphml")

        with Image.open(png) as image:
            source_width, source_height = image.size
        node_count, edge_count, labels = graph_counts(graphml.read_text(encoding="utf-8"))

        entries.append({
            "id": stem,
            "tag": tag,
            "title": title,
            "unit": unit,
            "thumb": f"/pid-corpus/{stem}-thumb.jpg",
            "display": f"/pid-corpus/{stem}-display.jpg",
            "width": source_width,
            "height": source_height,
            "node_count": node_count,
            "edge_count": edge_count,
            "labels": labels,
        })
        print(f"{tag}: {node_count} nodes, {edge_count} edges")

    (TARGET_DIR / "manifest.json").write_text(json.dumps({"drawings": entries}, indent=2), encoding="utf-8")
    print(f"Wrote {len(entries)} drawings to {TARGET_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
