"""Combine the real prototype exports and the Google Form into one pipeline dataset folder.

    python scripts/build_real_dataset.py \
        --exports hci2000_export_all_20261121-1701 hci2000_export_all_20261122-1605 \
        --form "[HCI2000] (Responses) - Form Responses 1.csv" \
        --out data/raw/session_export

- Each export came from a different researcher's phone, so participant IDs restart at P01 in each export.
  Every participant is a distinct person: the first export keeps its IDs, later exports are renumbered
  (continuing after the highest ID so far) in their original order. The IDs are rewritten consistently in
  events, ratings, session_info, participants, interrupted_trials and in trial_id (P02_T1 -> P09_T1).
  The mapping is written to `<out>/id_mapping.csv`.
- The Google Form has no participant ID. Each response is matched to the session that finished most recently
  before the response timestamp (form times are Philippine time, UTC+8; sessions are logged in UTC).
  The match is printed and saved to `<out>/form_match.csv`; check it by eye.
- Form columns used: age, gender, rank DH/MM/ND, comments, plus phone-browsing frequency and gov-site visit.
  The form did not ask for the 1-5 gov_familiarity score or prior use of the reference site, so those stay blank.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TABLES = ["events.csv", "ratings.csv", "session_info.csv", "exclusions.csv", "interrupted_trials.csv"]
PH = timedelta(hours=8)
GENDER = {"female": "F", "male": "M"}


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def pid_num(pid: str) -> int:
    return int(re.fullmatch(r"P(\d+)", pid).group(1))


def build_id_map(exports: list[Path]) -> list[dict]:
    """First export keeps its ids; in later exports an id already taken gets the next unused number."""
    mapping: list[dict] = []
    used: set[str] = set()
    top = 0
    for ex in exports:
        _, parts = read_csv(ex / "participants.csv")
        ids = sorted((p["participant_id"] for p in parts), key=pid_num)
        if len(set(ids)) != len(ids):
            raise SystemExit(f"{ex}: duplicate participant ids inside one export")
        for pid in ids:
            new = pid
            if new in used:
                top = max(top, max(pid_num(u) for u in used), max(pid_num(i) for i in ids))
                top += 1
                new = f"P{top:02d}"
            used.add(new)
            mapping.append({"export": ex.name, "old_id": pid, "new_id": new})
    return mapping


def remap_row(row: dict, m: dict[str, str]) -> dict:
    out = dict(row)
    if "participant_id" in out:
        out["participant_id"] = m[out["participant_id"]]
    if out.get("trial_id"):
        pid, _, rest = out["trial_id"].partition("_")
        out["trial_id"] = f"{m[pid]}_{rest}"
    return out


def parse_form(path: Path) -> list[dict]:
    """The form header has multi-line cells, so read by position:
    0 timestamp, 1 consent, 2 age, 3 gender, 4 phone frequency, 5 visited gov sites, 6 DH, 7 MM, 8 ND, 9 comments."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))[1:]
    out = []
    for r in rows:
        r = (r + [""] * 10)[:10]
        out.append(dict(ts=datetime.strptime(r[0].strip(), "%m/%d/%Y %H:%M:%S"), consent=r[1].strip(), age=r[2].strip(),
                        gender=r[3].strip(), phone_freq=r[4].strip(), visited_gov=r[5].strip(),
                        rank_DH=r[6].strip(), rank_MM=r[7].strip(), rank_ND=r[8].strip(), comments=r[9].strip()))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exports", nargs="+", required=True, type=Path)
    ap.add_argument("--form", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)

    # reference files must be identical
    refs = {}
    for name in ("tree.csv", "tasks.csv"):
        texts = {(e / "reference" / name).read_text(encoding="utf-8-sig").replace("\r\n", "\n") for e in a.exports}
        if len(texts) != 1:
            raise SystemExit(f"reference/{name} differs between exports; cannot merge")
        refs[name] = texts.pop()

    mapping = build_id_map(a.exports)
    renamed = [m for m in mapping if m["old_id"] != m["new_id"]]
    print(f"{len(mapping)} participants; {len(renamed)} renamed: " + ", ".join(f"{m['export'][-13:]}:{m['old_id']}->{m['new_id']}" for m in renamed))

    # tables
    for table in TABLES:
        header, rows = [], []
        for ex in a.exports:
            p = ex / table
            if not p.exists():
                continue
            m = {x["old_id"]: x["new_id"] for x in mapping if x["export"] == ex.name}
            h, r = read_csv(p)
            header = header or h
            rows += [remap_row(x, m) for x in r]
        if header:
            if table in ("events.csv", "ratings.csv"):
                keys = [tuple(x[k] for k in header) for x in rows]
                if len(set(keys)) != len(keys):
                    print(f"  note: {table} has exact duplicate rows (kept as is)")
            write_csv(a.out / table, header, rows)
            print(f"{table:24s}{len(rows):6d} rows")

    # participants: id + sequence from session_info/participants, then fill from the form
    phead = ["participant_id", "sequence", "age", "gender", "gov_familiarity", "used_reference_site",
             "rank_DH", "rank_MM", "rank_ND", "comments", "phone_browse_freq", "visited_gov_12mo"]
    sessions = []
    for ex in a.exports:
        m = {x["old_id"]: x["new_id"] for x in mapping if x["export"] == ex.name}
        _, si = read_csv(ex / "session_info.csv")
        for s in si:
            fin = datetime.strptime(s["finished_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            sessions.append(dict(participant_id=m[s["participant_id"]], sequence=s["sequence"], finished_local=(fin + PH).replace(tzinfo=None)))
    sessions.sort(key=lambda s: s["finished_local"])
    form = sorted(parse_form(a.form), key=lambda f: f["ts"])
    if len(form) > len(sessions):
        raise SystemExit(f"{len(form)} form responses but only {len(sessions)} sessions: cannot match")

    # each response -> the latest not-yet-matched session that ended 0-30 min before it
    by_pid: dict[str, dict] = {}
    for f in form:
        cands = [s for s in sessions if s["participant_id"] not in by_pid
                 and 0 <= (f["ts"] - s["finished_local"]).total_seconds() / 60 <= 30]
        if not cands:
            raise SystemExit(f"form response at {f['ts']} has no session ending in the 30 min before it")
        by_pid[max(cands, key=lambda s: s["finished_local"])["participant_id"]] = f

    match, prows = [], []
    for s in sessions:
        f = by_pid.get(s["participant_id"])
        if f is None:
            print(f"  warning: {s['participant_id']} (session ended {s['finished_local']:%Y-%m-%d %H:%M}) has no form response; "
                  "demographics and preference ranks left blank")
            match.append(dict(participant_id=s["participant_id"], session_finished_local=s["finished_local"].isoformat(sep=" "),
                              form_timestamp="", minutes_between=""))
            prows.append(dict(participant_id=s["participant_id"], sequence=s["sequence"]))
            continue
        gap = (f["ts"] - s["finished_local"]).total_seconds() / 60
        match.append(dict(participant_id=s["participant_id"], session_finished_local=s["finished_local"].isoformat(sep=" "),
                          form_timestamp=f["ts"].isoformat(sep=" "), minutes_between=round(gap, 1)))
        if f["consent"].lower() != "yes":
            raise SystemExit(f"{s['participant_id']}: consent is {f['consent']!r}")
        ranks = sorted(int(f[f"rank_{p}"]) for p in ("DH", "MM", "ND"))
        if ranks != [1, 2, 3]:
            raise SystemExit(f"{s['participant_id']}: ranks are not a permutation of 1..3: {ranks}")
        comment = f["comments"]
        comment = " ".join(comment.split())          # collapses odd unicode spaces
        if comment.lower() in ("n/a", "na", "no", "n o", "none", ""):
            comment = ""
        prows.append(dict(participant_id=s["participant_id"], sequence=s["sequence"], age=f["age"],
                          gender=GENDER.get(f["gender"].lower(), f["gender"]), gov_familiarity="", used_reference_site="",
                          rank_DH=f["rank_DH"], rank_MM=f["rank_MM"], rank_ND=f["rank_ND"], comments=comment,
                          phone_browse_freq=f["phone_freq"], visited_gov_12mo=f["visited_gov"]))
    prows.sort(key=lambda r: pid_num(r["participant_id"]))
    write_csv(a.out / "participants.csv", phead, prows)
    write_csv(a.out / "id_mapping.csv", ["export", "old_id", "new_id"], mapping)
    write_csv(a.out / "form_match.csv", list(match[0]), match)
    for name, text in refs.items():
        (a.out / "reference").mkdir(parents=True, exist_ok=True)
        (a.out / "reference" / name).write_text(text, encoding="utf-8", newline="")
    lags = [m["minutes_between"] for m in match if m["minutes_between"] != ""]
    print(f"participants.csv        {len(prows)} rows, {len(lags)} matched to the form (max form lag {max(lags, default=0)} min)")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main(sys.argv[1:])
