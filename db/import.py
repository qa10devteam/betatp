"""
betatp.io — PostgreSQL full import
===================================
Ładuje dane z parquet/CSV do relacyjnej bazy:
  1. Players      → players
  2. Tournaments  → tournaments + tournament_editions
  3. Matches      → matches
  4. Odds         → odds (pinnacle/bet365/max/avg)
  5. Weather      → weather_stations + weather_daily + tournament_weather
  6. Verify       → row counts + sample queries

Uruchomienie:
  PYTHONPATH=/home/ubuntu/betatp python db/import.py
"""
import sys, warnings, time
sys.path.insert(0, "/home/ubuntu/betatp")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DB_DSN   = "host=localhost dbname=betatp user=postgres password=betatp2024"
TML_PATH = Path("/home/ubuntu/TML-Database")
ODDS_PAR = Path("/home/ubuntu/betatp/data/matches_with_odds.parquet")
WRAW_PAR = Path("/home/ubuntu/betatp/data/weather_raw.parquet")
WFEAT_PAR= Path("/home/ubuntu/betatp/data/weather_features.parquet")

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

conn = psycopg2.connect(DB_DSN)
conn.autocommit = False
cur = conn.cursor()
log("✓ Połączono z betatp (PostgreSQL)")

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def upsert(table, rows, conflict_col, returning=None):
    if not rows: return []
    cols = list(rows[0].keys())
    vals = [[r.get(c) for c in cols] for r in rows]
    col_str = ", ".join(cols)
    set_str = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != conflict_col)
    ret_str = f"RETURNING {returning}" if returning else ""
    sql = f"""
        INSERT INTO {table} ({col_str}) VALUES %s
        ON CONFLICT ({conflict_col}) DO UPDATE SET {set_str}
        {ret_str}
    """
    execute_values(cur, sql, vals)
    if returning:
        return [r[0] for r in cur.fetchall()]
    return []

def safe(v, typ=None):
    if v is None: return None
    if isinstance(v, float) and np.isnan(v): return None
    if typ == "int":
        try: return int(v)
        except: return None
    if typ == "float":
        try: return float(v)
        except: return None
    if typ == "str":
        s = str(v).strip()
        return s if s and s.lower() not in ("nan","none","") else None
    return v

# ─── 1. PLAYERS ───────────────────────────────────────────────────────────────
log("\n=== ETAP 1: Players ===")

all_players = {}  # tml_id -> dict
for f in sorted(TML_PATH.glob("[0-9]*.csv")):
    df = pd.read_csv(f, low_memory=False)
    for role in [("winner","w"), ("loser","l")]:
        pref, _ = role
        for _, row in df.iterrows():
            pid = safe(row.get(f"{pref}_id"), "str")
            if not pid: continue
            if pid not in all_players:
                all_players[pid] = {
                    "tml_id":    pid,
                    "full_name": safe(row.get(f"{pref}_name"), "str") or pid,
                    "hand":      safe(row.get(f"{pref}_hand"), "str"),
                    "country_code": safe(row.get(f"{pref}_ioc"), "str"),
                    "height_cm":    safe(row.get(f"{pref}_ht"), "int"),
                    "birth_date":   None,
                    "turned_pro":   None,
                }

player_rows = []
for pid, p in all_players.items():
    hand = p["hand"]
    if hand not in ("R","L","U") or not hand:
        hand = "U"
    player_rows.append({
        "tml_id":       p["tml_id"],
        "full_name":    p["full_name"][:200],
        "hand":         hand,
        "country_code": (p["country_code"] or "")[:3] or None,
        "height_cm":    p["height_cm"],
    })

upsert("players", player_rows, "tml_id")
conn.commit()
cur.execute("SELECT COUNT(*) FROM players")
log(f"  Players: {cur.fetchone()[0]:,}")

# Buduj mapę tml_id → player_id
cur.execute("SELECT player_id, tml_id FROM players")
pid_map = {row[1]: row[0] for row in cur.fetchall()}

# ─── 2. TOURNAMENTS + EDITIONS ────────────────────────────────────────────────
log("\n=== ETAP 2: Tournaments + Editions ===")

