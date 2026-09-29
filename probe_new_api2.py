# -*- coding: utf-8 -*-
"""二次探测：确认 statuses/show 层级、时间线分页参数、转发接口正确形式。

只输出字段结构/计数，不输出用户内容。
"""
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")

S = requests.Session()
S.trust_env = True
UID = "2379928477"       # 上一步探测用到的作者
MID = "5343728593014367"

KEEP = ["ad_marked", "is_paid", "page_info", "promotion", "reposts_count",
        "comments_count", "attitudes_count", "created_at", "source",
        "pic_num", "pic_ids", "video_url", "textLength", "region_name",
        "repost_type", "mblogtype", "isLongText", "mblog_vip_type",
        "darwin_tags", "analysis_extra", "item_category"]


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
            return None, "HTTP %s" % r.status_code
        try:
            return r.json(), "200"
        except ValueError:
            return None, "非 JSON len=%d" % len(r.text)
    except Exception as e:  # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, e)


def report(mblog, tag):
    if not mblog:
        print("      [%s] 无 mblog" % tag)
        return
    print("      [%s] id=%s 转发=%s 评论=%s 赞=%s" % (
        tag, mblog.get("id"), mblog.get("reposts_count"),
        mblog.get("comments_count"), mblog.get("attitudes_count")))
    for k in KEEP:
        if k in mblog:
            v = mblog.get(k)
            s = str(v)
            if len(s) > 60:
                s = s[:57] + "..."
            print("        %-16s = %s" % (k, s))


def find_mblog(card):
    if card.get("mblog"):
        return card["mblog"]
    for g in card.get("card_group") or []:
        if g.get("mblog"):
            return g["mblog"]
    return None


def main():
    cookie = load_cookie()
    print("=" * 70)
    print("[A] statuses/show 的 data 层级")
    d, st = get("https://m.weibo.cn/statuses/show?id=%s" % MID, cookie)
    print("    状态:", st)
    if d:
        inner = d.get("data") or {}
        print("    data 键数:", len(inner))
        report(inner, "show")
    time.sleep(2)

    print("\n[B] 时间线分页参数")
    for tag, url in (
        ("page=2", "https://m.weibo.cn/api/container/getIndex?containerid=107603%s&page_type=03&page=2" % UID),
        ("since_id", "https://m.weibo.cn/api/container/getIndex?containerid=107603%s&page_type=03&since_id=%s" % (UID, MID)),
    ):
        d, st = get(url, cookie)
        data = (d or {}).get("data") or {}
        cards = data.get("cards") or []
        mb = find_mblog(cards[0]) if cards else None
        print("    [%s] 状态=%s cards=%d cardlistInfo=%s" % (
            tag, st, len(cards),
            {k: v for k, v in (data.get("cardlistInfo") or {}).items()
             if k in ("since_id", "total", "page", "containerid") if True}))
        report(mb, tag)
        print("    -> 该页首条 id =", (mb or {}).get("id"))
        time.sleep(2)

    print("\n[C] ad_marked / is_paid 在该作者时间线上的取值分布（最多 3 页）")
    dist = {}
    n = 0
    for page in (1, 2, 3):
        url = ("https://m.weibo.cn/api/container/getIndex?containerid=107603%s"
               "&page_type=03&page=%d" % (UID, page))
        d, st = get(url, cookie)
        cards = ((d or {}).get("data") or {}).get("cards") or []
        for c in cards:
            mb = find_mblog(c)
            if not mb:
                continue
            n += 1
            key = (mb.get("ad_marked"), mb.get("is_paid"))
            dist[key] = dist.get(key, 0) + 1
        time.sleep(2)
    print("    共 %d 条， (ad_marked, is_paid) 分布: %s" % (n, dist))

    print("\n[D] 转发接口正确形式")
    for tag, url in (
        ("api/statuses/reposts", "https://m.weibo.cn/api/statuses/reposts?id=%s&page=1" % MID),
        ("api/statuses/reposts&mid", "https://m.weibo.cn/api/statuses/reposts?id=%s&mid=%s&page=1" % (MID, MID)),
        ("statuses/reposts", "https://m.weibo.cn/statuses/reposts?id=%s&page=1" % MID),
        ("comments/hotflow", "https://m.weibo.cn/comments/hotflow?id=%s&mid=%s&max_id_type=0" % (MID, MID)),
    ):
        d, st = get(url, cookie)
        print("    [%-22s] %s" % (tag, st))
        if d:
            print("        顶层:", sorted(d.keys()))
            if "errno" in d:
                print("        errno=%s ok=%s msg=%s" % (d.get("errno"), d.get("ok"), d.get("msg")))
            data = d.get("data")
            if isinstance(data, dict):
                print("        data 键:", sorted(data.keys())[:20])
                arr = data.get("data") or []
            elif isinstance(data, list):
                arr = data
            else:
                arr = []
            if hasattr(arr, "__len__"):
                print("        条数:", len(arr))
                if arr:
                    print("        元素字段:", sorted(arr[0].keys())[:30])
                    u = arr[0].get("user") or {}
                    print("        user 字段:", sorted(u.keys())[:30])
        time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
