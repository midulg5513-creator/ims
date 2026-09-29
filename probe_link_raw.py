# -*- coding: utf-8 -*-
"""探测 product_link 为何全空：直接看 /statuses/show 返回的原始字段结构。

关键假设：微博正文里的外链是 <a href="...">网页链接</a> 这种 HTML 形式，
collector 先 strip_html 再抽 URL，href 已被丢掉 → product_link 必然为空。

本脚本只打印「是否存在 href / url_struct / 域名」等结构信息，不打印正文内容。
"""

import csv
import json
import os
import re
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts.csv")
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")
SHOW_URL = "https://m.weibo.cn/statuses/show?id={id}"

HREF_RE = re.compile(r'href=["\']([^"\']+)', re.I)


def main():
    with open(CONFIG, encoding="utf-8") as f:
        cookie = json.load(f).get("cookie", "")
    with open(POSTS, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    # 挑不同 media_type 的样本，优先 link / text
    picks = [r for r in rows if r["media_type"] in ("link", "text")][:6]
    if len(picks) < 6:
        picks += [r for r in rows if r not in picks][:6 - len(picks)]

    # link 类型（外链卡片）单独拿出来看 page_info
    link_picks = [r for r in rows if r["media_type"] == "link"][:4]

    s = requests.Session()
    s.headers.update({
        "Cookie": cookie,
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Referer": "https://m.weibo.cn/",
        "X-Requested-With": "XMLHttpRequest",
        "MWeibo-Pwa": "1",
    })

    print("字段结构探测（每条 1 请求，间隔 5 秒）")
    print("-" * 62)
    for r in picks:
        pid = r["post_id"]
        time.sleep(5)
        try:
            data = (s.get(SHOW_URL.format(id=pid), timeout=30).json() or {}).get("data") or {}
        except Exception as e:
            print("{} | 请求失败 {}".format(pid, type(e).__name__))
            continue

        raw = data.get("text") or ""
        hrefs = HREF_RE.findall(raw)
        hosts = sorted({re.sub(r"^https?://", "", h).split("/")[0] for h in hrefs})
        url_struct = data.get("url_struct") or []

        url_keys = [k for k in data.keys() if "url" in k.lower()]
        print("post_id={} media_type={}".format(pid, r["media_type"]))
        print("  text 含 href : {}  提取到 {} 个 href".format(bool(hrefs), len(hrefs)))
        print("  href 域名    : {}".format(hosts[:5] if hosts else "(无)"))
        print("  data 里含 url 的字段: {}".format(url_keys))
        if url_struct:
            print("  url_struct 条数: {}".format(len(url_struct)))
            for it in url_struct[:3]:
                print("    keys={}".format(sorted(it.keys())[:12]))
                for k in ("short_url", "long_url", "url_title", "ori_url"):
                    if it.get(k):
                        v = str(it[k])
                        # 只打印域名，不打印完整链接内容
                        print("      {}: {}".format(
                            k, re.sub(r"^https?://", "", v).split("/")[0]))
        print()

    print()
    print("=" * 62)
    print("link 类型帖子的 page_info（外链卡片到底指向哪）")
    print("-" * 62)
    for r in link_picks:
        pid = r["post_id"]
        time.sleep(5)
        try:
            data = (s.get(SHOW_URL.format(id=pid), timeout=30).json() or {}).get("data") or {}
        except Exception as e:
            print("{} | 请求失败 {}".format(pid, type(e).__name__))
            continue
        pi = data.get("page_info") or {}
        print("post_id={} page_info.type={} object_type={}".format(
            pid, pi.get("type"), pi.get("object_type")))
        for k in ("url", "page_url", "short_url", "long_url", "object_id", "url_ori"):
            v = pi.get(k)
            if v:
                host = re.sub(r"^https?://", "", str(v)).split("/")[0]
                print("    {:<10}: host={}".format(k, host))
        print("    page_info keys: {}".format(sorted(pi.keys())[:20]))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
