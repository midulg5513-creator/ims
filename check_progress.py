# -*- coding: utf-8 -*-
"""采集进度速查（只读，不改任何数据文件）。

用法：
    .\\weiboSpider\\venv\\Scripts\\python.exe check_progress.py
    .\\weiboSpider\\venv\\Scripts\\python.exe check_progress.py --log collect_run3.log
"""

import argparse
import collections
import csv
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts.csv")
COMMENTS = os.path.join(HERE, "comments.csv")
SAMPLING = os.path.join(HERE, "sampling_log.csv")


def load_rows(path):
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_tail(path, n=12):
    """日志可能是 utf-8（python 直接重定向）或 utf-16（PowerShell Tee-Object）。"""
    if not os.path.isfile(path):
        return [], None
    for enc in ("utf-8", "utf-8-sig", "utf-16", "gbk"):
        try:
            with open(path, encoding=enc) as f:
                lines = f.read().splitlines()
            if lines:
                return lines[-n:], enc
        except (UnicodeDecodeError, UnicodeError, ValueError):
            continue
    return [], None


def latest_log():
    cands = glob.glob(os.path.join(HERE, "collect_run*.log"))
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def file_integrity(path, name):
    """列数一致性 + 尾部截断检查。

    采集是按页追加写入的，如果进程在 write 中途被杀，最后一行可能是半行。
    这种行 csv.DictReader 会静默解析成缺列，到 Stata 里才发现 → 必须显式检查。
    """
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        print("  {}: 文件不存在或为空".format(name))
        return
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        print("  {}: 空".format(name))
        return
    width = len(rows[0])
    bad = [(i + 1, len(r)) for i, r in enumerate(rows) if len(r) != width]
    print("  {}: 表头 {} 列, 数据 {} 行, 列数异常 {} 行".format(
        name, width, len(rows) - 1, len(bad)))
    for lineno, ncol in bad[:5]:
        print("    第 {} 行只有 {} 列 <- 疑似截断/写坏".format(lineno, ncol))
    # 文件末尾是否以换行结束
    with open(path, "rb") as f:
        f.seek(-1, os.SEEK_END)
        last = f.read(1)
    if last not in (b"\n", b"\r"):
        print("    末行缺少换行符 <- 写入被中断，末行可能不完整")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=None, help="要看尾部的日志文件")
    args = ap.parse_args()

    posts = load_rows(POSTS)
    comments = load_rows(COMMENTS)
    sampling = load_rows(SAMPLING)

    print("=" * 56)
    print("数据量")
    print("  posts.csv     : {} 行".format(len(posts)))
    print("  comments.csv  : {} 行".format(len(comments)))
    print("  sampling_log  : {} 行".format(len(sampling)))
    print()
    print("结构完整性")
    file_integrity(POSTS, "posts.csv")
    file_integrity(COMMENTS, "comments.csv")
    file_integrity(SAMPLING, "sampling_log.csv")

    ids = [r.get("post_id") for r in posts if r.get("post_id")]
    dup = len(ids) - len(set(ids))
    print("  post_id 唯一数: {}（重复 {}）".format(len(set(ids)), dup))
    if posts and len(posts) > 0:
        print("  平均每帖评论  : {:.1f}".format(len(comments) / max(1, len(posts))))
    TARGET = 400
    done = len(posts)
    if done >= TARGET:
        print("  进度          : {}/{} 已达标 ✔".format(done, TARGET))
    else:
        print("  进度          : {}/{}  还差 {} 帖".format(
            done, TARGET, TARGET - done))

    print()
    print("采集时间跨度（created_at）")
    ca = sorted(r["created_at"] for r in posts
                if r.get("created_at", "").startswith("2"))
    if ca:
        print("  最早: {}".format(ca[0]))
        print("  最新: {}".format(ca[-1]))
        bad = sum(1 for r in posts
                  if not r.get("created_at", "").startswith("2"))
        print("  无法解析时间的行: {}".format(bad))

    print()
    print("关键词分层（来自 sampling_log）")
    counter = collections.Counter(r.get("keyword") for r in sampling)
    for k, v in counter.most_common():
        print("  {:<12} {:>4}".format(k, v))

    print()
    print("ad_type 分布")
    ad = collections.Counter(r.get("ad_type") for r in posts)
    total = max(1, len(posts))
    for k, v in ad.most_common():
        print("  {:<16} {:>4}  ({:.1f}%)".format(k, v, v * 100.0 / total))

    print()
    print("品牌命中")
    hit = [r for r in posts if r.get("brand_mentioned")]
    print("  brand_mentioned 非空: {}/{} ({:.1f}%)".format(
        len(hit), len(posts), len(hit) * 100.0 / total))
    bc = collections.Counter()
    for r in hit:
        for b in (r["brand_mentioned"] or "").split("|"):
            if b:
                bc[b] += 1
    if bc:
        print("  出现最多的品牌: " + "、".join(
            "{}×{}".format(b, n) for b, n in bc.most_common(10)))

    log = args.log or latest_log()
    if log:
        print()
        print("日志尾部: {} ({})".format(os.path.basename(log), log))
        lines, enc = read_tail(log)
        if lines:
            print("  编码 {}  最后修改 {}".format(
                enc, os.path.getmtime(log)))
            for ln in lines:
                print("  | " + ln)
        else:
            print("  （空）")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
