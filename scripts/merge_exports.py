"""Merge prototype exports (ZIPs or unzipped folders) into one pipeline dataset folder.

Use it when sessions were exported one at a time, or when more than one phone was used.
"Export all sessions" from a single phone already gives a complete folder, so merging is optional there.

    python scripts/merge_exports.py data/raw/exports/*.zip --out data/raw/session_export

- events / ratings / interrupted_trials / session_info: rows are concatenated, and exact duplicate rows are dropped
  (the same session exported twice). If a trial_id appears in two inputs with *different* rows, the merge stops:
  decide which export is correct by hand.
- participants.csv: one row per participant. Non-blank values win, so a copy already filled in from the
  Google Form is not overwritten by a blank template.
- exclusions.csv: concatenated (unique rows).
- reference/tree.csv and reference/tasks.csv must be identical in every input (same study build).
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path

TABLES = ["events.csv", "ratings.csv", "participants.csv", "exclusions.csv", "session_info.csv", "interrupted_trials.csv"]
REFERENCE = ["reference/tree.csv", "reference/tasks.csv"]


def read_source(src: Path) -> dict[str, str]:
    """Return {relative path: text} for one export (ZIP or folder)."""
    files: dict[str, str] = {}
    if src.is_file() and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            for name in z.namelist():
                if name.endswith(".csv"):
                    files[name.replace("\\", "/")] = z.read(name).decode("utf-8-sig")
    elif src.is_dir():
        for p in src.rglob("*.csv"):
            files[p.relative_to(src).as_posix()] = p.read_text(encoding="utf-8-sig")
    else:
        raise SystemExit(f"not a .zip or folder: {src}")
    return files


def parse(text: str) -> tuple[list[str], list[dict]]:
    r = csv.DictReader(io.StringIO(text))
    return list(r.fieldnames or []), list(r)


def write(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def merge(sources: list[Path], out: Path) -> dict[str, int]:
    loaded = [(s, read_source(s)) for s in sources]

    # reference files must match across all exports
    for ref in REFERENCE:
        texts = {s: f.get(ref) for s, f in loaded}
        missing = [str(s) for s, t in texts.items() if t is None]
        if missing:
            raise SystemExit(f"{ref} missing in: {', '.join(missing)}")
        if len({t.replace('\r\n', '\n') for t in texts.values()}) > 1:
            raise SystemExit(f"{ref} differs between exports (different study builds?); merge them separately.")

    counts: dict[str, int] = {}
    for table in TABLES:
        header: list[str] = []
        rows: list[dict] = []
        for s, files in loaded:
            if table not in files:
                continue
            h, r = parse(files[table])
            header = header or h
            rows += [{**row, "__src": str(s)} for row in r]
        if not header:
            continue

        if table == "participants.csv":
            merged: dict[str, dict] = {}
            for row in rows:
                cur = merged.setdefault(row["participant_id"], {k: "" for k in header})
                for k in header:
                    v = (row.get(k) or "").strip()
                    if v and cur[k] and cur[k] != v:
                        raise SystemExit(f"participants.csv: {row['participant_id']} has conflicting {k}: {cur[k]!r} vs {v!r}")
                    cur[k] = cur[k] or v
            out_rows = list(merged.values())
        else:
            seen, out_rows = set(), []
            for row in rows:
                key = tuple(row.get(k, "") for k in header)
                if key not in seen:
                    seen.add(key)
                    out_rows.append(row)
            if table in ("events.csv", "ratings.csv"):
                by_trial: dict[str, set] = {}
                for row in out_rows:
                    by_trial.setdefault(row["trial_id"], set()).add(row["__src"])
                clash = {t: srcs for t, srcs in by_trial.items() if len(srcs) > 1}
                # Same trial in two exports is fine only if the rows were identical (already de-duplicated above).
                for t, srcs in clash.items():
                    variants = {tuple(sorted(tuple(r.get(k, "") for k in header) for r in out_rows if r["trial_id"] == t and r["__src"] == s)) for s in srcs}
                    if len(variants) > 1:
                        raise SystemExit(f"{table}: trial {t} differs between {sorted(srcs)}; resolve by hand.")
        write(out / table, header, out_rows)
        counts[table] = len(out_rows)

    for ref in REFERENCE:
        (out / ref).parent.mkdir(parents=True, exist_ok=True)
        (out / ref).write_text(loaded[0][1][ref], encoding="utf-8", newline="")
    return counts


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Merge prototype exports into one pipeline dataset folder.")
    ap.add_argument("sources", nargs="+", type=Path, help="export .zip files and/or unzipped export folders")
    ap.add_argument("--out", type=Path, required=True, help="dataset folder to write (e.g. data/raw/session_export)")
    a = ap.parse_args(argv)
    counts = merge(a.sources, a.out)
    for k, v in counts.items():
        print(f"{k:24s} {v} rows")
    print(f"wrote {a.out}. Fill participants.csv from the Google Form, add exclusions, then run:\n"
          f"  python scripts/run_pipeline.py --data-dir {a.out} --out outputs")


if __name__ == "__main__":
    main(sys.argv[1:])
