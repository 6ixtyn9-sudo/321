from datetime import datetime, timedelta, timezone

from src.soccer_factory.sources.soccerstats.lifecycle import fixture_state, eligible_pre_match_snapshot


def test_lifecycle_respects_kickoff_and_result_evidence():
    kickoff = datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)
    assert fixture_state(source_status="pre-match", observed_at=kickoff - timedelta(minutes=1), kickoff_utc=kickoff) == "scheduled"
    assert fixture_state(source_status="pre-match", observed_at=kickoff + timedelta(minutes=30), kickoff_utc=kickoff) == "kickoff_due"
    assert fixture_state(source_status="pre-match", observed_at=kickoff + timedelta(minutes=151), kickoff_utc=kickoff) == "awaiting_result"
    assert fixture_state(source_status="live", observed_at=kickoff, kickoff_utc=kickoff) == "live"
    assert fixture_state(source_status="pre-match", observed_at=kickoff, kickoff_utc=kickoff, final_result_evidence=True) == "finished"


def test_only_verified_pre_kickoff_data_is_eligible():
    kickoff = datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)
    assert eligible_pre_match_snapshot(state="scheduled", observed_at=kickoff - timedelta(minutes=1), kickoff_utc=kickoff)
    assert not eligible_pre_match_snapshot(state="scheduled", observed_at=kickoff, kickoff_utc=kickoff)
    assert not eligible_pre_match_snapshot(state="live", observed_at=kickoff, kickoff_utc=kickoff)
