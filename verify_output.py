# -*- coding: utf-8 -*-
"""校验采集输出是否符合 spec：表头顺序、行数、时间格式、关键字段取值。

只打印结构信息与非敏感的数值/分类字段，不打印帖子正文内容。
"""

import csv
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts.csv")
COMMENTS = os.path.join(HERE, "comments.csv")

EXPECTED_POSTS = [
    "platform", "post_id", "post_url", "created_at", "text", "hashtags",
    "mentions", "media_type", "media_urls", "is_ad_labeled", "ad_type",
    "brand_mentioned", "product_link", "author_id", "author_name",
    "author_followers", "author_verified", "author_verified_type",
    "region_name", "status_city", "reposts_count", "comments_count",
    "attitudes_count", "collected_at", "collection_method",
]
EXPECTED_COMMENTS = [
    "comment_id", "post_id", "comment_text", "comment_author_id",
    "comment_author_followers", "comment_likes", "comment_created_at",
    "comment_ip_location",
]


def check(path, expected, label):
    print("=" * 62)
    print("[{}] {}".format(label, path))
    if not os.path.isfile(path):
        print("  文件不存在")
        return
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        f.seek(0)
        header = next(csv.reader(f))

    print("  表头字段数:", len(header), "| 期望:", len(expected))
    if header == expected:
        print("  [v] 表头与 spec 完全一致（顺序也对）")
    else:
        print("  [x] 表头不一致")
        print("      实际:", header)
        print("      期望:", expected)
    print("  数据行数:", len(rows))
    return rows, header


def show_posts(rows):
    print()
    print("  --- 关键字段取值抽样（不含正文）---")
    for r in rows[:5]:
        print("    post_id={} | created_at={} | media={} | ad_type={}".format(
            r["post_id"], r["created_at"], r["media_type"], r["ad_type"]))
        print("      author={} followers={} verified={} type={}".format(
            r["author_name"], r["author_followers"], r["author_verified"],
            r["author_verified_type"][:40]))
        print("      region={} city={} | repost={} comment={} like={}".format(
            r["region_name"], r["status_city"], r["reposts_count"],
            r["comments_count"], r["attitudes_count"]))
        print("      hashtags={} | mentions={} | brand={} | link={}".format(
            r["hashtags"][:40], r["mentions"][:30] or "(空)",
            r["brand_mentioned"] or "(空)", (r["product_link"] or "(空)")[:50]))
        print("      media_urls 个数={} | text 长度={}".format(
            len([u for u in r["media_urls"].split("|") if u]), len(r["text"])))
        print()

    print("  --- 值域分布 ---")
    for col in ("media_type", "ad_type", "is_ad_labeled", "author_verified",
                "collection_method"):
        c = Counter(r[col] for r in rows)
        print("    {:<20} {}".format(col, dict(c)))
    bad = [r["created_at"] for r in rows
           if r["created_at"] and not r["created_at"].endswith("Z")]
    print("    created_at 非 ISO-UTC 的条数:", len(bad), bad[:3])
    ints = all(str(r["reposts_count"]).isdigit() for r in rows)
    print("    数值列可解析为整数:", ints)


def show_comments(rows):
    print()
    print("  --- 评论抽样 ---")
    for r in rows[:3]:
        print("    post_id={} comment_id={} | likes={} | author_followers={}"
              .format(r["post_id"], r["comment_id"], r["comment_likes"],
                      r["comment_author_followers"]))
        print("      created_at={} | ip_location='{}' | text 长度={}".format(
            r["comment_created_at"], r["comment_ip_location"],
            len(r["comment_text"])))
    per_post = Counter(r["post_id"] for r in rows)
    print("  每条帖子的评论数:", dict(per_post))


def main():
    pr = check(POSTS, EXPECTED_POSTS, "posts")
    if pr:
        show_posts(pr[0])
    cr = check(COMMENTS, EXPECTED_COMMENTS, "comments")
    if cr:
        show_comments(cr[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
