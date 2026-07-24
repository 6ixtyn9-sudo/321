"""Backwards-compatibility shim: re-exports the canonical normalize/match API.

Normalization logic lives in :mod:`matcher` so it can be unit-tested next to
the matching code that depends on its exact behaviour.
"""
from .matcher import (
    normalize_team_name,
    similarity,
    match_teams,
    match_match,
    match_match_permissive,
    reserve_suffix,
)

__all__ = [
    "normalize_team_name",
    "similarity",
    "match_teams",
    "match_match",
    "match_match_permissive",
    "reserve_suffix",
]
