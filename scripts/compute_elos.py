"""
scripts/compute_elos.py — CLI tool to (re-)compute Elo ratings from TML-Database CSVs.

Usage
-----
python3 scripts/compute_elos.py [--source /path/to/csvs] [--output models/elo_ratings.joblib]

Defaults:
  --source  : auto-detected (checks TML-Database sibling dir, then $TML_DATABASE_PATH)
  --output  : models/elo_ratings.joblib  (relative to betatp project root)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# ── Ensure project root is on sys.path regardless of cwd ──────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent       # betatp/scripts/
_PROJECT_ROOT = _SCRIPT_DIR.parent                  # betatp/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import joblib
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_tml_source() -> Path | None:
    """Try to find the TML-Database directory automatically."""
    candidates = [
        _PROJECT_ROOT.parent / "TML-Database",
        _PROJECT_ROOT.parent / "tennis_atp",
        Path(os.environ.get("TML_DATABASE_PATH", "")),
    ]
    for c in candidates:
        if c and c.is_dir():
            return c
    return None


def _print_summary(elo_engine, n_matches: int) -> None:
    """Print a human-readable summary of the computed Elo ratings."""
    ratings: dict = {}

    # EloEngine stores ratings in .ratings dict keyed by player_id
    # Support both attribute names used in the project
    for attr in ("ratings", "_ratings", "elo_ratings"):
        if hasattr(elo_engine, attr):
            raw = getattr(elo_engine, attr)
            if isinstance(raw, dict):
                ratings = raw
                break

    n_players = len(ratings)

    print("\n" + "=" * 60)
    print("  ELO COMPUTATION SUMMARY")
    print("=" * 60)
    print(f"  Players processed  : {n_players:>8,}")
    print(f"  Matches processed  : {n_matches:>8,}")

    if ratings:
        # Build a sortable view — values may be floats, dicts, or objects
        def _extract_rating(v):
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, dict):
                return float(v.get("overall", v.get("elo", list(v.values())[0])))
            # Object with .overall or .elo attribute
            for attr_name in ("overall", "elo", "rating"):
                if hasattr(v, attr_name):
                    return float(getattr(v, attr_name))
            return 0.0

        sorted_players = sorted(ratings.items(), key=lambda kv: _extract_rating(kv[1]), reverse=True)
        top10 = sorted_players[:10]

        print("\n  TOP 10 ELO RATINGS")
        print("  " + "-" * 40)
        print(f"  {'Rank':<5} {'Player ID':<20} {'Elo':>8}")
        print("  " + "-" * 40)
        for rank, (pid, val) in enumerate(top10, start=1):
            elo_val = _extract_rating(val)
            print(f"  {rank:<5} {str(pid):<20} {elo_val:>8.1f}")

    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Main logic (also importable from tasks/daily_pipeline.py)
# ---------------------------------------------------------------------------

def run_compute_elos(source: str | None, output: str) -> dict:
    """
    Load CSVs, run compute_all_elos(), save to *output*.

    Returns
    -------
    dict with keys: n_players, n_matches, output_path
    """
    from data.loader import load_all_matches
    from engine.elo_runner import compute_all_elos
    from engine.elo import EloEngine

    # ── Resolve source directory ──────────────────────────────────────
    if source:
        tml_path = Path(source)
    else:
        tml_path = _detect_tml_source()

    if tml_path is None or not tml_path.is_dir():
        raise FileNotFoundError(
            f"TML-Database source directory not found. "
            f"Provide --source or set $TML_DATABASE_PATH. "
            f"Tried auto-detection; resolved to: {tml_path}"
        )

    logger.info("Loading matches from: %s", tml_path)
    matches_df: pd.DataFrame = load_all_matches(str(tml_path))
    n_matches = len(matches_df)
    logger.info("Loaded %d matches.", n_matches)

    # ── Run Elo engine ────────────────────────────────────────────────
    elo_engine = EloEngine()
    logger.info("Computing Elo ratings…")
    elo_engine = compute_all_elos(matches_df, elo_engine)

    # ── Determine player count ────────────────────────────────────────
    n_players = 0
    for attr in ("ratings", "_ratings", "elo_ratings"):
        if hasattr(elo_engine, attr):
            raw = getattr(elo_engine, attr)
            if isinstance(raw, dict):
                n_players = len(raw)
                break

    # ── Save ──────────────────────────────────────────────────────────
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(elo_engine, str(out_path))
    logger.info("Elo ratings saved to: %s", out_path)

    return {
        "n_players": n_players,
        "n_matches": n_matches,
        "output_path": str(out_path),
        "elo_engine": elo_engine,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="compute_elos",
        description=(
            "Compute Elo ratings for all ATP players from TML-Database CSV files "
            "and save the EloEngine object to a joblib file."
        ),
    )
    p.add_argument(
        "--source",
        metavar="DIR",
        default=None,
        help=(
            "Path to the TML-Database CSV directory. "
            "Defaults to auto-detection (sibling dir or $TML_DATABASE_PATH)."
        ),
    )
    p.add_argument(
        "--output",
        metavar="FILE",
        default=str(_PROJECT_ROOT / "models" / "elo_ratings.joblib"),
        help=(
            "Output path for the joblib file. "
            "Default: models/elo_ratings.joblib (relative to project root)."
        ),
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        result = run_compute_elos(source=args.source, output=args.output)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected error during Elo computation: %s", exc)
        sys.exit(2)

    _print_summary(result["elo_engine"], result["n_matches"])

    print(f"Output saved to: {result['output_path']}")


if __name__ == "__main__":
    main()
