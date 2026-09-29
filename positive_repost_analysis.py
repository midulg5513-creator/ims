# -*- coding: utf-8 -*-
"""Exploratory regression restricted to posts with at least one repost."""
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(__file__).resolve().parent
OUT = HERE / "positive_posts_analysis"


def num(s):
    return pd.to_numeric(s, errors="coerce")


def main():
    p = pd.read_csv(OUT / "positive_repost_posts.csv", dtype=str)
    for c in ["reposts", "followers", "author_followers", "n_images", "is_video", "is_lottery", "n_promo", "text_len_clean", "text_len"]:
        if c not in p:
            p[c] = np.nan
        p[c] = num(p[c])
    p["followers"] = p["followers"].fillna(p["author_followers"])
    p["text_len_clean"] = p["text_len_clean"].fillna(p["text_len"])
    p["is_video"] = p["is_video"].fillna((p["media_type"] == "video").astype(int))
    p["is_lottery"] = p["is_lottery"].fillna(0)
    p["n_promo"] = p["n_promo"].fillna(0)
    p["n_images"] = p["n_images"].fillna(0)
    p["log_followers"] = np.log1p(p["followers"].clip(lower=0))
    p["ln_reposts"] = np.log1p(p["reposts"])
    model_vars = ["ln_reposts", "log_followers", "text_len_clean", "n_images", "is_video", "is_lottery", "n_promo", "data_source"]
    d = p.dropna(subset=model_vars).copy()
    optional = [v for v in ["n_images", "is_video", "is_lottery", "n_promo"] if d[v].nunique(dropna=True) > 1]
    rhs = ["log_followers", "text_len_clean", "I(text_len_clean ** 2)"] + optional + ["C(data_source)"]
    formula = "ln_reposts ~ " + " + ".join(rhs)
    fit = smf.ols(formula, data=d).fit(cov_type="HC3")
    rows = [{"term": t, "estimate": fit.params[t], "std_error_HC3": fit.bse[t], "p_value": fit.pvalues[t], "n": int(fit.nobs), "r_squared": fit.rsquared, "adj_r_squared": fit.rsquared_adj} for t in fit.params.index]
    pd.DataFrame(rows).to_csv(OUT / "positive_ols_results.csv", index=False, encoding="utf-8-sig")
    (OUT / "positive_ols_summary.txt").write_text(fit.summary().as_text(), encoding="utf-8")
    pd.DataFrame([{"metric": "n_positive", "value": len(p)}, {"metric": "model_n", "value": len(d)}, {"metric": "r_squared", "value": fit.rsquared}, {"metric": "adj_r_squared", "value": fit.rsquared_adj}]).to_csv(OUT / "positive_model_fit.csv", index=False, encoding="utf-8-sig")
    print(f"[done] positive OLS n={len(d)} R2={fit.rsquared:.4f}")


if __name__ == "__main__":
    main()
