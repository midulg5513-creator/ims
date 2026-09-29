# -*- coding: utf-8 -*-
"""在 470 条数据上预演 OLS，量化「每项数据处理能提升多少 R²」。

目的：Q2 要求把 R² 提高 50%，必须先知道在**当前样本**上基线和各种改进的 R² 各是多少，
      否则跑 Stata 就是试错。这里用纯 Python（无第三方依赖）复现 OLS 的
      SSR / SSE / SST / R² / 调整 R² / Root MSE，与 Stata 的 regress 口径一致。

口径说明：
    - Y = ln(reposts + comments + likes + 1)  （与上次上机练习一致）
    - log_followers 是 pipeline 里已有的 log10(followers)
    - 类别变量做哑变量，丢弃第一水平以避免与常数项共线
    - 注意 is_ad 与 ad_type 完全共线（is_ad=1 恰好等价于 ad_type 属于三类之一），
      所以任何含 i.ad_type 的模型都必须去掉 is_ad

用法：
    .\\weiboSpider\\venv\\Scripts\\python.exe ols_preview.py
"""

import argparse
import collections
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts.csv")
SAMPLING = os.path.join(HERE, "sampling_log.csv")
STATA = os.path.join(HERE, "stata_data.csv")
OUT_FULL = os.path.join(HERE, "stata_data.csv")     # 全样本 470
OUT_ADS = os.path.join(HERE, "stata_ads.csv")       # 路线 B：广告帖 211

LOTTERY = ("#抽奖#", "#宠粉#", "#福利#")


# ---------------------------------------------------------------- 线性代数
def solve(A, b):
    """Gauss-Jordan 解 A x = b（部分主元）。"""
    n = len(A)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for r in range(n):
            if r != col and M[r][col]:
                f = M[r][col] / pv
                for c in range(col, n + 1):
                    M[r][c] -= f * M[col][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def independent_cols(X, tol=1e-7):
    """用修正 Gram-Schmidt 找出线性无关的列。

    模拟 Stata 的 "note: X omitted because of collinearity"：遇到共线列就剔掉，
    而不是让整个估计失败。用相对范数判据（|v|/|v0|），可容忍量纲差异。
    """
    n, k = len(X), len(X[0])
    keep, basis = [], []
    for j in range(k):
        v = [X[i][j] for i in range(n)]
        nrm0 = math.sqrt(sum(x * x for x in v))
        if nrm0 == 0:
            continue
        for u in basis:
            d = sum(v[i] * u[i] for i in range(n))
            if d:
                v = [v[i] - d * u[i] for i in range(n)]
        nrm = math.sqrt(sum(x * x for x in v))
        if nrm / nrm0 > tol:
            basis.append([x / nrm for x in v])
            keep.append(j)
    return keep


def ols_regress(y, X):
    """返回 dict：参数个数、SSR(模型)、SSE(残差)、SST、R²、调整 R²、Root MSE。"""
    n = len(y)
    keep = independent_cols(X)
    dropped = len(X[0]) - len(keep)
    X = [[row[j] for j in keep] for row in X]
    k = len(keep)                    # 有效参数个数（含常数项）
    if k == 0:
        return None
    xtx = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(k)]
           for a in range(k)]
    xty = [sum(X[i][a] * y[i] for i in range(n)) for a in range(k)]
    beta = solve(xtx, xty)
    if beta is None:
        return None
    yhat = [sum(beta[a] * X[i][a] for a in range(k)) for i in range(n)]
    ybar = sum(y) / n
    sse = sum((y[i] - yhat[i]) ** 2 for i in range(n))       # 残差平方和
    sst = sum((y[i] - ybar) ** 2 for i in range(n))          # 总离差平方和
    ssr = sst - sse                                          # 回归平方和
    df_m, df_r = k - 1, n - k
    r2 = ssr / sst
    adj = 1 - (1 - r2) * (n - 1) / df_r
    return {"k": k, "n": n, "ssr": ssr, "sse": sse, "sst": sst,
            "r2": r2, "adj": adj, "rmse": math.sqrt(sse / df_r),
            "df_m": df_m, "df_r": df_r, "dropped": dropped}