SURF_MAP  = {"Hard":"Hard","Clay":"Clay","Grass":"Grass","Carpet":"Hard","Indoor Hard":"Hard","Acrylic":"Hard"}
LEVEL_MAP = {"G":"G","M":"M","A":"500","D":"250","F":"F","C":"250","S":"500",
             "250":"250","500":"500","1000":"M","2000":"M","ATP250":"250","ATP500":"500"}
INDOOR_SURFACES = {"carpet","indoor hard"}

# GPS koordinaty turniejów (z fetch_weather.py)
TOUR_GEO = {
    "Australian Open": (-37.8214, 144.9781, "Melbourne", "AUS", 31),
    "Roland Garros": (48.8472, 2.2481, "Paris", "FRA", 35),
    "Wimbledon": (51.4334, -0.2138, "London", "GBR", 5),
    "US Open": (40.6969, -73.8517, "New York", "USA", 10),
    "ATP Finals": (51.5074, -0.1278, "London", "GBR", 5),
    "Monte-Carlo Masters": (43.7392, 7.4246, "Monte-Carlo", "MCO", 10),
    "Madrid Open": (40.4168, -3.7038, "Madrid", "ESP", 667),
    "Italian Open": (41.9028, 12.4964, "Rome", "ITA", 14),
    "Canada Masters": (45.5017, -73.5673, "Montreal", "CAN", 20),
    "Cincinnati Masters": (39.1031, -84.5120, "Cincinnati", "USA", 270),
    "Miami Open": (25.6601, -80.2439, "Miami", "USA", 1),
    "Indian Wells Masters": (33.7430, -116.3745, "Indian Wells", "USA", 420),
    "Shanghai Masters": (31.2304, 121.4737, "Shanghai", "CHN", 5),
    "Paris Masters": (48.8395, 2.3791, "Paris", "FRA", 35),
    "Vienna Open": (48.2082, 16.3738, "Vienna", "AUT", 170),
    "Basel Indoors": (47.5596, 7.5886, "Basel", "CHE", 260),
    "Marseille Open": (43.2965, 5.3698, "Marseille", "FRA", 5),
    "Rotterdam Open": (51.9225, 4.4792, "Rotterdam", "NLD", -1),
    "Dubai Tennis Championships": (25.2048, 55.2708, "Dubai", "UAE", 5),
    "Mexican Open": (16.8531, -99.8237, "Acapulco", "MEX", 1),
    "Rio Open": (-22.9068, -43.1729, "Rio de Janeiro", "BRA", 11),
    "Open 13": (43.2965, 5.3698, "Marseille", "FRA", 5),
}

seen_tourneys = {}  # name -> tournament_id
seen_editions = {}  # (tournament_id, year) -> edition_id

# Wczytaj wszystkie TML
dfs_all = []
for f in sorted(TML_PATH.glob("[0-9]*.csv")):
    yr = int(f.stem)
    df = pd.read_csv(f, low_memory=False); df["year"] = yr
    dfs_all.append(df)
