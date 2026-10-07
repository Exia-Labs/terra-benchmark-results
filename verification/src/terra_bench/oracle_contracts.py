"""Reject stale independent references before paying for a measured attempt."""
from .common import Blocked
from .heat_tasks import GRID, HEAT_TASKS, RADIUS_M


def validate_oracle_contracts(answers, task_ids):
    for task in task_ids:
        if task not in HEAT_TASKS:
            continue
        expected = answers[task]
        if expected.get("grid") != GRID or expected.get("radiusM") != RADIUS_M:
            raise Blocked(
                f"Task {task}: independent heatmap reference grid/radius differs from the declared prompt. "
                "Build a new reference from the frozen inputs before measurement; do not reuse this oracle."
            )
