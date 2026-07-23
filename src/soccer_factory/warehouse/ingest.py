"""Warehouse ingestion for ALL tables - ensures every link produces stats end-to-end."""

from typing import List
import json
from .db import Warehouse
from ..schemas.snapshots import RawSnapshot
from ..schemas.matches import Match
from ..schemas.features import Features
from ..schemas.predictions import Prediction, SourceObservation
from ..schemas.results import Result, Grading

def ingest_snapshots(warehouse: Warehouse, snapshots: List[RawSnapshot]) -> None:
    conn = warehouse.get_connection()
    for s in snapshots:
        conn.execute('''
            INSERT OR REPLACE INTO snapshots (
                snapshot_id, source, url, requested_at, response_status, 
                response_headers_subset, content_hash, content_length, 
                parser_version, extraction_method, match_date_if_known, 
                http_error, validation_status, local_file_path, collection_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            s.snapshot_id, s.source, s.url, s.requested_at, s.response_status,
            json.dumps(s.response_headers_subset), s.content_hash, s.content_length,
            s.parser_version, s.extraction_method, s.match_date_if_known,
            s.http_error, s.validation_status, s.local_file_path, s.collection_run_id
        ))

def ingest_matches(warehouse: Warehouse, matches: List[Match]) -> None:
    conn = warehouse.get_connection()
    for m in matches:
        conn.execute('''
            INSERT OR REPLACE INTO matches (
                match_id, sport, country, competition, competition_key,
                home_team, away_team, normalized_home_team, normalized_away_team,
                scheduled_kickoff, timezone, source_urls, status,
                identity_confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            m.match_id, m.sport, m.country, m.competition, m.competition_key,
            m.home_team, m.away_team, m.normalized_home_team, m.normalized_away_team,
            m.scheduled_kickoff, m.timezone, json.dumps(m.source_urls), m.status,
            m.identity_confidence, m.created_at, m.updated_at
        ))

def ingest_features(warehouse: Warehouse, features: List[Features]) -> None:
    """Ingest Features - covers ALL families: home_away, form_table, trends, team_stats, etc."""
    conn = warehouse.get_connection()
    for f in features:
        conn.execute('''
            INSERT OR REPLACE INTO features (
                match_id, collected_at, feature_cutoff, match_kickoff, data_type, source_status,
                home_ppg, away_ppg, home_goals_scored_avg, home_goals_conceded_avg,
                away_goals_scored_avg, away_goals_conceded_avg,
                btts_rate_home, btts_rate_away, over_25_rate_home, over_25_rate_away,
                sample_size_home, sample_size_away
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f.match_id, f.collected_at, f.feature_cutoff, f.match_kickoff, f.data_type, f.source_status,
            f.home_ppg, f.away_ppg, f.home_goals_scored_avg, f.home_goals_conceded_avg,
            f.away_goals_scored_avg, f.away_goals_conceded_avg,
            f.btts_rate_home, f.btts_rate_away, f.over_25_rate_home, f.over_25_rate_away,
            f.sample_size_home, f.sample_size_away
        ))

def ingest_forecasts(warehouse: Warehouse, observations: List[SourceObservation]) -> None:
    """Ingest Forebet observations - covers ALL Forebet families"""
    conn = warehouse.get_connection()
    for o in observations:
        conn.execute('''
            INSERT OR REPLACE INTO source_forecasts (
                source, match_id, market, selection, predicted_score_if_available,
                collected_at, source_status, source_url, parser_version,
                is_pre_match, is_live, is_finished
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            o.source, o.match_identity, o.market, o.selection, o.predicted_score,
            o.collected_at, o.source_status, o.source_url, o.parser_version,
            o.is_pre_match, o.is_live, o.is_finished
        ))

def ingest_predictions(warehouse: Warehouse, predictions: List[Prediction]) -> None:
    conn = warehouse.get_connection()
    for p in predictions:
        conn.execute('''
            INSERT OR REPLACE INTO predictions (
                prediction_id, match_id, market, selection, probability,
                confidence_grade, model_version, feature_cutoff, created_at,
                frozen_at, official, reasons, data_quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            p.prediction_id, p.match_id, p.market, p.selection, p.probability,
            p.confidence_grade, p.model_version, p.feature_cutoff, p.created_at,
            p.frozen_at, p.official, json.dumps(p.reasons), p.data_quality
        ))

def ingest_results(warehouse: Warehouse, results: List[Result]) -> None:
    conn = warehouse.get_connection()
    for r in results:
        conn.execute('''
            INSERT OR REPLACE INTO results (
                match_id, home_score, away_score, status, match_outcome,
                total_goals, btts_result, over_25_result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            r.match_id, r.home_score, r.away_score, r.status, r.match_outcome,
            r.total_goals, r.btts_result, r.over_25_result
        ))

def ingest_grading(warehouse: Warehouse, gradings: List[Grading]) -> None:
    conn = warehouse.get_connection()
    for g in gradings:
        conn.execute('''
            INSERT OR REPLACE INTO grading (
                prediction_id, match_id, correct, actual_outcome, final_score,
                total_goals, btts_result, graded_at, grading_source, unresolved_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            g.prediction_id, g.match_id, g.correct, g.actual_outcome, g.final_score,
            g.total_goals, g.btts_result, g.graded_at, g.grading_source, g.unresolved_status
        ))

def ingest_manifest(warehouse: Warehouse, manifest: dict) -> None:
    """Ingest run manifest for operational tracking"""
    conn = warehouse.get_connection()
    import datetime
    conn.execute('''
        INSERT OR REPLACE INTO manifests (
            run_id, mode, run_date, start_time, end_time, git_commit,
            pages_attempted, pages_succeeded, pages_failed, quarantined,
            matches_discovered, matches_matched, matches_rejected,
            features_built, predictions_generated, predictions_frozen,
            warnings, errors
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        manifest.get('run_id', 'unknown'),
        manifest.get('mode', 'unknown'),
        manifest.get('run_date'),
        manifest.get('start_time', datetime.datetime.now()),
        manifest.get('end_time', datetime.datetime.now()),
        manifest.get('git_commit', 'unknown'),
        manifest.get('pages_attempted', 0),
        manifest.get('pages_succeeded', 0),
        manifest.get('pages_failed', 0),
        manifest.get('quarantined', 0),
        manifest.get('matches_discovered', 0),
        manifest.get('matches_matched', 0),
        manifest.get('matches_rejected', 0),
        manifest.get('features_built', 0),
        manifest.get('predictions_generated', 0),
        manifest.get('predictions_frozen', 0),
        json.dumps(manifest.get('warnings', [])),
        json.dumps(manifest.get('errors', []))
    ))
