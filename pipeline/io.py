"""Load a dataset folder (events/ratings/participants/exclusions + reference tree and tasks)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import pandas as pd

from .config import NUMERIC_COLUMNS


class Tree:
    """Rooted content tree T = (V, E) from tree.csv (proposal 3.2)."""

    def __init__(self, df: pd.DataFrame):
        self.parent = dict(zip(df["node_id"], df["parent_id"]))
        self.level = dict(zip(df["node_id"], df["level"]))
        self.children: dict[str, list[str]] = {n: [] for n in df["node_id"]}
        for n, p in self.parent.items():
            if p and p in self.children:
                self.children[p].append(n)
        roots = [n for n, p in self.parent.items() if not p]
        if len(roots) != 1:
            raise ValueError(f"tree.csv must have exactly one root (blank parent_id); found {roots}")
        self.root = roots[0]
        self._path_cache: dict[str, tuple[str, ...]] = {}

    def __contains__(self, node: str) -> bool:
        return node in self.parent

    def path(self, node: str) -> tuple[str, ...]:
        """Correct path P* from the root to `node` (root first)."""
        if node not in self._path_cache:
            out, seen = [node], {node}
            while self.parent.get(out[-1]):
                nxt = self.parent[out[-1]]
                if nxt in seen or nxt not in self.parent:
                    raise ValueError(f"tree.csv has a broken parent chain at {out[-1]!r}")
                out.append(nxt)
                seen.add(nxt)
            self._path_cache[node] = tuple(reversed(out))
        return self._path_cache[node]


@dataclass
class Dataset:
    events: pd.DataFrame
    ratings: pd.DataFrame
    participants: pd.DataFrame
    exclusions: pd.DataFrame
    tree_df: pd.DataFrame
    tasks: pd.DataFrame
    data_dir: Path

    @cached_property
    def tree(self) -> Tree:
        return Tree(self.tree_df)


def _read(path: Path, numeric: list[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip()
    for c in numeric:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].replace("", pd.NA), errors="coerce")
    return df


def load_dataset(data_dir: str | Path) -> Dataset:
    """Read all CSVs with explicit string dtypes (blank = ''), numbers coerced (bad values become NaN
    and are reported by the validator rather than silently accepted)."""
    d = Path(data_dir)
    num = NUMERIC_COLUMNS
    return Dataset(
        events=_read(d / "events.csv", num["events"]),
        ratings=_read(d / "ratings.csv", num["ratings"]),
        participants=_read(d / "participants.csv", num["participants"]),
        exclusions=_read(d / "exclusions.csv", []),
        tree_df=_read(d / "reference" / "tree.csv", num["tree"]),
        tasks=_read(d / "reference" / "tasks.csv", []),
        data_dir=d,
    )
