# -*- coding: utf-8 -*-
"""批次 C 并发版：深挖评论（受众结构 + 扩散动力学）。

与 collect_comments_deep.py 输出完全一致（comments_deep.csv），断点续跑。
并发原因同批次 B：串行在连续请求后会被限流，单请求耗时从 0.2s 涨到 5s+。

用法：D:\\python\\python.exe collect_comments_fast.py --max-pages 3 --workers 4 --delay 0.5
"""
import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")
SRC = os.path.join(HERE, "stata_ads.csv")
OUT = os.path.join(HERE, "comments_deep.csv")

HEADERS_OUT = ["post_id", "comment_id", "created_at", "like_count",
               "author_followers", "author_verified", "author_statuses",
               "text_len", "floor_number", "total_number", "collected_at"]
HTML_RE = re.compile(r"<[^>]+>")
_tls = threading.local()
_lock = threading.Lock()


def session():
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session()
        s.trust_env = True
        _tls.s = s
    return s


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


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_int(v):
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "")
    m = re.match(r"^([\d.]+)\s*(万|亿|w|W|k|K)?$", s)
    if not m:
        return 0
    return int(float(m.group(1)) * {"万": 1e4, "w": 1e4, "W": 1e4, "亿": 1e8,
                                    "k": 1e3, "K": 1e3}.get(m.group(2), 1))


def load_posts():
    ids, seen = [], set()
    with open(SRC, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            p = (r.get("post_id") or "").strip()
            if p and p not in seen:
                seen.add(p)
                ids.append(p)
    return ids


def load_done():
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                done.add(r["post_id"])
    return done


def get_json(url, cookie, timeout=20):
    try:
        r = session().get(url, headers=headers(cookie), timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def fetch_comments(mid, cookie, max_pages, delay):
    rows = []
    max_id = None
    for page in range(max_pages):
        url = "https://m.weibo.cn/comments/hotflow?id={0}&mid={0}&max_id_type=0".format(mid)
        if max_id:
            url += "&max_id=%s" % max_id
        d = get_json(url, cookie)
        if not d or not d.get("ok"):
            break
        data = d.get("data") or {}
        arr = data.get("data") or []
        total = data.get("total_number")
        for c in arr:
            u = c.get("user") or {}
            rows.append({
                "post_id": mid,
                "comment_id": c.get("id") or "",
                "created_at": c.get("created_at") or "",
                "like_count": to_int(c.get("like_count")),
                "author_followers": to_int(u.get("followers_count")),
                "author_verified": int(bool(u.get("verified"))),
                "author_statuses": to_int(u.get("statuses_count")),
                "text_len": len(HTML_RE.sub("", c.get("text") or "").strip()),
                "floor_number": c.get("floor_number") or "",
                "total_number": total if total is not None else "",
                "collected_at": now_iso(),
            })
        nxt = data.get("max_id")
        if not arr or not nxt or nxt == max_id:
            break
        max_id = nxt
        time.sleep(delay)
    return mid, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cookie = load_cookie()
    if len(cookie) < 20:
        print("[x] config.json 无有效 cookie", flush=True)
        return 1

    posts = load_posts()
    done = load_done()
    todo = [p for p in posts if p not in done]
    if args.limit:
        todo = todo[:args.limit]
    print("[i] 帖子 %d，已有评论数据 %d，本次 %d × %d 页，并发 %d"
          % (len(posts), len(done), len(todo), args.max_pages, args.workers), flush=True)

    new_file = not os.path.exists(OUT)
    fout = open(OUT, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(fout, fieldnames=HEADERS_OUT, extrasaction="ignore")
    if new_file:
        w.writeheader()
        fout.flush()

    n_ok = n_fail = n_rows = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch_comments, m, cookie, args.max_pages, args.delay)
                for m in todo]
        for idx, fut in enumerate(futs, 1):
            try:
                mid, rows = fut.result()
            except Exception:  # noqa: BLE001
                mid, rows = "", []
            with _lock:
                for r in rows:
                    w.writerow(r)
                if rows:
                    n_ok += 1
                    n_rows += len(rows)
                else:
                    n_fail += 1
                if idx % 10 == 0 or idx == len(todo):
                    fout.flush()
                    el = time.time() - t0
                    print("[%3d/%3d] 有评论=%d 空=%d 累计评论行=%d | 已用 %.1f 分 剩余约 %.1f 分"
                          % (idx, len(todo), n_ok, n_fail, n_rows, el / 60.0,
                             (len(todo) - idx) * el / idx / 60.0), flush=True)
            del fut

    fout.close()
    print("\n[done] 有评论的帖 %d / 无评论或失败 %d | 评论行 %d" % (n_ok, n_fail, n_rows), flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
