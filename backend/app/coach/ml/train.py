"""Train and evaluate the learned marathon predictor. Reproducible: same data, same result.

    python -m app.coach.ml.train --data /path/to/run_ww_2019_d.parquet [more .parquet files]

Needs the training extras (``pip install -e ".[ml]"``) and the BMClab daily files
(run_ww_2019_d.parquet, run_ww_2020_d.parquet). The data isn't committed: it's large and
belongs to its authors. Steps:

1. Find marathons and their 8-week training features (``features.find_races``).
2. 5-fold cross-validation grouped by runner, so no runner is in both train and test, comparing
   on the same folds:
       Tanda         the published formula, no fitting
       Riegel        T = t × (42.195 / d)^1.06 from the fastest 10 km+ training day
       VDOT          Daniels from that same day
       Ridge         linear model on standardized features
       GBM           scikit-learn HistGradientBoostingRegressor
   and the coverage of a 10th–90th percentile range from two quantile GBMs.
3. Fit the best learned model on all races, save it with its metrics to ``model.joblib`` and
   ``metrics.json``, and write ``REPORT.md``. If no learned model beats the best baseline the
   report says so, and the app keeps using the formulas (``keep_baseline`` in the metrics).
"""

import argparse
import json
import math
from datetime import date
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.coach.ml.features import FEATURES, Day, find_races
from app.coach.predict import riegel, tanda_marathon_s
from app.coach.vdot import DISTANCES_M, race_time_s, vdot

HERE = Path(__file__).parent
SEED = 0
FOLDS = 5
MARATHON_M = DISTANCES_M["marathon"]


def load_races(paths: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    """(X, y minutes, runner groups, raw feature dicts) from BMClab daily parquet files."""
    import pandas as pd  # training-only dependency

    df = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    df = df[(df["distance"] > 0) & (df["duration"] > 0)]
    rows, y, groups = [], [], []
    for athlete, g in df.groupby("athlete", sort=True):
        male = str(g["gender"].iloc[0]).upper().startswith("M")
        days = [
            Day(ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10]), km, mins)
            for ts, km, mins in zip(g["datetime"], g["distance"], g["duration"], strict=True)
        ]
        days.sort(key=lambda d: d.day)
        for race, feats in find_races(days, male):
            rows.append(feats)
            y.append(race.minutes)
            groups.append(athlete)
    x = np.array([[r[f] for f in FEATURES] for r in rows], dtype=float)
    return x, np.array(y), np.array(groups), rows


def baselines(rows: list[dict]) -> dict[str, np.ndarray]:
    """Formula predictions in minutes (NaN where a formula has no input)."""
    tanda, rieg, vd = [], [], []
    for r in rows:
        tanda.append(tanda_marathon_s(r["weekly_km"], r["pace_s_per_km"]) / 60)
        if r["best_day_km"] and not math.isnan(r["best_pace_10k"]):
            d_m = r["best_day_km"] * 1000
            t_s = r["best_pace_10k"] * r["best_day_km"]
            rieg.append(riegel(t_s, d_m, MARATHON_M) / 60)
            vd.append(race_time_s(vdot(d_m, t_s), MARATHON_M) / 60)
        else:
            rieg.append(np.nan)
            vd.append(np.nan)
    return {"Tanda": np.array(tanda), "Riegel": np.array(rieg), "VDOT": np.array(vd)}


def models() -> dict:
    return {
        "Ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(1.0)),
        "GBM": HistGradientBoostingRegressor(random_state=SEED),
    }


def quantile_models() -> tuple:
    return (
        HistGradientBoostingRegressor(loss="quantile", quantile=0.1, random_state=SEED),
        HistGradientBoostingRegressor(loss="quantile", quantile=0.9, random_state=SEED),
    )


