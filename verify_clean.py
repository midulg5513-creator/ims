# -*- coding: utf-8 -*-
"""校验清洗链路：posts.csv -> clean_posts.csv -> stata_data.csv

重点校验 to_stata.py 的「按行号位置对齐」假设：
clean_posts.csv 里没有 post_id，两张表只能靠顺序对应，一旦顺序错位就会
静默把 A 帖的粉丝数配到 B 帖的转发数上。这里逐行回归验算。

用法：
    .\\weiboSpider\\venv\\Scripts\\python.exe verify_clean.py
"""

import csv
import datetime as dt
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts.csv")
CLEAN = os.path.join(HERE, "clean_posts.csv")
STATA = os.path.join(HERE, "stata_data.csv")
ADS_CSV = os.path.join(HERE, "stata_ads.csv")

EXPECT_CLEAN_HEADER = [
    "用户名", "转发数", "评论数", "点赞数", "是否广告",
    "促销词数量", "品牌词数量", "话题词数量", "文本长度", "图片数量",
    "粉丝数", "对数粉丝数", "对数转发", "是否企业账号", "个人认证账号",
]

EXPECT_STATA_HEADER = [
    "post_id", "author_id", "reposts", "comments", "likes", "is_ad",
    "n_promo", "n_brand", "n_topics", "text_len", "n_images", "followers",
    "log_followers", "is_enterprise", "is_personal_verified",
    "ad_type", "media_type", "pub_hour", "pub_dow", "is_weekend",
    "age_hours", "log_age_hours", "region",
    "region_grp", "kw_stratum", "n_mentions", "is_lottery",
    "appeal_lottery", "appeal_price", "appeal_review", "appeal_official",
    "appeal_explicit", "appeal_type", "appeal_grp",
]

NUMERIC_STATA = ["reposts", "comments", "likes", "is_ad", "n_promo", "n_brand",
                 "n_topics", "text_len", "n_images", "followers",
                 "log_followers", "is_enterprise", "is_personal_verified",
                 "pub_hour", "pub_dow", "is_weekend", "age_hours", "log_age_hours"]


def read(path, enc):
    with open(path, encoding=enc, newline="") as f:
        r = csv.DictReader(f)
        return list(r), r.fieldnames


def to_int(v):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return 0


