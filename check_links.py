# -*- coding: utf-8 -*-
"""诊断 product_link 为何全空：统计正文/媒体串里实际出现的链接域名。

只输出域名与计数，不输出正文内容。
"""

import collections
import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts.csv")

URL_RE = re.compile(r"https?://[^\s，。；、）】\"'<>]+")

# collector 里认定的电商域名
SHOP_HOSTS = ("taobao.com", "tmall.com", "tb.cn", "jd.com", "jd.hk", "u.jd.com",
              "3.cn", "douyin.com", "s.click.taobao.com", "detail.tmall",
              "item.taobao", "m.tb.cn", "e.tb.cn", "pinduoduo.com", "yangkeduo.com")


def main():
    with open(POSTS, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    dom = collections.Counter()
    has_url = 0
    shop_hit = 0
    tcn_hit = 0
    for r in rows:
        blob = (r.get("text") or "") + " " + (r.get("media_urls") or "")
        ms = URL_RE.findall(blob)
        if ms:
            has_url += 1
        if any(h in m.lower() for m in ms for h in SHOP_HOSTS):
            shop_hit += 1
        if any("t.cn" in m for m in ms):
            tcn_hit += 1
        for m in ms:
            host = re.sub(r"^https?://", "", m).split("/")[0].lower()
            dom[host] += 1

    n = max(1, len(rows))
    print("总帖数                :", len(rows))
    print("正文/媒体串含 URL 的帖 : {} ({:.1f}%)".format(has_url, has_url * 100.0 / n))
    print("已命中 SHOP_HOSTS 的帖 : {} ({:.1f}%)".format(shop_hit, shop_hit * 100.0 / n))
    print("含 t.cn 短链的帖       : {} ({:.1f}%)".format(tcn_hit, tcn_hit * 100.0 / n))
    print("product_link 非空的帖  :",
          sum(1 for r in rows if r.get("product_link")))
    print()
    print("域名 Top 20：")
    for d, c in dom.most_common(20):
        print("  {:<28} {}".format(d, c))


if __name__ == "__main__":
    main()