# ---------------------------------------------------------------- 数据装配
def to_int(v):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return 0


def load(path):
    """读 to_stata.py 产出的分析文件（所有列都已在该文件里）。"""
    with open(path, encoding="utf-8", newline="") as f:
        st = list(csv.DictReader(f))

    rows = []
    for r in st:
        rows.append({
            "post_id": r["post_id"],
            "y_sum": math.log(to_int(r["reposts"]) + to_int(r["comments"])
                              + to_int(r["likes"]) + 1),
            "y_repost": math.log(to_int(r["reposts"]) + 1),
            "log_followers": float(r["log_followers"] or 0),
            "text_len": to_int(r["text_len"]),
            "n_images": to_int(r["n_images"]),
            "n_topics": to_int(r["n_topics"]),
            "is_ad": to_int(r["is_ad"]),
            "is_enterprise": to_int(r["is_enterprise"]),
            "is_personal_verified": to_int(r["is_personal_verified"]),
            "is_lottery": to_int(r["is_lottery"]),
            "n_mentions": to_int(r["n_mentions"]),
            "pub_hour": to_int(r["pub_hour"]),
            "is_weekend": to_int(r["is_weekend"]),
            "pub_dow": to_int(r["pub_dow"]),
            "n_promo": to_int(r["n_promo"]),
            "n_brand": to_int(r["n_brand"]),
            "kw": r["kw_stratum"] or "unknown",
            "appeal_type": r["appeal_type"] or "unknown",
            "appeal_grp": r.get("appeal_grp") or r["appeal_type"] or "unknown",
            "media_type": r["media_type"],
            "ad_type": r["ad_type"],
            "region_grp": r.get("region_grp") or r["region"] or "unknown",
        })
    return rows


# ---------------------------------------------------------------- 规格定义
NUM_COLS = {
    "log_followers": lambda r: r["log_followers"],
    "text_len": lambda r: r["text_len"],
    "log_text_len": lambda r: math.log(r["text_len"] + 1),
    "n_images": lambda r: r["n_images"],
    "n_topics": lambda r: r["n_topics"],
    "is_ad": lambda r: r["is_ad"],
    "is_enterprise": lambda r: r["is_enterprise"],
    "is_personal_verified": lambda r: r["is_personal_verified"],
    "is_lottery": lambda r: r["is_lottery"],
    "n_mentions": lambda r: r["n_mentions"],
    "pub_hour": lambda r: r["pub_hour"],
    "is_weekend": lambda r: r["is_weekend"],
    "pub_dow": lambda r: r["pub_dow"],
    "n_promo": lambda r: r["n_promo"],
    "n_brand": lambda r: r["n_brand"],
    "logf_sq": lambda r: r["log_followers"] ** 2,
    "is_ad_x_logf": lambda r: r["is_ad"] * r["log_followers"],
    "is_ad_x_video": lambda r: r["is_ad"] * (1 if r["media_type"] == "video" else 0),
}
CAT_COLS = {
    "kw": lambda r: r["kw"],
    "media_type": lambda r: r["media_type"],
    "ad_type": lambda r: r["ad_type"],
    "appeal_grp": lambda r: r["appeal_grp"],
    "region_grp": lambda r: r["region_grp"],
}

