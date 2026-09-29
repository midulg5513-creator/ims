# -*- coding: utf-8 -*-
"""变量清理与重新量化：stata_ads2.csv（211 × 61） -> stata_ads3.csv（211 × 34）

只读 stata_ads2.csv，不覆盖任何已有文件。

三类处理：
  (1) 删除 33 个变量  —— 零方差 / 完全冗余 / 事后变量 / 时间泄漏 / 平台噪声
  (2) 重命名并修正 7 个变量 —— 对数底数错误、图片数被截断、计数过度离散、稀疏分类
  (3) 新增 7 个派生变量 —— 因变量、中心化粉丝项、百字文本、时段分箱、事前历史标记

用法：D:\\python\\python.exe clean_model_vars.py
"""
import csv
import math
import os
import statistics as st
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "stata_ads2.csv")
DST = os.path.join(HERE, "stata_ads3.csv")

MISS = {"", ".", "NA", "nan", "None", "null"}

# ---------------- 删除清单（33 个）----------------
DROP = [
    # 零方差 / 近零方差：进模型必被 Stata 剔除，或只由 3 条驱动
    "is_ad",            # 211/211 恒等于 1（该表本身就是仅广告帖样本）
    "pd_ok",            # 208/211 = 1，只有 3 条 0，是采集质量标记不是解释变量
    "is_hot_topic",     # 只有 3 条 = 1
    # 完全冗余：与保留变量一一对应（已实测 211/211 完全一致）
    "has_ext_link",     # ≡ (link_grp != none)
    "is_video_link",    # ≡ (link_grp == video_weibo)
    "is_lottery_link",  # ≡ (link_grp == lottery_weibo)
    "appeal_lottery",   # ≡ is_lottery（rho = 1.0000）
    "appeal_price",     # ≡ (n_promo >= 1)（rho = 0.8632）
    "appeal_review",    # 与 appeal_type / appeal_grp 同源（非互斥原始标记）
    "appeal_official",  # 同上
    "appeal_explicit",  # 同上
    "appeal_type",      # 与 appeal_grp 同源，保留合并版即可
    "pub_dow",          # ≡ is_weekend 的信息（weekend = dow ∈ {5,6}）
    "det_text_len",     # 与 text_len 同测（rho = 0.9952）
    "det_pic_num",      # 信息已并入 n_pics（详情接口口径），不单列
    # 事后变量：与因变量同期形成，进解释变量＝循环论证
    "cmt_total",        # 评论总数（= comments 的另一口径），且缺失 41.2%
    "cmt_deep_n",       # 深挖评论条数
    "aud_fol_med",      # 评论者粉丝中位数，缺失 41.2%
    "aud_ver_share",    # 评论者认证占比，缺失 41.2%
    # 时间泄漏 / 口径混乱的作者历史
    "hist_avg_lnengage",  # 混入目标帖与后发帖（文档已标注不可用）
    "hist_avg_reposts",   # 与 hist_prior 同族，rho(非广告均值) = 0.9602
    "hist_med_reposts",   # 与因变量 rho = 0.9179（被少数爆款拉动），中位 0 无分辨力
    "hist_n",             # 含目标帖与未来帖的抓取总数，与 hist_prior_n 共线
    "hist_prior_n",       # 与 has_prior_hist 高度共线，保留标记即可
    "non_ad_n",           # 与 hist_n 同源（rho = 0.8272）
    "non_ad_avg_reposts", # 缺失 + 与 hist_avg_reposts 重复（rho = 0.9602）
    "prof_followers",     # 同帖作者主页粉丝：93/211 为 0（缺失写成 0），与 followers rho = 0.9663
    "prof_statuses",      # 平台状态字段，无理论支撑
    # 三版广告密度里只留中间版；另两版一个被视频卡片污染、一个几乎零方差
    "ad_density_wide",    # 混入 37.9% 的视频卡片伪外链
    "ad_density_strict",  # 均值 0.0132，近零方差
    # 无理论支撑的平台字段 / 稀疏分类
    "source_grp",         # 发布工具（客户端/视频频道/超话），与传播机制无关
    "ptype_grp",          # 落地页类型，6 类中 2 类 n<5
    "region",             # 30 个省/地区，18 个 n<5；保留归并版 region_grp
]

