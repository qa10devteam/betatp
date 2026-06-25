"""
betatp.io — fetch_weather.py
Pobiera historyczne dane pogodowe dla wszystkich ATP turniejów 2013-2026
Źródło: Open-Meteo Archive API (darmowe, bez klucza)
Output: /home/ubuntu/betatp/data/weather_raw.parquet
        /home/ubuntu/betatp/data/weather_features.parquet (per mecz)
"""
import sys, time, json, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import requests
from pathlib import Path
from datetime import datetime, timedelta

TML_PATH = Path("/home/ubuntu/TML-Database")
OUT_PATH = Path("/home/ubuntu/betatp/data")
OUT_PATH.mkdir(exist_ok=True)

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─── 1. GEOCODING TABLE ───────────────────────────────────────────────────────
# Współrzędne dla wszystkich ATP turniejów (lat, lon, indoor flag)
GEOCODES = {
    "'s-Hertogenbosch":       (51.69,  5.30, False),
    "Acapulco":               (16.86,-99.88, False),
    "Adelaide":               (-34.93,138.60, False),
    "Adelaide-1":             (-34.93,138.60, False),
    "Adelaide-2":             (-34.93,138.60, False),
    "Almaty":                 (43.26, 76.94, False),
    "Antalya":                (36.90, 30.71, False),
    "Antwerp":                (51.22,  4.40, True),
    "Astana":                 (51.18, 71.45, True),
    "Athens":                 (37.98, 23.73, False),
    "Atlanta":                (33.75,-84.39, False),
    "Atp Cup":                (-33.87,151.21, False),
    "ATP Cup":                (-33.87,151.21, False),
    "ATP Finals":             (51.50, -0.12, True),
    "ATP Tour Finals":        (51.50, -0.12, True),
    "Tour Finals":            (51.50, -0.12, True),
    "Auckland":               (-36.85,174.76, False),
    "Australian Open":        (-37.82,144.98, False),
    "Bangkok":                (13.76,100.50, True),
    "Banja Luka":             (44.77, 17.19, False),
    "Barcelona":              (41.38,  2.18, False),
    "Basel":                  (47.56,  7.59, True),
    "Bastad":                 (56.43, 12.86, False),
    "Beijing":                (39.91,116.39, True),
    "Belgrade":               (44.82, 20.46, False),
    "Bogota":                 ( 4.71,-74.07, False),
    "Brisbane":               (-27.47,153.03, False),
    "Brussels":               (50.85,  4.35, True),
    "Bucharest":              (44.43, 26.10, False),
    "Budapest":               (47.50, 19.04, False),
    "Buenos Aires":           (-34.61,-58.38, False),
    "Cabo San Lucas":         (22.89,-109.91, False),
    "Los Cabos":              (22.89,-109.91, False),
    "Cagliari":               (39.22,  9.11, False),
    "Canada Masters":         (45.50,-73.57, False),  # Montreal/Toronto alternating
    "Casablanca":             (33.59, -7.62, False),
    "Chengdu":                (30.66,104.07, True),
    "Chennai":                (13.08, 80.27, False),
    "Cincinnati Masters":     (39.36,-84.52, False),
    "Cologne 1":              (50.94,  6.96, True),
    "Cologne 2":              (50.94,  6.96, True),
    "Cordoba":                (-31.42,-64.19, False),
    "Dallas":                 (32.78,-96.80, True),
    "Delray Beach":           (26.46,-80.07, False),
    "Doha":                   (25.29, 51.53, False),
    "Dubai":                  (25.20, 55.27, False),
    "Dusseldorf":             (51.23,  6.77, False),
    "Eastbourne":             (50.77,  0.29, False),
    "Estoril":                (38.71, -9.39, False),
    "Florence":               (43.77, 11.26, False),
    "Geneva":                 (46.20,  6.15, False),
    "Gijon":                  (43.54, -5.66, False),
    "Great Ocean Road Open":  (-37.82,144.98, False),
    "Murray River Open":      (-37.82,144.98, False),
    "Melbourne":              (-37.82,144.98, True),
    "Gstaad":                 (46.48,  7.28, False),
    "Halle":                  (51.98,  8.35, False),
    "Hamburg":                (53.55, 10.00, False),
    "Hangzhou":               (30.27,120.15, True),
    "Hong Kong":              (22.33,114.17, False),
    "Houston":                (29.76,-95.37, False),
    "Indian Wells Masters":   (33.72,-116.37, False),
    "Istanbul":               (41.01, 28.97, False),
    "Kitzbuhel":              (47.45, 12.39, False),
    "Kuala Lumpur":           ( 3.14,101.69, True),
    "Lyon":                   (45.75,  4.84, True),
    "Madrid Masters":         (40.42, -3.70, True),
    "Mallorca":               (39.57,  2.65, False),
    "Marbella":               (36.51, -4.88, False),
    "Marrakech":              (31.63, -8.00, False),
    "Marseille":              (43.30,  5.38, True),
    "Memphis":                (35.15,-90.05, True),
    "Metz":                   (49.12,  6.18, True),
    "Miami Masters":          (25.79,-80.13, False),
    "Monte Carlo Masters":    (43.74,  7.43, False),
    "Montpellier":            (43.61,  3.88, True),
    "Moscow":                 (55.75, 37.62, True),
    "Munich":                 (48.14, 11.58, False),
    "Naples":                 (40.85, 14.27, True),
    "New York":               (40.71,-73.93, True),
    "New York Open":          (40.71,-73.93, True),
    "NextGen Finals":         (45.47,  9.19, True),
    "Next Gen ATP Finals":    (45.47,  9.19, True),
    "Next Gen Finals":        (45.47,  9.19, True),
    "Nice":                   (43.71,  7.26, False),
    "Newport":                (41.49,-71.31, False),
    "Nottingham":             (52.95, -1.15, False),
    "Nur-Sultan":             (51.18, 71.45, True),
    "Oeiras":                 (38.69, -9.30, False),
    "Paris Masters":          (48.84,  2.37, True),
    "Parma":                  (44.80, 10.33, False),
    "Pune":                   (18.52, 73.86, False),
    "Queen's Club":           (51.49, -0.21, False),
    "Quito":                  (-0.23,-78.52, False),
    "Rio De Janeiro":         (-22.91,-43.17, False),
    "Rio de Janeiro":         (-22.91,-43.17, False),
    "Roland Garros":          (48.85,  2.25, False),
    "Rome Masters":           (41.93, 12.47, False),
    "Rotterdam":              (51.92,  4.48, True),
    "San Diego":              (32.72,-117.15, False),
    "San Jose":               (37.34,-121.89, True),
    "Santiago":               (-33.45,-70.67, False),
    "Sao Paulo":              (-23.55,-46.63, False),
    "Sardinia":               (39.22,  9.11, False),
    "Seoul":                  (37.57,126.98, True),
    "Serbia":                 (44.82, 20.46, False),
    "Shanghai":               (31.22,121.46, True),
    "Shanghai Masters":       (31.22,121.46, True),
    "Shenzhen":               (22.54,114.06, True),
    "Singapore":              ( 1.35,103.82, True),
    "Sofia":                  (42.70, 23.32, True),
    "St. Petersburg":         (59.95, 30.32, True),
    "Stockholm":              (59.33, 18.07, True),
    "Stuttgart":              (48.78,  9.18, False),
    "Sydney":                 (-33.87,151.21, False),
    "Tel Aviv":               (32.07, 34.78, True),
    "Tokyo":                  (35.69,139.69, True),
    "US Open":                (40.75,-73.85, False),
    "Umag":                   (45.44, 13.52, False),
    "Valencia":               (39.47, -0.38, False),
    "Vienna":                 (48.21, 16.37, True),
    "Vina del Mar":           (-33.02,-71.55, False),
    "Washington":             (38.90,-77.04, False),
    "Wimbledon":              (51.43, -0.21, False),
    "Winston Salem":          (36.10,-80.24, False),
    "Winston-Salem":          (36.10,-80.24, False),
    "Zagreb":                 (45.81, 15.98, True),
    "Zhuhai":                 (22.27,113.57, True),
    # Olympics
    "Rio Olympics":           (-22.91,-43.17, False),
    "Tokyo Olympics":         (35.69,139.69, False),
    "Paris Olympics":         (48.85,  2.25, False),
    "Laver Cup":              (51.50, -0.12, True),
    "United Cup":             (-33.87,151.21, False),
}