# 关键约束（都是实测撞出来的，不遵守会得到共线/无意义结果）：
#   1. is_ad 与 ad_type 是决定关系（is_ad=1 ⇔ ad_type ∈ {explicit_ad, brand_campaign, kol_collab}）
#      → 两者不能同时进模型
#   2. is_lottery=1 ⇔ kw ∈ {#抽奖#,#宠粉#,#福利#} → 与 kw 哑变量完全共线
#      → 放了 kw 就不要放 is_lottery
SPECS = [
    ("B0  上次基线 M0（7 变量）",
     ["log_followers", "text_len", "n_images", "n_topics", "is_ad",
      "is_enterprise", "is_personal_verified"], []),
    ("B1  上次精简 M1（4 变量）",
     ["log_followers", "text_len", "n_images", "is_ad"], []),
    ("S1  B1 + 抽奖哑变量",
     ["log_followers", "text_len", "n_images", "is_ad", "is_lottery"], []),
    ("S2  B1 + 抽样关键词层",
     ["log_followers", "text_len", "n_images", "is_ad"], ["kw"]),
    ("S3  S2 + 媒体类型",
     ["log_followers", "text_len", "n_images", "is_ad"], ["kw", "media_type"]),
    ("S4  S3 + 广告类型（替掉 is_ad）",
     ["log_followers", "text_len", "n_images"],
     ["kw", "media_type", "ad_type"]),
    ("S5  S4 + 地域（Top8 + 其他）",
     ["log_followers", "text_len", "n_images"],
     ["kw", "media_type", "ad_type", "region_grp"]),
    ("S6  S5 + @提及数 + 发布时间",
     ["log_followers", "text_len", "n_images", "n_mentions", "pub_hour",
      "is_weekend"],
     ["kw", "media_type", "ad_type", "region_grp"]),
    ("S7  S6 + 粉丝量二次项",
     ["log_followers", "logf_sq", "text_len", "n_images", "n_mentions",
      "pub_hour", "is_weekend"],
     ["kw", "media_type", "ad_type", "region_grp"]),
    ("S8  S6 + 促销词 + 品牌词",
     ["log_followers", "text_len", "n_images", "n_mentions", "pub_hour",
      "is_weekend", "n_promo", "n_brand"],
     ["kw", "media_type", "ad_type", "region_grp"]),
    ("S9  S8 + 星期 + 广告交互项",
     ["log_followers", "text_len", "n_images", "n_mentions", "pub_hour",
      "is_weekend", "n_promo", "n_brand", "pub_dow",
      "is_ad_x_logf", "is_ad_x_video"],
     ["kw", "media_type", "ad_type", "region_grp"]),
    ("S10 S9 + 粉丝量二次项【全合法菜单】",
     ["log_followers", "logf_sq", "text_len", "n_images", "n_mentions",
      "pub_hour", "is_weekend", "pub_dow", "n_promo", "n_brand",
      "is_ad_x_logf", "is_ad_x_video"],
     ["kw", "media_type", "ad_type", "region_grp"]),
]

# ============ 路线 B：只在广告帖内部（n=211），不需要 is_ad ============
SPECS_ADS = [
    ("A0  基线（粉丝+长度+图片+抽奖）",
     ["log_followers", "text_len", "n_images", "is_lottery"], []),
    ("A1  A0 + 粉丝量二次项",
     ["log_followers", "logf_sq", "text_len", "n_images", "is_lottery"], []),
    ("A2  A1 + @提及数",
     ["log_followers", "logf_sq", "text_len", "n_images", "is_lottery",
      "n_mentions"], []),
    ("A3  A2 + 发布时间",
     ["log_followers", "logf_sq", "text_len", "n_images", "is_lottery",
      "n_mentions", "pub_hour", "is_weekend"], []),
    ("A4  A3 + 诉求类型",
     ["log_followers", "logf_sq", "text_len", "n_images", "is_lottery",
      "n_mentions", "pub_hour", "is_weekend"], ["appeal_grp"]),
    ("A5  A4 + 媒体类型",
     ["log_followers", "logf_sq", "text_len", "n_images", "is_lottery",
      "n_mentions", "pub_hour", "is_weekend"],
     ["appeal_grp", "media_type"]),
    ("A6  A5 + 认证类型",
     ["log_followers", "logf_sq", "text_len", "n_images", "is_lottery",
      "n_mentions", "pub_hour", "is_weekend", "is_enterprise",
      "is_personal_verified"],
     ["appeal_grp", "media_type"]),
    ("A7  A6 + 促销词 + 品牌词",
     ["log_followers", "logf_sq", "text_len", "n_images", "is_lottery",
      "n_mentions", "pub_hour", "is_weekend", "is_enterprise",
      "is_personal_verified", "n_promo", "n_brand"],
     ["appeal_grp", "media_type"]),
    ("A8  A7 + 抽样关键词层",
     ["log_followers", "logf_sq", "text_len", "n_images", "is_lottery",
      "n_mentions", "pub_hour", "is_weekend", "is_enterprise",
      "is_personal_verified", "n_promo", "n_brand"],
     ["appeal_grp", "media_type", "kw"]),
    ("A9  A8 + 地域",
     ["log_followers", "logf_sq", "text_len", "n_images", "is_lottery",
      "n_mentions", "pub_hour", "is_weekend", "is_enterprise",
      "is_personal_verified", "n_promo", "n_brand"],
     ["appeal_grp", "media_type", "kw", "region_grp"]),
]


