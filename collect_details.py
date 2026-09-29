# -*- coding: utf-8 -*-
"""批次 A：为每条帖子补 statuses/show 详情字段 + 外链最终落地域名。

为什么要它：
  posts.csv 的 product_link 100% 为空（原采集器只读 page_info.url / page_url，
  而真实外链在 page_info.url_ori）。本脚本补齐外链、热搜标识、发布工具等，
  这些是 IAM「信息质量」路径与「分发渠道」变量的可观测来源。

输出：post_details.csv（UTF-8-sig，断点续跑：已采集的 post_id 直接跳过）

字段：
  post_id, ok, ad_marked, is_paid, page_type, page_url_ori,
  link_final_url, link_final_host, is_shop_link, is_video, pic_num,
  text_length, source_tool, is_hot_topic, region_name, detail_created_at, collected_at

用法（长跑请脱离终端）：
  D:\\python\\python.exe collect_details.py --scope ads --delay 1.5
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")
OUT = os.path.join(HERE, "post_details.csv")

S = requests.Session()
S.trust_env = True  # 继承本机代理 127.0.0.1:7897

HEADERS_OUT = [
    "post_id", "ok", "ad_marked", "is_paid", "page_type", "page_url_ori",
    "link_final_url", "link_final_host", "is_shop_link", "is_video", "pic_num",
    "text_length", "source_tool", "is_hot_topic", "region_name",
    "detail_created_at", "collected_at",
]

# 电商域名（t.cn 是微博通用短链，必须跟随跳转后才能判）
SHOP_HOSTS = ("taobao.com", "tmall.com", "tb.cn", "jd.com", "jd.hk", "u.jd.com",
              "3.cn", "douyin.com", "s.click.taobao.com", "detail.tmall",
              "item.taobao", "pinduoduo.com", "yangkeduo.com", "suning.com",
              "vip.com", "xiaohongshu.com", "dewu.com", "kaola.com")
# 微博站内域名（外链不算）
SELF_HOSTS = ("weibo.com", "weibo.cn", "sina.com.cn", "sinaimg.cn", "t.cn")


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


def load_ids(scope):
    """返回 [(post_id, author_id)]，保持文件顺序并去重。"""
    path = os.path.join(HERE, "stata_ads.csv" if scope == "ads" else "posts.csv")
    ids, seen = [], set()
    with open(path, encoding="utf-8-sig" if scope == "ads" else "utf-8-sig") as f:
        for r in csv.DictReader(f):
            pid = (r.get("post_id") or "").strip()
            if pid and pid not in seen:
                seen.add(pid)
                ids.append(pid)
    return ids


def load_done():
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("ok") or "") == "1":
                    done.add(r["post_id"])
    return done


def fetch_detail(cookie, mid, timeout=15):
    try:
        r = S.get("https://m.weibo.cn/statuses/show?id=%s" % mid,
                  headers=make_headers(cookie), timeout=timeout)
        if r.status_code != 200:
            return None, "HTTP%s" % r.status_code
        d = r.json()
        if not d.get("ok"):
            return None, "ok=0"
        return d.get("data") or {}, "200"
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def resolve_link(url):
    """跟随 t.cn 短链拿最终落地 URL。失败返回 (None, None)。"""
    if not url:
        return None, None
    try:
        r = S.get(url, headers={
            "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                           "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                           "Mobile/15E148 Safari/604.1"),
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }, timeout=15, allow_redirects=True)
        return r.url, urlparse(r.url).netloc.lower()
    except Exception:  # noqa: BLE001
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["ads", "all"], default="ads")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--resolve-links", type=int, default=0,
                    help="1=内联跟随短链（慢），0=只存 url_ori，交给 resolve_links.py")
    ap.add_argument("--limit", type=int, default=0, help="只采前 N 条（冒烟测试用）")
    ap.add_argument("--retry", type=int, default=1, help="单条失败重试次数")
    ap.add_argument("--timeout", type=float, default=15, help="单请求超时秒数")
    args = ap.parse_args()

    cookie = load_cookie()
    if len(cookie) < 20:
        print("[x] config.json 无有效 cookie", flush=True)
        return 1

    ids = load_ids(args.scope)
    done = load_done()
    todo = [i for i in ids if i not in done]
    if args.limit:
        todo = todo[:args.limit]
    print("[i] scope=%s 总 %d 条，已完成 %d，本次待采 %d，delay=%.1fs，预计 %.1f 分钟"
          % (args.scope, len(ids), len(done), len(todo), args.delay,
             len(todo) * args.delay / 60.0), flush=True)

    new_file = not os.path.exists(OUT)
    fout = open(OUT, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(fout, fieldnames=HEADERS_OUT, extrasaction="ignore")
    if new_file:
        w.writeheader()
        fout.flush()

    n_ok = n_fail = n_link = n_shop = 0
    fail_reasons = {}
    t0 = time.time()
    for idx, mid in enumerate(todo, 1):
        d, st = None, ""
        for attempt in range(args.retry + 1):
            d, st = fetch_detail(cookie, mid, args.timeout)
            if d is not None:
                break
            time.sleep(1.5 + attempt * 2)
        row = {k: "" for k in HEADERS_OUT}
        row["post_id"] = mid
        row["collected_at"] = now_iso()
        if d is None:
            row["ok"] = "0"
            n_fail += 1
            fail_reasons[st] = fail_reasons.get(st, 0) + 1
        else:
            row["ok"] = "1"
            n_ok += 1
            pi = d.get("page_info") or {}
            url_ori = (pi.get("url_ori") or "").strip()
            host = urlparse(url_ori).netloc.lower()
            # 站内链接不算外链（t.cn 例外：它是通用短链，需跳转才知道去哪）
            ext = url_ori if (url_ori and (host not in SELF_HOSTS or host.endswith("t.cn"))) else ""
            row.update({
                "ad_marked": int(bool(d.get("ad_marked"))),
                "is_paid": int(bool(d.get("is_paid"))),
                "page_type": pi.get("type") or "",
                "page_url_ori": url_ori,
                "is_video": int(bool(d.get("page_info", {}).get("type") == "video"
                                     or d.get("video_url") or d.get("page_info") and
                                     (d.get("page_info") or {}).get("object_type") == 11)),
                "pic_num": d.get("pic_num") or 0,
                "text_length": d.get("textLength") or 0,
                "source_tool": d.get("source") or "",
                "is_hot_topic": int(any(
                    (t or {}).get("object_type") == "hot_rank_darwin"
                    for t in (d.get("darwin_tags") or []))),
                "region_name": (d.get("region_name") or "").replace("发布于 ", ""),
                "detail_created_at": d.get("created_at") or "",
            })
            if ext and args.resolve_links:
                final_url, final_host = resolve_link(ext)
                row["link_final_url"] = final_url or ""
                row["link_final_host"] = final_host or ""
                row["is_shop_link"] = int(bool(final_host and any(
                    s in final_host for s in SHOP_HOSTS)))
                if final_host:
                    n_link += 1
                if row["is_shop_link"]:
                    n_shop += 1
                time.sleep(0.4)
        w.writerow(row)
        if idx % 5 == 0 or idx == len(todo) or d is None:
            fout.flush()
            el = time.time() - t0
            eta = (len(todo) - idx) * el / idx / 60.0
            print("[%4d/%4d] ok=%d fail=%d 外链跳转=%d 电商=%d | 平均 %.2f 秒/条 剩余约 %.1f 分%s"
                  % (idx, len(todo), n_ok, n_fail, n_link, n_shop, el / idx, eta,
                     (" | 失败原因: %s" % dict(fail_reasons)) if fail_reasons else ""),
                  flush=True)
        time.sleep(args.delay)

    fout.close()
    print("\n[done] 成功 %d / 失败 %d | 外链可解析 %d | 判定为电商 %d"
          % (n_ok, n_fail, n_link, n_shop), flush=True)
    if fail_reasons:
        print("[fail 原因分布] %s" % dict(fail_reasons), flush=True)
    print("[out] %s" % OUT, flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