# ─── 2. WCZYTAJ MECZE 2013-2026 ───────────────────────────────────────────────
log("=== ETAP 1: Wczytywanie meczów ATP 2013-2026 ===")
dfs = []
for f in sorted(TML_PATH.glob("[0-9]*.csv")):
    yr = int(f.stem)
    if yr < 2013: continue
    df = pd.read_csv(f, low_memory=False)
    df["year"] = yr
    dfs.append(df[["tourney_name","tourney_date","surface","year","tourney_level"]])

raw = pd.concat(dfs, ignore_index=True)
raw = raw[~raw["tourney_name"].str.contains(
    "Davis Cup|Laver Cup|Olympics|Next Gen|United Cup", case=False, na=False)]
raw["tourney_date"] = pd.to_datetime(raw["tourney_date"].astype(str),
                                      format="%Y%m%d", errors="coerce")
raw = raw.dropna(subset=["tourney_date"])

# Per turniej-rok: zakres dat (date_start, date_end)
tours = (raw.groupby(["tourney_name","year"])
    .agg(date_min=("tourney_date","min"), date_max=("tourney_date","max"))
    .reset_index())
tours["date_end"] = tours["date_max"] + pd.Timedelta(days=1)

# Dodaj geocoding
tours["geo"] = tours["tourney_name"].map(GEOCODES)
missing_geo = tours[tours["geo"].isna()]["tourney_name"].unique()
if len(missing_geo):
    log(f"  BRAK GEOCODES dla: {list(missing_geo)}")