def main():
    posts, _ = read(POSTS, "utf-8-sig")
    clean, chead = read(CLEAN, "utf-8-sig")
    stata, shead = read(STATA, "utf-8")

    ok = True
    print("=" * 62)
    print("行数")
    print("  posts.csv        :", len(posts))
    print("  clean_posts.csv  :", len(clean))
    print("  stata_data.csv   :", len(stata))
    if not (len(posts) == len(clean) == len(stata)):
        print("  [x] 三张表行数不一致 -> 位置对齐必然错位")
        ok = False
    else:
        print("  [v] 三张表行数一致")

    print()
    print("表头")
    if chead == EXPECT_CLEAN_HEADER:
        print("  [v] clean_posts.csv 表头与目标表完全一致（含顺序）")
    else:
        print("  [x] clean_posts.csv 表头不符")
        print("      实际:", chead)
        ok = False
    if shead == EXPECT_STATA_HEADER:
        print("  [v] stata_data.csv 表头与预期一致（含顺序）")
    else:
        print("  [x] stata_data.csv 表头不符")
        print("      实际:", shead)
        ok = False

    # ---- UTC/北京时间派生字段回归验算 ----
    print()
    print("位置对齐逐行验算（比对 4 个可回溯字段）")
    mismatch = {"post_id": 0, "author_id": 0, "reposts": 0, "likes": 0,
                "followers": 0, "pub_hour": 0, "age_hours": 0}
    for i, (p, c, s) in enumerate(zip(posts, clean, stata)):
        if s["post_id"] != p["post_id"]:
            mismatch["post_id"] += 1
        if s["author_id"] != p["author_id"]:
            mismatch["author_id"] += 1
        if to_int(s["reposts"]) != to_int(p["reposts_count"]):
            mismatch["reposts"] += 1
        if to_int(s["likes"]) != to_int(p["attitudes_count"]):
            mismatch["likes"] += 1
        if to_int(s["followers"]) != to_int(p["author_followers"]):
            mismatch["followers"] += 1
        if c["用户名"] != (p["author_name"] or ""):
            ok = False
            mismatch.setdefault("author_name", 0)
            mismatch["author_name"] += 1
        # pub_hour：created_at(UTC) + 8h
        ca = (p["created_at"] or "").strip()
        try:
            d = dt.datetime.strptime(ca, "%Y-%m-%dT%H:%M:%SZ") + dt.timedelta(hours=8)
            if int(s["pub_hour"]) != d.hour or int(s["pub_dow"]) != d.weekday():
                mismatch["pub_hour"] += 1
            if int(s["is_weekend"]) != (1 if d.weekday() >= 5 else 0):
                mismatch["pub_hour"] += 1
        except ValueError:
            pass
        try:
            created = dt.datetime.fromisoformat((p["created_at"] or "").replace("Z", "+00:00"))
            collected = dt.datetime.fromisoformat((p["collected_at"] or "").replace("Z", "+00:00"))
            age = max((collected - created).total_seconds() / 3600.0, 1.0 / 60.0)
            if abs(float(s["age_hours"]) - age) > 1e-5:
                mismatch["age_hours"] += 1
            if abs(float(s["log_age_hours"]) - math.log1p(age)) > 1e-7:
                mismatch["age_hours"] += 1
        except (ValueError, TypeError):
            mismatch["age_hours"] += 1
    for k, v in mismatch.items():
        tag = "[v]" if v == 0 else "[x]"
        if v:
            ok = False
        print("  {} {:<12} 不符 {} 行".format(tag, k, v))

    # ---- 派生列回归验算 ----
    print()
    print("派生列验算（对数粉丝数 / 对数转发 / 是否广告）")
    bad_logf = bad_logr = bad_ad = bad_inf = 0
    for p, c in zip(posts, clean):
        f = to_int(p["author_followers"])
        r = to_int(p["reposts_count"])
        exp_f = 0 if f <= 0 else round(math.log10(f), 4)
        try:
            if abs(float(c["对数粉丝数"]) - exp_f) > 1e-4:
                bad_logf += 1
        except ValueError:
            bad_logf += 1
        exp_r = 0 if r + 1 <= 0 else round(math.log10(r + 1), 4)
        try:
            if abs(float(c["对数转发"]) - exp_r) > 1e-4:
                bad_logr += 1
        except ValueError:
            bad_logr += 1
        if to_int(c["是否广告"]) != (1 if p["is_ad_labeled"].lower() == "true" else 0):
            bad_ad += 1
    for name, v in (("对数粉丝数", bad_logf), ("对数转发", bad_logr),
                    ("是否广告", bad_ad)):
        tag = "[v]" if v == 0 else "[x]"
        if v:
            ok = False
        print("  {} {:<10} 不符 {} 行".format(tag, name, v))

    # ---- influence 与零方差 ----
    print()
    ys = [math.log(to_int(s["reposts"]) + to_int(s["comments"])
                   + to_int(s["likes"]) + 1) for s in stata]
    print("  influence: n={} min={:.4f} max={:.4f} mean={:.4f}".format(
        len(ys), min(ys), max(ys), sum(ys) / len(ys)))

    # ---- 空值 / 缺失 ----
    print()
    print("stata_data.csv 空值检查")
    empty = 0
    for col in NUMERIC_STATA:
        n = sum(1 for s in stata if s[col].strip() == "")
        if n:
            print("  [x] {} 有 {} 行为空 -> Stata 会读成缺失值".format(col, n))
            empty += n
    if not empty:
        print("  [v] 所有数值列无空值")
    for col in ("ad_type", "media_type", "region"):
        n = sum(1 for s in stata if s[col].strip() == "")
        if n:
            print("  [!] {} 有 {} 行为空".format(col, n))

    print()
    print("region（帖子归属地）取值分布 Top 12")
    reg = {}
    for s in stata:
        reg[s["region"]] = reg.get(s["region"], 0) + 1
    for k, v in sorted(reg.items(), key=lambda x: -x[1])[:12]:
        print("  {:<14} {}".format(k or "(空)", v))

    # ---- 路线 B 分析文件 ----
    print()
    print("=" * 62)
    print("路线 B 分析文件 stata_ads.csv")
    if not os.path.isfile(ADS_CSV):
        print("  [x] 不存在（需运行 to_stata.py）")
        ok = False
    else:
        ads, ahead = read(ADS_CSV, "utf-8")
        n_ads = sum(1 for s in stata if to_int(s["is_ad"]) == 1)
        if ahead != EXPECT_STATA_HEADER:
            print("  [x] 表头与 stata_data.csv 不一致")
            ok = False
        else:
            print("  [v] 表头与 stata_data.csv 一致")
        if len(ads) == n_ads:
            print("  [v] 行数 {} 与全样本里 is_ad=1 的条数一致".format(len(ads)))
        else:
            print("  [x] 行数 {} != 全样本 is_ad=1 的 {} 条".format(len(ads), n_ads))
            ok = False
        bad = sum(1 for s in ads if to_int(s["is_ad"]) != 1)
        if bad:
            print("  [x] 有 {} 行 is_ad != 1（筛选写错了）".format(bad))
            ok = False
        else:
            print("  [v] 全部行的 is_ad 都等于 1")
        ids_ads = {s["post_id"] for s in ads}
        ids_full = {s["post_id"] for s in stata}
        if ids_ads - ids_full:
            print("  [x] 有 post_id 不在全样本里")
            ok = False
        else:
            print("  [v] 所有 post_id 都能在全样本里找到")
        for col in NUMERIC_STATA + ["is_lottery", "appeal_lottery",
                                    "appeal_price", "appeal_review",
                                    "appeal_official", "appeal_explicit"]:
            if col not in ahead:
                continue
            n = sum(1 for s in ads if s[col].strip() == "")
            if n:
                print("  [x] {} 有 {} 行为空".format(col, n))
                ok = False
        ac = {}
        for s in ads:
            ac[s["appeal_grp"]] = ac.get(s["appeal_grp"], 0) + 1
        print("  appeal_grp 分布（分组回归要看的样本量）：")
        for k, v in sorted(ac.items(), key=lambda x: -x[1]):
            print("    {:<10} {:>4}".format(k, v))

    print()
    print("pub_hour / is_weekend")
    hrs = [int(s["pub_hour"]) for s in stata]
    print("  pub_hour  min={} max={}  (北京时间)".format(min(hrs), max(hrs)))
    print("  is_weekend 1 的条数:", sum(int(s["is_weekend"]) for s in stata))

    print()
    print("=" * 62)
    print("[v] 全部校验通过" if ok else "[x] 存在校验失败项，请勿直接用于分析")
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
