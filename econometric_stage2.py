# -*- coding: utf-8 -*-
"""Econometric analysis for the 600-post fixed-window stage-2 sample."""
from __future__ import annotations

import argparse
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.stats import norm
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold


HERE = Path(__file__).resolve().parent
DATA = HERE / "stage2_analysis.csv"
PILOT = HERE / "stata_ads2.csv"
OUT = HERE / "econometric_stage2_results.csv"
GROUP_OUT = HERE / "stage2_group_counts.csv"
POWER_OUT = HERE / "stage2_power_design.csv"

CORE = (
    "log_followers + hist_prior + has_prior_hist + text_len_100 + text_len_100_sq + "
    "n_images + is_video + is_lottery + hard_ad + promo_density_100 + "
    "brand_density_100 + has_ext_link + log_age_hours_24h"
)
CONTROLS = "C(industry) + C(account_type) + C(pub_dow) + C(source_group)"
MAIN = CORE + " + " + CONTROLS


def prepare() -> pd.DataFrame:
    d = pd.read_csv(DATA, dtype={"post_id": str, "author_id": str}, na_values=["", "."])
    required = {
        "reposts_24h", "positive_repost_24h", "ln_repost_24h", "author_id",
        "log_followers", "hist_prior_avg_lnengage", "text_len_100", "n_images",
        "is_video", "is_lottery", "hard_ad", "industry", "account_type",
        "appeal_family", "log_age_hours_24h",
    }
    missing = sorted(required - set(d.columns))
    if missing:
        raise ValueError("Missing stage-2 variables: " + ", ".join(missing))
    d["has_prior_hist"] = d["hist_prior_avg_lnengage"].notna().astype(int)
    d["hist_prior"] = d["hist_prior_avg_lnengage"].fillna(0.0)
    if d["post_id"].duplicated().any():
        raise ValueError("stage2_analysis.csv contains duplicate post_id values")
    if (d["age_hours_24h"] < 22).any() or (d["age_hours_24h"] > 26).any():
        raise ValueError("Main sample contains snapshots outside T+24h tolerance")
    return d


def covariance(d: pd.DataFrame) -> tuple[str, dict, str]:
    counts = d.groupby("author_id").size()
    repeated_share = d["author_id"].map(counts).ge(2).mean()
    repeated_authors = int((counts >= 2).sum())
    if repeated_authors >= 30 and repeated_share >= 0.30:
        return "cluster", {"groups": d["author_id"]}, "author_cluster"
    return "HC3", {}, "HC3"


def fit_ols(formula: str, data: pd.DataFrame):
    cov, kwargs, label = covariance(data)
    return smf.ols(formula, data=data).fit(cov_type=cov, cov_kwds=kwargs), label


def fit_glm(formula: str, data: pd.DataFrame, family):
    cov, kwargs, label = covariance(data)
    return smf.glm(formula, data=data, family=family).fit(
        cov_type=cov, cov_kwds=kwargs
    ), label


def result_rows(result, model: str, outcome: str, inference: str,
                fit_name: str, fit_value: float, exploratory=0) -> list[dict]:
    rows = []
    for term in result.params.index:
        rows.append({
            "model": model, "outcome": outcome, "term": term,
            "estimate": float(result.params[term]), "std_error": float(result.bse[term]),
            "p_value": float(result.pvalues[term]), "n": int(result.nobs),
            "inference": inference, "fit_stat": fit_name, "fit_value": fit_value,
            "exploratory": exploratory,
        })
    return rows


def wald_rows(result, model: str, outcome: str, inference: str,
              tests: dict[str, list[str]], n: int, exploratory: int) -> list[dict]:
    rows = []
    for label, terms in tests.items():
        present = [term for term in terms if term in result.params.index]
        if not present:
            continue
        restriction = ", ".join(term + " = 0" for term in present)
        test = result.wald_test(restriction, scalar=True)
        rows.append({
            "model": model, "outcome": outcome, "term": label,
            "estimate": float(test.statistic), "std_error": np.nan,
            "p_value": float(test.pvalue), "n": n, "inference": inference,
            "fit_stat": "Wald_chi2", "fit_value": float(test.statistic),
            "exploratory": exploratory,
        })
    return rows