tours = tours[tours["geo"].notna()].copy()
tours["lat"]    = tours["geo"].apply(lambda x: x[0])
tours["lon"]    = tours["geo"].apply(lambda x: x[1])
tours["indoor"] = tours["geo"].apply(lambda x: x[2])

log(f"  Turnieje-lata: {len(tours):,} | geocoded: {tours['geo'].notna().sum()}")

# ─── 3. POBIERANIE DANYCH Z OPEN-METEO ARCHIVE API ───────────────────────────
log("\n=== ETAP 2: Pobieranie pogody z Open-Meteo Archive API ===")

WEATHER_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "windspeed_10m_max",
    "windgusts_10m_max",
    "relative_humidity_2m_max",
    "relative_humidity_2m_min",
    "shortwave_radiation_sum",    # nasłonecznienie
    "weathercode",                # WMO weather code (rain/snow/clear)
]

CACHE_FILE = OUT_PATH / "weather_raw_cache.json"
if CACHE_FILE.exists():
    with open(CACHE_FILE) as f:
        cache = json.load(f)
    log(f"  Cache: {len(cache)} wpisów")
else:
    cache = {}

def fetch_weather(lat, lon, start_date, end_date, retries=3):
    """Pobiera pogodę z Open-Meteo Archive API"""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": str(start_date)[:10],
        "end_date": str(end_date)[:10],
        "daily": ",".join(WEATHER_VARS),
        "timezone": "auto",
    }
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < retries-1:
                time.sleep(2**attempt)
            else:
                return None

# Grupuj turnieje po lokalizacji żeby minimalizować requesty
tours_sorted = tours.sort_values(["lat","lon","year"]).reset_index(drop=True)
missed = 0
fetched = 0
skipped = 0

