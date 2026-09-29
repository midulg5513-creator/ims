# -*- coding: utf-8 -*-
"""Reproducible econometric pipeline for Weibo advertising posts.

The script keeps the assignment OLS separate from the research models and writes
machine-readable model summaries to econometric_results.csv.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold


HERE = Path(__file__).resolve().parent
DATA = HERE / "stata_ads2.csv"
OUT = HERE / "econometric_results.csv"

BASE = "log_followers + text_len + n_images + is_lottery"
MAIN = (
    "log_followers + hist_prior + has_prior_hist + text_len + n_images + "
    "is_lottery + log_age_hours"
)


def prepare() -> pd.DataFrame:
    d = pd.read_csv(DATA, dtype={"post_id": str, "author_id": str}, na_values=".")
    required = {
        "reposts", "log_followers", "text_len", "n_images", "is_lottery",
        "hist_prior_avg_lnengage", "log_age_hours", "author_id", "appeal_grp",
        "media_type",
    }
    missing = sorted(required - set(d.columns))
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    d["ln_repost"] = np.log1p(d["reposts"])
    d["positive_repost"] = (d["reposts"] > 0).astype(int)
    d["has_prior_hist"] = d["hist_prior_avg_lnengage"].notna().astype(int)
    d["hist_prior"] = d["hist_prior_avg_lnengage"].fillna(0)
    if (d["age_hours"] <= 0).any() or d["log_age_hours"].isna().any():
        raise ValueError("Exposure age must be positive and complete")
    return d


def row(model: str, outcome: str, term: str, estimate: float, p: float,
        n: int, fit_name: str, fit_value: float) -> dict:
    return {
        "model": model, "outcome": outcome, "term": term,
        "estimate": estimate, "p_value": p, "n": n,
        "fit_stat": fit_name, "fit_value": fit_value,
    }


def collect(result, model: str, outcome: str, fit_name: str, fit_value: float) -> list[dict]:
    return [
        row(model, outcome, term, float(result.params[term]),
            float(result.pvalues[term]), int(result.nobs), fit_name, float(fit_value))
        for term in result.params.index
    ]


def grouped_cv(d: pd.DataFrame) -> tuple[float, float]:
    """Five-fold OLS validation that never splits one author across train/test."""
    groups = d["author_id"].astype(str)
    splitter = GroupKFold(n_splits=5)
    observed, predicted = [], []
    for train, test in splitter.split(d, groups=groups):
        fitted = smf.ols("ln_repost ~ " + MAIN, data=d.iloc[train]).fit()
        observed.extend(d.iloc[test]["ln_repost"].tolist())
        predicted.extend(fitted.predict(d.iloc[test]).tolist())
    return r2_score(observed, predicted), math.sqrt(mean_squared_error(observed, predicted))


def main() -> int:
    d = prepare()
    records: list[dict] = []

    # Q1 teaching specification: conventional OLS sums of squares and R-squared.
    q1 = smf.ols("ln_repost ~ " + BASE, data=d).fit()
    records += collect(q1, "Q1_OLS", "ln_repost", "R2", q1.rsquared)

    # Research OLS uses heteroskedasticity-consistent HC3 inference.
    ols = smf.ols("ln_repost ~ " + MAIN, data=d).fit(cov_type="HC3")
    records += collect(ols, "MAIN_OLS_HC3", "ln_repost", "R2", ols.rsquared)

    # PPML keeps zero counts and targets the conditional mean of repost counts.
    ppml = smf.glm("reposts ~ " + MAIN, data=d, family=sm.families.Poisson()).fit(
        cov_type="HC3"
    )
    pseudo_r2 = 1 - ppml.deviance / ppml.null_deviance
    records += collect(ppml, "PPML_HC3", "reposts", "deviance_R2", pseudo_r2)

    # Hurdle part 1: extensive margin, whether a post receives any repost.
    logit = smf.logit("positive_repost ~ " + MAIN, data=d).fit(
        disp=0, cov_type="HC3"
    )
    records += collect(logit, "HURDLE_LOGIT_HC3", "positive_repost",
                       "McFadden_R2", logit.prsquared)

    # Hurdle part 2: conditional intensity among posts with at least one repost.
    positive = d.loc[d["reposts"] > 0].copy()
    positive["ln_positive_repost"] = np.log(positive["reposts"])
    intensity = smf.ols("ln_positive_repost ~ " + MAIN, data=positive).fit(
        cov_type="HC3"
    )
    records += collect(intensity, "HURDLE_POSITIVE_OLS_HC3", "ln_reposts",
                       "R2", intensity.rsquared)

    # Formal heterogeneity tests. Significance differences across separate groups
    # are not treated as coefficient differences.
    appeal = smf.ols(
        "ln_repost ~ log_followers*C(appeal_grp) + text_len*C(appeal_grp) + "
        "n_images + is_lottery + hist_prior + has_prior_hist + log_age_hours",
        data=d,
    ).fit(cov_type="HC3")
    for label, marker in (
        ("appeal_x_followers", "log_followers:C(appeal_grp)"),
        ("appeal_x_text", "text_len:C(appeal_grp)"),
    ):
        terms = [name for name in appeal.params.index if marker in name]
        test = appeal.f_test([name + " = 0" for name in terms])
        records.append(row("HETEROGENEITY_WALD", "ln_repost", label,
                           float(test.fvalue), float(test.pvalue), int(appeal.nobs),
                           "F", float(test.fvalue)))

    media_subset = d[d["media_type"].isin(["image", "video"])].copy()
    lottery_media = smf.ols(
        "ln_repost ~ log_followers + hist_prior + has_prior_hist + text_len + "
        "n_images + log_age_hours + is_lottery*C(media_type)", data=media_subset,
    ).fit(cov_type="HC3")
    test = lottery_media.f_test("is_lottery:C(media_type)[T.video] = 0")
    records.append(row("HETEROGENEITY_WALD", "ln_repost", "media_x_lottery",
                       float(test.fvalue), float(test.pvalue), int(lottery_media.nobs),
                       "F", float(test.fvalue)))

    cv_r2, cv_rmse = grouped_cv(d)
    records.append(row("AUTHOR_GROUPED_5FOLD_CV", "ln_repost", "out_of_sample",
                       cv_r2, np.nan, len(d), "RMSE", cv_rmse))

    pd.DataFrame(records).to_csv(OUT, index=False, encoding="utf-8-sig")
    print("sample_n=%d authors=%d zero_share=%.4f" % (
        len(d), d["author_id"].nunique(), (d["reposts"] == 0).mean()))
    print("age_hours median=%.2f min=%.2f max=%.2f" % (
        d["age_hours"].median(), d["age_hours"].min(), d["age_hours"].max()))
    print("Q1 R2=%.6f adjR2=%.6f" % (q1.rsquared, q1.rsquared_adj))
    print("main OLS R2=%.6f adjR2=%.6f" % (ols.rsquared, ols.rsquared_adj))
    print("PPML deviance R2=%.6f" % pseudo_r2)
    print("author-grouped CV R2=%.6f RMSE=%.6f" % (cv_r2, cv_rmse))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
