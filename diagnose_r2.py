# -*- coding: utf-8 -*-
"""诊断 R2 偏低：量化「删零转发」的代价 与「漏掉强预测变量」的代价。

只读已有 CSV，不修改任何数据文件。
"""
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(r"d:\AI\爬虫")
INT = HERE / "positive_posts_analysis" / "all_posts_integrated.csv"


def num(s):
    return pd.to_numeric(s, errors="coerce")


def fit(formula, data, label, cov="HC3"):
    try:
        r = smf.ols(formula, data=data).fit(cov_type=cov)
        print(f"{label:<46s} n={int(r.nobs):>4d} k={int(r.df_model):>2d} "
              f"R2={r.rsquared:.4f} adjR2={r.rsquared_adj:.4f}")
        return r
    except Exception as e:  # noqa: BLE001
        print(f"{label:<46s} FAILED: {type(e).__name__}: {e}")
        return None


# ==========================================================================
# 第一部分：报告模型（6 变量）在 924 全样本 vs 329 正转发样本
# ==========================================================================
print("=" * 84)
print("第一部分  报告的 6 变量模型：只差「零转发帖在不在样本里」")
print("=" * 84)

d = pd.read_csv(INT, dtype=str, low_memory=False)
t = d["text"].fillna("").astype(str)
a = pd.DataFrame(index=d.index)
a["reposts"] = num(d["reposts"])
a["followers"] = num(d["author_followers"])
a["log_followers"] = np.log1p(a["followers"].clip(lower=0))
a["text_len"] = num(d["text_len_clean"]).fillna(
    t.str.replace(r"\s+", "", regex=True).str.len()
)
a["n_images"] = num(d["n_images"]).fillna(0)
a["is_video"] = (d["media_type"].fillna("") == "video").astype(int)
a["source"] = d["data_source"].fillna("unknown").replace("", "unknown")
a["ln_reposts"] = np.log1p(a["reposts"])
a["tl"] = a["text_len"] / 100.0
a["tl2"] = a["tl"] ** 2

a = a.dropna(subset=["ln_reposts", "log_followers", "text_len", "tl2",
                     "n_images", "is_video", "source"])
a = a[a["text_len"] > 0]
a_pos = a[a["reposts"] > 0]

RPT = "ln_reposts ~ log_followers + tl + tl2 + n_images + is_video + C(source)"
RPT_RAW = ("ln_reposts ~ log_followers + text_len + I(text_len**2) "
           "+ n_images + is_video + C(source)")

print(f"\n全样本 n={len(a)}   零转发 {(a['reposts'] == 0).sum()} "
      f"({(a['reposts'] == 0).mean():.1%})   正转发 n={len(a_pos)}")
print()
fit(RPT_RAW, a_pos, "  [复现] 正转发 329，报告原式")
fit(RPT, a_pos, "  [复现] 正转发 329，长度改以百字计")
fit(RPT_RAW, a, "  → 全样本 924（含零转发）")
fit(RPT, a, "  → 全样本 924（含零转发，稳定式）")

y_all, y_pos = a["ln_reposts"], a_pos["ln_reposts"]
print(f"\n  因变量标准差:  全样本 {y_all.std(ddof=1):.3f}   "
      f"正转发 {y_pos.std(ddof=1):.3f}   "
      f"→ 删零后损失了 {(1 - y_pos.std(ddof=1) / y_all.std(ddof=1)):.1%} 的变异")
print(f"  因变量总平方和 SST:  全样本 {((y_all - y_all.mean())**2).sum():.1f}   "
      f"正转发 {((y_pos - y_pos.mean())**2).sum():.1f}")

print("\n  正转发样本内 Y 的分位（说明截断位置）")
for q in (0, .25, .5, .75, .9, .99, 1.0):
    print(f"    P{int(q*100):<3d} = {y_pos.quantile(q):.3f}", end="")
print()

# ==========================================================================
# 第二部分：路线 B —— stata_ads.csv（211 条广告，其中 100 条零转发）
# ==========================================================================
print("\n" + "=" * 84)
print("第二部分  路线 B：stata_ads.csv（211 条广告帖，47% 零转发）")
print("=" * 84)

