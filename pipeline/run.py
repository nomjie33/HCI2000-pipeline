"""One call for the whole pipeline: validate -> clean -> derive -> describe -> figures -> models -> conclusions."""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .conclude import hypothesis_decisions, limitations, write_conclusions
from .describe import describe_all
from .models import ModelSuite, run_models
from .plots import make_all_figures, make_model_figures
from .prepare import Prepared, prepare


@dataclass
class RunResult:
    prep: Prepared
    suite: ModelSuite
    decisions: pd.DataFrame
    limitations: pd.DataFrame
    out_dir: Path
    draft_path: Path


def run_all(data_dir, out_dir="outputs", strict: bool = True) -> RunResult:
    """strict=True raises pipeline.validate.ValidationError on hard data problems."""
    out = Path(out_dir)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                  # statsmodels convergence chatter; real issues are in the notes
        prep = prepare(data_dir, strict=strict)
        prep.write(out)
        describe_all(prep, out)
        make_all_figures(prep, out)
        suite = run_models(prep)
        suite.write(out)
        make_model_figures(suite, out)
        paths = write_conclusions(prep, suite, out)
    return RunResult(prep, suite, hypothesis_decisions(suite), limitations(prep, suite), out, paths["draft"])
