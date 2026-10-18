"""Pure unit tests for the stage rules. No HTTP, no DB."""
import itertools
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.enums import StageStatus as S
from app.services import stage_logic as logic

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def make(*specs):
    """make(("Script", S.DONE), ("Shoot", S.TODO, True)) -> stage stubs. 3rd item = parallel_with_previous."""
    stages = []
    for spec in specs:
        title, status, *rest = spec
        stages.append(
            SimpleNamespace(
                id=uuid.uuid4(), title=title, status=status, position=0,
                parallel_with_previous=bool(rest and rest[0]), unlocked_early=False,
                completed_at=None, completed_by=None, blocked_reason=None,
            )
        )
    logic.renumber(stages)
    return stages


# ---------- steps and renumbering ----------

def test_steps_sequential_and_parallel():
    stages = make(("A", S.TODO), ("B", S.LOCKED), ("C", S.LOCKED, True), ("D", S.LOCKED))
    assert logic.steps(stages) == [1, 2, 2, 3]


def test_renumber_sets_positions_and_clears_first_stage_flag():
    stages = make(("A", S.TODO, True), ("B", S.LOCKED))
    assert [s.position for s in stages] == [1, 2]
    assert stages[0].parallel_with_previous is False


# ---------- unlocking ----------

def test_initial_unlock_only_opens_step_one():
    stages = make(("Script", S.LOCKED), ("Shoot", S.LOCKED), ("Edit", S.LOCKED))
    logic.recompute_locks(stages)
    assert [s.status for s in stages] == [S.TODO, S.LOCKED, S.LOCKED]


def test_parallel_stages_both_start_together_and_next_step_waits_for_both():
    stages = make(("Shoot", S.LOCKED), ("Graphics", S.LOCKED), ("Music", S.LOCKED, True), ("Export", S.LOCKED))
    logic.recompute_locks(stages)
    assert [s.status for s in stages] == [S.TODO, S.LOCKED, S.LOCKED, S.LOCKED]

    stages[0].status = S.DONE
    logic.recompute_locks(stages)
    assert [s.status for s in stages] == [S.DONE, S.TODO, S.TODO, S.LOCKED]  # graphics + music open together

    stages[1].status = S.DONE
    logic.recompute_locks(stages)
    assert stages[3].status == S.LOCKED  # music still not done

    stages[2].status = S.DONE
    logic.recompute_locks(stages)
    assert stages[3].status == S.TODO


def test_reopening_upstream_relocks_waiting_stages():
    stages = make(("A", S.DONE), ("B", S.TODO), ("C", S.LOCKED))
    stages[0].status = S.IN_PROGRESS  # reopened
    logic.recompute_locks(stages)
    assert [s.status for s in stages] == [S.IN_PROGRESS, S.LOCKED, S.LOCKED]


def test_early_unlock_survives_reopening_upstream():
    stages = make(("A", S.IN_PROGRESS), ("B", S.TODO), ("C", S.LOCKED))
    stages[1].unlocked_early = True
    logic.recompute_locks(stages)
    assert stages[1].status == S.TODO
    assert stages[2].status == S.LOCKED


def test_started_stages_are_never_touched_by_recompute():
    stages = make(("A", S.TODO), ("B", S.IN_PROGRESS), ("C", S.BLOCKED), ("D", S.DONE))
    logic.recompute_locks(stages)
    assert [s.status for s in stages] == [S.TODO, S.IN_PROGRESS, S.BLOCKED, S.DONE]


# ---------- progress and summary ----------

@pytest.mark.parametrize("done,total,expected", [
    (0, 3, 0), (1, 3, 33), (2, 3, 67), (3, 3, 100), (1, 2, 50), (1, 8, 13), (1, 6, 17), (5, 6, 83), (1, 1, 100),
])
def test_progress_rounds_half_up(done, total, expected):
    stages = make(*[(f"S{i}", S.DONE if i < done else S.LOCKED) for i in range(total)])
    assert logic.summarize(stages).progress == expected


