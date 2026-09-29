# -*- coding: utf-8 -*-
"""数据特点全景画像：规模 / 分类维度 / 因变量分布 / 缺失 / 质量风险。

只读，不修改任何数据文件。
"""
from pathlib import Path
import io
import sys
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)

ROOT = Path(r"d:\AI\爬虫")
PP = ROOT / "positive_posts_analysis"

# 控制台是 GBK，直接写 UTF-8 文件避免编码错误
sys.stdout = io.TextIOWrapper(
    open(ROOT / "_profile_out.txt", "wb"), encoding="utf-8", line_buffering=True
)


def num(s):
    return pd.to_numeric(s, errors="coerce")


def line(ch="=", w=92):
    print(ch * w)


def title(t):
    print()
    line()
    print(t)
    line()


def dist(s, name, top=None, as_pct=True):
    v = s.fillna("(空)").replace("", "(空)").value_counts(dropna=False)
    tot = v.sum()
    if top:
        v = v.head(top)
    print(f"\n  {name}  (n={tot})")
    for k, c in v.items():
        flag = " ⚠" if str(k) == "(空)" and c / tot > 0.2 else ""
        print(f"    {str(k):<26s} {c:>5d}  {c/tot:>6.1%}{flag}")


def ynum(s, name, indent="  "):
    v = num(s)
    print(f"{indent}{name:<22s} n={v.notna().sum():>4d}  "
          f"mean={v.mean():>10.2f} p50={v.median():>8.0f} "
          f"p90={v.quantile(.9):>9.0f} max={v.max():>10.0f} "
          f"skew={v.skew():>6.2f}  零值={((v == 0).mean()):>6.1%}")


# =========================================================================
title("一、数据集清单与规模")
# =========================================================================
FILES = {
    "posts.csv": ("第一批关键词采集（原始主表）", ROOT / "posts.csv"),
    "comments.csv": ("评论（第一+二批）", ROOT / "comments.csv"),
    "stage2_posts.csv": ("第二阶段行业配额采集", ROOT / "stage2_posts.csv"),
    "stata_data.csv": ("全样本建模表（470）", ROOT / "stata_data.csv"),
    "stata_ads.csv": ("仅广告帖子集（211）", ROOT / "stata_ads.csv"),
    "all_posts_integrated.csv": ("去重整合（924）", PP / "all_posts_integrated.csv"),
    "positive_repost_posts.csv": ("报告用的正转发样本（329）", PP / "positive_repost_posts.csv"),
    "post_details.csv": ("帖子详情快照", ROOT / "post_details.csv"),
    "post_snapshots.csv": ("T0 快照", ROOT / "post_snapshots.csv"),
    "sampling_log.csv": ("第一批采样溯源", ROOT / "sampling_log.csv"),
    "stage2_search_log.csv": ("第二批搜索日志", ROOT / "stage2_search_log.csv"),
    "stage2_accounts.csv": ("第二批账号名录", ROOT / "stage2_accounts.csv"),
    "stage2_attrition.csv": ("第二批损耗记录", ROOT / "stage2_attrition.csv"),
    "stage2_quota_audit.csv": ("第二批配额审计", ROOT / "stage2_quota_audit.csv"),
    "manual_coding.csv": ("人工编码（信度检验用）", ROOT / "manual_coding.csv"),
    "link_resolve.csv": ("外链跳转解析", ROOT / "link_resolve.csv"),
}
print(f"\n  {'文件':<34s} {'行数':>7s} {'列数':>5s}  说明")
print("  " + "-" * 88)
for f, (desc, p) in FILES.items():
    if not p.exists():
        print(f"  {f:<34s} {'缺失':>7s}")
        continue
    d = pd.read_csv(p, dtype=str, low_memory=False)
    print(f"  {f:<34s} {len(d):>7d} {len(d.columns):>5d}  {desc}")