s = pd.read_csv(HERE / "stata_ads.csv", dtype=str, low_memory=False)
b = pd.DataFrame(index=s.index)
for c in ["reposts", "log_followers", "text_len", "n_images", "is_lottery",
          "n_mentions", "log_age_hours", "n_promo", "n_brand"]:
    b[c] = num(s[c])
for c in ["media_type", "kw_stratum", "region_grp", "appeal_grp"]:
    b[c] = s[c].fillna("NA").replace("", "NA")
b["ln_reposts"] = np.log1p(b["reposts"])
b["is_video"] = (b["media_type"] == "video").astype(int)
b = b.dropna(subset=["ln_reposts", "log_followers", "text_len", "n_images",
                     "is_lottery", "n_mentions", "log_age_hours"])
b_pos = b[b["reposts"] > 0]

print(f"\n全样本 n={len(b)}   零转发 {(b['reposts'] == 0).sum()} "
      f"({(b['reposts'] == 0).mean():.1%})   正转发 n={len(b_pos)}")

BASE = "ln_reposts ~ log_followers + text_len + n_images"

print("\n[2a] 含零转发（n=211）")
fit(BASE, b, "  基准（粉丝/文本/图片）")
fit(BASE + " + is_lottery", b, "  + 抽奖")
fit(BASE + " + is_lottery + n_mentions", b, "  + @提及数")
fit(BASE + " + is_lottery + n_mentions + C(kw_stratum)", b, "  + 抽样关键词层")
fit(BASE + " + is_lottery + n_mentions + C(kw_stratum) + C(region_grp)",
    b, "  + 地域")
fit(BASE + " + is_lottery + n_mentions + C(kw_stratum) + C(region_grp)"
    " + log_age_hours + C(appeal_grp)", b, "  + 曝光时长 + 诉求类型")

print("\n[2b] 同一模型，剔除零转发（正转发子样本）")
fit(BASE, b_pos, "  基准")
fit(BASE + " + is_lottery", b_pos, "  + 抽奖")
fit(BASE + " + is_lottery + n_mentions", b_pos, "  + @提及数")
fit(BASE + " + is_lottery + n_mentions + C(kw_stratum)", b_pos, "  + 抽样关键词层")
fit(BASE + " + is_lottery + n_mentions + C(kw_stratum) + C(region_grp)",
    b_pos, "  + 地域")

# ==========================================================================
# 第三部分：零值本身有多少可预测性（下限参照）
# ==========================================================================
print("\n" + "=" * 84)
print("第三部分  “零 vs 非零”本身就吃掉多少可解释变异")
print("=" * 84)
b["has_repost"] = (b["reposts"] > 0).astype(int)
r_lpm = smf.ols("has_repost ~ log_followers + is_lottery + n_mentions",
                data=b).fit(cov_type="HC3")
print(f"  线性概率模型 P(转发>0) ~ 粉丝+抽奖+@   R2={r_lpm.rsquared:.4f}  "
      f"（n={int(r_lpm.nobs)}）")
print(f"  零转发组 抽奖占比   = {b.loc[b['reposts'] == 0, 'is_lottery'].mean():.1%}")
print(f"  正转发组 抽奖占比   = {b.loc[b['reposts'] > 0, 'is_lottery'].mean():.1%}")

# ==========================================================================
# 第四部分：爆款帖的杠杆
# ==========================================================================
print("\n" + "=" * 84)
print("第四部分  少数爆款帖的杠杆（stata_ads n=211，基准+抽奖）")
print("=" * 84)
F = BASE + " + is_lottery"
r = smf.ols(F, data=b).fit(cov_type="HC3")
cook = r.get_influence().cooks_distance[0]
print(f"  转发数 max={b['reposts'].max():.0f}  中位="
      f"{b['reposts'].median():.0f}  P99={b['reposts'].quantile(.99):.0f}")
print(f"  Cook's D > 4/n 的帖子数 = {(cook > 4 / len(b)).sum()}")
for q in (.999, .99, .975, .95):
    thr = b["reposts"].quantile(q)
    sub = b[b["reposts"] <= thr]
    rr = smf.ols(F, data=sub).fit(cov_type="HC3")
    print(f"  剔除 reposts > P{q*100:.1f} = {thr:>6.0f} 后 n={len(sub):>4d}  "
          f"R2={rr.rsquared:.4f}")
