# -*- coding: utf-8 -*-
"""网络基准：对比「走系统代理」与「直连」访问 m.weibo.cn 的耗时，决定采集参数。"""
import csv
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")


def ids(n):
    out = []
    with open(os.path.join(HERE, "stata_ads.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out.append(r["post_id"])
            if len(out) >= n:
                break
    return out


def headers(cookie):
    return {"Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://m.weibo.cn/", "X-Requested-With": "XMLHttpRequest",
            "MWeibo-Pwa": "1", "Accept": "application/json, text/plain, */*"}


def bench(use_proxy, mids, cookie, concurrency=1):
    import concurrent.futures as cf
    s = requests.Session()
    s.trust_env = use_proxy
    h = headers(cookie)

    def one(mid):
        t = time.time()
        try:
            r = s.get("https://m.weibo.cn/statuses/show?id=%s" % mid, headers=h, timeout=15)
            ok = r.status_code == 200 and r.json().get("ok")
        except Exception:  # noqa: BLE001
            ok = False
        return time.time() - t, bool(ok)

    t0 = time.time()
    if concurrency == 1:
        res = [one(m) for m in mids]
    else:
        with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
            res = list(ex.map(one, mids))
    wall = time.time() - t0
    ok = sum(1 for _, o in res if o)
    print("  代理=%-5s 并发=%d | 成功 %d/%d | 平均单请求 %.2fs | 墙钟 %.1fs"
          % (use_proxy, concurrency, ok, len(mids),
             sum(d for d, _ in res) / len(res), wall))
    return wall


def main():
    cookie = json.load(open(CONFIG, encoding="utf-8")).get("cookie", "")
    mids = ids(6)
    print("[i] 用 %d 个真实 post_id 基准测试" % len(mids))
    print("[1] 串行")
    bench(True, mids, cookie, 1)
    bench(False, mids, cookie, 1)
    print("[2] 并发")
    bench(True, mids, cookie, 4)
    bench(False, mids, cookie, 4)
    print("[3] 高并发")
    bench(True, mids, cookie, 8)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