all_weather_rows = []

for i, row in tours_sorted.iterrows():
    name = row["tourney_name"]
    yr   = row["year"]
    lat  = round(float(row["lat"]), 2)
    lon  = round(float(row["lon"]), 2)
    d0   = row["date_min"].strftime("%Y-%m-%d")
    d1   = row["date_end"].strftime("%Y-%m-%d")
    key  = f"{lat}_{lon}_{d0}_{d1}"

    if row["indoor"]:
        skipped += 1
        # Indoor: wstaw NaN — pogoda nieistotna
        all_weather_rows.append({
            "tourney_name": name, "year": yr, "date": d0,
            "indoor": True, **{v: np.nan for v in WEATHER_VARS}
        })
        continue

    if key in cache:
        data = cache[key]
    else:
        data = fetch_weather(lat, lon, d0, d1)
        if data:
            cache[key] = data
            fetched += 1
            time.sleep(0.12)  # rate limit ~8 req/s
        else:
            missed += 1
            log(f"  FAIL: {name} {yr} ({lat},{lon})")
            continue

    if not data or "daily" not in data:
        continue

    daily = data["daily"]
    dates = daily.get("time", [])
    for j, d in enumerate(dates):
        wrow = {"tourney_name": name, "year": yr, "date": d, "indoor": False}
        for v in WEATHER_VARS:
            vals = daily.get(v, [])
            wrow[v] = vals[j] if j < len(vals) else np.nan
        all_weather_rows.append(wrow)

    if (i+1) % 50 == 0:
        log(f"  [{i+1}/{len(tours_sorted)}] fetched={fetched} cached={len(cache)} missed={missed}")
        # Zapisz cache co 50 requestów
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)

# Zapisz cache końcowy
with open(CACHE_FILE, "w") as f:
    json.dump(cache, f)

log(f"\n  Gotowe: fetched={fetched} | skipped_indoor={skipped} | missed={missed}")
log(f"  Cache: {len(cache)} lokalizacji")

df_weather = pd.DataFrame(all_weather_rows)
df_weather["date"] = pd.to_datetime(df_weather["date"])
log(f"  Wierszy pogody: {len(df_weather):,}")

# Zapisz surowe
df_weather.to_parquet(OUT_PATH / "weather_raw.parquet", index=False)
log(f"  Zapisano: weather_raw.parquet")

# ─── 4. AGREGACJA PER TURNIEJ-ROK → WEATHER FEATURES ─────────────────────────
log("\n=== ETAP 3: Budowanie weather features per turniej-rok ===")

def weather_features(grp):
    """Agreguje dane pogodowe turnieju do feature'ów ML"""
    d = {}
    # Temperatury
    d["temp_max_mean"]  = grp["temperature_2m_max"].mean()
    d["temp_min_mean"]  = grp["temperature_2m_min"].mean()
    d["temp_mean"]      = grp["temperature_2m_mean"].mean()
    d["temp_range"]     = d["temp_max_mean"] - d["temp_min_mean"]
    d["temp_extreme"]   = (grp["temperature_2m_max"] > 35).mean()   # % dni >35°C
    d["temp_cold"]      = (grp["temperature_2m_max"] < 15).mean()   # % dni <15°C

    # Opady
    d["rain_total"]     = grp["precipitation_sum"].sum()
    d["rain_days"]      = (grp["precipitation_sum"] > 0.5).sum()    # dni deszczowych
    d["rain_heavy"]     = (grp["precipitation_sum"] > 5).sum()       # dni ulewnych

    # Wiatr
    d["wind_max_mean"]  = grp["windspeed_10m_max"].mean()
    d["wind_gust_mean"] = grp["windgusts_10m_max"].mean()
    d["wind_strong"]    = (grp["windspeed_10m_max"] > 30).mean()     # % dni >30 km/h

    # Wilgotność
    d["humidity_mean"]  = grp["relative_humidity_2m_max"].mean()
    d["humidity_high"]  = (grp["relative_humidity_2m_max"] > 80).mean()  # % dni >80%

    # Nasłonecznienie
    d["solar_mean"]     = grp["shortwave_radiation_sum"].mean()

    # Weather code (WMO): 0-2=clear, 3=cloudy, 45-57=fog, 61-77=rain, 80-99=storm
    d["pct_clear"]      = (grp["weathercode"] <= 2).mean()
    d["pct_rain"]       = ((grp["weathercode"] >= 61) & (grp["weathercode"] <= 77)).mean()
    d["pct_storm"]      = (grp["weathercode"] >= 80).mean()

    # Composite: "trudne warunki" — hot + humid lub rain + wind
    d["harsh_conditions"] = (
        ((grp["temperature_2m_max"] > 32) & (grp["relative_humidity_2m_max"] > 70)) |
        ((grp["windspeed_10m_max"] > 25) & (grp["precipitation_sum"] > 1))
    ).mean()

    # Indoor flag
    d["indoor"] = grp["indoor"].any()
    return pd.Series(d)