# ---------------- 重命名 / 重新量化 ----------------
RENAME = {
    "log_followers": "ln_followers",              # 原列实为 log10，非自然对数
    "log_age_hours": "ln_age_hours",              # 统一 ln 命名
    "hist_prior_avg_lnengage": "hist_prior_lnengage",
    "n_images": "n_pics",                         # 原 n_images 被采集器截断在 9
    "n_mentions": "n_mentions_c",                 # 极端右偏，额外提供 0/1/2/3+ 截尾版（原始计数也保留）
    "kw_stratum": "kw_grp",                       # 16 层中 8 层 n<5，按主题归并
}

# 抽样关键词 -> 归并层（每层 n >= 20）
KW_MAP = {
    "#广告#": "广告标签",
    "#新品发布#": "新品上新", "上新": "新品上新", "#联名款#": "新品上新", "首发": "新品上新",
    "#抽奖#": "抽奖导流",
    "品牌合作": "品牌合作", "#品牌日#": "品牌合作",
}
KW_OTHER = "种草优惠"   # 限时优惠/优惠/开箱/种草/推荐/好物推荐/安利/带货

# 地域 -> 归并（n>=10 才单列，其余进「其他」；unknown 单列）
REG_KEEP = ["广东", "上海", "北京", "浙江", "四川", "江苏"]

PUB_PERIOD = [
    (0, 6, "深夜"), (7, 9, "早间"), (10, 12, "上午"),
    (13, 17, "下午"), (18, 23, "晚间"),
]

OUT_COLS = [
    "post_id", "author_id",
    "reposts", "comments", "likes", "ln_repost",
    "followers", "ln_followers", "lnf_c", "lnf_c2",
    "is_enterprise", "is_personal_verified",
    "hist_prior_lnengage", "hist_prior_lnengage0", "has_prior_hist", "ad_density",
    "text_len", "text_len100", "n_pics", "media_type",
    "n_topics", "n_mentions", "n_mentions_c", "n_promo", "n_brand",
    "appeal_grp", "is_lottery", "ad_type", "link_grp",
    "age_hours", "ln_age_hours", "pub_hour", "pub_period", "is_weekend",
    "region_grp", "kw_grp",
]


