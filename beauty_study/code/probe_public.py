# -*- coding: utf-8 -*-
r"""探测无需登录的公开接口（PC 端 weibo.com/ajax/* 与 m.weibo.cn 旧式 containerid）。

目的：判断能否在不使用登录 cookie 的前提下拿到「账号资料」与「主页时间线」，
      以满足需求 §3「只处理公开可见内容、不绕过访问控制」。

用法
----
python code/probe_public.py
python code/probe_public.py --uid 1669879400
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import banner, log, open_log, resolve_path  # noqa: E402

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
PC_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/128.0.0.0 Safari/537.36")


def count_statuses(node) -> int:
    """统计形如微博对象的数量（有 id+created_at 或 id+text）。"""
    n = 0
    if isinstance(node, dict):
        if "id" in node and ("created_at" in node or "text_raw" in node or "text" in node):
            n += 1
        for v in node.values():
            n += count_statuses(v)
    elif isinstance(node, list):
        for v in node:
            n += count_statuses(v)
    return n


def probe(tag: str, url: str, headers: dict, params: dict | None = None, referer: str = "") -> None:
    h = dict(headers)
    if referer:
        h["Referer"] = referer
    try:
        r = requests.get(url, params=params, headers=h, timeout=20)
    except Exception as e:                                     # noqa: BLE001
        log(f"  [--] {tag}: 异常 {type(e).__name__}: {e}")
        return
    body = r.text
    if r.status_code != 200:
        log(f"  [x ] {tag}: HTTP {r.status_code} len={len(body)}")
        return
    try:
        d = r.json()
    except ValueError:
        log(f"  [x ] {tag}: HTTP 200 但非 JSON，len={len(body)} head={body[:100]!r}")
        return
    ok = d.get("ok") if isinstance(d, dict) else None
    ns = count_statuses(d)
    extra = ""
    if isinstance(d, dict):
        if d.get("data") and isinstance(d["data"], dict):
            k = list(d["data"].keys())[:8]
            extra = f" data.keys={k}"
        elif "statuses" in d:
            extra = f" statuses={len(d.get('statuses') or [])}"
        elif isinstance(d.get("list"), list):
            extra = f" list={len(d['list'])}"
    log(f"  [{'OK' if (ok in (1, None) and ns > 0) else '? '}] {tag}: HTTP 200 ok={ok} 微博对象≈{ns}{extra}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", default="1669879400")
    args = ap.parse_args()
    uid = args.uid

    open_log(resolve_path("data/probe_public.log"))
    banner(f"公开接口探测（不使用 cookie，uid={uid}）")

    mobile = {"User-Agent": MOBILE_UA, "X-Requested-With": "XMLHttpRequest",
              "MWeibo-Pwa": "1", "Accept": "application/json, text/plain, */*"}
    pc = {"User-Agent": PC_UA, "X-Requested-With": "XMLHttpRequest",
          "Accept": "application/json, text/plain, */*", "Accept-Language": "zh-CN,zh;q=0.9"}
    mref, pref = "https://m.weibo.cn/", f"https://weibo.com/u/{uid}"

    log("\n[A] m.weibo.cn 旧式入口（先预热拿访客 cookie）")
    s = requests.Session()
    s.headers.update(mobile)
    try:
        s.get("https://m.weibo.cn/", timeout=20)
        log(f"  预热 cookie: {sorted(s.cookies.get_dict())}")
    except Exception as e:                                     # noqa: BLE001
        log(f"  预热失败 {type(e).__name__}")
    time.sleep(2)
    for tag, params in [
        ("type=uid&value", {"type": "uid", "value": uid}),
        ("containerid=230413<uid>", {"containerid": f"230413{uid}_-_WEIBO_SECOND_PROFILE_WEIBO"}),
        ("containerid=100505<uid>", {"containerid": f"100505{uid}"}),
        ("containerid=107603<uid>", {"containerid": f"107603{uid}", "page": 1}),
    ]:
        r = s.get("https://m.weibo.cn/api/container/getIndex", params=params, timeout=20)
        try:
            d = r.json()
        except ValueError:
            log(f"  [x ] {tag}: HTTP {r.status_code} 非JSON len={len(r.text)}")
        else:
            log(f"  [{'OK' if d.get('ok') == 1 else 'x '}] {tag}: HTTP {r.status_code} ok={d.get('ok')} "
                f"微博对象≈{count_statuses(d)}")
        time.sleep(2)

    log("\n[B] weibo.com/ajax（PC 端公开接口）")
    probe("ajax/profile/info", "https://weibo.com/ajax/profile/info", pc, {"uid": uid}, pref)
    time.sleep(2)
    probe("ajax/statuses/mymblog", "https://weibo.com/ajax/statuses/mymblog",
          pc, {"uid": uid, "page": 1, "feature": 0}, pref)
    time.sleep(2)
    probe("ajax/profile/detail", "https://weibo.com/ajax/profile/detail", pc, {"uid": uid}, pref)
    time.sleep(2)
    probe("ajax/statuses/mymblog(count=10)", "https://weibo.com/ajax/statuses/mymblog",
          pc, {"uid": uid, "page": 1, "feature": 0, "count": 10}, pref)

    log("")
    log("结论：任一接口返回 OK 且微博对象>0，即可在无登录态下采集。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