def build(rows, nums, cats):
    labels = ["_cons"]
    cols = []
    for c in nums:
        labels.append(c)
        cols.append([NUM_COLS[c](r) for r in rows])
    for c in cats:
        vals = [CAT_COLS[c](r) for r in rows]
        levels = sorted(set(vals))[1:]          # 丢第一个水平，避免与常数项共线
        for lv in levels:
            col = [1.0 if v == lv else 0.0 for v in vals]
            s = sum(col)
            # 全 0（该水平被过滤后没人了）或全 1（与常数项共线）都会让 X'X 奇异
            if s == 0 or s == len(col):
                continue
            labels.append("{}={}".format(c, lv))
            cols.append(col)
    k = len(cols) + 1
    X = []
    for i in range(len(rows)):
        X.append([1.0] + [cols[j][i] for j in range(k - 1)])
    return X, labels


def run_specs(rows, yfield, specs, title, target=None):
    ys = [r[yfield] for r in rows]
    print()
    print("### " + title + "   (n={})".format(len(rows)))
    print("  {:<32} {:>4} {:>6} {:>10} {:>10} {:>10}".format(
        "规格", "k", "共线", "R²", "调整R²", "Root MSE"))
    print("  " + "-" * 84)
    for name, nums, cats in specs:
        X, _ = build(rows, nums, cats)
        res = ols_regress(ys, X)
        if not res:
            print("  {:<32} 无法估计（矩阵奇异）".format(name))
            continue
        mark = "  <= 达标" if (target and res["r2"] >= target) else ""
        print("  {:<32} {:>4} {:>6} {:>10.6f} {:>10.6f} {:>10.4f}{}".format(
            name, res["k"], res["dropped"], res["r2"], res["adj"],
            res["rmse"], mark))