# =========================================================================
title("二、样本量链条（每次筛选丢了多少）")
# =========================================================================
c = pd.read_csv(PP / "all_posts_integrated.csv", dtype=str, low_memory=False)
r = num(c["reposts"])
print(f"\n  去重整合后                       {len(c):>5d}")
print(f"  其中 零转发（reposts=0）          {(r == 0).sum():>5d}  {(r == 0).mean():>6.1%}")
print(f"  → 正转发（报告用的分析样本）        {(r > 0).sum():>5d}  {(r > 0).mean():>6.1%}")
print(f"\n  另一支：stata_data.csv {len(pd.read_csv(ROOT/'stata_data.csv',dtype=str)):>5d}"
      f"  → 其中 is_ad=1 的 stata_ads.csv 211")
print("  ⚠ 注意：924 与 470/211 是两套口径，后者的风险暴露期不一致（见第七节）")

# =========================================================================
title("三、帖子分类维度（核心：你的分类体系）")
# =========================================================================
s2 = pd.read_csv(ROOT / "stage2_posts.csv", dtype=str, low_memory=False)
st = pd.read_csv(ROOT / "stata_data.csv", dtype=str, low_memory=False)
sa = pd.read_csv(ROOT / "stata_ads.csv", dtype=str, low_memory=False)

print("\n【3.1 广告类型 ad_type】（stata_data 全样本 n=470）")
dist(st["ad_type"], "ad_type")

print("\n【3.2 诉求类型 appeal_type】（内容识别，互斥，优先级分类）")
dist(sa["appeal_type"], "appeal_type（仅广告帖 n=211）")

print("\n【3.3 诉求合并组 appeal_grp】（分组回归用）")
dist(sa["appeal_grp"], "appeal_grp（仅广告帖）")

print("\n【3.4 媒体类型 media_type】")
dist(st["media_type"], "media_type（全样本）")
print()
dist(s2["media_type"], "media_type（stage2 行业配额样本 n=454）", top=8)

print("\n【3.5 行业 industry】（仅 stage2 采集）")
dist(s2["industry"], "industry（n=454）")

print("\n【3.6 账号类型 account_type】")
dist(s2["account_type"], "account_type（stage2）", top=10)
print()
for col, nm in [("is_enterprise", "企业/机构认证"), ("is_personal_verified", "个人认证")]:
    v = num(st[col])
    print(f"  {nm:<16s} n={v.notna().sum():>4d}  占比={v.mean():>6.1%}")

print("\n【3.7 抽样关键词层 kw_stratum】（设计变量，不是传播机制变量）")
dist(st["kw_stratum"], "kw_stratum（全样本）", top=22)

print("\n【3.8 抽奖 is_lottery】（内容判定：抽奖/中奖/全文抽/开奖/福利）")
v = num(st["is_lottery"])
print(f"\n  全样本  n={v.notna().sum()}  抽奖占比={v.mean():.1%}")
v2 = num(sa["is_lottery"])
print(f"  广告帖  n={v2.notna().sum()}  抽奖占比={v2.mean():.1%}")

print("\n【3.9 地域 region_grp】")
dist(st["region_grp"], "region_grp（全样本）", top=10)

print("\n【3.10 数据来源 data_source】（这是报告模型的分类控制变量）")
dist(c["data_source"], "data_source（924 整合样本）")

# =========================================================================
title("四、因变量分布（三个结果变量）")
# =========================================================================
print("\n  【全样本 470（stata_data）】")
for k in ("reposts", "comments", "likes"):
    ynum(st[k], k)

print("\n  【仅广告帖 211（stata_ads）】")
for k in ("reposts", "comments", "likes"):
    ynum(sa[k], k)

print("\n  【报告用的正转发样本 329】")
for k in ("reposts", "comments", "likes"):
    ynum(c.loc[r > 0, k], k)

print("\n  【整合样本 924（含零）】")
for k in ("reposts", "comments", "likes"):
    ynum(c[k], k)

print("\n  因变量口径（已定案）")
print("    对数转发 = log10(转发数+1)   （stata_data.csv 里的 log_* 列）")
print("    报告/整合用的是 ln(reposts+1) —— 底数不同，注意别混用")

