# -*- coding: utf-8 -*-
"""把 clean_posts.csv 转换成 Stata 可直接 import 的数据集。

中文列名 → ASCII 变量名（Stata 变量名不支持中文）。
输出：stata_data.csv（UTF-8 无 BOM，Stata import delimited 直接读）

用法：
    .\\weiboSpider\\venv\\Scripts\\python.exe to_stata.py
"""

import collections
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS_CSV = os.path.join(HERE, "posts.csv")
CLEAN_CSV = os.path.join(HERE, "clean_posts.csv")
SAMPLING_CSV = os.path.join(HERE, "sampling_log.csv")
OUT_CSV = os.path.join(HERE, "stata_data.csv")

# 输出列：clean_posts.csv 的中文列名 -> Stata 变量名
COLUMN_MAP = [
    ("转发数", "reposts"),
    ("评论数", "comments"),
    ("点赞数", "likes"),
    ("是否广告", "is_ad"),
    ("促销词数量", "n_promo"),
    ("品牌词数量", "n_brand"),
    ("话题词数量", "n_topics"),
    ("文本长度", "text_len"),
    ("图片数量", "n_images"),
    ("粉丝数", "followers"),
    ("对数粉丝数", "log_followers"),
    ("是否企业账号", "is_enterprise"),
    ("个人认证账号", "is_personal_verified"),
]

# posts.csv 中直接带入的分类字段（用于分组回归）
CATEGORY_MAP = [
    ("ad_type", "ad_type"),
    ("media_type", "media_type"),
]

# ---- 路线 B（只在广告帖内部做）所需的派生变量 ----
# 诉求类型词表：从**内容**识别广告的诉求，与采集器的 ad_type 判定规则解耦。
# 原因：ad_type 是"判定来源"（explicit_ad / brand_campaign / kol_collab）而非内容类型，
#       且 254 条 unknown 无法归类；做分组回归必须用内容维度。
LOTTERY_WORDS = ["抽奖", "转发抽", "关注+转发", "关注并转发", "评论区抽",
                 "转发微博抽", "中奖", "开奖", "转发本条", "宠粉", "福利",
                 "免费送", "送福利", "抽送", "蹲一个"]
REVIEW_WORDS = ["种草", "测评", "实测", "开箱", "安利", "好物推荐", "推荐",
                "回购", "拔草", "评测", "试色", "上身效果"]
OFFICIAL_WORDS = ["新品发布", "首发", "上新", "联名", "代言", "官宣", "限定",
                  "品牌日", "全新上市", "携手", "全球首", "发布即"]
# 只打广告标签、没有任何诉求内容的帖子（硬广口播/形象广告），单列一类，
# 否则它们会全部堆进「无诉求信号」，让分组回归里出现一块无法解释的大类
EXPLICIT_WORDS = ["广告", "赞助", "sponsored", "推广合作", "商务合作", "AD"]

# 广告帖子样本（路线 B 的分析文件）
ADS_CSV = os.path.join(HERE, "stata_ads.csv")

# 从 created_at / collected_at 派生的外生时间特征。
# 注意：微博用户行为按北京时间理解，所以转成 UTC+8 后再取小时/星期。
# posts.csv 里没有「发布工具」列（那是 weiboSpider 的字段，本采集器按 spec 不输出）。
OUT_HEADERS = (["post_id", "author_id"] + [v for _, v in COLUMN_MAP]
               + [v for _, v in CATEGORY_MAP]
               + ["pub_hour", "pub_dow", "is_weekend", "age_hours", "log_age_hours",
                  "region", "region_grp",
                  "kw_stratum", "n_mentions", "is_lottery",
                  "appeal_lottery", "appeal_price", "appeal_review",
                  "appeal_official", "appeal_explicit", "appeal_type",
                  "appeal_grp"])


def parse_utc(s):
    """Parse the ISO timestamp used by posts.csv as a timezone-aware UTC datetime."""
    if not s:
        return None
    import datetime as _dt
    txt = s.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        value = _dt.datetime.fromisoformat(txt)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=_dt.timezone.utc)
    return value.astimezone(_dt.timezone.utc)


