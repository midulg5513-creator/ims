# -*- coding: utf-8 -*-
"""把采集结果 posts.csv 清洗成目标表格（Excel 表头口径）。

输出：clean_posts.csv（UTF-8 BOM，Excel 可直接打开）

用法：
    .\\weiboSpider\\venv\\Scripts\\python.exe clean_data.py
"""

import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS_CSV = os.path.join(HERE, "posts.csv")
BRANDS_FILE = os.path.join(HERE, "brands.txt")
PROMO_FILE = os.path.join(HERE, "promo_words.txt")
OUT_CSV = os.path.join(HERE, "clean_posts.csv")

# 目标表格表头，顺序严格照 Excel
OUT_HEADERS = [
    "用户名", "转发数", "评论数", "点赞数", "是否广告",
    "促销词数量", "品牌词数量", "话题词数量", "文本长度", "图片数量",
    "粉丝数", "对数粉丝数", "对数转发", "是否企业账号", "个人认证账号",
]


def load_wordlist(path):
    """读取词库文件，跳过空行和 # 注释行。"""
    if not os.path.isfile(path):
        return []
    words = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                words.append(line)
    return words


def to_int(v):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return 0


def split_field(v):
    """把 '|' 分隔的字段拆成列表，空值返回空列表。"""
    if not v:
        return []
    return [x.strip() for x in str(v).split("|") if x.strip()]


def count_image_urls(media_type, media_urls):
    """统计图片数量。

    采集器的 media_urls 在视频帖里是「图片... + 视频URL(最后一个)」，
    所以视频帖要扣掉最后那个视频地址。
    """
    urls = split_field(media_urls)
    if media_type == "video":
        # 排除形似视频的地址（采集器保证视频 URL 排在最后）
        if urls and ("mp4" in urls[-1].lower() or "video" in urls[-1].lower()):
            return len(urls) - 1
        return max(0, len(urls) - 1)
    if media_type == "image":
        return len(urls)
    return 0


def count_hits(text, words):
    """统计词表里有多少个词出现在文本中（每词最多计 1 次）。"""
    if not text or not words:
        return 0
    return sum(1 for w in words if w in text)


def verified_flags(vtype_raw, verified_raw):
    """从认证信息文本推断「是否企业账号」「个人认证账号」。"""
    is_verified = str(verified_raw).strip().lower() == "true"
    t = str(vtype_raw or "")
    if not is_verified:
        return 0, 0
    enterprise = 1 if ("企业" in t or "机构" in t or "政府" in t) else 0
    personal = 1 if "个人认证" in t else 0
    # 若认证类型无法归类，按个人认证兜底（微博个人认证占多数）
    if not enterprise and not personal:
        personal = 1
    return enterprise, personal


def log10_safe(n):
    """log10，0 或负数返回 0（避免 -inf 污染表格）。"""
    try:
        n = float(n)
    except (ValueError, TypeError):
        return 0
    if n <= 0:
        return 0
    return round(math.log10(n), 4)


def main():
    if not os.path.isfile(POSTS_CSV):
        print("[x] 找不到 {}".format(POSTS_CSV))
        return 1

    brands = load_wordlist(BRANDS_FILE)
    promos = load_wordlist(PROMO_FILE)

    print("[i] 品牌词库: {} 个词".format(len(brands)))
    print("[i] 促销词库: {} 个词".format(len(promos)))
    if not brands:
        print("    [!] brands.txt 为空 → 「品牌词数量」会全是 0")
    if not promos:
        print("    [!] promo_words.txt 为空 → 「促销词数量」会全是 0")

    with open(POSTS_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    print("[i] 读入 {} 条记录".format(len(rows)))

    out_rows = []
    for r in rows:
        text = r.get("text") or ""
        tags = split_field(r.get("hashtags"))
        followers = to_int(r.get("author_followers"))
        reposts = to_int(r.get("reposts_count"))
        ent, personal = verified_flags(r.get("author_verified_type"),
                                      r.get("author_verified"))

        # 品牌词数量：口径与采集器 classify_ad 保持一致 —— 在「正文 + 话题」里做子串
        # 精确匹配，每个词最多计 1 次。
        # 不要用 brand_mentioned 的管道串长度，也不要退回「只匹配正文」的旧分支：
        # 那样同一列会存在两套口径（老数据 brand_mentioned 为空时走的是正文匹配）。
        brand_hits = count_hits(text + " " + " ".join(tags), brands)

        out_rows.append({
            "用户名": r.get("author_name") or "",
            "转发数": reposts,
            "评论数": to_int(r.get("comments_count")),
            "点赞数": to_int(r.get("attitudes_count")),
            "是否广告": 1 if str(r.get("is_ad_labeled")).lower() == "true" else 0,
            "促销词数量": count_hits(text, promos),
            "品牌词数量": brand_hits,
            "话题词数量": len(tags),
            "文本长度": len(text),
            "图片数量": count_image_urls(r.get("media_type"), r.get("media_urls")),
            "粉丝数": followers,
            "对数粉丝数": log10_safe(followers),
            # 口径：与「对数粉丝数」同为 log10，统一 +1 做零值保护（转发数=0 → 0）。
            # 之所以不用 ln：该表其他「对数」列都用 log10；ln 口径的因变量 influence
            # 在 Stata 里现算（analysis*.do），不进这张交付表。
            "对数转发": log10_safe(reposts + 1),
            "是否企业账号": ent,
            "个人认证账号": personal,
        })

    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_HEADERS)
        w.writeheader()
        w.writerows(out_rows)

    # ---- 预览（只打印数值/分类列，不打印正文）----
    print()
    print("=" * 78)
    print("清洗完成 → {}".format(OUT_CSV))
    print("=" * 78)
    show = ["用户名", "转发数", "评论数", "点赞数", "是否广告",
            "促销词数量", "品牌词数量", "话题词数量", "文本长度", "图片数量",
            "粉丝数", "对数粉丝数", "对数转发", "是否企业账号", "个人认证账号"]
    print(" | ".join("{:<6}".format(h) for h in show[:8]))
    for r in out_rows[:5]:
        print(" | ".join("{:<6}".format(str(r[h])[:6]) for h in show[:8]))
    print()
    print("--- 其余列统计 ---")
    for col in ["是否广告", "促销词数量", "品牌词数量", "话题词数量",
                "图片数量", "对数粉丝数", "对数转发",
                "是否企业账号", "个人认证账号"]:
        vals = [r[col] for r in out_rows]
        if all(isinstance(v, (int, float)) for v in vals if v != ""):
            nums = [v for v in vals if v != ""]
            if nums:
                print("  {:<12} 非零 {}/{}  最小 {}  最大 {}".format(
                    col, sum(1 for v in nums if v), len(nums),
                    min(nums), max(nums)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
