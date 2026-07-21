-- 321 Soccer Analytics DuckDB Schema

CREATE TABLE IF NOT EXISTS manifests (
    run_id VARCHAR PRIMARY KEY,
    mode VARCHAR,
    run_date DATE,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    git_commit VARCHAR,
    pages_attempted INTEGER,
    pages_succeeded INTEGER,
    pages_failed INTEGER,
    quarantined INTEGER,
    matches_discovered INTEGER,
    matches_matched INTEGER,
    matches_rejected INTEGER,
    features_built INTEGER,
    predictions_generated INTEGER,
    predictions_frozen INTEGER,
    warnings JSON,
    errors JSON
);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id VARCHAR PRIMARY KEY,
    source VARCHAR,
    url VARCHAR,
    requested_at TIMESTAMP,
    response_status INTEGER,
    response_headers_subset JSON,
    content_hash VARCHAR,
    content_length INTEGER,
    parser_version VARCHAR,
    extraction_method VARCHAR,
    match_date_if_known VARCHAR,
    http_error VARCHAR,
    validation_status VARCHAR,
    local_file_path VARCHAR,
    collection_run_id VARCHAR
);

CREATE TABLE IF NOT EXISTS matches (
    match_id VARCHAR PRIMARY KEY,
    sport VARCHAR DEFAULT 'soccer',
    country VARCHAR,
    competition VARCHAR,
    competition_key VARCHAR,
    home_team VARCHAR,
    away_team VARCHAR,
    normalized_home_team VARCHAR,
    normalized_away_team VARCHAR,
    scheduled_kickoff TIMESTAMP,
    timezone VARCHAR,
    source_urls JSON,
    status VARCHAR,
    identity_confidence DOUBLE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_forecasts (
    source VARCHAR,
    match_id VARCHAR,
    market VARCHAR,
    selection VARCHAR,
    predicted_score_if_available VARCHAR,
    collected_at TIMESTAMP,
    source_status VARCHAR,
    source_url VARCHAR,
    parser_version VARCHAR,
    is_pre_match BOOLEAN,
    is_live BOOLEAN,
    is_finished BOOLEAN,
    PRIMARY KEY (source, match_id, market)
);

CREATE TABLE IF NOT EXISTS features (
    match_id VARCHAR PRIMARY KEY,
    collected_at TIMESTAMP,
    feature_cutoff TIMESTAMP,
    match_kickoff TIMESTAMP,
    data_type VARCHAR,
    source_status VARCHAR,
    home_ppg DOUBLE,
    away_ppg DOUBLE,
    home_goals_scored_avg DOUBLE,
    home_goals_conceded_avg DOUBLE,
    away_goals_scored_avg DOUBLE,
    away_goals_conceded_avg DOUBLE,
    btts_rate_home DOUBLE,
    btts_rate_away DOUBLE,
    over_25_rate_home DOUBLE,
    over_25_rate_away DOUBLE,
    sample_size_home INTEGER,
    sample_size_away INTEGER
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id VARCHAR PRIMARY KEY,
    match_id VARCHAR,
    market VARCHAR,
    selection VARCHAR,
    probability DOUBLE,
    confidence_grade VARCHAR,
    model_version VARCHAR,
    feature_cutoff TIMESTAMP,
    created_at TIMESTAMP,
    frozen_at TIMESTAMP,
    official BOOLEAN,
    reasons JSON,
    data_quality VARCHAR
);

CREATE TABLE IF NOT EXISTS results (
    match_id VARCHAR PRIMARY KEY,
    home_score INTEGER,
    away_score INTEGER,
    status VARCHAR,
    match_outcome VARCHAR,
    total_goals INTEGER,
    btts_result BOOLEAN,
    over_25_result BOOLEAN
);

CREATE TABLE IF NOT EXISTS grading (
    prediction_id VARCHAR PRIMARY KEY,
    match_id VARCHAR,
    correct BOOLEAN,
    actual_outcome VARCHAR,
    final_score VARCHAR,
    total_goals INTEGER,
    btts_result BOOLEAN,
    graded_at TIMESTAMP,
    grading_source VARCHAR,
    unresolved_status VARCHAR
);