raw_all = pd.concat(dfs_all, ignore_index=True)
raw_all["tourney_date"] = pd.to_datetime(raw_all["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
raw_all = raw_all.dropna(subset=["tourney_date"])
raw_all["surface_norm"] = raw_all["surface"].map(SURF_MAP).fillna("Hard")
raw_all["level_norm"]   = raw_all["tourney_level"].map(LEVEL_MAP).fillna("250")
raw_all["indoor_flag"]  = raw_all["surface"].str.lower().isin(INDOOR_SURFACES)

for tname, grp in raw_all.groupby("tourney_name"):
    tname_s = str(tname).strip()
    slug    = tname_s.lower().replace(" ","_").replace("-","_").replace("'","").replace(".","")[:80]
    surf    = grp["surface_norm"].mode()[0] if len(grp) else "Hard"
    level   = grp["level_norm"].mode()[0] if len(grp) else "250"
    indoor  = bool(grp["indoor_flag"].mode()[0]) if len(grp) else False

    geo = TOUR_GEO.get(tname_s)
    lat, lon, city, ctry, elev = (geo[0], geo[1], geo[2], geo[3], geo[4]) if geo else (None, None, None, None, None)

    cur.execute("""
        INSERT INTO tournaments (tourney_name, tourney_slug, surface, level, indoor, city, country_code, lat, lon, elevation_m)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tourney_slug) DO UPDATE SET surface=EXCLUDED.surface
        RETURNING tournament_id
    """, (tname_s, slug, surf, level, indoor, city, ctry, lat, lon, elev))
    tid = cur.fetchone()[0]
    seen_tourneys[tname_s] = tid

    for (yr,), edf in grp.groupby(["year"]):
        first_date = edf["tourney_date"].min().date()
        draw_size  = safe(edf["draw_size"].iloc[0], "int") if "draw_size" in edf else None
        e_surf     = safe(edf["surface_norm"].mode()[0], "str") if len(edf) else surf
        cur.execute("""
            INSERT INTO tournament_editions (tournament_id, year, tourney_date, draw_size, surface)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (tournament_id, year) DO UPDATE SET tourney_date=EXCLUDED.tourney_date
            RETURNING edition_id
        """, (tid, int(yr), first_date, draw_size, e_surf))
        eid = cur.fetchone()[0]
        seen_editions[(tid, int(yr))] = eid

conn.commit()
cur.execute("SELECT COUNT(*) FROM tournaments"); log(f"  Tournaments: {cur.fetchone()[0]:,}")
cur.execute("SELECT COUNT(*) FROM tournament_editions"); log(f"  Editions: {cur.fetchone()[0]:,}")

# ─── 3. MATCHES ───────────────────────────────────────────────────────────────
log("\n=== ETAP 3: Matches ===")
ROUND_MAP = {
    "R128":"R128","R64":"R64","R32":"R32","R16":"R16",
    "QF":"QF","SF":"SF","F":"F","RR":"RR","BR":"BR",
    "1st Round":"R64","2nd Round":"R32","3rd Round":"R16",
    "4th Round":"R128","Quarterfinals":"QF","Semifinals":"SF","Final":"F",
}

match_batch = []
tml_to_mid  = {}  # tml rowkey → match_id

for f in sorted(TML_PATH.glob("[0-9]*.csv")):
    yr = int(f.stem)
    df = pd.read_csv(f, low_memory=False)
    df["tourney_date"] = pd.to_datetime(df["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
    df["surface_norm"] = df["surface"].map(SURF_MAP).fillna("Hard")
    df["level_norm"]   = df["tourney_level"].map(LEVEL_MAP).fillna("250")

    for _, row in df.iterrows():
        wid = safe(row.get("winner_id"), "str")
        lid = safe(row.get("loser_id"), "str")
        if not wid or not lid: continue
        if wid not in pid_map or lid not in pid_map: continue

        tname = str(row.get("tourney_name","")).strip()
        tid   = seen_tourneys.get(tname)
        if not tid: continue
        eid   = seen_editions.get((tid, yr))
        if not eid: continue

        tdate = row["tourney_date"]
        mdate = tdate.date() if pd.notna(tdate) else None

        rnd_raw = str(row.get("round","")).strip()
        rnd     = ROUND_MAP.get(rnd_raw, rnd_raw[:10] if rnd_raw else None)

        tml_key = f"{yr}_{safe(row.get('match_num'),'str')}_{tname}"

        def si(col): return safe(row.get(col), "int")
        def sf(col): return safe(row.get(col), "float")

        cur.execute("""
            INSERT INTO matches (
                edition_id, match_date, round, best_of,
                winner_id, loser_id, score,
                w_rank, l_rank, w_rank_pts, l_rank_pts,
                w_ace, w_df, w_svpt, w_1stin, w_1stwon, w_2ndwon, w_svgms, w_bpsaved, w_bpfaced,
                l_ace, l_df, l_svpt, l_1stin, l_1stwon, l_2ndwon, l_svgms, l_bpsaved, l_bpfaced,
                minutes, retired, walkover, tml_id
            ) VALUES (
                %s,%s,%s,%s, %s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s
            )
            ON CONFLICT (tml_id) WHERE tml_id IS NOT NULL DO NOTHING
            RETURNING match_id
        """, (
            eid, mdate, rnd, si("best_of"),
            pid_map[wid], pid_map[lid], safe(row.get("score"),"str"),
            si("winner_rank"), si("loser_rank"), si("winner_rank_points"), si("loser_rank_points"),
            si("w_ace"), si("w_df"), si("w_svpt"), si("w_1stIn"), si("w_1stWon"), si("w_2ndWon"), si("w_SvGms"), si("w_bpSaved"), si("w_bpFaced"),
            si("l_ace"), si("l_df"), si("l_svpt"), si("l_1stIn"), si("l_1stWon"), si("l_2ndWon"), si("l_SvGms"), si("l_bpSaved"), si("l_bpFaced"),
            si("minutes"),
            bool(str(row.get("score","")).upper().find("RET") >= 0),
            bool(str(row.get("score","")).upper().find("W/O") >= 0),
            tml_key,
        ))
        res = cur.fetchone()
        if res:
            tml_to_mid[tml_key] = res[0]

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM matches")
    cnt = cur.fetchone()[0]
    if yr % 5 == 0:
        log(f"  {yr}: matches={cnt:,}")

cur.execute("SELECT COUNT(*) FROM matches")
log(f"  TOTAL Matches: {cur.fetchone()[0]:,}")

# ─── 4. ODDS ──────────────────────────────────────────────────────────────────
log("\n=== ETAP 4: Odds ===")

odds_df = pd.read_parquet(ODDS_PAR)

# Potrzebujemy match_id — matchujemy przez edition_id + winner_last + loser_last + round
cur.execute("""
    SELECT m.match_id, te.year,
           p1.full_name AS w_name, p2.full_name AS l_name,
           m.round, te.tournament_id
    FROM matches m
    JOIN tournament_editions te ON m.edition_id = te.edition_id
    JOIN players p1 ON m.winner_id = p1.player_id
    JOIN players p2 ON m.loser_id  = p2.player_id
    WHERE te.year >= 2002
""")
match_lookup = {}
for mid, yr, wname, lname, rnd, tid in cur.fetchall():
    # last name (last word of full_name)
    wl = str(wname).split()[-1].lower().replace("-","").replace("'","")
    ll = str(lname).split()[-1].lower().replace("-","").replace("'","")
    match_lookup[(yr, wl, ll, rnd)] = mid

def last_tml(name):
    return str(name).strip().split(" ")[-1].lower().replace("-","").replace("'","")

RND_NORM = {"1st Round":"R64","2nd Round":"R32","3rd Round":"R16","4th Round":"R128",
            "Quarterfinals":"QF","Semifinals":"SF","Final":"F",
            "R128":"R128","R64":"R64","R32":"R32","R16":"R16","QF":"QF","SF":"SF","F":"F","RR":"RR"}

BOOKMAKERS = {
    "pinnacle": ("PSW","PSL","pin_prob_w","pin_prob_l"),
    "bet365":   ("B365W","B365L","b365_prob_w","b365_prob_l"),
    "max":      ("MaxW","MaxL","max_prob_w","max_prob_w"),
    "avg":      ("AvgW","AvgL","avg_prob_w","avg_prob_l"),
}

odds_batch = []
matched = 0
for _, row in odds_df.iterrows():
    yr  = safe(row.get("year"), "int")
    wl  = last_tml(row.get("wl",""))
    ll  = last_tml(row.get("ll",""))
    rnd = RND_NORM.get(str(row.get("rnd","")), str(row.get("rnd","")))

    mid = match_lookup.get((yr, wl, ll, rnd))
    if not mid: continue
    matched += 1

    for bk, (ow_col, ol_col, pw_col, pl_col) in BOOKMAKERS.items():
        ow = safe(row.get(ow_col), "float")
        ol = safe(row.get(ol_col), "float")
        pw = safe(row.get(pw_col), "float")
        pl = safe(row.get(pl_col), "float")
        if ow is None and pw is None: continue

        margin = None
        if ow and ol and ow > 1 and ol > 1:
            margin = round(1/ow + 1/ol - 1, 5)
        log_odds = None
        if pw and pw > 0 and pw < 1:
            log_odds = round(np.log(pw / (1-pw+1e-9)), 5)

        odds_batch.append({
            "match_id":  mid,
            "bookmaker": bk,
            "odds_winner": ow,
            "odds_loser":  ol,
            "prob_winner": pw,
            "prob_loser":  pl,
            "margin":      margin,
            "log_odds":    log_odds,
        })

if odds_batch:
    execute_values(cur, """
        INSERT INTO odds (match_id, bookmaker, odds_winner, odds_loser, prob_winner, prob_loser, margin, log_odds)
        VALUES %s ON CONFLICT (match_id, bookmaker) DO NOTHING
    """, [[r["match_id"],r["bookmaker"],r["odds_winner"],r["odds_loser"],
           r["prob_winner"],r["prob_loser"],r["margin"],r["log_odds"]] for r in odds_batch])
conn.commit()
cur.execute("SELECT COUNT(*) FROM odds"); log(f"  Odds: {cur.fetchone()[0]:,} (matched {matched:,} meczów)")

# ─── 5. WEATHER ───────────────────────────────────────────────────────────────
log("\n=== ETAP 5: Weather ===")

# Wczytaj weather_raw i weather_features
wraw  = pd.read_parquet(WRAW_PAR)
wfeat = pd.read_parquet(WFEAT_PAR)

# Rejestruj stacje (Open-Meteo = grid point per turniej)
def norm_name(n): return str(n).strip().lower().replace("-"," ").replace("_"," ")

station_rows = []
for _, row in wraw.groupby("tourney_name").first().reset_index().iterrows():
    tname = str(row["tourney_name"]).strip()
    slug  = norm_name(tname).replace(" ","_")[:50]
    geo   = TOUR_GEO.get(tname)
    lat, lon, city, ctry, elev = (geo[0],geo[1],geo[2],geo[3],geo[4]) if geo else (None,None,None,None,None)
    station_rows.append({
        "station_id":   f"OPENMETEO_{slug}",
        "source":       "OPENMETEO_ERA5",
        "name":         tname,
        "country_code": (ctry or "")[:3] or None,
        "lat":          lat,
        "lon":          lon,
        "elevation_m":  elev,
    })

execute_values(cur, """
    INSERT INTO weather_stations (station_id, source, name, country_code, lat, lon, elevation_m)
    VALUES %s ON CONFLICT (station_id) DO NOTHING
""", [[r["station_id"],r["source"],r["name"],r["country_code"],r["lat"],r["lon"],r["elevation_m"]] for r in station_rows])
conn.commit()
cur.execute("SELECT COUNT(*) FROM weather_stations"); log(f"  Stations: {cur.fetchone()[0]:,}")

# Załaduj weather_daily
daily_rows = []
for _, row in wraw.iterrows():
    tname = str(row["tourney_name"]).strip()
    slug  = norm_name(tname).replace(" ","_")[:50]
    sid   = f"OPENMETEO_{slug}"
    obs_date = pd.to_datetime(row["date"]).date() if pd.notna(row.get("date")) else None
    if not obs_date: continue

    def sg(col): return safe(row.get(col), "float")
    daily_rows.append((
        sid, obs_date, "OPENMETEO_ERA5",
        sg("temperature_2m_mean"), sg("temperature_2m_max"), sg("temperature_2m_min"),
        sg("precipitation_sum"), None,
        sg("windspeed_10m_max"), None, sg("windgusts_10m_max"),
        sg("relative_humidity_2m_max"), sg("relative_humidity_2m_max"), None,
        None, sg("shortwave_radiation_sum"), None, safe(row.get("weathercode"),"int"),
    ))

execute_values(cur, """
    INSERT INTO weather_daily (
        station_id, obs_date, source,
        temp_mean, temp_max, temp_min,
        precip_mm, snow_mm,
        wind_max_kmh, wind_mean_kmh, wind_gust_kmh,
        humidity_max, humidity_mean, pressure_hpa,
        cloud_cover_pct, solar_mj, visibility_km, weather_code
    ) VALUES %s ON CONFLICT (station_id, obs_date, source) DO NOTHING
""", daily_rows)
conn.commit()
cur.execute("SELECT COUNT(*) FROM weather_daily"); log(f"  Weather daily: {cur.fetchone()[0]:,}")

# Załaduj tournament_weather
wfeat["_tname"] = wfeat["tourney_name"].apply(norm_name)
tw_rows = []
for _, row in wfeat.iterrows():
    tname = str(row["tourney_name"]).strip()
    yr    = safe(row.get("year"), "int")
    if not yr: continue

    slug = norm_name(tname).replace(" ","_")[:80]
    tid  = seen_tourneys.get(tname)
    if not tid: continue
    eid  = seen_editions.get((tid, yr))
    if not eid: continue

    def fg(col): return safe(row.get(col), "float")
    def ig(col): return safe(row.get(col), "int")

    tw_rows.append((
        eid, f"OPENMETEO_{slug[:50]}", "OPENMETEO_ERA5",
        None, None,
        fg("temp_mean"), fg("temp_max_mean"), fg("temp_min_mean"), fg("temp_range"),
        fg("temp_extreme"), fg("temp_cold"),
        fg("rain_total"), ig("rain_days"), ig("rain_heavy"),
        fg("wind_max_mean"), None, ig("wind_strong"),
        fg("humidity_mean"), None,
        fg("solar_mean"), None,
        fg("pct_clear"), None, fg("pct_rain"), fg("pct_storm"),
        fg("harsh_conditions"), None,
    ))

execute_values(cur, """
    INSERT INTO tournament_weather (
        edition_id, station_id, source,
        n_days, n_outdoor_days,
        temp_mean, temp_max_mean, temp_min_mean, temp_range_mean,
        temp_extreme_hot, temp_extreme_cold,
        rain_total_mm, rain_days, rain_heavy_days,
        wind_max_kmh, wind_mean_kmh, wind_strong_days,
        humidity_mean, pressure_mean,
        solar_total_mj, cloud_cover_mean,
        pct_clear, pct_overcast, pct_rain, pct_storm,
        harsh_conditions, heat_index_mean
    ) VALUES %s ON CONFLICT (edition_id, source) DO NOTHING
""", tw_rows)
conn.commit()
cur.execute("SELECT COUNT(*) FROM tournament_weather"); log(f"  Tournament weather: {cur.fetchone()[0]:,}")

# ─── 6. VERIFY ────────────────────────────────────────────────────────────────
log("\n=== ETAP 6: Weryfikacja ===")
tables = ["players","tournaments","tournament_editions","matches","odds",
          "weather_stations","weather_daily","tournament_weather"]
for tbl in tables:
    cur.execute(f"SELECT COUNT(*) FROM {tbl}")
    log(f"  {tbl:30s}: {cur.fetchone()[0]:>8,}")

log("\n  Sample: najgorętsze turnieje z kursami Pinnacle:")
cur.execute("""
    SELECT t.tourney_name, te.year,
           tw.temp_max_mean, tw.rain_total_mm, tw.wind_max_kmh,
           COUNT(o.odds_id) as n_odds
    FROM tournament_weather tw
    JOIN tournament_editions te ON tw.edition_id = te.edition_id
    JOIN tournaments t ON te.tournament_id = t.tournament_id
    LEFT JOIN matches m ON m.edition_id = te.edition_id
    LEFT JOIN odds o ON o.match_id = m.match_id AND o.bookmaker='pinnacle'
    GROUP BY t.tourney_name, te.year, tw.temp_max_mean, tw.rain_total_mm, tw.wind_max_kmh
    HAVING tw.temp_max_mean > 30
    ORDER BY tw.temp_max_mean DESC
    LIMIT 10
""")
for row in cur.fetchall():
    log(f"  {row[0]:25s} {row[1]}  temp={row[2]:.1f}°C  rain={row[3]:.0f}mm  wind={row[4]:.0f}kmh  odds={row[5]}")

log("\n  Sample: mecze z wartością pogodową (Roland Garros 2024):")
cur.execute("""
    SELECT pw.full_name, pl.full_name, m.round,
           o.prob_winner, tw.temp_mean, tw.rain_days
    FROM matches m
    JOIN tournament_editions te ON m.edition_id = te.edition_id
    JOIN tournaments t ON te.tournament_id = t.tournament_id
    JOIN players pw ON m.winner_id = pw.player_id
    JOIN players pl ON m.loser_id = pl.player_id
    LEFT JOIN odds o ON o.match_id = m.match_id AND o.bookmaker='pinnacle'
    LEFT JOIN tournament_weather tw ON tw.edition_id = te.edition_id
    WHERE t.tourney_name ILIKE '%roland%' AND te.year = 2024
    LIMIT 5
""")
for row in cur.fetchall():
    log(f"  {row[0]} def. {row[1]} [{row[2]}] pin={row[3]} temp={row[4]}°C rain_days={row[5]}")

cur.close()
conn.close()

log("\n" + "="*60)
log("IMPORT DONE — PostgreSQL betatp gotowy!")
log("="*60)
