"""Convert the team's navigation-tree sheet into the prototype / pipeline tree format.

Input : "Navigation tree - Sheet1.csv"  (columns To:, From:, tap/s, page)
Output: prototype/data/tree.csv         (columns node_id, parent_id, level, label)

The prototype loads prototype/data/tree.csv at runtime and copies it into every export as
reference/tree.csv, so the analysis pipeline always sees the same tree the participant used.

Run:  python scripts/build_prototype_tree.py
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "Navigation tree - Sheet1.csv"
OUT = ROOT / "prototype" / "data" / "tree.csv"

# Manual label fixes, kept here so they are visible and reviewable.
LABEL_FIXES = {
    # The sheet holds an example post title instead of a menu label.
    "C7.2": "Posts",
}
# Mojibake from copying curly quotes through a Mac/Windows codepage round trip.
MOJIBAKE = {"‚Äô": "'", "â€™": "'", "’": "'"}


def clean_label(label: str) -> str:
    for bad, good in MOJIBAKE.items():
        label = label.replace(bad, good)
    return " ".join(label.split())


def build(src: Path = SRC, out: Path = OUT) -> list[dict]:
    with src.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    nodes = []
    for r in rows:
        node_id = r["To:"].strip()
        if not node_id:
            continue
        nodes.append({
            "node_id": node_id,
            "parent_id": r["From:"].strip(),
            "level": int(r["tap/s"].strip()),
            "label": LABEL_FIXES.get(node_id, clean_label(r["page"])),
        })

    ids = {n["node_id"] for n in nodes}
    roots = [n for n in nodes if not n["parent_id"]]
    if len(roots) != 1:
        raise SystemExit(f"tree must have exactly one root, found {[n['node_id'] for n in roots]}")
    for n in nodes:
        if n["parent_id"] and n["parent_id"] not in ids:
            raise SystemExit(f"{n['node_id']}: parent {n['parent_id']} not in tree")
    by_id = {n["node_id"]: n for n in nodes}
    for n in nodes:
        if n["parent_id"] and by_id[n["parent_id"]]["level"] != n["level"] - 1:
            raise SystemExit(f"{n['node_id']}: level {n['level']} is not parent level + 1")

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["node_id", "parent_id", "level", "label"], lineterminator="\n")
        w.writeheader()
        w.writerows(nodes)
    return nodes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    nodes = build(a.src, a.out)
    print(f"wrote {len(nodes)} nodes to {a.out.relative_to(ROOT) if a.out.is_relative_to(ROOT) else a.out}")


if __name__ == "__main__":
    main()
