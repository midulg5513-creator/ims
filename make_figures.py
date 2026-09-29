# -*- coding: utf-8 -*-
"""
make_figures.py —— 为论文/报告生成展示用数据图（全部基于 stata_ads3.csv，与 Stata 输出口径一致）

输出 6 张图（PNG，200dpi，可直接插入 Word）：
  fig1_DV分布.png          因变量为什么取对数（零值 + 右偏）
  fig2_粉丝非线性.png      H1d：二次关系 + 边际效应曲线（含 95% 置信带）
  fig3_Q2阶梯.png          Q2：M0→M9 的 R² 阶梯 + 目标线，M4 为何是"最小充分模型"
  fig4_主模型森林图.png    主模型 20 个系数 + HC3 95% 置信区间
  fig5_Q3分组R2.png        Q3：4 个维度的分组回归 R²
  fig6_残差诊断.png        残差 vs 拟合值（异方差）+ 正态 QQ 图

自检：脚本会重算 M0–M9 的 R² 并与 Stata 记录值逐一比对，差异 >5e-5 会报警。
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False
rcParams["figure.dpi"] = 110
rcParams["savefig.dpi"] = 200
rcParams["savefig.bbox"] = "tight"
rcParams["axes.edgecolor"] = "#666666"
rcParams["axes.labelcolor"] = "#222222"
rcParams["text.color"] = "#222222"

DATA = r"d:\AI\爬虫\stata_ads3.csv"
OUT = r"d:\AI\爬虫\figures"
os.makedirs(OUT, exist_ok=True)

C_MAIN = "#2E5C8A"     # 主色（深蓝）
C_ACC = "#C0392B"      # 强调（砖红）
C_OK = "#1E8449"       # 达标（绿）
C_GRey = "#9AA5B1"

# ----------------------------------------------------------------- 数据
df = pd.read_csv(DATA, encoding="utf-8")
df["lnf_sq"] = df["ln_followers"] ** 2
N = len(df)


# ----------------------------------------------------------------- OLS 工具
def build_X(d, cont, dums=(), drop_collinear=True):
    """构造设计矩阵：连续/二值列 + 分类哑变量（基准=字母序首个），自动剔除零方差与共线列。"""
    parts, names = [], []
    for c in cont:
        parts.append(d[c].to_numpy(float))
        names.append(c)
    for v in dums:
        levs = sorted(d[v].astype(str).unique())
        for lv in levs[1:]:
            parts.append((d[v].astype(str) == lv).to_numpy(float))
            names.append(f"{v}:{lv}")
    X = np.column_stack([np.ones(len(d))] + parts)
    names = ["_cons"] + names

    # 注意：常数项的标准差恒为 0，必须无条件保留（v1 就是在这里把截距删掉了）
    keep = [0] + [i for i in range(1, X.shape[1]) if X[:, i].std() > 1e-12]
    X, names = X[:, keep], [names[i] for i in keep]

    if drop_collinear:                      # 顺序正交化，剔除共线列（模拟 Stata 的 omitted）
        keep2, Q = [], np.zeros((X.shape[0], 0))
        for i in range(X.shape[1]):
            v = X[:, i].copy()
            if Q.shape[1]:
                v = v - Q @ (Q.T @ v)
            if np.linalg.norm(v) > 1e-8 * max(np.linalg.norm(X[:, i]), 1e-12):
                keep2.append(i)
                Q = np.column_stack([Q, v / np.linalg.norm(v)])
        X, names = X[:, keep2], [names[i] for i in keep2]
    return X, names


def ols_hc3(y, X, hc3=True):
    XtXi = np.linalg.inv(X.T @ X)
    b = XtXi @ (X.T @ y)
    e = y - X @ b
    n, k = X.shape
    sst = ((y - y.mean()) ** 2).sum()
    r2 = 1.0 - (e ** 2).sum() / sst
    r2a = 1.0 - (1.0 - r2) * (n - 1) / (n - k)
    if hc3:
        h = np.einsum("ij,jk,ik->i", X, XtXi, X)
        u2 = e ** 2 / np.clip(1.0 - h, 1e-10, None) ** 2
        V = XtXi @ (X.T @ (u2[:, None] * X)) @ XtXi
    else:
        s2 = (e ** 2).sum() / (n - k)
        V = s2 * XtXi
    return dict(b=b, se=np.sqrt(np.maximum(np.diag(V), 0)), V=V, e=e, fit=X @ b,
                r2=r2, r2a=r2a, n=n, k=k)


Y = np.log(df["reposts"].to_numpy(float) + 1.0)   # 双精度重算，与 do 脚本的 drop+gen double 一致

# 连续/二值变量
CORE = ["ln_followers", "hist_prior_lnengage0", "has_prior_hist",
        "text_len", "n_pics", "is_lottery", "ln_age_hours"]
AUTH = ["is_enterprise", "is_personal_verified"]
MEDIA_D = ["media_type"]
APPEAL_D = ["appeal_grp"]
REGION_D = ["region_grp"]

LADDER = {
    "M0 基准": (["ln_followers", "text_len", "n_pics", "is_lottery"], []),
    "M1 +曝光时长": (["ln_followers", "text_len", "n_pics", "is_lottery", "ln_age_hours"], []),
    "M2 +事前互动": (CORE, []),
    "M3 +粉丝二次项": (["ln_followers", "lnf_sq"] + CORE[1:], []),
    "M4 +话题/@数": (["ln_followers", "lnf_sq"] + CORE[1:] + ["n_topics", "n_mentions"], []),
    "M5 +促销/品牌": (["ln_followers", "lnf_sq"] + CORE[1:] + ["n_topics", "n_mentions", "n_promo", "n_brand"], []),
    "M6 +认证身份": (["ln_followers", "lnf_sq"] + CORE[1:] + ["n_topics", "n_mentions", "n_promo", "n_brand"] + AUTH, []),
    "M7 +媒体形态": (["ln_followers", "lnf_sq"] + CORE[1:] + ["n_topics", "n_mentions", "n_promo", "n_brand"] + AUTH, MEDIA_D),
    "M8 +诉求类型": (["ln_followers", "lnf_sq"] + CORE[1:] + ["n_topics", "n_mentions", "n_promo", "n_brand"] + AUTH, MEDIA_D + APPEAL_D),
    "M9 +地域": (["ln_followers", "lnf_sq"] + CORE[1:] + ["n_topics", "n_mentions", "n_promo", "n_brand"] + AUTH, MEDIA_D + APPEAL_D + REGION_D),
}
STATA_R2 = {  # 来自 reproduce_all.log（stata_ads3.csv）
    "M0 基准": 0.308606, "M1 +曝光时长": 0.312457, "M2 +事前互动": 0.449215,
    "M3 +粉丝二次项": 0.460951, "M4 +话题/@数": 0.465922, "M5 +促销/品牌": 0.474817,
    "M6 +认证身份": 0.479310, "M7 +媒体形态": 0.479460, "M8 +诉求类型": 0.486908,
    "M9 +地域": 0.499844,
}
BASE_R2 = STATA_R2["M0 基准"]
TARGET = round(1.5 * BASE_R2, 6)

log_lines = []


def log(s=""):
    print(s)
    log_lines.append(str(s))


# ----------------------------------------------------------------- 自检
log("=" * 68)
log("Python OLS 与 Stata 记录值比对（容差 5e-5）")
log("=" * 68)
ladder_res = {}
for name, (cont, dums) in LADDER.items():
    X, nm = build_X(df, cont, dums)
    res = ols_hc3(Y, X, hc3=False)
    ladder_res[name] = (res, nm)
    d = abs(res["r2"] - STATA_R2[name])
    flag = "OK " if d < 5e-5 else "!! "
    log(f"[{flag}] {name:<14} py={res['r2']:.6f}  stata={STATA_R2[name]:.6f}  diff={d:.2e}  k={res['k']-1}")

# 主模型（HC3，k=20）
main_res, main_names = ladder_res["M8 +诉求类型"]
# 用 HC3 重估取标准误
Xm, main_names = build_X(df, LADDER["M8 +诉求类型"][0], LADDER["M8 +诉求类型"][1])
main = ols_hc3(Y, Xm, hc3=True)
log(f"[{'OK ' if abs(main['r2'] - 0.486908) < 5e-5 else '!! '}] 主模型 M8(HC3)  py={main['r2']:.6f}  stata=0.486908  k={main['k']-1}")
log("")

# ----------------------------------------------------------------- 图1 因变量分布
fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.2))
ax = axes[0]
rep = df["reposts"].to_numpy(float)
buckets = [("0", rep == 0), ("1–9", (rep >= 1) & (rep <= 9)), ("10–99", (rep >= 10) & (rep <= 99)),
           ("100–999", (rep >= 100) & (rep <= 999)), (r"$\geq$1000", rep >= 1000)]
labs = [b[0] for b in buckets]
cnt = np.array([b[1].sum() for b in buckets])
sh = cnt / cnt.sum() * 100
cmap = plt.get_cmap("Blues")
cols = [cmap(0.85), cmap(0.62), cmap(0.45), cmap(0.30), cmap(0.18)]
cols[0] = C_ACC
bars = ax.bar(labs, cnt, color=cols, alpha=0.92, width=0.62)
for i, (c, s) in enumerate(zip(cnt, sh)):
    ax.text(i, c + 4, f"{c} 条\n{s:.1f}%", ha="center", fontsize=9.4, color="#222222")
ax.set_ylim(0, cnt.max() * 1.34)
ax.set_ylabel("帖子数")
ax.set_xlabel("转发量分组")
ax.set_title("(a) 原始转发量：零堆积 + 极端集中", fontsize=11.5, fontweight="bold")
top5 = np.sort(rep)[::-1][:max(1, int(round(N * 0.05)))]
share5 = top5.sum() / rep.sum() * 100
ax.text(0.40, 0.965, f"偏度 = {pd.Series(rep).skew():.1f}　最大值 = {rep.max():,.0f}\n"
                     f"最高的 5% 帖子贡献了 {share5:.1f}% 的转发量\n"
                     f"→ 直接建模会被极端值主导，故取对数",
        transform=ax.transAxes, fontsize=9.2, va="top",
        bbox=dict(boxstyle="round,pad=0.5", fc="#F7F9FB", ec="#B9C4CE"))

ax = axes[1]
ln = df["ln_repost"].to_numpy(float)
ax.hist(ln, bins=32, color="#4A7FB5", alpha=0.85, edgecolor="white", linewidth=0.5)
ax.set_xlabel("ln(转发量 + 1)")
ax.set_ylabel("帖子数")
ax.set_title("(b) 取对数后：分布形态明显改善", fontsize=11.5, fontweight="bold")
ax.text(0.58, 0.86, f"偏度 = {pd.Series(ln).skew():.2f}\n均值 = {ln.mean():.2f}\n标准差 = {ln.std(ddof=1):.2f}",
        transform=ax.transAxes, fontsize=9.5, va="top",
        bbox=dict(boxstyle="round,pad=0.45", fc="#F7F9FB", ec="#B9C4CE"))
fig.suptitle("图 1  因变量的分布特征与对数变换效果（N = 211）", fontsize=12.5, fontweight="bold", y=1.03)
fig.savefig(os.path.join(OUT, "fig1_DV分布.png"))
plt.close(fig)
log("[saved] fig1_DV分布.png")

# ----------------------------------------------------------------- 图2 粉丝规模非线性
cont3, dums3 = LADDER["M3 +粉丝二次项"]
X3, nm3 = build_X(df, cont3, dums3)
m3 = ols_hc3(Y, X3, hc3=True)
i1, i2 = nm3.index("ln_followers"), nm3.index("lnf_sq")
b1, b2 = m3["b"][i1], m3["b"][i2]
log(f"M3 偏效应系数：ln_followers = {b1:.4f}，lnf_sq = {b2:.4f}")

x = df["ln_followers"].to_numpy(float)
xs = np.linspace(x.min(), x.max(), 200)
# 边际效应 dy/dx = b1 + 2*b2*x，其方差用 delta method 基于 HC3 的 V
g = np.column_stack([np.ones_like(xs), 2 * xs])          # [∂/∂b1, ∂/∂b2]
Vsub = m3["V"][np.ix_([i1, i2], [i1, i2])]
me = g @ np.array([b1, b2])
se_me = np.sqrt(np.einsum("ij,jk,ik->i", g, Vsub, g))

fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
ax = axes[0]
ax.scatter(x, Y, s=17, color=C_GRey, alpha=0.55, edgecolor="none", label="观测值")
order = np.argsort(x)
# 纯二次拟合曲线（仅这两个变量），用于可视化相关性形状
c2 = np.polyfit(x, Y, 2)
ax.plot(xs, np.polyval(c2, xs), color=C_ACC, lw=2.4, label="二次拟合曲线")
q = pd.qcut(x, 5)
binned = df.groupby(q, observed=True).agg(xm=("ln_followers", "mean"), ym=("ln_repost", "mean"))
ax.plot(binned["xm"], binned["ym"], "o-", color=C_MAIN, lw=1.6, ms=6, label="五等分箱均值")
ax.set_xlabel("ln(粉丝数)")
ax.set_ylabel("ln(转发量 + 1)")
ax.set_title("(a) 散点与二次拟合：关系呈加速上行", fontsize=11.5, fontweight="bold")
ax.legend(fontsize=9, frameon=False, loc="upper left")

ax = axes[1]
ax.fill_between(xs, me - 1.96 * se_me, me + 1.96 * se_me, color=C_MAIN, alpha=0.18,
                label="95% 置信带（HC3）")
ax.plot(xs, me, color=C_MAIN, lw=2.4, label="边际效应")
ax.axhline(0, color=C_ACC, lw=1.4, ls="--")
med = np.median(x)
ax.axvline(med, color=C_GRey, lw=1.1, ls=":")
ax.annotate(f"中位粉丝量\n（ln = {med:.1f}）", xy=(med, ax.get_ylim()[0]), xytext=(med + 0.35, 0.06),
            fontsize=9, color="#555555",
            arrowprops=dict(arrowstyle="->", color=C_GRey, lw=1.0))
ax.set_xlabel("ln(粉丝数)")
ax.set_ylabel("边际效应  ∂ln(转发量+1) / ∂ln(粉丝数)")
ax.set_title("(b) 边际效应随粉丝规模递增（H1d）", fontsize=11.5, fontweight="bold")
ax.legend(fontsize=9, frameon=False, loc="upper left")
fig.suptitle("图 2  粉丝规模与转发量的非线性关系（控制曝光时长、事前互动质量等，N = 211）",
             fontsize=12.5, fontweight="bold", y=1.02)
fig.savefig(os.path.join(OUT, "fig2_粉丝非线性.png"))
plt.close(fig)
log("[saved] fig2_粉丝非线性.png")

# ----------------------------------------------------------------- 图3 Q2 阶梯
names = list(LADDER.keys())
r2s = [ladder_res[n][0]["r2"] for n in names]
r2as = [ladder_res[n][0]["r2a"] for n in names]
xp = np.arange(len(names))

fig, ax = plt.subplots(figsize=(11.8, 4.9))
bar_cols = [C_OK if n.startswith("M4") else C_MAIN for n in names]
bars1 = ax.bar(xp, r2s, 0.52, color=bar_cols, alpha=0.92, label="R²")
ax.plot(xp, r2as, "o-", color=C_ACC, lw=1.9, ms=6.5, label="调整 R²", zorder=4)
ax.axhline(TARGET, color=C_ACC, lw=1.8, ls="--", zorder=2)
for i, v in enumerate(r2s):
    ax.text(xp[i], v + 0.009, f"{v:.4f}", ha="center", fontsize=8.5, color="#333333")
ax.text(0.60, TARGET - 0.042, f"目标 R² = 1.5 × {BASE_R2:.6f} = {TARGET:.6f}",
        color=C_ACC, fontsize=10.2, fontweight="bold", zorder=5,
        bbox=dict(boxstyle="round,pad=0.32", fc="white", ec="none", alpha=0.92))
i4 = [i for i, n in enumerate(names) if n.startswith("M4")][0]
ax.annotate("M4：首个达标模型\n（+50.98%）", xy=(xp[i4] - 0.30, r2s[i4] - 0.004),
            xytext=(xp[i4] - 1.75, r2s[i4] + 0.070), ha="center",
            fontsize=9.6, color=C_OK, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=C_OK, lw=1.4))
ax.annotate("调整 R² 在 M5 见顶后持续回落：\n后续 R² 上升只是参数变多的机械效应",
            xy=(xp[-1] + 0.06, r2as[-1]), xytext=(len(names) - 3.75, 0.607),
            fontsize=9.2, color="#555555",
            arrowprops=dict(arrowstyle="->", color=C_GRey, lw=1.1))
ax.set_xticks(xp)
ax.set_xticklabels(names, rotation=22, ha="right", fontsize=9.5)
ax.set_ylabel("R²")
ax.set_ylim(0, 0.70)
ax.set_title("图 3  Q2：逐步扩展模型的 R² 阶梯（N = 211，M4 为首个达标模型）",
             fontsize=12.5, fontweight="bold")
ax.legend(fontsize=10, frameon=False, loc="upper left", bbox_to_anchor=(0.0, 1.0))
ax.grid(axis="y", ls=":", alpha=0.35)
ax.set_axisbelow(True)
fig.savefig(os.path.join(OUT, "fig3_Q2阶梯.png"))
plt.close(fig)
log("[saved] fig3_Q2阶梯.png")

# ----------------------------------------------------------------- 图4 主模型森林图
idx = [i for i, n in enumerate(main_names) if n != "_cons"]
b, se = main["b"][idx], main["se"][idx]
labels = [main_names[i] for i in idx]
order = np.argsort(b)
b, se, labels = b[order], se[order], [labels[i] for i in order]
lo, hi = b - 1.96 * se, b + 1.96 * se
sig = (lo > 0) | (hi < 0)
col = [C_OK if s else C_GRey for s in sig]

fig, ax = plt.subplots(figsize=(9.2, 7.4))
ypos = np.arange(len(b))
ax.errorbar(b, ypos, xerr=1.96 * se, fmt="none", ecolor="#7F8C8D", elinewidth=1.3, capsize=3, zorder=2)
ax.scatter(b, ypos, s=52, c=col, zorder=3, edgecolor="white", linewidth=0.8)
ax.axvline(0, color=C_ACC, lw=1.6, ls="--", zorder=1)
ax.set_yticks(ypos)
ax.set_yticklabels(labels, fontsize=9.5)
ax.set_xlabel("回归系数（点）与 95% 置信区间（HC3 稳健标准误）")
ax.set_title("图 4  主模型系数森林图（M8，k = 20，R² = 0.4869）", fontsize=12.5, fontweight="bold")
for yy, bb, ll, hh in zip(ypos, b, lo, hi):
    ax.text(ax.get_xlim()[1] * 0.995, yy, f"{bb:+.3f}" + ("" if (ll > 0 or hh < 0) else "  n.s."),
            fontsize=8.6, va="center", ha="right", color="#333333")
ax.grid(axis="x", ls=":", alpha=0.35)
ax.set_axisbelow(True)
ax.text(0.015, 0.015, "绿色 = 95% 置信区间不含 0；灰色 = 不显著", transform=ax.transAxes,
        fontsize=9, color="#555555")
fig.savefig(os.path.join(OUT, "fig4_主模型森林图.png"))
plt.close(fig)
log("[saved] fig4_主模型森林图.png")

# ----------------------------------------------------------------- 图5 Q3 分组 R²
GRP = [
    ("诉求类型", "appeal_grp", None),
    ("媒体形态", "media_type", None),
    ("账号类型", "__acct__", None),
    ("落地页类型", "link_grp", None),
]
df["__acct__"] = np.select(
    [df["is_enterprise"].eq(1), df["is_personal_verified"].eq(1)],
    ["企业认证", "个人认证"], default="未认证")

fig, axes = plt.subplots(2, 2, figsize=(11, 7.2))
fig.suptitle("图 5  Q3：不同广告类型分组回归的 R²（统一规格，HC3，仅报 n ≥ 25 的组）",
             fontsize=12.5, fontweight="bold", y=0.985)

for ax, (title, var, _) in zip(axes.ravel(), GRP):
    rows = []
    for lv, sub in df.groupby(var, observed=True):
        if len(sub) < 25:
            rows.append((str(lv), len(sub), np.nan))
            continue
        Xs, _ = build_X(sub, CORE, [])
        rs = ols_hc3(sub["ln_repost"].to_numpy(float), Xs, hc3=False)
        rows.append((str(lv), len(sub), rs["r2"]))
    rows.sort(key=lambda t: (-1e9 if np.isnan(t[2]) else t[2]))
    labs = [f"{a}\n(n={b})" if not np.isnan(c) else f"{a}\n(n={b}, 跳过)" for a, b, c in rows]
    vals = [0 if np.isnan(c) else c for _, _, c in rows]
    cols = [C_GRey if np.isnan(c) else C_MAIN for _, _, c in rows]
    yp = np.arange(len(rows))
    ax.barh(yp, vals, color=cols, alpha=0.9, height=0.6)
    for i, (a, bb, c) in enumerate(rows):
        txt = "n<25" if np.isnan(c) else f"{c:.3f}"
        ax.text(vals[i] + 0.012, i, txt, va="center", fontsize=9,
                color="#777777" if np.isnan(c) else "#222222")
    ax.set_yticks(yp)
    ax.set_yticklabels(labs, fontsize=9.2)
    ax.set_xlim(0, max(vals) * 1.30 if max(vals) > 0 else 1)
    ax.set_xlabel("R²", fontsize=9.5)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.grid(axis="x", ls=":", alpha=0.35)
    ax.set_axisbelow(True)
fig.tight_layout(rect=(0, 0, 1, 0.955))
fig.savefig(os.path.join(OUT, "fig5_Q3分组R2.png"))
plt.close(fig)
log("[saved] fig5_Q3分组R2.png")

# ----------------------------------------------------------------- 图6 残差诊断
e, fit = main["e"], main["fit"]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
ax = axes[0]
ax.scatter(fit, e, s=18, color=C_MAIN, alpha=0.55, edgecolor="none")
ax.axhline(0, color=C_ACC, lw=1.6, ls="--")
# LOWESS 式趋势：按拟合值分箱的均值
bins = pd.qcut(pd.Series(fit), 8, duplicates="drop")
tr = pd.DataFrame({"f": fit, "e": e}).groupby(bins, observed=True).mean()
ax.plot(tr["f"], tr["e"], "o-", color=C_ACC, lw=1.5, ms=5, label="分箱残差均值")
ax.set_xlabel("拟合值")
ax.set_ylabel("残差")
ax.set_title("(a) 残差 vs 拟合值：随拟合值增大而扩散", fontsize=11.5, fontweight="bold")
ax.legend(fontsize=9, frameon=False)
ax.text(0.03, 0.04, "→ 存在异方差，故全模型使用 HC3 稳健标准误", transform=ax.transAxes,
        fontsize=9.2, color=C_ACC)

ax = axes[1]
z = np.sort((e - e.mean()) / e.std(ddof=1))
pp = (np.arange(1, len(z) + 1) - 0.5) / len(z)


def norm_ppf(p):  # Acklam 近似，避免依赖 scipy
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    bq = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
          6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        qq = np.sqrt(-2 * np.log(p))
        return (((((c[0] * qq + c[1]) * qq + c[2]) * qq + c[3]) * qq + c[4]) * qq + c[5]) / \
               ((((d[0] * qq + d[1]) * qq + d[2]) * qq + d[3]) * qq + 1)
    if p > ph:
        qq = np.sqrt(-2 * np.log(1 - p))
        return -(((((c[0] * qq + c[1]) * qq + c[2]) * qq + c[3]) * qq + c[4]) * qq + c[5]) / \
                ((((d[0] * qq + d[1]) * qq + d[2]) * qq + d[3]) * qq + 1)
    qq = p - 0.5
    r = qq * qq
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * qq / \
           (((((bq[0] * r + bq[1]) * r + bq[2]) * r + bq[3]) * r + bq[4]) * r + 1)


qth = np.array([norm_ppf(p) for p in pp])
ax.scatter(qth, z, s=16, color=C_MAIN, alpha=0.55, edgecolor="none")
lim = [min(qth.min(), z.min()) - 0.3, max(qth.max(), z.max()) + 0.3]
ax.plot(lim, lim, color=C_ACC, lw=1.6, ls="--", label="正态参考线")
ax.set_xlabel("理论分位数（正态）")
ax.set_ylabel("标准化残差")
ax.set_title("(b) 正态 QQ 图：两端略厚，中部贴合", fontsize=11.5, fontweight="bold")
ax.legend(fontsize=9, frameon=False, loc="upper left")
fig.suptitle("图 6  主模型残差诊断（N = 211）", fontsize=12.5, fontweight="bold", y=1.02)
fig.savefig(os.path.join(OUT, "fig6_残差诊断.png"))
plt.close(fig)
log("[saved] fig6_残差诊断.png")

# ----------------------------------------------------------------- 分组结果落盘
rows = []
for title, var, _ in GRP:
    for lv, sub in df.groupby(var, observed=True):
        if len(sub) < 25:
            rows.append((title, str(lv), len(sub), None, None))
            continue
        Xs, _ = build_X(sub, CORE, [])
        rs = ols_hc3(sub["ln_repost"].to_numpy(float), Xs, hc3=False)
        rows.append((title, str(lv), len(sub), rs["r2"], rs["r2a"]))

log("")
log("=" * 68)
log("分组回归 R² 明细")
log("=" * 68)
for t, lv, n, r2, r2a in rows:
    log(f"{t:<10} {lv:<8} n={n:<4} R2={'--' if r2 is None else f'{r2:.6f}'}")

with open(os.path.join(OUT, "figures_report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log("")
log(f"全部输出目录：{OUT}")