def rd(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        cols = list(rdr.fieldnames)
        return cols, list(rdr)


def f(v, d=None):
    if v is None:
        return d
    v = str(v).strip()
    if v in MISS:
        return d
    try:
        return float(v)
    except ValueError:
        return d


def r6(x):
    return round(x, 6)


def r12(x):
    """派生对数变量保留 12 位小数：6 位会让 SST 等平方和与直接计算的版本差 1e-6。"""
    return round(x, 12)


def main():
    cols, rows = rd(SRC)
    for c in DROP:
        if c not in cols:
            print("[!] 删除清单中的 {} 不在原表列中，请检查".format(c))
    for a, b in RENAME.items():
        if a not in cols:
            print("[!] 重命名清单中的 {} 不在原表列中，请检查".format(a))
    if "n_images" not in cols or "det_pic_num" not in cols:
        print("[x] 缺少 n_images / det_pic_num，无法重建图片数")
        return 1

    # 中心化基准
    lnf = [math.log(f(r["followers"])) for r in rows]
    lnf_mean = sum(lnf) / len(lnf)

    out = []
    for r, lnf_i in zip(rows, lnf):
        o = {}
        o["post_id"] = r["post_id"]
        o["author_id"] = r["author_id"]

        # --- 因变量 ---
        reposts = f(r["reposts"], 0.0)
        o["reposts"] = int(reposts)
        o["comments"] = int(f(r["comments"], 0.0))
        o["likes"] = int(f(r["likes"], 0.0))
        o["ln_repost"] = r12(math.log(reposts + 1.0))

        # --- 粉丝规模：改正对数底数 + 中心化消除 x 与 x² 的机械共线 ---
        o["followers"] = int(f(r["followers"], 0.0))
        o["ln_followers"] = r12(lnf_i)
        o["lnf_c"] = r12(lnf_i - lnf_mean)
        o["lnf_c2"] = r12((lnf_i - lnf_mean) ** 2)

        o["is_enterprise"] = int(f(r["is_enterprise"], 0.0))
        o["is_personal_verified"] = int(f(r["is_personal_verified"], 0.0))

        # --- 事前作者互动质量：保留缺失，另给 0 填充版 + 标记 ---
        hp = f(r["hist_prior_avg_lnengage"])
        o["hist_prior_lnengage"] = "" if hp is None else r12(hp)
        o["hist_prior_lnengage0"] = 0.0 if hp is None else r12(hp)
        o["has_prior_hist"] = 0 if hp is None else 1

        ad = f(r["ad_density"])
        o["ad_density"] = "" if ad is None else r6(ad)

        # --- 内容特征 ---
        tl = f(r["text_len"], 0.0)
        o["text_len"] = int(tl)
        o["text_len100"] = r6(tl / 100.0)

        # 图片数：n_images 被采集器截断在 9，用详情接口的 det_pic_num 补齐上限
        o["n_pics"] = int(max(f(r["n_images"], 0.0), f(r["det_pic_num"], 0.0)))

        o["media_type"] = r["media_type"]
        o["n_topics"] = int(f(r["n_topics"], 0.0))

        # @提及数：保留原始计数（均值 0.41、偏度 6.03）；
        # n_mentions_c 是 3+ 以上合并的截尾版，作稳健性检验用
        nm = int(f(r["n_mentions"], 0.0))
        o["n_mentions"] = nm
        o["n_mentions_c"] = 3 if nm >= 3 else nm

        o["n_promo"] = int(f(r["n_promo"], 0.0))
        o["n_brand"] = int(f(r["n_brand"], 0.0))

        # --- 诉求 / 机制 ---
        o["appeal_grp"] = r["appeal_grp"]
        o["is_lottery"] = int(f(r["is_lottery"], 0.0))
        o["ad_type"] = r["ad_type"]

        # 外链去向：lottery_weibo(7) / passport(5) 太薄，并入 other
        g = r["link_grp"]
        o["link_grp"] = "video" if g == "video_weibo" else ("none" if g == "none" else "other")

        # --- 时间 ---
        ah = f(r["age_hours"], 0.0)
        o["age_hours"] = r6(ah)
        o["ln_age_hours"] = r12(math.log1p(ah))
        ph = int(f(r["pub_hour"], 0.0))
        o["pub_hour"] = ph
        o["pub_period"] = next(lab for lo, hi, lab in PUB_PERIOD if lo <= ph <= hi)
        o["is_weekend"] = int(f(r["is_weekend"], 0.0))

        # --- 地域：n<5 的层并入「其他」 ---
        rg = r["region_grp"]
        if rg in REG_KEEP:
            o["region_grp"] = rg
        elif str(rg).lower() == "unknown":
            o["region_grp"] = "未知"
        else:
            o["region_grp"] = "其他"

        # --- 抽样关键词层：归并到 4 层 ---
        kw = r["kw_stratum"]
        o["kw_grp"] = KW_MAP.get(kw, KW_OTHER)

        out.append(o)

    with open(DST, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(out)

    # ================= 校验报告 =================
    print("=" * 74)
    print("源表 {} ：{} 行 × {} 列".format(os.path.basename(SRC), len(rows), len(cols)))
    print("新表 {} ：{} 行 × {} 列".format(os.path.basename(DST), len(out), len(OUT_COLS)))
    print("删除 {} 列，重命名/重编码 {} 列，新增 {} 列".format(
        len(DROP), len(RENAME),
        len([c for c in OUT_COLS if c not in cols and c not in RENAME.values()])))
    print("=" * 74)

    IDS = {"post_id", "author_id"}

    def is_num_col(c):
        vals = [str(r[c]).strip() for r in out]
        nonmiss = [v for v in vals if v not in MISS]
        if not nonmiss:
            return False
        return sum(1 for v in nonmiss if f(v) is not None) / len(nonmiss) >= 0.95

    num_cols = [c for c in OUT_COLS if c not in IDS and is_num_col(c)]
    cats = [c for c in OUT_COLS if c not in IDS and c not in num_cols]

    print("\n【1】数值变量：缺失 / 唯一值 / 极值 / 方差")
    print("{:<24} {:>5} {:>8} {:>10} {:>10} {:>10} {:>8} {:>9} {:>7}".format(
        "变量", "nMiss", "唯一值", "min", "max", "mean", "sd", "p50", "偏度"))
    bad = []
    for c in num_cols:
        vals = [f(r[c]) for r in out]
        nm = [v for v in vals if v is not None]
        if not nm:
            continue
        mean = sum(nm) / len(nm)
        sd = st.pstdev(nm) if len(nm) > 1 else 0.0
        med = st.median(nm)
        sk = (sum(((v - mean) / sd) ** 3 for v in nm) / len(nm)) if sd > 0 else 0.0
        flag = ""
        if sd == 0:
            flag = "  <== 零方差"
            bad.append(c)
        print("{:<24} {:>5} {:>8} {:>10.4g} {:>10.4g} {:>10.4g} {:>8.4g} {:>9.4g} {:>7.2f}{}".format(
            c, len(vals) - len(nm), len(set(nm)), min(nm), max(nm), mean, sd, med, sk, flag))

    print("\n【2】分类变量：水平数与各层条数（要求每层 n ≥ 5）")
    for c in cats:
        cnt = Counter(str(r[c]).strip() for r in out)
        small = {k: v for k, v in cnt.items() if v < 5}
        print("  {:<16} {:>2} 层  {}".format(
            c, len(cnt), "全部 ≥5 ✅" if not small else "⚠️ 稀疏层 {}".format(small)))
        for k, v in cnt.most_common():
            print("        {:<12} {:>4}".format(k if k else "(空)", v))

    print("\n【3】与旧变量的对照校验（应逐行一致）")
    checks = [
        ("ln_repost == ln(reposts+1)",
         lambda r: f(r["ln_repost"]),
         lambda r: round(math.log(f(r["reposts"], 0) + 1), 6)),
        ("ln_followers == ln(followers)",
         lambda r: f(r["ln_followers"]),
         lambda r: round(math.log(f(r["followers"], 1)), 6)),
        ("ln_age_hours == ln(1+age_hours)",
         lambda r: f(r["ln_age_hours"]),
         lambda r: round(math.log1p(f(r["age_hours"], 0)), 6)),
        ("is_lottery 与旧表一致",
         lambda r: f(r["is_lottery"]),
         lambda r: f(r["appeal_lottery"])),
    ]
    old = {r["post_id"]: r for r in rows}
    for name, new_fn, old_fn in checks:
        diff = 0
        for r in out:
            a, b = new_fn(r), old_fn(old[r["post_id"]])
            if a is None or b is None:
                continue
            if abs(a - b) > 1e-5:
                diff += 1
        print("  {:<34} 不一致 = {}".format(name, diff))

    print("\n【4】因变量分布（ln_repost）")
    y = sorted(f(r["ln_repost"]) for r in out)
    print("  n={} min={:.4f} p25={:.4f} p50={:.4f} p75={:.4f} max={:.4f} mean={:.4f}".format(
        len(y), y[0], y[len(y) // 4], y[len(y) // 2], y[3 * len(y) // 4], y[-1],
        sum(y) / len(y)))
    print("  零转发占比 = {:.4f}".format(
        sum(1 for r in out if f(r["reposts"]) == 0) / float(len(out))))

    print("\n【5】被删除的 {} 个变量".format(len(DROP)))
    for i in range(0, len(DROP), 4):
        print("  " + "  ".join("{:<22}".format(x) for x in DROP[i:i + 4]))

    if bad:
        print("\n[!] 仍有零方差变量：{}".format(bad))
    else:
        print("\n[OK] 新表无零方差变量。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