def parse_created_at(s):
    """'2026-08-06T07:58:56Z' (UTC) -> 北京时间 (hour, weekday, is_weekend)。

    解析失败返回 (None, None, None)。
    """
    if not s:
        return None, None, None
    value = parse_utc(s)
    if value is None:
        return None, None, None
    # UTC -> 北京时间
    import datetime as _dt
    local = value + _dt.timedelta(hours=8)
    return local.hour, local.weekday(), (1 if local.weekday() >= 5 else 0)


def main():
    if not os.path.isfile(CLEAN_CSV):
        print("[x] 找不到 {}，请先运行 clean_data.py".format(CLEAN_CSV))
        return 1
    if not os.path.isfile(POSTS_CSV):
        print("[x] 找不到 {}".format(POSTS_CSV))
        return 1

    # 读 clean_posts.csv（含派生列）
    with open(CLEAN_CSV, encoding="utf-8-sig", newline="") as f:
        clean_rows = list(csv.DictReader(f))
    # 读 posts.csv（取 post_id / author_id 作为标识）
    with open(POSTS_CSV, encoding="utf-8-sig", newline="") as f:
        post_rows = list(csv.DictReader(f))

    if len(clean_rows) != len(post_rows):
        print("[!] 行数不一致：clean={} posts={}，按较小值截断".format(
            len(clean_rows), len(post_rows)))
    n = min(len(clean_rows), len(post_rows))

    # 抽样关键词层（来自 sampling_log.csv）：这是**抽样设计变量**，
    # 不控制它，类型系数里会混进"是哪个关键词召回的帖子"
    kw_map = {}
    if os.path.isfile(SAMPLING_CSV):
        with open(SAMPLING_CSV, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                kw_map[r["post_id"]] = r.get("keyword") or "unknown"

    # 地域归并：全样本频次 Top8 单列，其余合并为「其他」
    reg_count = collections.Counter(
        (p.get("region_name") or "unknown") for p in post_rows[:n])
    top_reg = {k for k, _ in reg_count.most_common(8)}

    out = []
    for i in range(n):
        c = clean_rows[i]
        p = post_rows[i]
        row = {"post_id": p.get("post_id", ""), "author_id": p.get("author_id", "")}
        for cn, en in COLUMN_MAP:
            row[en] = c.get(cn, "")
        for src, dst in CATEGORY_MAP:
            row[dst] = p.get(src, "")
        h, dow, wk = parse_created_at(p.get("created_at", ""))
        row["pub_hour"] = "" if h is None else h
        row["pub_dow"] = "" if dow is None else dow
        row["is_weekend"] = "" if wk is None else wk
        created = parse_utc(p.get("created_at", ""))
        collected = parse_utc(p.get("collected_at", ""))
        if created is None or collected is None:
            row["age_hours"] = ""
            row["log_age_hours"] = ""
        else:
            age_hours = max((collected - created).total_seconds() / 3600.0, 1.0 / 60.0)
            row["age_hours"] = round(age_hours, 6)
            row["log_age_hours"] = round(math.log1p(age_hours), 8)
        region = p.get("region_name", "") or "unknown"
        row["region"] = region
        row["region_grp"] = region if region in top_reg else "其他"

        # ---- 路线 B 的派生变量 ----
        # is_lottery 用**内容**判定（机制性激励），kw_stratum 是抽样来源，两者是不同东西
        blob = (p.get("text") or "") + " " + (p.get("hashtags") or "").replace("|", " ")
        lot = 1 if any(w in blob for w in LOTTERY_WORDS) else 0
        rev = 1 if any(w in blob for w in REVIEW_WORDS) else 0
        off = 1 if any(w in blob for w in OFFICIAL_WORDS) else 0
        exp = 1 if any(w in blob for w in EXPLICIT_WORDS) else 0
        try:
            pri = 1 if int(c.get("促销词数量") or 0) >= 1 else 0
        except (ValueError, TypeError):
            pri = 0
        # 互斥分类：机制性激励 > 价格刺激 > 内容种草 > 品牌官宣 > 硬广标识
        if lot:
            appeal = "抽奖导流"
        elif pri:
            appeal = "价格促销"
        elif rev:
            appeal = "种草测评"
        elif off:
            appeal = "品牌官宣"
        elif exp:
            appeal = "硬广标识"
        else:
            appeal = "无诉求信号"
        # 分组回归用的合并版：种草测评与无诉求信号都属「内容植入、无硬性诉求导流」，
        # 各自只有 16 / 14 条，单跑回归会过拟合，合并成一组
        if appeal in ("种草测评", "无诉求信号"):
            appeal_grp = "软植入"
        else:
            appeal_grp = appeal

        row["kw_stratum"] = kw_map.get(p.get("post_id"), "unknown")
        row["n_mentions"] = len(
            [m for m in (p.get("mentions") or "").split("|") if m])
        row["is_lottery"] = lot
        row["appeal_lottery"] = lot
        row["appeal_price"] = pri
        row["appeal_review"] = rev
        row["appeal_official"] = off
        row["appeal_explicit"] = exp
        row["appeal_type"] = appeal
        row["appeal_grp"] = appeal_grp
        out.append(row)

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_HEADERS)
        w.writeheader()
        w.writerows(out)

    # 路线 B 的分析文件：只保留广告帖
    ads = [r for r in out if str(r.get("is_ad")).strip() == "1"]
    with open(ADS_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_HEADERS)
        w.writeheader()
        w.writerows(ads)

    # ---- 零方差变量检查（会被 Stata 剔除，提前提示）----
    print("[i] 写出 {} 行 -> {}".format(len(out), OUT_CSV))
    print("[i] 写出 {} 行（广告帖子样本）-> {}".format(len(ads), ADS_CSV))
    print()
    print("--- 路线 B 派生变量检查（全样本 / 广告帖子样本）---")
    for col in ("is_lottery", "appeal_lottery", "appeal_price",
                "appeal_review", "appeal_official", "appeal_explicit"):
        a = sum(1 for r in out if str(r[col]) == "1")
        b = sum(1 for r in ads if str(r[col]) == "1")
        print("  {:<18} 全样本 {:>4}   广告帖 {:>4}".format(col, a, b))
    print()
    print("  appeal_type 互斥分类：")
    cnt_all = collections.Counter(r["appeal_type"] for r in out)
    cnt_ads = collections.Counter(r["appeal_type"] for r in ads)
    print("    {:<12} {:>8} {:>8}".format("类型", "全样本", "广告帖"))
    for k, v in cnt_ads.most_common():
        print("    {:<12} {:>8} {:>8}".format(k, cnt_all.get(k, 0), v))
    print()
    print("  广告帖样本的 kw_stratum 分布（抽样设计变量）：")
    for k, v in collections.Counter(r["kw_stratum"] for r in ads).most_common():
        print("    {:<12} {}".format(k, v))
    print()
    print("  media_type 分布（广告帖样本）：")
    for k, v in collections.Counter(r["media_type"] for r in ads).most_common():
        print("    {:<12} {}".format(k, v))
    print()
    print("  region_grp 分布（广告帖样本）：")
    for k, v in collections.Counter(r["region_grp"] for r in ads).most_common():
        print("    {:<12} {}".format(k, v))
    print()
    print()
    print("--- 变量检查 ---")
    print("  {:<22} {:>5}  {:>6}  {:>8}  {:>8}".format(
        "变量", "n", "非零", "min", "max"))
    zero_var = []
    for _, en in COLUMN_MAP:
        vals = []
        for r in out:
            try:
                vals.append(float(r[en]))
            except (ValueError, TypeError):
                pass
        if not vals:
            continue
        nz = sum(1 for v in vals if v != 0)
        flag = ""
        if min(vals) == max(vals):
            flag = "  <== 零方差，Stata 会剔除"
            zero_var.append(en)
        print("  {:<22} {:>5}  {:>6}  {:>8}  {:>8}{}".format(
            en, len(vals), nz, round(min(vals), 4), round(max(vals), 4), flag))

    if zero_var:
        print()
        print("[!] 以下变量无变异，不会进入回归：{}".format(", ".join(zero_var)))
        print("    原因：对应的词表（brands.txt / promo_words.txt）还是空的。")

    # ---- 因变量描述 ----
    print()
    print("--- 因变量 influence = ln(reposts+comments+likes+1) ---")
    ys = []
    for r in out:
        try:
            v = float(r["reposts"]) + float(r["comments"]) + float(r["likes"])
            ys.append(math.log(v + 1))
        except (ValueError, TypeError):
            continue
    if ys:
        ys_sorted = sorted(ys)
        print("  n={}  min={:.4f}  max={:.4f}  mean={:.4f}  median={:.4f}".format(
            len(ys), ys_sorted[0], ys_sorted[-1],
            sum(ys) / len(ys), ys_sorted[len(ys_sorted) // 2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
