# -*- coding: utf-8 -*-
"""关键词可用性探测（不写任何数据文件）。

对每个候选关键词抓第 1 页搜索，统计：
    - 返回的 mblog 条数
    - 其中「发布时间可解析且落在最近 N 天内」的条数
只打印统计数字，不打印微博内容，避免污染终端输出。

用法：
    .\\weiboSpider\\venv\\Scripts\\python.exe probe_keywords.py --days 90
"""

import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")
SEARCH_URL = ("https://m.weibo.cn/api/container/getIndex"
              "?containerid=100103type%3D1%26q%3D{q}&page_type=searchall&page={page}")

CANDIDATES = [
    "#广告#", "#抽奖#", "#品牌日#", "种草", "推荐",
    "#好物推荐#", "#新品发布#", "#联名款#", "#双11#", "#618#",
    "#恰饭#", "#推广#", "#优惠#", "#试用#", "#开箱#",
    "#测评#", "#安利#", "#宠粉#", "#福利#", "#代言人#",
    "带货", "品牌合作", "上新", "首发", "限时优惠",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--delay", type=float, default=5.0)
    args = ap.parse_args()

    with open(CONFIG, encoding="utf-8") as f:
        cookie = json.load(f).get("cookie", "")

    headers = {
        "Cookie": cookie,
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Referer": "https://m.weibo.cn/",
        "X-Requested-With": "XMLHttpRequest",
        "MWeibo-Pwa": "1",
        "Accept": "application/json, text/plain, */*",
    }
    s = requests.Session()
    s.headers.update(headers)

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    p_recent = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T")

    print("{:<14} {:>6} {:>8} {:>8}".format("关键词", "本页", "近%d天" % args.days, "可解析"))
    print("-" * 42)
    for kw in CANDIDATES:
        time.sleep(args.delay)
        url = SEARCH_URL.format(q=quote(kw), page=1)
        try:
            r = s.get(url, timeout=30)
            data = r.json()
        except Exception as e:
            print("{:<14} {:>6}  {}".format(kw, "-", type(e).__name__))
            continue

        mblogs = []
        for card in (data.get("data") or {}).get("cards") or []:
            for grp in (card.get("card_group") or [card]):
                mb = grp.get("mblog")
                if mb:
                    mblogs.append(mb)

        recent = 0
        parsed = 0
        for mb in mblogs:
            ca = mb.get("created_at") or ""
            try:
                dt = datetime.strptime(ca.strip(), "%a %b %d %H:%M:%S %z %Y")
            except ValueError:
                continue
            parsed += 1
            if dt.astimezone(timezone.utc) >= cutoff:
                recent += 1

        print("{:<14} {:>6} {:>8} {:>8}".format(kw, len(mblogs), recent, parsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
