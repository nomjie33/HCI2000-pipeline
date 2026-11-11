"""Run the whole analysis on one dataset folder.

    python scripts/run_pipeline.py --data-dir data/dummy --out outputs
    python scripts/run_pipeline.py --data-dir data/raw/session_export --out outputs/real

Exit code 0 = finished; 1 = hard validation failure (the list of problems is printed, nothing is analysed).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from pipeline.run import run_all  # noqa: E402
from pipeline.validate import ValidationError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, type=Path, help="folder with events.csv, ratings.csv, participants.csv, exclusions.csv, reference/")
    ap.add_argument("--out", default=Path("outputs"), type=Path, help="output folder (default: outputs)")
    a = ap.parse_args()
    try:
        r = run_all(a.data_dir, a.out)
    except ValidationError as e:
        print(str(e), file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"Missing input: {e}", file=sys.stderr)
        return 1

    soft = r.prep.report.soft_failures
    print(f"Analysed {len(r.prep.trials)} trials from {r.prep.trials.participant_id.nunique()} participants.")
    if soft:
        print("Validation warnings (soft): " + ", ".join(f"{x.name} ({x.n_issues})" for x in soft))
    pd.set_option("display.width", 200)
    print("\nHypothesis decisions")
    print(r.decisions[["hypothesis", "outcome", "test", "p", "decision", "significant_contrasts"]].round(4).to_string(index=False))
    print(f"\nTables:  {a.out / 'tables'}\nFigures: {a.out / 'figures'}\nDraft:   {r.draft_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
