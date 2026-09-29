# -*- coding: utf-8 -*-
"""网络诊断：确认访问 m.weibo.cn 失败是「代理」还是「接口需要登录态」。

用法
----
python code/diag_net.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import banner, log, open_log, resolve_path  # noqa: E402

URL = "https://m.weibo.cn/api/container/getIndex?containerid=1005051669879400"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"),
    "Referer": "https://m.weibo.cn/",
    "X-Requested-With": "XMLHttpRequest",
    "MWeibo-Pwa": "1",
    "Accept": "application/json, text/plain, */*",
}


def probe(tag: str, trust_env: bool, proxy: str | None = None) -> None:
    s = requests.Session()
    s.trust_env = trust_env
    s.headers.update(HEADERS)
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    try:
        r = s.get(URL, timeout=20)
        body = r.text[:160].replace("\n", " ")
        log(f"  [{tag}] HTTP {r.status_code}  len={len(r.text)}  head={body}")
    except Exception as e:                                    # noqa: BLE001
        log(f"  [{tag}] 异常 {type(e).__name__}: {e}")


def main() -> int:
    open_log(resolve_path("data/diag_net.log"))
    banner("网络诊断")
    log("环境代理变量：")
    found = False
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy"):
        v = os.environ.get(k)
        if v:
            found = True
            log(f"  {k} = {v}")
    if not found:
        log("  （无代理环境变量）")

    log("")
    log("请求测试：")
    probe("默认(尊重环境代理)", trust_env=True)
    probe("忽略环境代理", trust_env=False)
    probe("显式本地代理7897", trust_env=False, proxy="http://127.0.0.1:7897")

    log("")
    log("另测一个非微博站点，判断是否整体断网：")
    try:
        r = requests.get("https://www.bing.com", timeout=15)
        log(f"  bing.com HTTP {r.status_code}")
    except Exception as e:                                    # noqa: BLE001
        log(f"  bing.com 异常 {type(e).__name__}: {e}")

    # ---- 关键：先访问首页拿访客 cookie，再请求接口 ----
    log("")
    log("【访客 cookie 方案】先 GET https://m.weibo.cn/ 再调接口：")
    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    try:
        r0 = s.get("https://m.weibo.cn/", timeout=20)
        names = sorted(s.cookies.get_dict().keys())
        log(f"  首页 HTTP {r0.status_code}  拿到 cookie: {names if names else '（无）'}")
    except Exception as e:                                    # noqa: BLE001
        log(f"  首页异常 {type(e).__name__}: {e}")

    s.headers["Accept"] = "application/json, text/plain, */*"
    s.headers["X-Requested-With"] = "XMLHttpRequest"
    try:
        r1 = s.get(URL, timeout=20)
        body = r1.text[:200].replace("\n", " ")
        log(f"  带访客 cookie 调接口: HTTP {r1.status_code}  len={len(r1.text)}  head={body}")
    except Exception as e:                                    # noqa: BLE001
        log(f"  调接口异常 {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
