-- ============================================================
-- betatp.io — PostgreSQL Schema
-- Tennis prediction platform: matches + odds + weather + elo
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fuzzy text search (player names)
CREATE EXTENSION IF NOT EXISTS btree_gist; -- range indexing (dates)

-- ============================================================
-- 1. PLAYERS
-- ============================================================
CREATE TABLE players (
    player_id       SERIAL PRIMARY KEY,
    tml_id          TEXT UNIQUE,          -- TML-Database key (e.g. "djokovic_n")
    full_name       TEXT NOT NULL,
    hand            CHAR(1),              -- R/L/U
    birth_date      DATE,
    country_code    CHAR(3),
    height_cm       SMALLINT,
    turned_pro      SMALLINT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT players_hand_chk CHECK (hand IN ('R','L','U'))
);
CREATE INDEX players_name_trgm ON players USING gin(full_name gin_trgm_ops);

-- ============================================================
-- 2. TOURNAMENTS
-- ============================================================
CREATE TABLE tournaments (
    tournament_id   SERIAL PRIMARY KEY,
    tourney_name    TEXT NOT NULL,
    tourney_slug    TEXT UNIQUE NOT NULL,  -- normalized: "roland_garros"
    surface         TEXT,                  -- Hard/Clay/Grass
    level           TEXT,                  -- G/M/500/250/F/A
    indoor          BOOLEAN DEFAULT FALSE,
    -- Location
    city            TEXT,
    country_code    CHAR(3),
    lat             NUMERIC(7,4),
    lon             NUMERIC(7,4),
    elevation_m     SMALLINT,
    -- Nearest weather station
    station_id      TEXT,                  -- NOAA/Meteostat station ID
    station_dist_km NUMERIC(6,2),
    CONSTRAINT tournaments_surface_chk CHECK (surface IN ('Hard','Clay','Grass','Carpet'))
);

-- ============================================================
-- 3. TOURNAMENT EDITIONS (1 per year)
-- ============================================================
CREATE TABLE tournament_editions (
    edition_id      SERIAL PRIMARY KEY,
    tournament_id   INTEGER NOT NULL REFERENCES tournaments(tournament_id),
    year            SMALLINT NOT NULL,
    tourney_date    DATE NOT NULL,         -- first day of tournament
    draw_size       SMALLINT,
    surface         TEXT,                  -- może się zmienić rok do roku
    UNIQUE (tournament_id, year)
);
CREATE INDEX te_date_idx ON tournament_editions(tourney_date);