def desc_by(rows, key, yfield, label):
    """按分类变量分组描述因变量（含零值比例，因为中位数是 0 时均值会骗人）。"""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r[key]].append(r[yfield])
    print()
    print("### {}（{}）".format(label, yfield))
    print("  {:<12} {:>5} {:>8} {:>10} {:>10}".format(
        key, "n", "零值%", "中位数", "均值"))
    print("  " + "-" * 50)
    for g, vs in sorted(groups.items(), key=lambda x: -len(x[1])):
        n = len(vs)
        z = 100.0 * sum(1 for v in vs if v <= 0) / n
        med = sorted(vs)[n // 2]
        print("  {:<12} {:>5} {:>8.1f} {:>10.3f} {:>10.3f}".format(
            g, n, z, med, sum(vs) / n))


def run_route_b(rows):
    """路线 B：只在广告帖内部找转发的决定因素。"""
    print("路线 B：样本 = 广告帖，不使用 is_ad，不需要对照组")
    print("=" * 96)
    run_specs(rows, "y_repost", SPECS_ADS, "主口径 Y = ln(转发+1)", None)
    run_specs(rows, "y_sum", SPECS_ADS, "参考口径 Y = ln(转发+评论+点赞+1)", None)
    desc_by(rows, "appeal_grp", "y_repost", "诉求类型 × 转发（对数）")
    desc_by(rows, "media_type", "y_repost", "媒体类型 × 转发（对数）")
    desc_by(rows, "is_lottery", "y_repost", "是否抽奖机制 × 转发（对数）")
    print()
    print("说明：因变量已取 ln，表中「中位数 0.000」表示该组有半数帖子转发数为 0。")
    print("=" * 96)


def main():
    ap = argparse.ArgumentParser(description="OLS 预演（纯 Python，模拟 Stata regress）")
    ap.add_argument("--file", default=OUT_FULL, help="分析文件")
    ap.add_argument("--ads", action="store_true", help="路线 B：只分析广告帖样本")
    args = ap.parse_args()

    rows = load(args.file)
    TARGET_OLD = 0.41596467 * 1.5
    print("=" * 96)
    print("预演样本 n = {}   来源 {}".format(len(rows), os.path.basename(args.file)))
    if args.ads:
        run_route_b(rows)
        return
    print("作业目标锚点：上次基线 R² = 0.41596467（当时 n=83）× 1.5 = {:.6f}"
          .format(TARGET_OLD))
    print("=" * 96)

    run_specs(rows, "y_sum", SPECS,
              "Y = ln(转发+评论+点赞+1)  【与上次上机练习同口径】", TARGET_OLD)

    key = [SPECS[0], SPECS[1], SPECS[6]]
    run_specs(rows, "y_repost", key,
              "Y = ln(转发+1)  【只以转发数衡量影响力】", TARGET_OLD)

    # ---- 基线的方差分解（Q1 用） ----
    print()
    print("### 方差分解明细（B0 上次基线，n=470）")
    X, _ = build(rows, SPECS[0][1], SPECS[0][2])
    res = ols_regress([r["y_sum"] for r in rows], X)
    print("  SSR(回归平方和)   = {:.6f}".format(res["ssr"]))
    print("  SSE(残差平方和)   = {:.6f}".format(res["sse"]))
    print("  SST(总离差平方和) = {:.6f}".format(res["sst"]))
    print("  SSR + SSE         = {:.6f}   (应等于 SST)".format(res["ssr"] + res["sse"]))
    print("  df_m = {}  df_r = {}".format(res["df_m"], res["df_r"]))
    print("  MSR = SSR/df_m    = {:.6f}".format(res["ssr"] / res["df_m"]))
    print("  MSE = SSE/df_r    = {:.6f}".format(res["sse"] / res["df_r"]))
    print("  Root MSE          = {:.6f}".format(res["rmse"]))
    print("  R²    = SSR/SST   = {:.6f}".format(res["r2"]))
    print("  调整R² = 1-(1-R²)(n-1)/(n-k-1) = {:.6f}".format(res["adj"]))

    # ---- 样本处理方案对 R² 的影响（Q2 的关键杠杆） ----
    print()
    print("### 样本处理对 R² 的影响（统一用 S6 规格，Y = ln(转发+评论+点赞+1)）")
    base = [s for s in SPECS if s[0].startswith("S10")][0]
    nums, cats = base[1], base[2]
    ys_all = sorted(r["y_sum"] for r in rows)
    cap = ys_all[int(len(ys_all) * 0.99)]
    n_top = sum(1 for r in rows if r["y_sum"] > cap)
    n_lot = sum(1 for r in rows if r["is_lottery"])
    n_unk = sum(1 for r in rows if r["ad_type"] == "unknown")
    win = []
    for r in rows:
        rr = dict(r)
        rr["y_sum"] = min(r["y_sum"], cap)
        win.append(rr)

    variants = [
        ("① 全样本", rows),
        ("② 剔除影响力 Top1%（{} 条）".format(n_top),
         [r for r in rows if r["y_sum"] <= cap]),
        ("③ Y 缩尾至 P99", win),
        ("④ 剔除抽奖类（{} 条）".format(n_lot),
         [r for r in rows if not r["is_lottery"]]),
        ("⑤ 剔除 ad_type=unknown（{} 条）".format(n_unk),
         [r for r in rows if r["ad_type"] != "unknown"]),
        ("⑥ 同时剔除抽奖 + unknown",
         [r for r in rows if not r["is_lottery"] and r["ad_type"] != "unknown"]),
    ]
    print("  {:<34} {:>5} {:>6} {:>10} {:>10}".format(
        "处理", "n", "共线", "R²", "调整R²"))
    print("  " + "-" * 70)
    for label, sub in variants:
        X, _ = build(sub, nums, cats)
        res = ols_regress([r["y_sum"] for r in sub], X)
        if not res:
            print("  {:<34} 无法估计".format(label))
            continue
        print("  {:<34} {:>5} {:>6} {:>10.6f} {:>10.6f}".format(
            label, res["n"], res["dropped"], res["r2"], res["adj"]))
    print("=" * 96)


if __name__ == "__main__":
    main()
