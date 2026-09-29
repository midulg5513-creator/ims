# -*- coding: utf-8 -*-
"""Validate the pre-registered hypotheses on the positive-repost sample."""
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(__file__).resolve().parent
OUT = HERE / "positive_posts_analysis"


def n(s):
    return pd.to_numeric(s, errors="coerce")


def main():
    d = pd.read_csv(OUT / "positive_repost_posts.csv", dtype=str)
    def col(name, default=np.nan):
        return d[name] if name in d else pd.Series(default, index=d.index)
    d["reposts"] = n(col("reposts"))
    d["ln_reposts"] = np.log1p(d["reposts"])
    d["followers"] = n(col("followers")).fillna(n(col("author_followers")))
    d["log_followers"] = np.log1p(d["followers"].clip(lower=0))
    d["text"] = col("text", "").fillna("").astype(str)
    d["text_len"] = n(col("text_len_clean")).fillna(d["text"].str.replace(r"\s+", "", regex=True).str.len())
    d["n_images"] = n(col("n_images")).fillna(0)
    d["is_video"] = n(col("is_video")).fillna((col("media_type", "") == "video").astype(int))
    d["n_promo"] = n(col("n_promo"))
    promo_words = [x.strip() for x in (HERE / "promo_words.txt").read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    d["n_promo"] = d["n_promo"].fillna(d["text"].map(lambda x: sum(x.count(w) for w in promo_words)))
    d["promo_density"] = 100 * d["n_promo"] / d["text_len"].clip(lower=1)
    d["is_lottery"] = n(col("is_lottery")).fillna(n(col("is_lottery_auto")))
    lottery_words = ["抽奖", "中奖", "转发抽", "评论区抽", "开奖", "福利"]
    d["is_lottery"] = d["is_lottery"].fillna(d["text"].map(lambda x: int(any(w in x for w in lottery_words))))
    d["hard_ad"] = n(col("hard_ad_auto")).fillna(0)
    d["text_len_sq"] = d["text_len"] ** 2
    d["appeal"] = col("appeal_auto", "other").fillna("other").replace("", "other")
    d["media"] = col("media_type", "other").fillna("other")
    d["source"] = col("data_source", "unknown").fillna("unknown")

    # Drop variables with no variation rather than reporting singular coefficients.
    candidates = ["log_followers", "text_len", "text_len_sq", "n_images", "is_video", "is_lottery", "hard_ad", "promo_density"]
    terms = [x for x in candidates if d[x].nunique(dropna=True) > 1]
    vars_needed = ["ln_reposts"] + terms + ["source"]
    m = d.dropna(subset=vars_needed).copy()
    formula = "ln_reposts ~ " + " + ".join(terms + ["C(source)"])
    fit = smf.ols(formula, data=m).fit(cov_type="HC3")
    rows = []
    for term in fit.params.index:
        rows.append({"term": term, "estimate": fit.params[term], "std_error_HC3": fit.bse[term], "p_value": fit.pvalues[term], "n": int(fit.nobs), "r_squared": fit.rsquared, "adj_r_squared": fit.rsquared_adj})
    pd.DataFrame(rows).to_csv(OUT / "hypothesis_regression.csv", index=False, encoding="utf-8-sig")

    mapping = {
        "H1a": ("log_followers", "粉丝规模与正转发帖子转发量正相关"),
        "H2_text": ("text_len", "文本长度与转发量正相关"),
        "H2_text_sq": ("text_len_sq", "文本长度存在二次项"),
        "H2_images": ("n_images", "图片数与转发量正相关"),
        "H2_video": ("is_video", "视频与转发量正相关"),
        "H3_promo": ("promo_density", "促销词密度降低转发量"),
        "H4_lottery": ("is_lottery", "抽奖机制提高正转发帖子转发量"),
        "H3_hard_ad": ("hard_ad", "硬广告标识降低转发量"),
    }
    tests = []
    for h, (term, statement) in mapping.items():
        present = term in fit.params.index
        est = float(fit.params[term]) if present else np.nan
        p = float(fit.pvalues[term]) if present else np.nan
        direction = "支持" if present and p < .05 and ((h in {"H3_promo", "H3_hard_ad"} and est < 0) or (h not in {"H3_promo", "H3_hard_ad"} and est > 0)) else ("不支持" if present else "无法检验")
        tests.append({"hypothesis": h, "statement": statement, "term": term, "estimate": est, "p_value": p, "conclusion": direction, "note": "正转发条件样本；非获得转发概率"})
    tests += [
        {"hypothesis": "H1b", "statement": "作者历史互动质量提高转发量", "term": "hist_prior", "estimate": np.nan, "p_value": np.nan, "conclusion": "无法检验", "note": "整合数据缺少严格早于发帖时间的历史特征"},
        {"hypothesis": "H4_probability", "statement": "抽奖提高获得至少一次转发的概率", "term": "positive_repost", "estimate": np.nan, "p_value": np.nan, "conclusion": "无法检验", "note": "零转发帖子已按要求删除"},
        {"hypothesis": "H5", "statement": "内容型/福利型组间斜率差异", "term": "appeal_interactions", "estimate": np.nan, "p_value": np.nan, "conclusion": "探索性", "note": "正转发样本且诉求类别稀疏，未作确认性Wald检验"},
    ]
    pd.DataFrame(tests).to_csv(OUT / "hypothesis_validation.csv", index=False, encoding="utf-8-sig")
    (OUT / "hypothesis_regression_summary.txt").write_text(fit.summary().as_text(), encoding="utf-8")
    lines = ["# 正转发样本假设检验", "", f"样本量：{len(m)}；因变量：ln(reposts)。使用HC3稳健标准误，控制数据来源。模型R²={fit.rsquared:.4f}，调整R²={fit.rsquared_adj:.4f}。", "", "## 解释边界", "由于零转发帖子已删除，所有系数解释为‘在已经发生转发的帖子中，转发量高低的相关关系’，不能解释获得转发概率。H1b需要严格的作者历史特征，当前整合数据未提供，因此不强行估计。", "", "详细结果见 hypothesis_validation.csv 和 hypothesis_regression.csv。"]
    (OUT / "假设检验报告.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[done] hypotheses n={len(m)} R2={fit.rsquared:.4f}")


if __name__ == "__main__":
    main()
