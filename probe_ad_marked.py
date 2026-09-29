# -*- coding: utf-8 -*-
"""验证两件事（决定研究设计能否成立）：
  A) 平台官方商业化标识 ad_marked / is_paid 在真实广告帖上的命中率
     —— 若命中率过低，则「官方标识作黄金标准」不成立
  B) page_info.url_ori 是否能补上 posts.csv 里 100% 为空的 product_link
     —— 并看外链宿主分布（t.cn 短链需跟随跳转才能判电商）

抽样：按 ad_type 分层各取若干条，只输出统计，不输出用户内容。
用法：D:\\python\\python.exe probe_ad_marked.py [--per-type 10] [--delay 1.5]
"""
import argparse
import collections
import csv
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")
S = requests.Session()
S.trust_env = True

TYPE_ORDER = ["explicit_ad", "brand_campaign", "kol_collab", "organic", "unknown"]


def load_cookie():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f).get("cookie", "")


def headers(cookie):
    return {
        "Cookie": cookie,
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Referer": "https://m.weibo.cn/",
        "X-Requested-With": "XMLHttpRequest",
        "MWeibo-Pwa": "1",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def show(cookie, mid):
    try:
        r = S.get("https://m.weibo.cn/statuses/show?id=%s" % mid,
                  headers=headers(cookie), timeout=25)
        if r.status_code != 200:
            return None, "HTTP%s" % r.status_code
        d = r.json()
        if not d.get("ok"):
            return None, "ok=0"
        return d.get("data") or {}, "200"
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=10)
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    cookie = load_cookie()
    buckets = collections.defaultdict(list)
    with open(os.path.join(HERE, "posts.csv"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            buckets[row["ad_type"]].append(row["post_id"])

    picks = []
    for t in TYPE_ORDER:
        ids = buckets.get(t, [])
        picks += [(t, i) for i in ids[:args.per_type]]
    picks += [("unknown", i) for i in buckets.get("unknown", [])[args.per_type:args.per_type * 2]]
    print("拟探测 %d 条" % len(picks))

    stat = collections.defaultdict(lambda: collections.Counter())
    host_ct = collections.Counter()
    link_kind = collections.Counter()
    fails = collections.Counter()
    n_ok = 0

    for ad_type, mid in picks:
        d, st = show(cookie, mid)
        if d is None:
            fails[st] += 1
            time.sleep(args.delay)
            continue
        n_ok += 1
        am, ip = bool(d.get("ad_marked")), bool(d.get("is_paid"))
        stat[ad_type]["n"] += 1
        stat[ad_type]["ad_marked" if am else "-ad_marked"] += 1
        stat[ad_type]["is_paid" if ip else "-is_paid"] += 1
        pi = d.get("page_info") or {}
        u = (pi.get("url_ori") or "").strip()
        if u:
            stat[ad_type]["有外链"] += 1
            host_ct[urlparse(u).netloc.lower()] += 1
            link_kind[pi.get("type")] += 1
        else:
            stat[ad_type]["无外链"] += 1
        time.sleep(args.delay)

    print("\n== A) ad_marked / is_paid 命中率（按采集器自建的 ad_type 分层）==")
    print("%-16s %4s %10s %9s %10s %8s %8s" % (
        "ad_type", "n", "ad_marked", "占比", "is_paid", "有外链", "无外链"))
    for t in TYPE_ORDER:
        s = stat.get(t)
        if not s:
            continue
        n = s["n"]
        print("%-16s %4d %10d %8.1f%% %10d %8d %8d" % (
            t, n, s["ad_marked"], 100.0 * s["ad_marked"] / n, s["is_paid"],
            s["有外链"], s["无外链"]))

    tot = sum(s["n"] for s in stat.values())
    if tot:
        am_all = sum(s["ad_marked"] for s in stat.values())
        ip_all = sum(s["is_paid"] for s in stat.values())
        lk_all = sum(s["有外链"] for s in stat.values())
        print("\n合计 n=%d | ad_marked=%d (%.1f%%) | is_paid=%d (%.1f%%) | 有外链=%d (%.1f%%)"
              % (tot, am_all, 100.0 * am_all / tot, ip_all, 100.0 * ip_all / tot,
                 lk_all, 100.0 * lk_all / tot))

    print("\n== B) 外链宿主 Top12 ==")
    for h, c in host_ct.most_common(12):
        print("   %-28s %d" % (h, c))
    print("   page_info.type 分布:", dict(link_kind))
    if fails:
        print("\n失败:", dict(fails), "| 成功:", n_ok)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
