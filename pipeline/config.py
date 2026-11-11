"""Constants shared across the pipeline. Change study parameters here only."""

TIME_LIMIT_MS = 180_000          # app ends a task automatically at 180 s (proposal 4.3)
ALPHA = 0.05                     # two-sided (proposal 4.7)
PRACTICE_PREFIX = "PR"           # practice task ids start with this (e.g. PR1)

PATTERNS = ("DH", "MM", "ND")
MIN_SELECTIONS = {"DH": 3, "MM": 2, "ND": 3}

EVENT_TYPES = (
    "start", "select", "back", "collapse", "menu_open", "menu_close", "logo",
    "give_up", "target_reached", "timeout",
)
# terminal event -> end_reason
TERMINAL_EVENTS = {"target_reached": "target", "give_up": "give_up", "timeout": "timeout"}

# Table 3: sequence -> [(pattern, task pair) for block 1..3]
LATIN_SQUARE = {
    "S1": [("DH", "A"), ("MM", "B"), ("ND", "C")],
    "S2": [("MM", "A"), ("ND", "B"), ("DH", "C")],
    "S3": [("ND", "A"), ("DH", "B"), ("MM", "C")],
}

# expected sample (soft checks): 15 participants, 5 per sequence, 6 experimental trials each
N_PARTICIPANTS = 15
PER_SEQUENCE = 5
EXPERIMENTAL_TRIALS = 6

SEQ_RANGE = (1, 7)

REQUIRED_COLUMNS = {
    "events": [
        "participant_id", "trial_id", "sequence", "block_position", "trial_order", "pattern", "task_id",
        "task_pair", "target_node", "min_selections", "t_ms", "event_type", "node_id",
        "current_node_after", "on_path",
    ],
    "ratings": ["participant_id", "trial_id", "difficulty_rating"],
    "participants": [
        "participant_id", "sequence", "age", "gender", "gov_familiarity", "used_reference_site",
        "rank_DH", "rank_MM", "rank_ND",
    ],
    "exclusions": ["trial_id", "reason"],
    "tree": ["node_id", "parent_id", "level", "label"],
    "tasks": ["task_id", "task_pair", "target_node"],
}

NUMERIC_COLUMNS = {
    "events": ["block_position", "trial_order", "min_selections", "t_ms", "on_path"],
    "ratings": ["difficulty_rating"],
    "participants": ["age", "gov_familiarity", "rank_DH", "rank_MM", "rank_ND"],
    "tree": ["level"],
}