# =========================================================================
title("五、自变量缺失与退化情况（数据质量红线）")
# =========================================================================
CHK = ["n_promo", "n_brand", "n_topics", "text_len", "n_images", "log_followers",
       "n_mentions", "is_lottery", "log_age_hours", "kw_stratum", "region_grp",
       "pub_hour", "is_weekend", "appeal_grp", "media_type"]
print(f"\n  {'变量':<18s} {'缺失率':>7s} {'唯一值':>7s}  状态")
print("  " + "-" * 62)
for col in CHK:
    if col not in st.columns:
        print(f"  {col:<18s} {'—':>7s} {'—':>7s}  不在表中")
        continue
    s = st[col]
    miss = s.isna().mean() + (s == "").mean()
    nu = s.nunique(dropna=True)
    bad = []
    if miss > 0.05:
        bad.append("高缺失")
    if nu <= 1:
        bad.append("零方差")
    print(f"  {col:<18s} {miss:>7.1%} {nu:>7d}  {'/'.join(bad) if bad else 'ok'}")

print("\n  ⚠ 已知退化变量（在报告的 329 样本里）")
p = pd.read_csv(PP / "positive_repost_posts.csv", dtype=str, low_memory=False)
h = p["hard_ad_auto"].fillna("(空)").value_counts()
print(f"    hard_ad_auto: {dict(h)} → 仅 1 条取值 1，且只存在于 stage2 行")
print("      ⇒ 与 C(data_source) 完全共线，报告里 hard_ad 的 SE=874 是伪数值")

# =========================================================================
title("六、采集侧元数据的特点")
# =========================================================================
sl = pd.read_csv(ROOT / "sampling_log.csv", dtype=str, low_memory=False)
dist(sl.iloc[:, 1] if sl.shape[1] > 1 else sl.iloc[:, 0], f"sampling_log 第2列 {sl.columns[1] if sl.shape[1]>1 else sl.columns[0]}", top=22)

au = pd.read_csv(ROOT / "stage2_quota_audit.csv", dtype=str, low_memory=False)
print(f"\n  stage2_quota_audit.csv 列: {list(au.columns)}")
print(au.head(25).to_string(index=False))

at = pd.read_csv(ROOT / "stage2_attrition.csv", dtype=str, low_memory=False)
print(f"\n  stage2_attrition.csv（采集损耗）")
print(at.to_string(index=False))

# =========================================================================
title("七、时间跨度与风险暴露")
# =========================================================================
for nm, dd, col in [("整合 924", c, "created_at"), ("stage2 454", s2, "created_at")]:
    t = pd.to_datetime(dd[col], errors="coerce", utc=True)
    print(f"\n  {nm:<12s} 发布区间 {t.min()} → {t.max()}   "
          f"跨度 {(t.max()-t.min()).days} 天")
print("\n  post_snapshots.csv 的观察窗口")
ps = pd.read_csv(ROOT / "post_snapshots.csv", dtype=str, low_memory=False)
print(f"    列: {list(ps.columns)}")
if "age_hours" in ps.columns:
    a = num(ps["age_hours"])
    print(f"    age_hours: n={a.notna().sum()} p10={a.quantile(.1):.1f} "
          f"p50={a.median():.1f} p90={a.quantile(.9):.1f} max={a.max():.1f}")
    print("    ⇒ 若离散度大，不同帖子的累计转发不可直接比较")

# =========================================================================
title("八、人工编码与信度（报告 §4.5 要求的 Cohen's κ）")
# =========================================================================
mc = pd.read_csv(ROOT / "manual_coding.csv", dtype=str, low_memory=False)
print(f"\n  manual_coding.csv: {len(mc)} 行 × {len(mc.columns)} 列")
print(f"    列: {list(mc.columns)}")
print("    ⚠ 文件存在但无数据 → 广告判定/诉求类型目前无人工编码，无 κ 值")
print("    ⇒ 报告里所有「广告/诉求」分类都是规则识别，无信度检验支撑")