def cross_validate(x: np.ndarray, y: np.ndarray, groups: np.ndarray, rows: list[dict]) -> dict:
    preds = {name: np.full(len(y), np.nan) for name in models()}
    low, high = np.full(len(y), np.nan), np.full(len(y), np.nan)
    for train, test in GroupKFold(n_splits=FOLDS).split(x, y, groups):
        for name, model in models().items():
            preds[name][test] = model.fit(x[train], y[train]).predict(x[test])
        q10, q90 = quantile_models()
        low[test] = q10.fit(x[train], y[train]).predict(x[test])
        high[test] = q90.fit(x[train], y[train]).predict(x[test])
    preds |= baselines(rows)

    out = {}
    for name, p in preds.items():
        ok = ~np.isnan(p)
        out[name] = {
            "mae_min": float(np.mean(np.abs(p[ok] - y[ok]))),
            "median_ae_min": float(np.median(np.abs(p[ok] - y[ok]))),
            "n": int(ok.sum()),
        }
    # Compare every method on the races where all of them have a prediction, too.
    common = np.all([~np.isnan(p) for p in preds.values()], axis=0)
    for name, p in preds.items():
        out[name]["mae_min_common"] = float(np.mean(np.abs(p[common] - y[common])))
    out["range_80"] = {
        "coverage": float(np.mean((y >= low) & (y <= high))),
        "mean_width_min": float(np.mean(high - low)),
    }
    return out


def report(metrics: dict, n_races: int, n_runners: int) -> str:
    methods = [m for m in metrics["cv"] if m != "range_80"]
    lines = [
        "# Learned marathon predictor: evaluation",
        "",
        f"Data: BMClab long-distance running dataset, {n_races} marathons from {n_runners} "
        f"runners. {FOLDS}-fold cross-validation grouped by runner. Errors in minutes.",
        "",
        "| Method | MAE | Median abs. error | MAE on common races | Races |",
        "| --- | --- | --- | --- | --- |",
    ]
    for m in sorted(methods, key=lambda m: metrics["cv"][m]["mae_min_common"]):
        r = metrics["cv"][m]
        lines.append(
            f"| {m} | {r['mae_min']:.1f} | {r['median_ae_min']:.1f} | "
            f"{r['mae_min_common']:.1f} | {r['n']} |"
        )
    rng = metrics["cv"]["range_80"]
    lines += [
        "",
        f"10th–90th percentile range: covers {rng['coverage']:.0%} of real times "
        f"(target 80%), {rng['mean_width_min']:.0f} minutes wide on average.",
        "",
        f"Chosen: **{metrics['chosen']}**. "
        + (
            "No learned model beat the best formula, so the app keeps the formulas."
            if metrics["keep_baseline"]
            else f"It beats the best formula ({metrics['best_baseline']}) on the same races."
        ),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", nargs="+", required=True, help="BMClab *_d.parquet files")
    parser.add_argument("--out", default=str(HERE), help="where to write the model and report")
    args = parser.parse_args()

    x, y, groups, rows = load_races(args.data)
    cv = cross_validate(x, y, groups, rows)
    learned = min(models(), key=lambda m: cv[m]["mae_min_common"])
    best_baseline = min(("Tanda", "Riegel", "VDOT"), key=lambda m: cv[m]["mae_min_common"])
    keep_baseline = cv[learned]["mae_min_common"] >= cv[best_baseline]["mae_min_common"]
    metrics = {
        "cv": cv,
        "chosen": best_baseline if keep_baseline else learned,
        "best_baseline": best_baseline,
        "keep_baseline": keep_baseline,
        "features": FEATURES,
        "n_races": len(y),
        "n_runners": len(set(groups)),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not keep_baseline:
        q10, q90 = quantile_models()
        joblib.dump(
            {
                "model": models()[learned].fit(x, y),
                "q10": q10.fit(x, y),
                "q90": q90.fit(x, y),
                "features": FEATURES,
                "name": learned,
            },
            out / "model.joblib",
            compress=3,
        )
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (out / "REPORT.md").write_text(report(metrics, len(y), len(set(groups))))
    print((out / "REPORT.md").read_text())


if __name__ == "__main__":
    main()
