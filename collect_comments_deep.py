# -*- coding: utf-8 -*-
"""批次 C：评论深挖（受众结构 + 扩散动力学）。

现 comments.csv 只有 2910 条、且是 hotflow 首屏。本脚本用 max_id 翻页抓更深，
并记录评论者属性与评论时间，用于：
  - 受众层级：评论者粉丝数、认证、发帖量（长尾 vs 头部）
  - 扩散曲线：评论 created_at 相对发帖时间的偏移（T+1h/6h/24h 累计占比）
  - 讨论强度：hotflow 的 total_number（帖子评论总量）

输出：comments_deep.csv（UTF-8-sig，断点续跑）
  post_id, comment_id, created_at, like_count, author_followers, author_verified,
  author_statuses, text_len, floor_number, total_number, collected_at

用法（长跑请脱离终端）：
  D:\\python\\python.exe collect_comments_deep.py --max-pages 3 --delay 1.2
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")
SRC = os.path.join(HERE, "stata_ads.csv")
OUT = os.path.join(HERE, "comments_deep.csv")

S = requests.Session()
S.trust_env = True

HEADERS_OUT = ["post_id", "comment_id", "created_at", "like_count",
               "author_followers", "author_verified", "author_statuses",
               "text_len", "floor_number", "total_number", "collected_at"]
HTML_RE = re.compile(r"<[^>]+>")


def load_cookie():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f).get("cookie", "")


def make_headers(cookie):
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
    num = float(m.group(1))
    unit = m.group(2)
    return int(num * {"万": 1e4, "w": 1e4, "W": 1e4, "亿": 1e8,
                      "k": 1e3, "K": 1e3}.get(unit, 1))


def load_posts():
    ids, seen = [], set()
    with open(SRC, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            pid = (r.get("post_id") or "").strip()
            if pid and pid not in seen:
                seen.add(pid)
                ids.append(pid)
    return ids


def load_done():
    """已抓过评论的 post_id（只要出现过就算完成，避免重复抓）。"""
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                done.add(r["post_id"])
    return done


def fetch_page(cookie, mid, max_id):
    url = ("https://m.weibo.cn/comments/hotflow?id={0}&mid={0}&max_id_type=0".format(mid))
    if max_id:
        url += "&max_id=%s" % max_id
    try:
        r = S.get(url, headers=make_headers(cookie), timeout=25)
        if r.status_code != 200:
            return None, "HTTP%s" % r.status_code
        return r.json(), "200"
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--delay", type=float, default=1.2)
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
    print("[i] 帖子 %d，已有评论数据的 %d，本次待抓 %d × 最多 %d 页 ≈ %d 请求，预计 %.1f 分钟"
          % (len(posts), len(done), len(todo), args.max_pages,
             len(todo) * args.max_pages, len(todo) * args.max_pages * args.delay / 60.0),
          flush=True)

    new_file = not os.path.exists(OUT)
    fout = open(OUT, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(fout, fieldnames=HEADERS_OUT, extrasaction="ignore")
    if new_file:
        w.writeheader()
        fout.flush()

    n_ok = n_fail = n_rows = 0
    t0 = time.time()
    for idx, mid in enumerate(todo, 1):
        max_id = None
        got = 0
        for page in range(args.max_pages):
            d, st = fetch_page(cookie, mid, max_id)
            if d is None or not d.get("ok"):
                if page == 0:
                    n_fail += 1
                break
            data = d.get("data") or {}
            arr = data.get("data") or []
            total = data.get("total_number")
            for c in arr:
                u = c.get("user") or {}
                text = HTML_RE.sub("", c.get("text") or "").strip()
                w.writerow({
                    "post_id": mid,
                    "comment_id": c.get("id") or "",
                    "created_at": c.get("created_at") or "",
                    "like_count": to_int(c.get("like_count")),
                    "author_followers": to_int(u.get("followers_count")),
                    "author_verified": int(bool(u.get("verified"))),
                    "author_statuses": to_int(u.get("statuses_count")),
                    "text_len": len(text),
                    "floor_number": c.get("floor_number") or "",
                    "total_number": total if total is not None else "",
                    "collected_at": now_iso(),
                })
                got += 1
            nxt = data.get("max_id")
            if not arr or not nxt or nxt == max_id:
                break
            max_id = nxt
            time.sleep(args.delay)
        if got:
            n_ok += 1
            n_rows += got
        fout.flush()
        if idx % 5 == 0 or idx == len(todo):
            el = time.time() - t0
            eta = (len(todo) - idx) * el / idx / 60.0
            print("[%3d/%3d] 帖成功=%d 失败=%d 累计评论=%d | 已用 %.1f 分 剩余约 %.1f 分"
                  % (idx, len(todo), n_ok, n_fail, n_rows, el / 60.0, eta), flush=True)
        time.sleep(args.delay)

    fout.close()
    print("\n[done] 有评论的帖 %d / 失败 %d | 评论行 %d" % (n_ok, n_fail, n_rows), flush=True)
    print("[out] %s" % OUT, flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
