# -*- coding: utf-8 -*-
"""核查批次 B 产出质量：作者资料覆盖率、历史帖数、疑似广告信号分布。

用法：D:\\python\\python.exe check_authors.py
"""
import collections
import csv
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def rd(n):
    p = os.path.join(HERE, n)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def main():
    prof = rd("author_profile.csv")
    posts = rd("author_posts.csv")
    base = rd("stata_ads.csv")

    okp = [r for r in prof if r.get("ok") == "1"]
    print("作者行 %d（ok=%d）| 历史帖行 %d" % (len(prof), len(okp), len(posts)))

    fol = [num(r["followers"]) for r in okp]
    nz = [x for x in fol if x > 0]
    print("粉丝数覆盖：非 0 的 %d / %d；中位 %.0f；最小 %.0f；最大 %.0f"
          % (len(nz), len(okp), st.median(nz) if nz else 0,
             min(nz) if nz else 0, max(nz) if nz else 0))

    by_author = collections.Counter(r["author_id"] for r in posts)
    if by_author:
        cnts = list(by_author.values())
        print("每作者抓到帖数：中位 %d，最小 %d，最大 %d（<5 条的作者 %d 位）"
              % (st.median(cnts), min(cnts), max(cnts),
                 sum(1 for c in cnts if c < 5)))

    n = len(posts) or 1
    for f in ("ad_tag", "kol_kw", "lottery_kw", "has_link", "has_video"):
        c = sum(1 for r in posts if r.get(f) == "1")
        print("   %-10s %4d (%.1f%%)" % (f, c, 100.0 * c / n))

    # 覆盖率：多少条 stata_ads 找到了作者历史
    ids = {r["author_id"] for r in posts}
    cov = sum(1 for r in base if r["author_id"] in ids)
    print("\nstata_ads 211 帖中，作者有历史数据的 %d 帖（%.1f%%）" % (cov, 100.0 * cov / len(base)))

    # 作者历史互动率示例分布
    eng = []
    for a, rows in collections.Counter(r["author_id"] for r in posts).items():
        pass
    print("\n历史帖 source_tool Top5:",
          collections.Counter(r["source_tool"] for r in posts).most_common(5))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
