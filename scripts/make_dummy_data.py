"""Generate SYNTHETIC test data for the analysis pipeline.

Nothing here is real participant data. The simulator walks a simulated participant through
the prototype's content tree for each trial and writes the same CSVs the real logger/questionnaires
will produce (see docs/ANALYSIS_PLAN.md, section 1.1).

Planted effects (so the analysis can be checked against known truth; they are NOT findings):
  * MM needs one fewer selection, so it is fastest overall.
  * ND has the highest per-choice error rate; DH has the longest recoveries (one Back per level).
  * Participants differ in speed; later blocks are slightly faster; task pair B is slightly harder.
  * A few trials end in give-up or timeout.

Usage:
    python scripts/make_dummy_data.py                  # clean data  -> data/dummy/
    python scripts/make_dummy_data.py --dirty          # with faults -> data/dummy_dirty/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = "ROOT"
TIME_LIMIT_MS = 180_000
MIN_SEL = {"DH": 3, "MM": 2, "ND": 3}

# Table 3 (Latin square): sequence -> [(pattern, task pair) for block 1..3]
SEQUENCES = {
    "S1": [("DH", "A"), ("MM", "B"), ("ND", "C")],
    "S2": [("MM", "A"), ("ND", "B"), ("DH", "C")],
    "S3": [("ND", "A"), ("DH", "B"), ("MM", "C")],
}
PAIR_TASKS = {"A": ["T1", "T2"], "B": ["T3", "T4"], "C": ["T5", "T6"]}
# six targets, each under a different L2 parent (proposal 4.3)
TARGETS = {
    "T1": "C1.1.2", "T2": "C2.2.1",
    "T3": "C3.1.3", "T4": "C4.3.2",
    "T5": "C1.3.1", "T6": "C2.1.3",
    "PR1": "PR1.2.1",  # practice task, separate practice tree
}
TASK_PAIR = {"T1": "A", "T2": "A", "T3": "B", "T4": "B", "T5": "C", "T6": "C", "PR1": "PR"}

# --- simulation parameters (seconds unless noted) -------------------------------------------
SCAN = {  # median time to scan and choose at each tree level
    "DH": {1: 2.4, 2: 2.6, 3: 2.8},
    "MM": {1: 2.4, 3: 4.5},
    "ND": {1: 2.4, 2: 3.0, 3: 3.4},
}
P_ERR = {  # probability of choosing a wrong item at each level
    "DH": {1: 0.15, 2: 0.15, 3: 0.15},
    "MM": {1: 0.10, 3: 0.15},
    "ND": {1: 0.25, 2: 0.25, 3: 0.25},
}
PAIR_FACTOR = {"A": 1.0, "B": 1.1, "C": 0.95, "PR": 1.0}
BLOCK_FACTOR = {0: 1.0, 1: 1.0, 2: 0.95, 3: 0.90}
P_DEEPER = 0.4          # after a wrong pick, chance of tapping deeper into the wrong branch
P_STUCK = 0.06          # trial in which the participant is badly lost (gives timeouts/give-ups)
REC = 1.2               # median seconds per recovery action (Back / collapse)
NOTICE = 1.5            # median seconds to notice an error before the first recovery action


# --- content tree ---------------------------------------------------------------------------
def build_tree() -> pd.DataFrame:
    rows = [(ROOT, "", 0, "Home")]

    def add(prefix: str, n1: int, n2: int, n3: int, label: str) -> None:
        for i in range(1, n1 + 1):
            a = f"{prefix}{i}"
            rows.append((a, ROOT, 1, f"{label} category {i}"))
            for j in range(1, n2 + 1):
                b = f"{a}.{j}"
                rows.append((b, a, 2, f"{label} subcategory {i}.{j}"))
                for k in range(1, n3 + 1):
                    rows.append((f"{b}.{k}", b, 3, f"{label} page {i}.{j}.{k}"))

    add("C", 4, 3, 3, "Service")      # experimental tree (placeholder labels)
    add("PR", 2, 2, 2, "Library")     # practice tree
    return pd.DataFrame(rows, columns=["node_id", "parent_id", "level", "label"])


class Tree:
    def __init__(self, df: pd.DataFrame):
        self.parent = dict(zip(df.node_id, df.parent_id))
        self.level = dict(zip(df.node_id, df.level))
        self.children: dict[str, list[str]] = {n: [] for n in df.node_id}
        for n, p in self.parent.items():
            if p:
                self.children[p].append(n)

    def path(self, node: str) -> list[str]:
        out = [node]
        while self.parent[out[-1]]:
            out.append(self.parent[out[-1]])
        return out[::-1]

    def leaves_under(self, node: str) -> list[str]:
        if self.level[node] == 3:
            return [node]
        return [lf for c in self.children[node] for lf in self.leaves_under(c)]


# --- one simulated trial --------------------------------------------------------------------
class TimeOut(Exception):
    pass


class GaveUp(Exception):
    pass


class Trial:
    def __init__(self, tree: Tree, rng: np.random.Generator, pattern: str, target: str, speed: float):
        self.T, self.rng, self.pattern, self.speed = tree, rng, pattern, speed
        self.path = tree.path(target)
        self.pathset = set(self.path)
        self.target = target
        self.t = 0                  # ms
        self.cur = ROOT
        self.events: list[tuple] = []   # (t_ms, event_type, node_id, current_node_after)
        self.E = 0
        self.R_ms = 0
        self._ep_start: int | None = None
        self.stuck = rng.random() < P_STUCK

    # timing helpers
    def _ln(self, median: float, sigma: float = 0.3) -> int:
        return max(1, int(round(self.rng.lognormal(np.log(median), sigma) * 1000)))

    def scan(self, level: int) -> int:
        m = SCAN[self.pattern][level] * self.speed * (4.0 if self.stuck else 1.0)
        return self._ln(m)

    def rec(self, first: bool) -> int:
        return self._ln(REC * self.speed) + (self._ln(NOTICE) if first else 0)

    def p_err(self, level: int) -> float:
        return 0.9 if self.stuck else P_ERR[self.pattern][level]

    # logging
    def log(self, etype: str, node: str, cur: str) -> None:
        self.events.append((self.t, etype, node, cur))

    def act(self, etype: str, node: str, new_cur: str, dt_ms: int) -> None:
        if self.t + dt_ms >= TIME_LIMIT_MS:
            raise TimeOut
        self.t += dt_ms
        self.cur = new_cur
        self.log(etype, node, new_cur)
        if etype == "select" and node not in self.pathset:
            self.E += 1
            if self._ep_start is None:
                self._ep_start = self.t
        if new_cur in self.pathset and self._ep_start is not None:
            self.R_ms += self.t - self._ep_start
            self._ep_start = None

    # navigation
    def run(self) -> tuple[str, int]:
        """Returns (end_reason, t_end_ms)."""
        self.log("start", "", ROOT)
        try:
            self.act("menu_open", "", ROOT, self._ln(0.9))
            if self.rng.random() < 0.10:
                self.act("menu_close", "", ROOT, self._ln(0.8))
                self.act("menu_open", "", ROOT, self._ln(0.8))
            if self.pattern == "MM":
                self._nav_mm()
            else:
                self._nav_list()
            self.log("target_reached", self.target, self.target)
            end, t_end = "target", self.t
        except GaveUp:
            self.t += self._ln(1.5)
            self.log("give_up", "", self.cur)
            end, t_end = "give_up", self.t
        except TimeOut:
            self.t = TIME_LIMIT_MS
            self.log("timeout", "", self.cur)
            end, t_end = "timeout", self.t
        if self._ep_start is not None:      # episode still open when trial ends (3.3)
            self.R_ms += t_end - self._ep_start
            self._ep_start = None
        return end, t_end

    def _maybe_give_up(self) -> None:
        if self.E >= 4 and self.rng.random() < (0.05 if self.stuck else 0.25):
            raise GaveUp

    def _nav_list(self) -> None:
        T, rng = self.T, self.rng
        for lvl in (1, 2, 3):
            good, correct = self.path[lvl - 1], self.path[lvl]
            while True:
                if rng.random() < self.p_err(lvl):
                    wrong = [s for s in T.children[good] if s != correct]
                    pick = wrong[rng.integers(len(wrong))]
                    self.act("select", pick, pick, self.scan(lvl))
                    self._recover_list(lvl, pick, good, correct)
                    self._maybe_give_up()
                    if self.cur == correct:
                        break
                else:
                    self.act("select", correct, correct, self.scan(lvl))
                    break

    def _recover_list(self, lvl: int, pick: str, good: str, correct: str) -> None:
        T, rng = self.T, self.rng
        if lvl < 3 and rng.random() < P_DEEPER:     # tap deeper into the wrong branch
            kids = T.children[pick]
            child = kids[rng.integers(len(kids))]
            self.act("select", child, child, self.scan(lvl + 1))
        first = True
        if T.level[self.cur] == 3:                  # on a placeholder page: Back to its parent
            self.act("back", "", T.parent[self.cur], self.rec(first))
            first = False
        if self.cur != good and self.pattern == "ND" and rng.random() < 0.4:
            # parent lists stay visible in ND: tap the correct sibling directly
            self.act("select", correct, correct, self.rec(first))
            return
        while self.cur != good:
            if good == ROOT and rng.random() < 0.10:
                self.act("logo", "", ROOT, self.rec(first))
            elif self.pattern == "DH":
                self.act("back", "", T.parent[self.cur], self.rec(first))
            else:
                self.act("collapse", self.cur, T.parent[self.cur], self.rec(first))
            first = False

    def _nav_mm(self) -> None:
        T, rng = self.T, self.rng
        l1 = self.path[1]
        if rng.random() < self.p_err(1):            # wrong L1 panel
            wrong = [s for s in T.children[ROOT] if s != l1 and s.startswith("PR") == l1.startswith("PR")]
            pick = wrong[rng.integers(len(wrong))]
            self.act("select", pick, pick, self.scan(1))
            first = True
            if rng.random() < P_DEEPER:
                leaves = T.leaves_under(pick)
                lf = leaves[rng.integers(len(leaves))]
                self.act("select", lf, lf, self.scan(3))
                self.act("back", "", pick, self.rec(first))
                first = False
            self.act("select", l1, l1, self.rec(first))
            self._maybe_give_up()
        else:
            self.act("select", l1, l1, self.scan(1))
        while True:                                 # choose among all L3 links in the open panel
            if rng.random() < self.p_err(3):
                leaves = [lf for lf in T.leaves_under(l1) if lf != self.target]
                lf = leaves[rng.integers(len(leaves))]
                self.act("select", lf, lf, self.scan(3))
                self.act("back", "", l1, self.rec(True))
                self._maybe_give_up()
            else:
                self.act("select", self.target, self.target, self.scan(3))
                break


# --- dataset --------------------------------------------------------------------------------
def simulate(n_participants: int, seed: int):
    rng = np.random.default_rng(seed)
    tree_df = build_tree()
    tree = Tree(tree_df)
    tasks_df = pd.DataFrame(
        [(t, TASK_PAIR[t], tgt) for t, tgt in TARGETS.items()], columns=["task_id", "task_pair", "target_node"]
    )

    ev_rows, truth_rows, rating_rows, part_rows = [], [], [], []
    seq_counter = {s: 0 for s in SEQUENCES}
    for i in range(1, n_participants + 1):
        pid = f"P{i:02d}"
        seq = list(SEQUENCES)[(i - 1) % 3]
        k = seq_counter[seq]
        seq_counter[seq] += 1
        speed = float(rng.lognormal(0, 0.25))

        plan = [("PR1", SEQUENCES[seq][0][0], "PR", 0, 0)]   # practice: first block's pattern
        order = 0
        for b, (pattern, pair) in enumerate(SEQUENCES[seq], start=1):
            tasks = PAIR_TASKS[pair][::-1] if k % 2 == 1 else PAIR_TASKS[pair]   # alternate within pair
            for tk in tasks:
                order += 1
                plan.append((tk, pattern, pair, b, order))

        seq_scores = {p: [] for p in MIN_SEL}
        for task_id, pattern, pair, block, order in plan:
            tid = f"{pid}_{task_id}"
            sp = speed * PAIR_FACTOR[pair] * BLOCK_FACTOR[block]
            tr = Trial(tree, rng, pattern, TARGETS[task_id], sp)
            end, t_end = tr.run()
            for t_ms, et, node, cur in tr.events:
                ev_rows.append(dict(
                    participant_id=pid, trial_id=tid, sequence=seq, block_position=block, trial_order=order,
                    pattern=pattern, task_id=task_id, task_pair=pair, target_node=TARGETS[task_id],
                    min_selections=MIN_SEL[pattern], t_ms=t_ms, event_type=et, node_id=node,
                    current_node_after=cur, on_path=int(cur in tr.pathset),
                ))
            t_find = t_end / 1000
            truth_rows.append(dict(
                trial_id=tid, E=tr.E, R=tr.R_ms / 1000, T_find=t_find, T_clean=t_find - tr.R_ms / 1000,
                end_reason=end, success=int(end == "target"),
            ))
            if task_id.startswith("PR"):
                continue
            if end == "target":
                seq_val = 6.0 - 0.7 * tr.E - 0.015 * max(0.0, t_find - 15) + rng.normal(0, 0.8)
            else:
                seq_val = 2.0 + rng.normal(0, 0.8)
            seq_val = int(np.clip(round(seq_val), 1, 7))
            seq_scores[pattern].append(seq_val)
            rating_rows.append(dict(participant_id=pid, trial_id=tid, difficulty_rating=seq_val))

        # preference ranking: driven by that participant's mean SEQ, plus noise (1 = most preferred)
        score = {p: np.mean(v) + rng.normal(0, 0.6) for p, v in seq_scores.items()}
        ranked = sorted(score, key=score.get, reverse=True)
        rank = {p: ranked.index(p) + 1 for p in ranked}
        part_rows.append(dict(
            participant_id=pid, sequence=seq, age=int(rng.integers(18, 46)),
            gender=str(rng.choice(["F", "M", "F", "M", "Prefer not to say"])),
            gov_familiarity=int(rng.integers(1, 6)), used_reference_site=str(rng.choice(["Y", "N"], p=[0.3, 0.7])),
            rank_DH=rank["DH"], rank_MM=rank["MM"], rank_ND=rank["ND"],
            comments=str(rng.choice(["", "", "", "MM was easy to scan", "Too many taps", "Back button helped"])),
        ))

    events = pd.DataFrame(ev_rows)
    truth = pd.DataFrame(truth_rows)
    ratings = pd.DataFrame(rating_rows)
    participants = pd.DataFrame(part_rows)
    exclusions = pd.DataFrame(
        [dict(trial_id="P07_T4", reason="DUMMY app fault: screen froze, confirmed on screen recording")]
    )
    truth["excluded"] = truth.trial_id.isin(exclusions.trial_id).astype(int)
    return tree_df, tasks_df, events, ratings, participants, exclusions, truth


def inject_faults(events, ratings, participants):
    """Corrupt a few known places so the validator has something to catch. Returns the faults log."""
    faults = []
    ev = events.copy()

    def trial_idx(tid):
        return ev.index[ev.trial_id == tid]

    idx = trial_idx("P02_T2")                       # 1 duplicate row (soft)
    sel = [i for i in idx if ev.at[i, "event_type"] == "select"][0]
    ev = pd.concat([ev, ev.loc[[sel]]]).sort_index(kind="stable").reset_index(drop=True)
    faults.append(("F1", "events.csv", "P02_T2", "duplicate event row", "duplicate_rows", "soft"))

    idx = trial_idx("P03_T1")                       # 2 non-monotonic timestamps (hard)
    ev.at[idx[2], "t_ms"] = ev.loc[idx, "t_ms"].max()
    faults.append(("F2", "events.csv", "P03_T1", "t_ms goes backwards after the third event", "monotonic_time", "hard"))

    idx = trial_idx("P04_T3")                       # 3 node not in tree (hard)
    first_sel = [i for i in idx if ev.at[i, "event_type"] == "select"][0]
    ev.at[first_sel, "node_id"] = "ZZ9"
    ev.at[first_sel, "current_node_after"] = "ZZ9"
    faults.append(("F3", "events.csv", "P04_T3", "unknown node ZZ9", "nodes_in_tree", "hard"))

    idx = trial_idx("P05_T5")                       # 4 missing terminal event (hard)
    ev = ev.drop(idx[-1]).reset_index(drop=True)
    faults.append(("F4", "events.csv", "P05_T5", "terminal event removed", "one_terminal_event", "hard"))

    idx = trial_idx("P06_T2")                       # 5 wrong logged on_path flag (soft)
    sel = [i for i in idx if ev.at[i, "event_type"] == "select"][0]
    ev.at[sel, "on_path"] = 1 - ev.at[sel, "on_path"]
    faults.append(("F5", "events.csv", "P06_T2", "logged on_path flag flipped", "on_path_matches_tree", "soft"))

    rt = ratings[ratings.trial_id != "P08_T6"].reset_index(drop=True)   # 6 missing rating (soft)
    faults.append(("F6", "ratings.csv", "P08_T6", "rating missing", "ratings_complete", "soft"))

    pt = participants.copy()                        # 7 ranking not a permutation (soft)
    pt.loc[pt.participant_id == "P09", ["rank_DH", "rank_MM", "rank_ND"]] = [1, 1, 3]
    faults.append(("F7", "participants.csv", "P09", "preference ranks 1,1,3", "ranking_permutation", "soft"))

    ev = ev[ev.trial_id != "P10_T4"].reset_index(drop=True)             # 8 whole trial missing (soft)
    rt = rt[rt.trial_id != "P10_T4"].reset_index(drop=True)
    faults.append(("F8", "events.csv", "P10", "trial P10_T4 missing: only 5 trials", "trials_per_participant", "soft"))

    log = pd.DataFrame(faults, columns=["fault_id", "file", "where", "description", "expected_check", "severity"])
    return ev, rt, pt, log


def write(out: Path, tree_df, tasks_df, events, ratings, participants, exclusions, truth, faults=None):
    (out / "reference").mkdir(parents=True, exist_ok=True)
    tree_df.to_csv(out / "reference" / "tree.csv", index=False)
    tasks_df.to_csv(out / "reference" / "tasks.csv", index=False)
    events.to_csv(out / "events.csv", index=False)
    ratings.to_csv(out / "ratings.csv", index=False)
    participants.to_csv(out / "participants.csv", index=False)
    exclusions.to_csv(out / "exclusions.csv", index=False)
    truth.to_csv(out / "_ground_truth_trials.csv", index=False)   # for tests only; pipeline never reads it
    if faults is not None:
        faults.to_csv(out / "_injected_faults.csv", index=False)
    (out / "README.txt").write_text(
        "SYNTHETIC DUMMY DATA generated by scripts/make_dummy_data.py. Not real participants; never cite.\n"
        "Files starting with '_' are test aids (ground truth / injected faults) and are not pipeline inputs.\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirty", action="store_true", help="inject known faults (default out: data/dummy_dirty)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--participants", type=int, default=15)
    a = ap.parse_args()
    out = a.out or Path("data/dummy_dirty" if a.dirty else "data/dummy")

    tree_df, tasks_df, events, ratings, participants, exclusions, truth = simulate(a.participants, a.seed)
    faults = None
    if a.dirty:
        events, ratings, participants, faults = inject_faults(events, ratings, participants)
    write(out, tree_df, tasks_df, events, ratings, participants, exclusions, truth, faults)
    print(f"wrote {out}: {events.trial_id.nunique()} trials, {len(events)} events, "
          f"{participants.participant_id.nunique()} participants")


if __name__ == "__main__":
    main()
