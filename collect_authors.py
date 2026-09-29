# -*- coding: utf-8 -*-
"""批次 B：抓广告帖作者的近期主页时间线，用于构造 H1c / H4d 所需变量。

产出两张表（均 UTF-8-sig，断点续跑）：
  1) author_profile.csv —— 作者层面：粉丝/关注/发帖总量/认证类型
  2) author_posts.csv   —— 作者的近期帖（每条一行），用于派生：
       hist_n            抓到的历史帖数
       hist_avg_engage   ln(转发+评论+赞+1) 的均值   → H1c 信源质量
       hist_avg_reposts  转发均值
       ad_density        疑似广告帖占比              → H4d 说服知识累积
       non_ad_base       非广告帖的转发均值          → 作者内对照基准

实测依据：`containerid=107603<uid>&page=N` 可用，48 字段，page 与 since_id 均可分页；
         广告帖在主页仅占约 5%，故对照帖易得。

用法（长跑请脱离终端）：
  D:\\python\\python.exe collect_authors.py --pages 3 --delay 1.2
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")
SRC = os.path.join(HERE, "stata_ads.csv")
P_PROFILE = os.path.join(HERE, "author_profile.csv")
P_POSTS = os.path.join(HERE, "author_posts.csv")

S = requests.Session()
S.trust_env = True

PROFILE_HEADERS = ["author_id", "ok", "followers", "follow_count", "statuses_count",
                   "verified", "verified_type", "has_desc", "collected_at"]
POST_HEADERS = ["author_id", "post_id", "created_at", "reposts", "comments",
                "attitudes", "text_len", "pic_num", "has_video", "has_link",
                "ad_tag", "kol_kw", "lottery_kw", "source_tool", "collected_at"]

AD_TAG = re.compile(r"#\s*(广告|赞助|推广|sponsored|ad)\s*#", re.I)
KOL_KW = ["商务合作", "品牌合作", "合作推广", "感谢品牌方", "广告推广", "恰饭", "赞助", "推广"]
LOTTERY_KW = ["抽奖", "转发抽", "评论区抽", "关注并转发", "中奖", "开奖", "送福利", "宠粉", "抽送"]
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
    """'931.2万' / '1,276' / 1276 -> int"""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "").replace("+", "")
    m = re.match(r"^([\d.]+)\s*(万|亿|w|W|k|K)?$", s)
    if not m:
        return 0
    num = float(m.group(1))
    unit = m.group(2)
    mult = {"万": 1e4, "w": 1e4, "W": 1e4, "亿": 1e8, "k": 1e3, "K": 1e3}.get(unit, 1)
    return int(num * mult)


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


def get_json(url, cookie, timeout=25):
    try:
        r = S.get(url, headers=make_headers(cookie), timeout=timeout)
        if r.status_code != 200:
            return None, "HTTP%s" % r.status_code
        return r.json(), "200"
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def find_mblog(card):
    if card.get("mblog"):
        return card["mblog"]
    for g in card.get("card_group") or []:
        if g.get("mblog"):
            return g["mblog"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--delay", type=float, default=1.2)
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
    print("[i] 作者总数 %d，已完成 %d，本次 %d 位 × %d 页 ≈ %d 请求，预计 %.1f 分钟"
          % (len(authors), len(done), len(todo), args.pages, len(todo) * args.pages,
             len(todo) * args.pages * args.delay / 60.0), flush=True)

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
    for idx, uid in enumerate(todo, 1):
        prof = {"author_id": uid, "ok": 0, "followers": "", "follow_count": "",
                "statuses_count": "", "verified": "", "verified_type": "",
                "has_desc": "", "collected_at": now_iso()}
        got_any = False
        for page in range(1, args.pages + 1):
            url = ("https://m.weibo.cn/api/container/getIndex?containerid=107603%s"
                   "&page_type=03&page=%d" % (uid, page))
            d, st = get_json(url, cookie)
            cards = ((d or {}).get("data") or {}).get("cards") or []
            # 第一页顺带取作者资料（userInfo 在 card 里）
            for c in cards:
                ui = c.get("user") or {}
                if ui and not prof["followers"]:
                    prof["followers"] = to_int(ui.get("followers_count"))
                    prof["follow_count"] = to_int(ui.get("follow_count"))
                    prof["statuses_count"] = to_int(ui.get("statuses_count"))
                    prof["verified"] = int(bool(ui.get("verified")))
                    prof["verified_type"] = ui.get("verified_type")
                    prof["has_desc"] = int(bool((ui.get("description") or "").strip()))
                mb = find_mblog(c)
                if not mb:
                    continue
                got_any = True
                n_posts += 1
                text = mb.get("text") or ""
                pi = mb.get("page_info") or {}
                wpo.writerow({
                    "author_id": uid,
                    "post_id": mb.get("id") or "",
                    "created_at": mb.get("created_at") or "",
                    "reposts": mb.get("reposts_count") or 0,
                    "comments": mb.get("comments_count") or 0,
                    "attitudes": mb.get("attitudes_count") or 0,
                    "text_len": len(strip_html(text)),
                    "pic_num": mb.get("pic_num") or 0,
                    "has_video": int(bool(pi.get("type") == "video" or mb.get("page_info", {}).get("object_type") == 11)),
                    "has_link": int(bool((pi.get("url_ori") or "").strip())),
                    "ad_tag": int(bool(AD_TAG.search(text))),
                    "kol_kw": int(any(k in text for k in KOL_KW)),
                    "lottery_kw": int(any(k in text for k in LOTTERY_KW)),
                    "source_tool": mb.get("source") or "",
                    "collected_at": now_iso(),
                })
            time.sleep(args.delay)
            if not cards:
                break
        if got_any:
            prof["ok"] = 1
            n_ok += 1
        else:
            n_fail += 1
        wp.writerow(prof)
        if idx % 5 == 0 or idx == len(todo):
            fp.flush()
            fpo.flush()
            el = time.time() - t0
            eta = (len(todo) - idx) * el / idx / 60.0
            print("[%3d/%3d] 作者成功=%d 失败=%d 累计帖=%d | 已用 %.1f 分 剩余约 %.1f 分"
                  % (idx, len(todo), n_ok, n_fail, n_posts, el / 60.0, eta), flush=True)

    fp.close()
    fpo.close()
    print("\n[done] 作者成功 %d / 失败 %d | 抓到帖子 %d 条" % (n_ok, n_fail, n_posts), flush=True)
    print("[out] %s\n[out] %s" % (P_PROFILE, P_POSTS), flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
