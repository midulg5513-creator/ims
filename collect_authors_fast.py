# -*- coding: utf-8 -*-
"""批次 B 并发版：多线程抓作者主页时间线（沿用 collect_authors.py 的输出格式与断点续跑）。

为什么要并发：串行实测在连续请求后单请求耗时从 0.2s 涨到 5s+（限流/抖动），
205 位作者 × 3 页串行要 50 分钟以上。每线程用独立 Session，可把墙钟压到 1/3 左右。

输出与 collect_authors.py 完全一致（author_profile.csv / author_posts.csv），
两个脚本可交替运行，已完成的作者会被跳过。

用法：D:\\python\\python.exe collect_authors_fast.py --pages 3 --workers 4 --delay 0.5
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
P_PROFILE = os.path.join(HERE, "author_profile.csv")
P_POSTS = os.path.join(HERE, "author_posts.csv")

PROFILE_HEADERS = ["author_id", "ok", "followers", "follow_count", "statuses_count",
                   "verified", "verified_type", "has_desc", "collected_at"]
POST_HEADERS = ["author_id", "post_id", "created_at", "reposts", "comments",
                "attitudes", "text_len", "pic_num", "has_video", "has_link",
                "ad_tag", "kol_kw", "lottery_kw", "source_tool", "collected_at"]

AD_TAG = re.compile(r"#\s*(广告|赞助|推广|sponsored|ad)\s*#", re.I)
KOL_KW = ["商务合作", "品牌合作", "合作推广", "感谢品牌方", "广告推广", "恰饭", "赞助", "推广"]
LOTTERY_KW = ["抽奖", "转发抽", "评论区抽", "关注并转发", "中奖", "开奖", "送福利", "宠粉", "抽送"]
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
    s = str(v).strip().replace(",", "").replace("+", "")
    m = re.match(r"^([\d.]+)\s*(万|亿|w|W|k|K)?$", s)
    if not m:
        return 0
    return int(float(m.group(1)) * {"万": 1e4, "w": 1e4, "W": 1e4, "亿": 1e8,
                                    "k": 1e3, "K": 1e3}.get(m.group(2), 1))


def strip_html(s):
    return HTML_RE.sub("", s or "").replace("&nbsp;", " ").replace("&amp;", "&").strip()


def load_authors():
    ids, seen = [], set()
    with open(SRC, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            a = (r.get("author_id") or "").strip()
            if a and a not in seen:
                seen.add(a)
                ids.append(a)
    return ids


def load_done():
    done = set()
    if os.path.exists(P_PROFILE):
        with open(P_PROFILE, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("ok") or "") == "1":
                    done.add(r["author_id"])
    return done


def find_mblog(card):
    if card.get("mblog"):
        return card["mblog"]
    for g in card.get("card_group") or []:
        if g.get("mblog"):
            return g["mblog"]
    return None


def get_json(url, cookie, timeout=20):
    try:
        r = session().get(url, headers=headers(cookie), timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def fetch_author(uid, cookie, pages, delay):
    prof = {"author_id": uid, "ok": 0, "followers": 0, "follow_count": 0,
            "statuses_count": 0, "verified": 0, "verified_type": "",
            "has_desc": 0, "collected_at": now_iso()}
    rows, got_any = [], False
    for page in range(1, pages + 1):
        url = ("https://m.weibo.cn/api/container/getIndex?containerid=107603%s"
               "&page_type=03&page=%d" % (uid, page))
        d = get_json(url, cookie)
        cards = ((d or {}).get("data") or {}).get("cards") or []
        for c in cards:
            mb = find_mblog(c)
            if not mb:
                continue
            got_any = True
            # 博主资料：时间线每条 mblog.user 即博主本人
            ui = mb.get("user") or {}
            if ui and not prof["followers"]:
                prof["followers"] = to_int(ui.get("followers_count"))
                prof["follow_count"] = to_int(ui.get("follow_count"))
                prof["statuses_count"] = to_int(ui.get("statuses_count"))
                prof["verified"] = int(bool(ui.get("verified")))
                prof["verified_type"] = ui.get("verified_type")
                prof["has_desc"] = int(bool((ui.get("description") or "").strip()))
            text = mb.get("text") or ""
            pi = mb.get("page_info") or {}
            rows.append({
                "author_id": uid,
                "post_id": mb.get("id") or "",
                "created_at": mb.get("created_at") or "",
                "reposts": mb.get("reposts_count") or 0,
                "comments": mb.get("comments_count") or 0,
                "attitudes": mb.get("attitudes_count") or 0,
                "text_len": len(strip_html(text)),
                "pic_num": mb.get("pic_num") or 0,
                "has_video": int(bool(pi.get("type") == "video"
                                      or pi.get("object_type") == 11)),
                "has_link": int(bool((pi.get("url_ori") or "").strip())),
                "ad_tag": int(bool(AD_TAG.search(text))),
                "kol_kw": int(any(k in text for k in KOL_KW)),
                "lottery_kw": int(any(k in text for k in LOTTERY_KW)),
                "source_tool": mb.get("source") or "",
                "collected_at": now_iso(),
            })
        time.sleep(delay)
        if not cards:
            break
    if got_any:
        prof["ok"] = 1
    return prof, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cookie = load_cookie()
    if len(cookie) < 20:
        print("[x] config.json 无有效 cookie", flush=True)
        return 1

    authors = load_authors()
    done = load_done()
    todo = [a for a in authors if a not in done]
    if args.limit:
        todo = todo[:args.limit]
    print("[i] 作者 %d，已完成 %d，本次 %d × %d 页，并发 %d，delay %.2fs"
          % (len(authors), len(done), len(todo), args.pages, args.workers, args.delay),
          flush=True)

    new_p = not os.path.exists(P_PROFILE)
    new_po = not os.path.exists(P_POSTS)
    fp = open(P_PROFILE, "a", encoding="utf-8-sig", newline="")
    fpo = open(P_POSTS, "a", encoding="utf-8-sig", newline="")
    wp = csv.DictWriter(fp, fieldnames=PROFILE_HEADERS, extrasaction="ignore")
    wpo = csv.DictWriter(fpo, fieldnames=POST_HEADERS, extrasaction="ignore")
    if new_p:
        wp.writeheader()
    if new_po:
        wpo.writeheader()
    fp.flush()
    fpo.flush()

    n_ok = n_fail = n_posts = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_author, uid, cookie, args.pages, args.delay): uid
                for uid in todo}
        for idx, fut in enumerate(futs, 1):
            uid = futs[fut]
            try:
                prof, rows = fut.result()
            except Exception as e:  # noqa: BLE001
                prof, rows = ({"author_id": uid, "ok": 0}, [])
                print("[!] %s 异常 %s" % (uid, type(e).__name__), flush=True)
            with _lock:
                wp.writerow(prof)
                for r in rows:
                    wpo.writerow(r)
                if prof.get("ok") == 1:
                    n_ok += 1
                    n_posts += len(rows)
                else:
                    n_fail += 1
                if idx % 10 == 0 or idx == len(todo):
                    fp.flush()
                    fpo.flush()
                    el = time.time() - t0
                    print("[%3d/%3d] 成功=%d 失败=%d 累计帖=%d | 已用 %.1f 分 剩余约 %.1f 分"
                          % (idx, len(todo), n_ok, n_fail, n_posts, el / 60.0,
                             (len(todo) - idx) * el / idx / 60.0), flush=True)
            del fut  # 已完成

    fp.close()
    fpo.close()
    print("\n[done] 作者成功 %d / 失败 %d | 帖 %d" % (n_ok, n_fail, n_posts), flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
