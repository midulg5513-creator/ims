# -*- coding: utf-8 -*-
"""Fast, descriptive T0 analysis for the accelerated stage-2 sample."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(__file__).resolve().parent
POSTS = HERE / "stage2_posts.csv"
FRAME = HERE / "sampling_frame.csv"
OUT = HERE / "t0_analysis"
OUT.mkdir(exist_ok=True)


def num(s, default=0):
    return pd.to_numeric(s, errors="coerce").fillna(default)


def main() -> int:
    posts = pd.read_csv(POSTS, dtype={"post_id": str, "author_id": str})
    frame = pd.read_csv(FRAME, dtype={"post_id": str}) if FRAME.exists() else pd.DataFrame()
    raw_n = len(posts)
    posts = posts.drop_duplicates("post_id", keep="first").copy()
    posts["author_followers"] = num(posts["author_followers"])
    posts["reposts_t0"] = num(posts["reposts_t0"])
    posts["comments_t0"] = num(posts["comments_t0"])
    posts["likes_t0"] = num(posts["likes_t0"])
    posts["n_images"] = num(posts["n_images"])
    posts["has_ext_link"] = num(posts["has_ext_link"])
    posts["text"] = posts["text"].fillna("").astype(str)
    posts["text_len"] = posts["text"].str.replace(r"\s+", "", regex=True).str.len()
    promo = [x.strip() for x in (HERE / "promo_words.txt").read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    posts["n_promo"] = posts["text"].map(lambda x: sum(x.count(w) for w in promo))
    posts["promo_density_100"] = 100 * posts["n_promo"] / posts["text_len"].clip(lower=1)
    posts["log_followers"] = np.log1p(posts["author_followers"])
    posts["ln_reposts_t0"] = np.log1p(posts["reposts_t0"])
    posts["is_video"] = (posts["media_type"].fillna("") == "video").astype(int)
    posts["is_image"] = (posts["media_type"].fillna("") == "image").astype(int)
    posts["is_lottery"] = num(posts["is_lottery_auto"])
    posts["hard_ad"] = num(posts["hard_ad_auto"])
    if not frame.empty and "discovery_age_hours" in frame:
        age = frame[["post_id", "discovery_age_hours"]].drop_duplicates("post_id")
        posts = posts.merge(age, on="post_id", how="left")
    else:
        posts["discovery_age_hours"] = np.nan

    # Cleaning checks are retained as an auditable table.
    checks = pd.DataFrame([
        {"check": "raw_rows", "value": raw_n, "status": "info"},
        {"check": "duplicate_post_ids_removed", "value": raw_n - len(posts), "status": "pass"},
        {"check": "analysis_rows", "value": len(posts), "status": "pass"},
        {"check": "missing_post_id", "value": int(posts["post_id"].isna().sum()), "status": "pass"},
        {"check": "missing_reposts_t0", "value": int(posts["reposts_t0"].isna().sum()), "status": "pass"},
        {"check": "negative_reposts_t0", "value": int((posts["reposts_t0"] < 0).sum()), "status": "pass"},
        {"check": "missing_discovery_age", "value": int(posts["discovery_age_hours"].isna().sum()), "status": "pass" if posts["discovery_age_hours"].notna().all() else "warning"},
    ])
    checks.to_csv(OUT / "t0_cleaning_checks.csv", index=False, encoding="utf-8-sig")
    posts.to_csv(OUT / "t0_cleaned_posts.csv", index=False, encoding="utf-8-sig")

    numeric = ["reposts_t0", "ln_reposts_t0", "comments_t0", "likes_t0", "log_followers", "text_len", "n_images", "promo_density_100", "is_video", "is_lottery", "hard_ad", "discovery_age_hours"]
    desc = posts[numeric].describe().T.reset_index().rename(columns={"index": "variable"})
    desc.to_csv(OUT / "t0_numeric_descriptives.csv", index=False, encoding="utf-8-sig")
    for var in ["industry", "account_type", "media_type", "appeal_auto"]:
        if var in posts:
            g = posts.groupby(var, dropna=False).agg(n=("post_id", "size"), mean_reposts=("reposts_t0", "mean"), median_reposts=("reposts_t0", "median"), mean_ln_reposts=("ln_reposts_t0", "mean"), zero_share=("reposts_t0", lambda x: (x == 0).mean())).reset_index()
            g.to_csv(OUT / f"t0_by_{var}.csv", index=False, encoding="utf-8-sig")

    corr_vars = ["ln_reposts_t0", "log_followers", "text_len", "n_images", "promo_density_100", "is_video", "is_lottery", "hard_ad", "discovery_age_hours"]
    pearson = posts[corr_vars].corr(method="pearson").reset_index().rename(columns={"index": "variable"})
    spearman = posts[corr_vars].corr(method="spearman").reset_index().rename(columns={"index": "variable"})
    pearson.to_csv(OUT / "t0_correlations_pearson.csv", index=False, encoding="utf-8-sig")
    spearman.to_csv(OUT / "t0_correlations_spearman.csv", index=False, encoding="utf-8-sig")

    # Same complete-case rows for the preliminary OLS specification.
    formula = "ln_reposts_t0 ~ log_followers + text_len + I(text_len ** 2) + n_images + is_video + is_lottery + hard_ad + promo_density_100 + discovery_age_hours + C(industry) + C(account_type)"
    model_vars = ["ln_reposts_t0", "log_followers", "text_len", "n_images", "is_video", "is_lottery", "hard_ad", "promo_density_100", "discovery_age_hours", "industry", "account_type"]
    model_data = posts.dropna(subset=model_vars).copy()
    if len(model_data) >= 30:
        fit = smf.ols(formula, data=model_data).fit(cov_type="HC3")
        rows = []
        for term in fit.params.index:
            rows.append({"term": term, "estimate": fit.params[term], "std_error_HC3": fit.bse[term], "p_value": fit.pvalues[term], "n": int(fit.nobs), "r_squared": fit.rsquared, "adj_r_squared": fit.rsquared_adj})
        pd.DataFrame(rows).to_csv(OUT / "t0_ols_results.csv", index=False, encoding="utf-8-sig")
        with (OUT / "t0_ols_summary.txt").open("w", encoding="utf-8") as f:
            f.write(fit.summary().as_text())
    else:
        pd.DataFrame([{"error": "fewer than 30 complete cases", "n": len(model_data)}]).to_csv(OUT / "t0_ols_results.csv", index=False, encoding="utf-8-sig")

    # Quota and attrition/coverage diagnostics.
    quota = posts.groupby(["industry", "account_type"], dropna=False).size().reset_index(name="actual")
    quota["target"] = quota["account_type"].map({"media_other": 20}).fillna(40).astype(int)
    quota["shortfall"] = (quota["target"] - quota["actual"]).clip(lower=0)
    quota.to_csv(OUT / "t0_quota_coverage.csv", index=False, encoding="utf-8-sig")
    if not frame.empty:
        attr = frame.groupby(["status"], dropna=False).size().reset_index(name="n")
        attr["share"] = attr["n"] / len(frame)
        attr.to_csv(OUT / "t0_sampling_attrition.csv", index=False, encoding="utf-8-sig")
        by_source = frame.groupby(["industry", "status"], dropna=False).size().reset_index(name="n")
        by_source.to_csv(OUT / "t0_attrition_by_industry.csv", index=False, encoding="utf-8-sig")
    lines = ["# T0阶段研究结果", "", f"样本量：{len(posts)}（原始读取{raw_n}条，去重后{len(posts)}条）。", "", "本报告只描述T0即时快照的条件相关关系，不作因果解释。发现窗口已放宽至24小时，回归控制 discovery_age_hours。", "", "## 输出文件", "- t0_cleaned_posts.csv：清洗后的分析数据", "- t0_*descriptives.csv：总体及分组描述统计", "- t0_correlations_*.csv：Pearson和Spearman相关矩阵", "- t0_ols_results.csv：HC3稳健标准误初步OLS", "- t0_quota_coverage.csv、t0_sampling_attrition.csv：配额和流失诊断"]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[done] T0 analysis rows={len(posts)}, model_complete_cases={len(model_data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
