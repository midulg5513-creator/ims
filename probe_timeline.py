# -*- coding: utf-8 -*-
"""验证「作者内对照」是否可行：广告帖作者的近期时间线里，是否存在非广告帖（组内变异）。

若同一作者时间线中既有疑似广告帖又有疑似非广告帖，则可用作者固定效应做弱因果比较；
若全部同质，则该设计不可行（这也是原方案 470 帖 / 453 作者的结构性缺陷）。

判定「疑似广告」用多信号共识（不含品牌词库，避免词库偏差）：
  含外链(page_info.url_ori) / 含 #广告# 类标签 / 含合作推广话术 / 含电商域名
用法：D:\\python\\python.exe probe_timeline.py [--authors 3] [--pages 2] [--delay 1.5]
"""
import argparse
import collections
import csv
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")
S = requests.Session()
S.trust_env = True

AD_TAG = re.compile(r"#\s*(广告|赞助|推广|sponsored|ad)\s*#", re.I)
KOL_KW = ["商务合作", "品牌合作", "合作推广", "感谢品牌方", "广告推广", "恰饭", "赞助"]
LOTTERY = ["抽奖", "转发抽", "关注并转发", "评论区抽", "中奖", "开奖", "送福利", "宠粉"]
SHOP = ["taobao.com", "tmall.com", "tb.cn", "jd.com", "u.jd.com", "3.cn", "s.click"]


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


def get(url, cookie):
    try:
        r = S.get(url, headers=headers(cookie), timeout=25)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def find_mblog(card):
    if card.get("mblog"):
        return card["mblog"]
    for g in card.get("card_group") or []:
        if g.get("mblog"):
            return g["mblog"]
    return None


def signal(mb):
    """返回 (是否疑似广告, 触发信号集合)"""
    text = mb.get("text") or ""
    pi = mb.get("page_info") or {}
    u = (pi.get("url_ori") or "") + " " + (pi.get("url") or "")
    hits = set()
    if AD_TAG.search(text):
        hits.add("广告标签")
    if pi.get("url_ori"):
        hits.add("外链")
    if any(k in text for k in KOL_KW):
        hits.add("合作话术")
    if any(k in text for k in LOTTERY):
        hits.add("抽奖话术")
    if any(k in u.lower() for k in SHOP):
        hits.add("电商域名")
    ad = bool(hits & {"广告标签", "合作话术", "电商域名"}) or ("外链" in hits and "抽奖话术" not in hits and pi.get("type") in ("webpage", "fangle", "article"))
    if "抽奖话术" in hits:
        ad = True
    return ad, hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--authors", type=int, default=3)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    cookie = load_cookie()
    # 取广告帖里转发量中上、作者不同的几条（避免极头部，尽量贴近常规品牌/账号）
    rows = []
    with open(os.path.join(HERE, "stata_ads.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    rows.sort(key=lambda r: int(r["reposts"]), reverse=True)
    cand, seen = [], set()
    mid_lo, mid_hi = len(rows) // 3, len(rows) * 2 // 3
    for r in rows[mid_lo:mid_hi]:
        if r["author_id"] in seen:
            continue
        seen.add(r["author_id"])
        cand.append(r)
        if len(cand) >= args.authors:
            break

    for r in cand:
        uid = r["author_id"]
        n = ad = 0
        sig_ct = collections.Counter()
        print("\n作者 %s（本样本广告帖转发=%s）主页时间线探测：" % (uid, r["reposts"]))
        for page in range(1, args.pages + 1):
            d = get("https://m.weibo.cn/api/container/getIndex?containerid=107603%s"
                    "&page_type=03&page=%d" % (uid, page), cookie)
            cards = ((d or {}).get("data") or {}).get("cards") or []
            total = ((d or {}).get("data") or {}).get("cardlistInfo") or {}
            if page == 1:
                print("    cardlistInfo.total =", total.get("total"), "| 本页 cards =", len(cards))
            for c in cards:
                mb = find_mblog(c)
                if not mb:
                    continue
                n += 1
                isad, hits = signal(mb)
                if isad:
                    ad += 1
                for h in hits:
                    sig_ct[h] += 1
            time.sleep(args.delay)
        if n:
            print("    抓取 %d 条 | 疑似广告 %d 条 (%.0f%%) | 疑似非广告 %d 条"
                  % (n, ad, 100.0 * ad / n, n - ad))
            print("    信号分布:", dict(sig_ct))
            print("    组内变异:", "有（可做作者内对照）" if 0 < ad < n else "无")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
