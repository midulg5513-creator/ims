# -*- coding: utf-8 -*-
"""诊断「转发数」作为因变量的分布特征（只输出统计量，不输出正文）。

决定建模策略前必须知道三件事：
    1. 离散计数 + 过离散程度（决定 Poisson / NB）
    2. 零的比例（决定要不要 hurdle / ZINB）
    3. 分组均值差异（抽奖机制、广告标签的原始对比）
"""

import collections
import csv
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts.csv")
SAMPLING = os.path.join(HERE, "sampling_log.csv")

LOTTERY = ("#抽奖#", "#宠粉#", "#福利#")


def desc(name, xs):
    if not xs:
        return
    n = len(xs)
    zero = sum(1 for x in xs if x == 0)
    mean = statistics.mean(xs)
    var = statistics.variance(xs) if n > 1 else 0
    print("  {:<16} n={:<4} 零={:<4}({:>5.1f}%) 均值={:>9.1f} 中位={:>7.0f} "
          "最大={:>8} var/mean={:>7.1f}".format(
              name, n, zero, 100.0 * zero / n, mean, statistics.median(xs),
              max(xs), (var / mean) if mean else 0))


def main():
    with open(POSTS, encoding="utf-8-sig", newline="") as f:
        posts = list(csv.DictReader(f))
    with open(SAMPLING, encoding="utf-8-sig", newline="") as f:
        kw = {r["post_id"]: r["keyword"] for r in csv.DictReader(f)}

    R = [int(r["reposts_count"]) for r in posts]

    print("=" * 78)
    print("一、转发数总体分布")
    desc("全部", R)
    print("  分位数 P10={} P25={} P50={} P75={} P90={} P99={}".format(
        *[sorted(R)[int(len(R) * q)] for q in (0.10, 0.25, 0.50, 0.75, 0.90, 0.99)]))
    print("  最高的 10 个值:", sorted(R)[-10:])
    print("  前 1% 的帖子贡献的转发占比: {:.1f}%".format(
        100.0 * sum(sorted(R)[-5:]) / sum(R)))
    n, mean = len(R), statistics.mean(R)
    print("  零膨胀诊断: 观察零占比 {:.1f}%".format(100.0 * sum(1 for x in R if x == 0) / n))
    print("  过离散诊断: var/mean = {:.1f}".format(statistics.variance(R) / mean))

    print()
    print("二、按广告标签分组")
    for label, sel in (("广告帖 is_ad=1", lambda r: r["is_ad_labeled"] == "true"),
                       ("非广告 is_ad=0", lambda r: r["is_ad_labeled"] != "true")):
        desc(label, [int(r["reposts_count"]) for r in posts if sel(r)])

    print()
    print("三、按关键词层（抽奖类转发是机制性转发，不是影响力）")
    for label, sel in (("抽奖类", lambda r: kw.get(r["post_id"]) in LOTTERY),
                       ("非抽奖类", lambda r: kw.get(r["post_id"]) not in LOTTERY)):
        desc(label, [int(r["reposts_count"]) for r in posts if sel(r)])

    print()
    print("四、抽奖类里广告帖的表现")
    for label, sel in (
        ("抽奖+广告", lambda r: kw.get(r["post_id"]) in LOTTERY and r["is_ad_labeled"] == "true"),
        ("抽奖+非广告", lambda r: kw.get(r["post_id"]) in LOTTERY and r["is_ad_labeled"] != "true"),
        ("非抽奖+广告", lambda r: kw.get(r["post_id"]) not in LOTTERY and r["is_ad_labeled"] == "true"),
        ("非抽奖+非广告", lambda r: kw.get(r["post_id"]) not in LOTTERY and r["is_ad_labeled"] != "true"),
    ):
        desc(label, [int(r["reposts_count"]) for r in posts if sel(r)])

    print()
    print("五、2x2 单元格样本量（后面做交互项要看这个）")
    grid = collections.Counter()
    for r in posts:
        grid[(kw.get(r["post_id"]) in LOTTERY, r["is_ad_labeled"] == "true")] += 1
    for (lot, ad), c in sorted(grid.items()):
        print("  抽奖={:<5} 广告={:<5} n={}".format(str(lot), str(ad), c))
    print("=" * 78)


if __name__ == "__main__":
    main()