def test_task_status_values():
    assert logic.summarize(make(("A", S.TODO), ("B", S.LOCKED))).status == "not_started"
    assert logic.summarize(make(("A", S.IN_PROGRESS), ("B", S.LOCKED))).status == "in_progress"
    assert logic.summarize(make(("A", S.BLOCKED), ("B", S.LOCKED))).status == "in_progress"
    assert logic.summarize(make(("A", S.DONE), ("B", S.TODO))).status == "in_progress"
    assert logic.summarize(make(("A", S.DONE), ("B", S.DONE))).status == "done"


def test_current_stages_are_the_unfinished_ones_in_the_earliest_open_step():
    summary = logic.summarize(make(("Script", S.DONE), ("Graphics", S.TODO), ("Music", S.IN_PROGRESS, True), ("Export", S.LOCKED)))
    assert summary.current_title == "Graphics, Music"
    assert len(summary.current_ids) == 2


def test_current_stage_is_none_when_everything_is_done():
    summary = logic.summarize(make(("A", S.DONE), ("B", S.DONE)))
    assert summary.current == [] and summary.current_title is None


def test_blocked_flag():
    assert logic.summarize(make(("A", S.BLOCKED))).is_blocked is True
    assert logic.summarize(make(("A", S.TODO))).is_blocked is False


# ---------- allowed statuses: every row of the contract table ----------

def allowed(status, *, participant=False, can_edit=False, can_override=False, later=None):
    specs = [("A", status)]
    if later:
        specs.append(("B", later))
    stages = make(*specs)
    return logic.allowed_statuses(stages, 0, participant=participant, can_edit=can_edit, can_override=can_override)


def test_participant_rows():
    assert allowed(S.LOCKED, participant=True) == []
    assert allowed(S.TODO, participant=True) == [S.IN_PROGRESS, S.DONE]
    assert allowed(S.IN_PROGRESS, participant=True) == [S.TODO, S.DONE, S.BLOCKED]
    assert allowed(S.BLOCKED, participant=True) == [S.IN_PROGRESS]
    assert allowed(S.DONE, participant=True) == []


def test_head_rows():
    head = dict(can_edit=True, can_override=True)
    assert allowed(S.LOCKED, **head) == [S.TODO, S.IN_PROGRESS]
    assert allowed(S.TODO, **head) == [S.IN_PROGRESS, S.DONE]
    assert allowed(S.IN_PROGRESS, **head) == [S.TODO, S.DONE, S.BLOCKED]
    assert allowed(S.BLOCKED, **head) == [S.IN_PROGRESS]
    assert allowed(S.DONE, **head) == [S.IN_PROGRESS]


def test_reopen_is_hidden_once_a_later_step_started():
    head = dict(can_edit=True, can_override=True)
    assert allowed(S.DONE, later=S.LOCKED, **head) == [S.IN_PROGRESS]
    assert allowed(S.DONE, later=S.TODO, **head) == [S.IN_PROGRESS]
    for started in (S.IN_PROGRESS, S.BLOCKED, S.DONE):
        assert allowed(S.DONE, later=started, **head) == []


def test_stranger_gets_nothing_in_any_status():
    for status in (S.LOCKED, S.TODO, S.IN_PROGRESS, S.BLOCKED, S.DONE):
        assert allowed(status) == []


# ---------- applying a status ----------

def test_apply_done_and_reopen_set_and_clear_completion():
    (stage,) = make(("A", S.IN_PROGRESS))
    uid = uuid.uuid4()
    logic.apply_status(stage, S.DONE, None, uid, NOW)
    assert (stage.status, stage.completed_at, stage.completed_by) == (S.DONE, NOW, uid)
    logic.apply_status(stage, S.IN_PROGRESS, None, uid, NOW)
    assert (stage.completed_at, stage.completed_by) == (None, None)


def test_apply_blocked_stores_reason_and_clears_it_on_leaving():
    (stage,) = make(("A", S.IN_PROGRESS))
    logic.apply_status(stage, S.BLOCKED, "  Waiting for footage ", uuid.uuid4(), NOW)
    assert stage.blocked_reason == "Waiting for footage"
    logic.apply_status(stage, S.IN_PROGRESS, None, uuid.uuid4(), NOW)
    assert stage.blocked_reason is None


def test_unlocking_a_locked_stage_marks_it_unlocked_early():
    (stage,) = make(("A", S.LOCKED))
    logic.apply_status(stage, S.TODO, None, uuid.uuid4(), NOW)
    assert stage.unlocked_early is True
