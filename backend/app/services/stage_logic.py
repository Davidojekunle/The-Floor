"""Pure rules for stages: steps, unlocking, progress, and who may set which status.

No database and no HTTP in here, so every rule is unit-tested directly.
Stages are always passed in position order.
"""
from dataclasses import dataclass
from datetime import datetime

from app.models.enums import StageStatus as S
from app.models.enums import TaskStatus
from app.utils.time import as_utc


# A stage "needs its people" in these states (locked = not yet, done = no longer)
ACTIONABLE = (S.TODO, S.IN_PROGRESS, S.BLOCKED)


def renumber(stages) -> None:
    """Positions become 1..N, and the first stage can never be 'parallel with previous'."""
    for i, stage in enumerate(stages, start=1):
        stage.position = i
    if stages:
        stages[0].parallel_with_previous = False


def steps(stages) -> list[int]:
    """Step number per stage. Consecutive stages flagged parallel share a step."""
    out, step = [], 0
    for i, stage in enumerate(stages):
        if i == 0 or not stage.parallel_with_previous:
            step += 1
        out.append(step)
    return out


def recompute_locks(stages) -> None:
    """Stages still waiting (locked/todo) unlock when every earlier step is done.

    Stages already started or finished are never touched, and an early unlock sticks.
    """
    step_of = steps(stages)
    for i, stage in enumerate(stages):
        if stage.status not in (S.LOCKED, S.TODO):
            continue
        upstream_done = all(o.status == S.DONE for o, st in zip(stages, step_of) if st < step_of[i])
        stage.status = S.TODO if (upstream_done or stage.unlocked_early) else S.LOCKED


def later_started(stages, idx: int) -> bool:
    """Has any LATER step started (in progress, blocked, or done)?"""
    step_of = steps(stages)
    return any(
        stages[j].status in (S.IN_PROGRESS, S.BLOCKED, S.DONE) and step_of[j] > step_of[idx]
        for j in range(len(stages))
    )


def allowed_statuses(stages, idx: int, *, participant: bool, can_edit: bool, can_override: bool) -> list[str]:
    """Statuses this person may set on this stage right now (the table in the contract)."""
    stage = stages[idx]
    can_act = participant or can_edit

    if stage.status == S.LOCKED:
        return [S.TODO, S.IN_PROGRESS] if can_override else []
    if stage.status == S.TODO:
        return [S.IN_PROGRESS, S.DONE] if can_act else []
    if stage.status == S.IN_PROGRESS:
        return [S.TODO, S.DONE, S.BLOCKED] if can_act else []
    if stage.status == S.BLOCKED:
        return [S.IN_PROGRESS] if can_act else []
    if stage.status == S.DONE:
        return [S.IN_PROGRESS] if can_override and not later_started(stages, idx) else []
    return []


def apply_status(stage, new: str, reason: str | None, actor_id, now: datetime) -> None:
    old = stage.status
    if old == S.LOCKED and new in (S.TODO, S.IN_PROGRESS):
        stage.unlocked_early = True
    if new == S.DONE:
        stage.completed_at, stage.completed_by = now, actor_id
    elif old == S.DONE:
        stage.completed_at, stage.completed_by = None, None
    stage.blocked_reason = (reason or "").strip() if new == S.BLOCKED else None
    stage.status = new


@dataclass(frozen=True)
class Summary:
    total: int
    done: int
    status: str
    progress: int
    current: list  # stages in the earliest unfinished step that aren't done
    is_blocked: bool
    completed_at: datetime | None

    @property
    def current_ids(self) -> list:
        return [s.id for s in self.current]

    @property
    def current_title(self) -> str | None:
        return ", ".join(s.title for s in self.current) if self.current else None


def summarize(stages) -> Summary:
    total = len(stages)
    done = sum(1 for s in stages if s.status == S.DONE)

    if total and done == total:
        status = TaskStatus.DONE
    elif done > 0 or any(s.status in (S.IN_PROGRESS, S.BLOCKED) for s in stages):
        status = TaskStatus.IN_PROGRESS
    else:
        status = TaskStatus.NOT_STARTED

    progress = (200 * done + total) // (2 * total) if total else 0  # round half up

    step_of = steps(stages)
    current = []
    for step in sorted(set(step_of)):
        pending = [s for s, st in zip(stages, step_of) if st == step and s.status != S.DONE]
        if pending:
            current = pending
            break

    completed_at = max((as_utc(s.completed_at) for s in stages if s.completed_at), default=None) if status == TaskStatus.DONE else None
    return Summary(
        total=total,
        done=done,
        status=status,
        progress=progress,
        current=current,
        is_blocked=any(s.status == S.BLOCKED for s in stages),
        completed_at=completed_at,
    )
