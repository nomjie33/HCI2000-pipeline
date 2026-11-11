"""Steps 1-3 in one call: validate -> clean -> derive. Also runnable from the command line:

    python -m pipeline.prepare --data-dir data/dummy --out outputs
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .clean import clean
from .derive import derive_trials
from .io import Dataset, load_dataset
from .validate import ValidationReport, validate


@dataclass
class Prepared:
    raw: Dataset
    clean: Dataset
    report: ValidationReport
    cleaning_log: pd.DataFrame
    trials: pd.DataFrame
    episodes: pd.DataFrame

    def write(self, out_dir: str | Path) -> Path:
        t = Path(out_dir) / "tables"
        t.mkdir(parents=True, exist_ok=True)
        self.report.to_frame().to_csv(t / "validation_report.csv", index=False)
        self.report.details_frame().to_csv(t / "validation_details.csv", index=False)
        self.cleaning_log.to_csv(t / "cleaning_log.csv", index=False)
        self.trials.to_csv(t / "trials.csv", index=False)
        self.episodes.to_csv(t / "episodes.csv", index=False)
        return t


def prepare(data_dir: str | Path, strict: bool = True) -> Prepared:
    """strict=True raises ValidationError on hard failures (the default for real analysis)."""
    raw = load_dataset(data_dir)
    report = validate(raw)
    if strict:
        report.raise_if_hard()
    cleaned, log = clean(raw)
    trials, episodes = derive_trials(cleaned)
    return Prepared(raw, cleaned, report, log, trials, episodes)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--out", default="outputs", type=Path)
    a = ap.parse_args()
    p = prepare(a.data_dir)
    out = p.write(a.out)
    print(p.report.to_frame().to_string(index=False))
    print(f"\n{len(p.trials)} analysed trials from {p.trials.participant_id.nunique()} participants; "
          f"{len(p.cleaning_log)} cleaning-log entries; tables written to {out}")


if __name__ == "__main__":
    main()
