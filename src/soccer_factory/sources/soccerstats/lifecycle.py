"""Time-aware lifecycle rules for SoccerStats fixture observations.

A URL is never treated as a permanent state indicator: the observation time,
kickoff time, source status, and final-result evidence determine the state.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

LifecycleState = Literal[
    "scheduled", "kickoff_due", "live", "awaiting_result", "finished", "postponed", "unknown"
]


def fixture_state(*, source_status: str, observed_at: datetime,
                  kickoff_utc: datetime | None, final_result_evidence: bool = False,
                  finalisation_buffer_minutes: int = 150) -> LifecycleState:
    """Classify one immutable source observation.

    `final_result_evidence` means a confirmed result page/final marker, not a
    merely visible score.  The buffer avoids declaring a fixture finished just
    because its expected 90-minute window has passed.
    """
    status = source_status.lower()
    if status == "postponed":
        return "postponed"
    if final_result_evidence or status == "finished":
        return "finished"
    if status == "live":
        return "live"
    if kickoff_utc is None:
        return "scheduled" if status in {"pre-match", "scheduled"} else "unknown"
    if observed_at < kickoff_utc:
        return "scheduled"
    finalisation_due = kickoff_utc + timedelta(minutes=finalisation_buffer_minutes)
    if observed_at < finalisation_due:
        return "kickoff_due"
    return "awaiting_result"


def eligible_pre_match_snapshot(*, state: LifecycleState, observed_at: datetime,
                                kickoff_utc: datetime | None) -> bool:
    """Return true only for an observation known to precede a verified kickoff."""
    return state == "scheduled" and kickoff_utc is not None and observed_at < kickoff_utc