-- ============================================================
-- 4. MATCHES
-- ============================================================
CREATE TABLE matches (
    match_id        BIGSERIAL PRIMARY KEY,
    edition_id      INTEGER NOT NULL REFERENCES tournament_editions(edition_id),
    match_date      DATE,
    round           TEXT,                  -- R128/R64/R32/R16/QF/SF/F
    best_of         SMALLINT,             -- 3 or 5
    -- Players (winner first — symmetric A/B done at feature time)
    winner_id       INTEGER NOT NULL REFERENCES players(player_id),
    loser_id        INTEGER NOT NULL REFERENCES players(player_id),
    -- Score
    score           TEXT,
    w_sets          SMALLINT,
    l_sets          SMALLINT,
    w_games         SMALLINT,
    l_games         SMALLINT,
    minutes         SMALLINT,
    retired         BOOLEAN DEFAULT FALSE,
    walkover        BOOLEAN DEFAULT FALSE,
    -- Rankings at match time
    w_rank          SMALLINT,
    l_rank          SMALLINT,
    w_rank_pts      INTEGER,
    l_rank_pts      INTEGER,
    -- Serve stats winner
    w_ace           SMALLINT,
    w_df            SMALLINT,
    w_svpt          SMALLINT,
    w_1stin         SMALLINT,
    w_1stwon        SMALLINT,
    w_2ndwon        SMALLINT,
    w_svgms         SMALLINT,
    w_bpsaved       SMALLINT,
    w_bpfaced       SMALLINT,
    -- Serve stats loser
    l_ace           SMALLINT,
    l_df            SMALLINT,
    l_svpt          SMALLINT,
    l_1stin         SMALLINT,
    l_1stwon        SMALLINT,
    l_2ndwon        SMALLINT,
    l_svgms         SMALLINT,
    l_bpsaved       SMALLINT,
    l_bpfaced       SMALLINT,
    -- Source
    tml_id          TEXT,                  -- oryginalny match_id z TML
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX matches_edition_idx ON matches(edition_id);
CREATE INDEX matches_winner_idx  ON matches(winner_id);
CREATE INDEX matches_loser_idx   ON matches(loser_id);
CREATE INDEX matches_date_idx    ON matches(match_date);
CREATE UNIQUE INDEX matches_tml_idx ON matches(tml_id) WHERE tml_id IS NOT NULL;

-- ============================================================
-- 5. ODDS
-- ============================================================
CREATE TABLE odds (
    odds_id         BIGSERIAL PRIMARY KEY,
    match_id        BIGINT NOT NULL REFERENCES matches(match_id),
    bookmaker       TEXT NOT NULL,         -- 'pinnacle','bet365','max','avg'
    odds_winner     NUMERIC(7,3),          -- decimal odds (winner)
    odds_loser      NUMERIC(7,3),
    prob_winner     NUMERIC(6,5),          -- de-vig probability
    prob_loser      NUMERIC(6,5),
    margin          NUMERIC(6,4),          -- overround
    log_odds        NUMERIC(8,5),          -- ln(prob_w/prob_l)
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (match_id, bookmaker)
);
CREATE INDEX odds_match_idx ON odds(match_id);
CREATE INDEX odds_bk_idx    ON odds(bookmaker);

-- ============================================================
-- 6. WEATHER STATIONS
-- ============================================================
CREATE TABLE weather_stations (
    station_id      TEXT PRIMARY KEY,      -- NOAA GSOD: "724080-14739" / Meteostat: "10382"
    source          TEXT NOT NULL,         -- 'NOAA_GSOD','METEOSTAT','ERA5_GRID'
    name            TEXT,
    country_code    CHAR(3),
    lat             NUMERIC(7,4),
    lon             NUMERIC(7,4),
    elevation_m     SMALLINT,
    wmo_id          TEXT,                  -- WMO station number
    icao            CHAR(4),               -- ICAO airport code
    active_from     DATE,
    active_to       DATE,                  -- NULL = still active
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ws_geo_idx ON weather_stations(lat, lon);

-- ============================================================
-- 7. DAILY WEATHER OBSERVATIONS
-- ============================================================
CREATE TABLE weather_daily (
    obs_id          BIGSERIAL PRIMARY KEY,
    station_id      TEXT NOT NULL REFERENCES weather_stations(station_id),
    obs_date        DATE NOT NULL,
    source          TEXT NOT NULL,         -- 'NOAA_GSOD','METEOSTAT','ERA5'
    -- Temperature (°C)
    temp_mean       NUMERIC(5,2),
    temp_max        NUMERIC(5,2),
    temp_min        NUMERIC(5,2),
    -- Precipitation (mm)
    precip_mm       NUMERIC(7,2),
    snow_mm         NUMERIC(7,2),
    -- Wind (km/h)
    wind_mean_kmh   NUMERIC(6,2),
    wind_max_kmh    NUMERIC(6,2),
    wind_gust_kmh   NUMERIC(6,2),
    -- Humidity (%)
    humidity_mean   NUMERIC(5,2),
    humidity_max    NUMERIC(5,2),
    -- Pressure (hPa)
    pressure_hpa    NUMERIC(7,2),
    -- Visibility (km)
    visibility_km   NUMERIC(6,2),
    -- Sky / radiation
    cloud_cover_pct NUMERIC(5,2),
    solar_mj        NUMERIC(7,3),          -- MJ/m² daily
    -- WMO weather code
    weather_code    SMALLINT,
    -- Quality flags
    temp_qc         BOOLEAN DEFAULT TRUE,
    precip_qc       BOOLEAN DEFAULT TRUE,
    wind_qc         BOOLEAN DEFAULT TRUE,
    UNIQUE (station_id, obs_date, source)
);
-- Partition by year for performance
CREATE INDEX wd_station_date_idx ON weather_daily(station_id, obs_date);
CREATE INDEX wd_date_idx         ON weather_daily(obs_date);

-- ============================================================
-- 8. WEATHER → TOURNAMENT MAPPING (pre-computed per edition)
-- ============================================================
CREATE TABLE tournament_weather (
    tw_id               BIGSERIAL PRIMARY KEY,
    edition_id          INTEGER NOT NULL REFERENCES tournament_editions(edition_id),
    station_id          TEXT REFERENCES weather_stations(station_id),
    source              TEXT,
    -- Aggregated per edition window
    n_days              SMALLINT,
    n_outdoor_days      SMALLINT,
    -- Temperature
    temp_mean           NUMERIC(5,2),
    temp_max_mean       NUMERIC(5,2),
    temp_min_mean       NUMERIC(5,2),
    temp_range_mean     NUMERIC(5,2),
    temp_extreme_hot    NUMERIC(5,4),  -- fraction days >35°C
    temp_extreme_cold   NUMERIC(5,4),  -- fraction days <10°C
    -- Precipitation
    rain_total_mm       NUMERIC(8,2),
    rain_days           SMALLINT,
    rain_heavy_days     SMALLINT,      -- >10mm
    -- Wind
    wind_mean_kmh       NUMERIC(6,2),
    wind_max_kmh        NUMERIC(6,2),
    wind_strong_days    SMALLINT,      -- max >30 km/h
    -- Humidity / pressure
    humidity_mean       NUMERIC(5,2),
    pressure_mean       NUMERIC(7,2),
    -- Solar / cloud
    solar_total_mj      NUMERIC(8,3),
    cloud_cover_mean    NUMERIC(5,2),
    -- Sky conditions (fractions)
    pct_clear           NUMERIC(5,4),
    pct_overcast        NUMERIC(5,4),
    pct_rain            NUMERIC(5,4),
    pct_storm           NUMERIC(5,4),
    -- Composite
    harsh_conditions    NUMERIC(5,4),  -- hot+humid OR rain+wind
    heat_index_mean     NUMERIC(5,2),  -- feels-like
    UNIQUE (edition_id, source)
);

-- ============================================================
-- 9. ELO + FORM STATE (snapshot per match)
-- ============================================================
CREATE TABLE player_ratings (
    rating_id       BIGSERIAL PRIMARY KEY,
    match_id        BIGINT NOT NULL REFERENCES matches(match_id),
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    -- Pre-match ratings (before this match)
    elo_general     NUMERIC(8,2),
    elo_surface     NUMERIC(8,2),
    -- Form features
    ewma_form       NUMERIC(6,4),
    ewma_surf       NUMERIC(6,4),
    fat14           NUMERIC(6,4),   -- fatigue 14-day
    streak          SMALLINT,       -- +W -L streak
    matches_365     SMALLINT,       -- matches last 365 days
    win_pct_365     NUMERIC(5,4),
    surf_spec       NUMERIC(6,4),   -- surface specialization
    UNIQUE (match_id, player_id)
);
CREATE INDEX pr_player_idx ON player_ratings(player_id);
CREATE INDEX pr_match_idx  ON player_ratings(match_id);

-- ============================================================
-- 10. MODEL PREDICTIONS (v4, v5, ... vN)
-- ============================================================
CREATE TABLE predictions (
    pred_id         BIGSERIAL PRIMARY KEY,
    match_id        BIGINT NOT NULL REFERENCES matches(match_id),
    model_version   TEXT NOT NULL,         -- 'v4', 'v5', ...
    prob_winner     NUMERIC(6,5),          -- P(winner wins)
    prob_winner_cal NUMERIC(6,5),          -- calibrated (Platt/Isotonic)
    pin_prob        NUMERIC(6,5),          -- Pinnacle de-vig
    market_edge     NUMERIC(7,5),          -- model_prob - pin_prob
    value_bet       BOOLEAN,               -- edge > threshold
    kelly_fraction  NUMERIC(6,5),
    predicted_at    TIMESTAMPTZ DEFAULT now(),
    features_json   JSONB,                 -- snapshot cech (do audytu)
    UNIQUE (match_id, model_version)
);
CREATE INDEX pred_match_idx   ON predictions(match_id);
CREATE INDEX pred_model_idx   ON predictions(model_version);
CREATE INDEX pred_value_idx   ON predictions(value_bet) WHERE value_bet = TRUE;

-- ============================================================
-- 11. BACKTEST RESULTS
-- ============================================================
CREATE TABLE backtest_runs (
    run_id          SERIAL PRIMARY KEY,
    model_version   TEXT NOT NULL,
    edge_threshold  NUMERIC(5,3),
    kelly_fraction  NUMERIC(5,3),          -- 0.25 = quarter Kelly
    period_start    DATE,
    period_end      DATE,
    n_bets          INTEGER,
    n_won           INTEGER,
    win_rate        NUMERIC(6,4),
    roi_per_bet     NUMERIC(8,5),          -- avg odds * win_rate - 1
    total_pnl       NUMERIC(12,4),         -- w jednostkach stawki
    max_drawdown    NUMERIC(8,5),
    sharpe          NUMERIC(7,4),
    run_at          TIMESTAMPTZ DEFAULT now(),
    params_json     JSONB
);

-- ============================================================
-- VIEWS: wygodne widoki dla ML i API
-- ============================================================

-- v_match_features: kompletny wiersz per mecz dla ML
CREATE OR REPLACE VIEW v_match_features AS
SELECT
    m.match_id,
    m.match_date,
    te.year,
    t.tourney_name,
    t.surface,
    t.level,
    t.indoor,
    m.round,
    m.best_of,
    -- Winner
    pw.full_name    AS winner_name,
    pw.country_code AS winner_country,
    m.w_rank,
    -- Loser
    pl.full_name    AS loser_name,
    pl.country_code AS loser_country,
    m.l_rank,
    -- Odds: Pinnacle
    op.odds_winner  AS pin_odds_w,
    op.odds_loser   AS pin_odds_l,
    op.prob_winner  AS pin_prob_w,
    op.margin       AS pin_margin,
    -- Odds: Bet365
    ob.odds_winner  AS b365_odds_w,
    ob.prob_winner  AS b365_prob_w,
    -- Odds: Max
    om.prob_winner  AS max_prob_w,
    -- Weather (z edition)
    tw.temp_mean,
    tw.temp_max_mean,
    tw.rain_total_mm,
    tw.rain_days,
    tw.wind_max_kmh,
    tw.humidity_mean,
    tw.pct_clear,
    tw.pct_rain,
    tw.harsh_conditions,
    tw.heat_index_mean,
    tw.source       AS weather_source,
    -- Elo winner (pre-match)
    rw.elo_general  AS w_elo,
    rw.elo_surface  AS w_elo_surf,
    rw.ewma_form    AS w_ewma,
    rw.fat14        AS w_fat14,
    rw.surf_spec    AS w_surf_spec,
    -- Elo loser
    rl.elo_general  AS l_elo,
    rl.elo_surface  AS l_elo_surf,
    rl.ewma_form    AS l_ewma,
    rl.fat14        AS l_fat14,
    rl.surf_spec    AS l_surf_spec
FROM matches m
JOIN tournament_editions te ON m.edition_id = te.edition_id
JOIN tournaments t          ON te.tournament_id = t.tournament_id
JOIN players pw             ON m.winner_id = pw.player_id
JOIN players pl             ON m.loser_id  = pl.player_id
LEFT JOIN odds op           ON m.match_id = op.match_id AND op.bookmaker = 'pinnacle'
LEFT JOIN odds ob           ON m.match_id = ob.match_id AND ob.bookmaker = 'bet365'
LEFT JOIN odds om           ON m.match_id = om.match_id AND om.bookmaker = 'max'
LEFT JOIN tournament_weather tw ON te.edition_id = tw.edition_id
LEFT JOIN player_ratings rw ON m.match_id = rw.match_id AND rw.player_id = m.winner_id
LEFT JOIN player_ratings rl ON m.match_id = rl.match_id AND rl.player_id = m.loser_id;

-- v_value_bets: aktywne value bety (najnowszy model)
CREATE OR REPLACE VIEW v_value_bets AS
SELECT
    p.pred_id,
    m.match_date,
    t.tourney_name,
    t.surface,
    pw.full_name AS player_a,
    pl.full_name AS player_b,
    p.prob_winner,
    p.pin_prob,
    p.market_edge,
    p.kelly_fraction,
    op.odds_winner AS pin_odds,
    p.model_version
FROM predictions p
JOIN matches m  ON p.match_id = m.match_id
JOIN tournament_editions te ON m.edition_id = te.edition_id
JOIN tournaments t          ON te.tournament_id = t.tournament_id
JOIN players pw ON m.winner_id = pw.player_id
JOIN players pl ON m.loser_id  = pl.player_id
LEFT JOIN odds op ON m.match_id = op.match_id AND op.bookmaker = 'pinnacle'
WHERE p.value_bet = TRUE
ORDER BY m.match_date DESC, p.market_edge DESC;

-- ============================================================
-- INDEXES dla typowych zapytań API
-- ============================================================
CREATE INDEX matches_date_range_idx ON matches USING brin(match_date);
CREATE INDEX weather_daily_range_idx ON weather_daily USING brin(obs_date);
CREATE INDEX predictions_date_idx ON predictions(predicted_at DESC);
