"""The prototype's study config must agree with the analysis pipeline, or exports will fail validation."""
import csv
import json
import zipfile
from pathlib import Path

import pytest

from pipeline import config
from pipeline.io import Tree
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "prototype"


@pytest.fixture(scope="module")
def study():
    return json.loads((PROTO / "data" / "study.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tree():
    return Tree(pd.read_csv(PROTO / "data" / "tree.csv", dtype=str, keep_default_na=False))


def test_latin_square_matches_pipeline(study):
    got = {s: [tuple(b) for b in blocks] for s, blocks in study["latinSquare"].items()}
    assert got == config.LATIN_SQUARE


def test_constants_match_pipeline(study):
    assert study["minSelections"] == config.MIN_SELECTIONS
    assert study["timeLimitMs"] == config.TIME_LIMIT_MS
    assert set(study["patterns"]) == set(config.PATTERNS)
    assert not study["practice"]["task_id"].startswith("T")
    assert study["practice"]["task_id"].startswith(config.PRACTICE_PREFIX)


def test_tasks_are_l3_leaves_with_distinct_l2_parents(study, tree):
    parents = []
    for task_id, t in study["tasks"].items():
        target = t["target"]
        assert target in tree, f"{task_id}: {target} not in tree.csv"
        assert int(tree.level[target]) == 3, f"{task_id}: {target} is not at depth 3"
        assert not tree.children[target], f"{task_id}: {target} is not a leaf"
        parents.append(tree.parent[target])
    assert len(parents) == len(set(parents)), "two targets share an L2 parent (proposal 4.3)"


def test_pairs_cover_six_tasks(study):
    paired = [t for ids in study["pairs"].values() for t in ids]
    assert sorted(paired) == sorted(study["tasks"]) == [f"T{i}" for i in range(1, 7)]
    for pair, ids in study["pairs"].items():
        assert all(study["tasks"][t]["pair"] == pair for t in ids)


def test_scenarios_do_not_copy_target_labels(study, tree):
    """Proposal C.2: scenario text must not copy the target's label or its parents' labels."""
    with (PROTO / "data" / "tree.csv").open(encoding="utf-8") as f:
        labels = {r["node_id"]: r["label"].lower() for r in csv.DictReader(f)}
    for task_id, t in study["tasks"].items():
        text = t["scenario"].lower()
        for node in tree.path(t["target"])[1:]:
            assert labels[node] not in text, f"{task_id}: scenario contains the menu label {labels[node]!r}"


def test_service_worker_precaches_every_app_file():
    sw = (PROTO / "sw.js").read_text(encoding="utf-8")
    for p in PROTO.rglob("*"):
        if p.is_file() and p.suffix in {".js", ".css", ".json", ".csv", ".html", ".png", ".webmanifest"} and p.name != "sw.js":
            rel = p.relative_to(PROTO).as_posix()
            assert f'"{rel}"' in sw, f"sw.js does not precache {rel}; the app would break offline"


def test_merge_exports_roundtrip(tmp_path):
    from scripts.merge_exports import merge
    ref_tree = (PROTO / "data" / "tree.csv").read_text(encoding="utf-8")
    tasks = "task_id,task_pair,target_node\nT3,B,C2.2.1\n"
    head = ",".join(["participant_id", "trial_id", "sequence", "block_position", "trial_order", "pattern", "task_id",
                     "task_pair", "target_node", "min_selections", "t_ms", "event_type", "node_id", "current_node_after", "on_path"])
    ev = head + "\nP01,P01_T3,S1,2,3,MM,T3,B,C2.2.1,2,0,start,,ROOT,1\nP01,P01_T3,S1,2,3,MM,T3,B,C2.2.1,2,900,give_up,,ROOT,1\n"
    part_blank = "participant_id,sequence,age\nP01,S1,\n"
    part_filled = "participant_id,sequence,age\nP01,S1,22\n"
    for name, part in (("a.zip", part_blank), ("b.zip", part_filled)):
        with zipfile.ZipFile(tmp_path / name, "w") as z:
            z.writestr("events.csv", ev)
            z.writestr("ratings.csv", "participant_id,trial_id,difficulty_rating\nP01,P01_T3,4\n")
            z.writestr("participants.csv", part)
            z.writestr("exclusions.csv", "trial_id,reason\n")
            z.writestr("reference/tree.csv", ref_tree)
            z.writestr("reference/tasks.csv", tasks)
    out = tmp_path / "merged"
    counts = merge([tmp_path / "a.zip", tmp_path / "b.zip"], out)
    assert counts["events.csv"] == 2          # identical rows de-duplicated
    assert counts["ratings.csv"] == 1
    assert "22" in (out / "participants.csv").read_text()
    assert (out / "reference" / "tree.csv").exists()
