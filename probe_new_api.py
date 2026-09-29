# -*- coding: utf-8 -*-
"""探测「重新规划」所需的新数据源是否可取：只输出字段结构/计数，不输出用户内容。

探测项：
  1) 用户资料      containerid=100505<uid>      -> 粉丝/关注/发帖总量
  2) 用户时间线    containerid=107603<uid>      -> 历史帖（算历史互动率、取非广告对照帖）
  3) 单条详情      statuses/show?id=<mid>       -> page_info / 推广标识位
  4) 转发链        api/statuses/reposts         -> 转发者粉丝数 + 转发时间（扩散曲线）

用法：D:\\python\\python.exe probe_new_api.py
"""
import csv
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")

S = requests.Session()
S.trust_env = True


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
            return None, "非 JSON（可能被风控/登录页） len=%d" % len(r.text)
    except Exception as e:  # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, e)


def keys_of(d, limit=40):
    if not isinstance(d, dict):
        return []
    return sorted(d.keys())[:limit]


def pick_posts(n=2):
    """取转发最多的 1 条 + 一条普通帖。"""
    rows = []
    with open(os.path.join(HERE, "posts.csv"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    rows.sort(key=lambda r: int(r["reposts_count"] or 0), reverse=True)
    out = [rows[0]]
    for r in rows[len(rows) // 2:]:
        if r["post_id"] != rows[0]["post_id"]:
            out.append(r)
            break
    return out[:n]


def main():
    cookie = load_cookie()
    if len(cookie) < 20:
        print("[x] config.json 无有效 cookie")
        return 1

    posts = pick_posts()
    p = posts[0]
    print("样本帖: post_id=%s author_id=%s 转发=%s" % (
        p["post_id"], p["author_id"], p["reposts_count"]))

    # ---- 1) 用户资料 ----
    print("\n[1] 用户资料 containerid=100505")
    url = ("https://m.weibo.cn/api/container/getIndex?containerid=100505%s"
           % p["author_id"])
    d, st = get(url, cookie)
    print("    状态:", st)
    if d:
        ui = (d.get("data") or {}).get("userInfo") or {}
        print("    data 顶层键:", keys_of(d.get("data") or {}))
        print("    userInfo 键数:", len(ui), "->", keys_of(ui, 60))
        for k in ("followers_count", "follow_count", "statuses_count",
                  "verified", "verified_type", "description"):
            print("      %-16s = %s" % (k, ui.get(k, "<缺>")))
    time.sleep(2)

    # ---- 2) 用户时间线 ----
    print("\n[2] 用户时间线 containerid=107603")
    url = ("https://m.weibo.cn/api/container/getIndex?containerid=107603%s"
           "&page_type=03" % p["author_id"])
    d, st = get(url, cookie)
    print("    状态:", st)
    if d:
        cards = (d.get("data") or {}).get("cards") or []
        print("    cards 数:", len(cards))
        mb = None
        for c in cards:
            if c.get("mblog"):
                mb = c["mblog"]
                break
            for g in c.get("card_group") or []:
                if g.get("mblog"):
                    mb = g["mblog"]
                    break
            if mb:
                break
        if mb:
            print("    mblog 字段数:", len(mb), "->", keys_of(mb, 60))
            print("    支持分页: since_id 字段存在 =", "since_id" in (d.get("data") or {}))
        else:
            print("    [!] 未在 cards 中找到 mblog")
    time.sleep(2)

    # ---- 3) 单条详情 ----
    print("\n[3] 单条详情 statuses/show")
    d, st = get("https://m.weibo.cn/statuses/show?id=%s" % p["post_id"], cookie)
    print("    状态:", st)
    if d:
        print("    顶层键:", keys_of(d, 60))
        for k in ("page_info", "promotion", "isAd", "ad_state", "reposts_count",
                  "comments_count", "attitudes_count", "pic_num", "video_url"):
            print("      %-16s 类型=%s" % (k, type(d.get(k)).__name__))
        pi = d.get("page_info") or {}
        if pi:
            print("    page_info 键:", keys_of(pi, 40))
    time.sleep(2)

    # ---- 4) 转发链 ----
    print("\n[4] 转发链 api/statuses/reposts")
    for tmpl in ("https://m.weibo.cn/api/statuses/reposts?id=%s&page=1",
                 "https://m.weibo.cn/statuses/reposts?id=%s&page=1"):
        d, st = get(tmpl % p["post_id"], cookie)
        print("    %s -> %s" % (tmpl.split("m.weibo.cn")[1][:46], st))
        if d:
            print("      顶层键:", keys_of(d, 30))
            data = d.get("data")
            if isinstance(data, dict):
                print("      data 键:", keys_of(data, 30))
                arr = data.get("data") or []
            elif isinstance(data, list):
                arr = data
            else:
                arr = []
            print("      本页条数:", len(arr) if hasattr(arr, "__len__") else "?")
            if arr:
                print("      元素字段:", keys_of(arr[0], 40))
                u = (arr[0].get("user") or {})
                print("      user 字段:", keys_of(u, 40))
        if d:
            break
        time.sleep(2)

    # ---- 5) 转发者视角：该帖是否可看到转发时间 ----
    print("\n[5] 补充：搜索接口分页游标（判断能否做时间序列回溯）")
    url = ("https://m.weibo.cn/api/container/getIndex?containerid=100103type%3D1"
           "%26q%3D%23%E5%B9%BF%E5%91%8A%23&page_type=searchall&page=2")
    d, st = get(url, cookie)
    print("    状态:", st)
    if d:
        data = d.get("data") or {}
        print("    data 键:", keys_of(data, 30))
        cards = data.get("cards") or []
        print("    cards 数:", len(cards), "| card_type 集合:",
              sorted({c.get("card_type") for c in cards}))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
