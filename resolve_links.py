# -*- coding: utf-8 -*-
"""链接落地解析（从 collect_details.py 拆出来的第二阶段）。

背景（实测）：`page_info.url_ori` 覆盖约 40%，宿主**全部是 t.cn**，
但前两条跳转后落到 `h5.video.weibo.com`（站内视频页）而非电商
→ 必须跟跳转才能判定，且未必是电商。本脚本把这件事独立出来，便于重跑与统计。

输入：post_details.csv 的 page_url_ori（自动去重）
输出：link_resolve.csv（UTF-8-sig，断点续跑）
  src_url, ok, final_url, final_host, is_shop, hops, collected_at

用法：D:\\python\\python.exe resolve_links.py [--delay 0.5] [--timeout 10] [--limit 0]
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DETAILS = os.path.join(HERE, "post_details.csv")
OUT = os.path.join(HERE, "link_resolve.csv")

HEADERS_OUT = ["src_url", "ok", "final_url", "final_host", "is_shop", "hops", "collected_at"]

SHOP_HOSTS = ("taobao.com", "tmall.com", "tb.cn", "jd.com", "jd.hk", "u.jd.com",
              "3.cn", "douyin.com", "s.click.taobao.com", "detail.tmall",
              "item.taobao", "pinduoduo.com", "yangkeduo.com", "suning.com",
              "vip.com", "xiaohongshu.com", "dewu.com", "kaola.com")

UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
        "Mobile/15E148 Safari/604.1")

S = requests.Session()
S.trust_env = True


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_src():
    urls, seen = [], set()
    with open(DETAILS, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            u = (r.get("page_url_ori") or "").strip()
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
    return urls


def load_done():
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("ok") or "") == "1":
                    done.add(r["src_url"])
    return done


def resolve(url, timeout):
    """手动跟随跳转（最多 6 跳），返回 (final_url, hops)。"""
    cur, hops = url, 0
    for _ in range(6):
        try:
            r = S.get(cur, headers={"User-Agent": UA_M,
                                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
                      timeout=timeout, allow_redirects=False)
        except Exception:  # noqa: BLE001
            return None, hops
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location")
            if not loc:
                return cur, hops
            cur = requests.compat.urljoin(cur, loc)
            hops += 1
            continue
        return r.url, hops
    return cur, hops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--timeout", type=float, default=10)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not os.path.exists(DETAILS):
        print("[x] 缺少 post_details.csv，先跑 collect_details.py")
        return 1

    urls = load_src()
    done = load_done()
    todo = [u for u in urls if u not in done]
    if args.limit:
        todo = todo[:args.limit]
    print("[i] 待解析链接 %d / 共 %d（已完成 %d）" % (len(todo), len(urls), len(done)), flush=True)

    new_file = not os.path.exists(OUT)
    fout = open(OUT, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(fout, fieldnames=HEADERS_OUT, extrasaction="ignore")
    if new_file:
        w.writeheader()
        fout.flush()

    ok = shop = 0
    host_ct = {}
    for idx, u in enumerate(todo, 1):
        final, hops = resolve(u, args.timeout)
        host = urlparse(final).netloc.lower() if final else ""
        is_shop = int(bool(host and any(s in host for s in SHOP_HOSTS)))
        if final:
            ok += 1
            host_ct[host] = host_ct.get(host, 0) + 1
        if is_shop:
            shop += 1
        w.writerow({"src_url": u, "ok": int(bool(final)), "final_url": final or "",
                    "final_host": host, "is_shop": is_shop, "hops": hops,
                    "collected_at": now_iso()})
        if idx % 20 == 0 or idx == len(todo):
            fout.flush()
            print("[%3d/%3d] 解析成功=%d 电商=%d" % (idx, len(todo), ok, shop), flush=True)
        time.sleep(args.delay)

    fout.close()
    print("\n[done] 成功 %d / %d | 电商 %d" % (ok, len(todo), shop), flush=True)
    print("[host 分布 Top10]", flush=True)
    for h, c in sorted(host_ct.items(), key=lambda x: -x[1])[:10]:
        print("   %-32s %d" % (h, c), flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