def grouped_cv(d: pd.DataFrame) -> tuple[float, float, int]:
    groups = d["author_id"].astype(str)
    folds = min(5, groups.nunique())
    if folds < 2:
        return np.nan, np.nan, folds
    splitter = GroupKFold(n_splits=folds)
    observed, predicted = [], []
    for train, test in splitter.split(d, groups=groups):
        model = smf.ols("ln_repost_24h ~ " + MAIN, data=d.iloc[train]).fit()
        observed.extend(d.iloc[test]["ln_repost_24h"].tolist())
        predicted.extend(model.predict(d.iloc[test]).tolist())
    return (
        float(r2_score(observed, predicted)),
        float(math.sqrt(mean_squared_error(observed, predicted))), folds,
    )


def power_design() -> None:
    p = 0.5
    pilot_n = 0
    if PILOT.exists():
        pilot = pd.read_csv(PILOT, na_values=["", "."])
        pilot_n = len(pilot)
        if "is_lottery" in pilot and len(pilot):
            p = float(pilot["is_lottery"].mean())
    p = min(max(p, 0.05), 0.95)
    z = norm.ppf(0.975) + norm.ppf(0.80)
    target_n = 600
    # Approximate standardized interaction MDE for a centered binary group x
    # standardized continuous predictor. This is a design diagnostic, not power hacking.
    mde = z / math.sqrt(target_n * p * (1.0 - p))
    pd.DataFrame([{
        "target_n": target_n, "pilot_n": pilot_n, "two_sided_alpha": 0.05,
        "target_power": 0.80, "pilot_welfare_share": p,
        "approx_standardized_interaction_mde": mde,
        "assumption": "independent observations; centered binary group x standardized predictor",
    }]).to_csv(POWER_OUT, index=False, encoding="utf-8-sig")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Stage-2 fixed-window econometric analysis")
    parser.add_argument("--power-only", action="store_true",
                        help="Write the pre-collection MDE design report and exit")
    args = parser.parse_args(argv)
    if args.power_only:
        power_design()
        print(f"[done] {POWER_OUT.name}")
        return 0
    if not DATA.exists():
        print("[x] stage2_analysis.csv is missing; run build_stage2_data.py first")
        return 1
    d = prepare()
    if len(d) < 30:
        print(f"[x] only {len(d)} valid T+24h rows; at least 30 are required for a diagnostic run")
        return 1
    records = []

    ols, inference = fit_ols("ln_repost_24h ~ " + MAIN, d)
    records += result_rows(ols, "OLS_LOG_HC3_OR_CLUSTER", "ln_repost_24h", inference,
                           "R2", float(ols.rsquared))

    ppml, inference = fit_glm("reposts_24h ~ " + MAIN, d, sm.families.Poisson())
    dev_r2 = 1.0 - ppml.deviance / ppml.null_deviance
    records += result_rows(ppml, "PPML_PRIMARY", "reposts_24h", inference,
                           "deviance_R2", float(dev_r2))

    logit, inference = fit_glm(
        "positive_repost_24h ~ " + MAIN, d, sm.families.Binomial()
    )
    records += result_rows(logit, "HURDLE_LOGIT", "positive_repost_24h", inference,
                           "AIC", float(logit.aic))

    positive = d.loc[d["reposts_24h"] > 0].copy()
    if len(positive) >= 30:
        conditional, inference = fit_glm(
            "reposts_24h ~ " + MAIN, positive, sm.families.Poisson()
        )
        records += result_rows(conditional, "HURDLE_POSITIVE_PPML", "reposts_24h_positive",
                               inference, "AIC", float(conditional.aic))

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            nb = smf.negativebinomial("reposts_24h ~ " + MAIN, data=d).fit(disp=0, maxiter=300)
        records += result_rows(nb, "NEGATIVE_BINOMIAL", "reposts_24h", "model_based",
                               "AIC", float(nb.aic))
    except Exception as exc:  # noqa: BLE001
        records.append({
            "model": "NEGATIVE_BINOMIAL", "outcome": "reposts_24h", "term": "fit_failed",
            "estimate": np.nan, "std_error": np.nan, "p_value": np.nan, "n": len(d),
            "inference": type(exc).__name__, "fit_stat": "failed", "fit_value": np.nan,
            "exploratory": 1,
        })

    group_counts = d.groupby("appeal_family", dropna=False).size().rename("n").reset_index()
    group_counts["confirmatory"] = (group_counts["n"] >= 80).astype(int)
    group_counts.to_csv(GROUP_OUT, index=False, encoding="utf-8-sig")
    exploratory = int((group_counts["n"] < 80).any())
    hetero_formula = (
        "ln_repost_24h ~ " + MAIN +
        " + C(appeal_family) + "
        "C(appeal_family):(log_followers + text_len_100 + n_images + is_video + is_lottery)"
    )
    hetero, inference = fit_ols(hetero_formula, d)
    tests = {}
    for driver in ("log_followers", "text_len_100", "n_images", "is_video", "is_lottery"):
        tests["appeal_x_" + driver] = [
            term for term in hetero.params.index
            if term.startswith("C(appeal_family)") and term.endswith(":" + driver)
        ]
    records += result_rows(hetero, "H5_APPEAL_INTERACTIONS", "ln_repost_24h", inference,
                           "R2", float(hetero.rsquared), exploratory)
    records += wald_rows(hetero, "H5_WALD", "ln_repost_24h", inference,
                         tests, len(d), exploratory)

    counts = d.groupby("author_id").size()
    repeated = d[d["author_id"].isin(counts[counts >= 2].index)].copy()
    if len(repeated) >= 100 and repeated["author_id"].nunique() >= 30:
        fe_formula = (
            "ln_repost_24h ~ text_len_100 + text_len_100_sq + n_images + is_video + "
            "is_lottery + hard_ad + promo_density_100 + brand_density_100 + "
            "has_ext_link + log_age_hours_24h + C(pub_dow) + C(author_id)"
        )
        fe = smf.ols(fe_formula, data=repeated).fit(
            cov_type="cluster", cov_kwds={"groups": repeated["author_id"]}
        )
        records += result_rows(fe, "AUTHOR_FIXED_EFFECTS", "ln_repost_24h",
                               "author_cluster", "within_sample_R2", float(fe.rsquared))

    valid7 = d[d["has_valid_7d"] == 1].copy()
    if len(valid7) >= 30:
        ppml7, inference = fit_glm("reposts_7d ~ " + MAIN, valid7, sm.families.Poisson())
        records += result_rows(ppml7, "PPML_T7D_ROBUSTNESS", "reposts_7d", inference,
                               "AIC", float(ppml7.aic))

    cv_r2, cv_rmse, folds = grouped_cv(d)
    records.append({
        "model": "AUTHOR_GROUPED_CV", "outcome": "ln_repost_24h", "term": "out_of_sample",
        "estimate": cv_r2, "std_error": np.nan, "p_value": np.nan, "n": len(d),
        "inference": f"GroupKFold_{folds}", "fit_stat": "RMSE", "fit_value": cv_rmse,
        "exploratory": 0,
    })

    pd.DataFrame(records).to_csv(OUT, index=False, encoding="utf-8-sig")
    power_design()
    print(f"sample_n={len(d)} authors={d.author_id.nunique()} zero_share={(d.reposts_24h == 0).mean():.4f}")
    print(f"inference={covariance(d)[2]} PPML_deviance_R2={dev_r2:.6f}")
    print(f"author_grouped_CV_R2={cv_r2:.6f} RMSE={cv_rmse:.6f}")
    print(f"[done] {OUT.name}, {GROUP_OUT.name}, {POWER_OUT.name}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