wf = (df_weather.groupby(["tourney_name","year"])
      .apply(weather_features)
      .reset_index())

log(f"  Weather features: {wf.shape} | turnieje-lata: {len(wf)}")
wf.to_parquet(OUT_PATH / "weather_features.parquet", index=False)
log(f"  Zapisano: weather_features.parquet")

# ─── 5. MERGE Z MECZAMI TML ───────────────────────────────────────────────────
log("\n=== ETAP 4: Merge weather features z meczami TML ===")

dfs2 = []
for f in sorted(TML_PATH.glob("[0-9]*.csv")):
    yr = int(f.stem)
    if yr < 2013: continue
    df = pd.read_csv(f, low_memory=False)
    df["year"] = yr
    dfs2.append(df)

matches = pd.concat(dfs2, ignore_index=True)
matches = matches[~matches["tourney_name"].str.contains(
    "Davis Cup|Laver Cup|Olympics|Next Gen|United Cup", case=False, na=False)]

before = len(matches)
matches = matches.merge(wf, on=["tourney_name","year"], how="left")
after = matches[matches["temp_mean"].notna()].shape[0]
log(f"  Meczów: {before:,} | z weather features: {after:,} ({100*after/before:.1f}%)")

# Indoor: ustaw NaN dla pogody (bez wpływu)
# Nie usuwamy — model może nauczyć się indoor vs outdoor
matches["indoor_flag"] = matches["indoor_x"].fillna(matches.get("indoor_y", False)).fillna(False) if "indoor_x" in matches.columns else matches.get("indoor", pd.Series(False, index=matches.index)).fillna(False)

matches.to_parquet(OUT_PATH / "matches_with_weather.parquet", index=False)
log(f"  Zapisano: matches_with_weather.parquet")

# ─── 6. STATYSTYKI ────────────────────────────────────────────────────────────
log("\n=== ETAP 5: Statystyki ===")
log(f"\n  TOP-10 najgorętszych turniejów (avg max temp):")
hot = wf.groupby("tourney_name")["temp_max_mean"].mean().sort_values(ascending=False).head(10)
for t, v in hot.items():
    log(f"    {t:30s}: {v:.1f}°C")

log(f"\n  TOP-10 najbardziej deszczowych:")
wet = wf.groupby("tourney_name")["rain_total"].mean().sort_values(ascending=False).head(10)
for t, v in wet.items():
    log(f"    {t:30s}: {v:.1f} mm/turniej")

log(f"\n  TOP-10 najbardziej wietrznych:")
windy = wf.groupby("tourney_name")["wind_max_mean"].mean().sort_values(ascending=False).head(10)
for t, v in windy.items():
    log(f"    {t:30s}: {v:.1f} km/h")

log("\n" + "="*60)
log("DONE | weather_raw.parquet + weather_features.parquet + matches_with_weather.parquet")
log("="*60)
