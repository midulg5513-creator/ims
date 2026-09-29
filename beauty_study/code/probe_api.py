# -*- coding: utf-8 -*-
"""接口探测（只读，只打印结构与状态，不打印正文内容）。

目的：确认在**不带登录态**下，哪些 m.weibo.cn 接口可用，尤其是「用户搜索」。

用法
----
python code/probe_api.py
python code/probe_api.py --uid 1669879400      # 指定已知 uid 测资料/时间线
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import banner, ensure_dirs, load_config, log, open_log, resolve_path  # noqa: E402
from mweibo import MWeibo, iter_mblogs, iter_users  # noqa: E402


def describe(tag: str, data) -> None:
    if data is None:
        log(f"  [--] {tag}: 无响应/失败")
        return
    if not isinstance(data, dict):
        log(f"  [--] {tag}: 非 dict ({type(data).__name__})")
        return
    ok = data.get("ok")
    msg = data.get("msg")
    d = data.get("data") or {}
    cards = d.get("cards") if isinstance(d, dict) else None
    n_cards = len(cards) if isinstance(cards, list) else 0
    n_mblog = len(list(iter_mblogs(cards))) if n_cards else 0
    n_user = len(list(iter_users(cards))) if n_cards else 0
    keys = ""
    if isinstance(d, dict):
        keys = ",".join(list(d.keys())[:8])
    log(f"  [{'OK' if ok == 1 else 'x '}] {tag}: ok={ok} cards={n_cards} mb={n_mblog} users={n_user}"
        + (f" msg={msg!r}" if msg else "") + (f"  data.keys=[{keys}]" if keys else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="m.weibo.cn 接口探测")
    ap.add_argument("--uid", default="1669879400", help="已知可用 uid（默认取一个公开账号）")
    ap.add_argument("--kw", default="薇诺娜", help="用户搜索关键词")
    ap.add_argument("--cookie-file", help="cookie 文件（JSON 的 cookie 字段 / cURL 头 / 纯字符串）")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    open_log(resolve_path("data/probe_api.log"))

    banner(f"接口探测（{'带' if args.cookie_file else '不带'}登录态，uid={args.uid}）")
    client = MWeibo(cfg, cookie_file=args.cookie_file, use_cookie=bool(args.cookie_file),
                    log_fn=lambda m: log(m))

    log("\n[1] 用户资料  containerid=100505<uid>")
    describe("100505", client._get("/api/container/getIndex", {"containerid": f"100505{args.uid}"}))

    log("\n[2] 主页时间线  containerid=107603<uid>&page=1")
    describe("107603 p1", client._get("/api/container/getIndex", {"containerid": f"107603{args.uid}", "page": 1}))

    log("\n[3] 用户搜索 各种 containerid 变体")
    variants = [
        ("100103type=3&q=KW + searchall", {"containerid": f"100103type=3&q={args.kw}", "page_type": "searchall"}),
        ("100103type=3&q=KW", {"containerid": f"100103type=3&q={args.kw}"}),
        ("100103type=1&q=KW + searchall", {"containerid": f"100103type=1&q={args.kw}", "page_type": "searchall"}),
        ("type=user&queryVal=KW", {"type": "user", "queryVal": args.kw,
                                   "containerid": f"100103type=3&q={args.kw}", "page_type": "searchall"}),
        ("100505type=3&q=KW", {"containerid": f"100505type=3&q={args.kw}", "page_type": "searchall"}),
        ("100103type=60&q=KW", {"containerid": f"100103type=60&q={args.kw}", "page_type": "searchall"}),
    ]
    for tag, params in variants:
        describe(tag, client._get("/api/container/getIndex", params))

    log("\n[4] 帖子搜索（旧项目验证过可用）")
    describe("100103type=1&q=KW",
             client._get("/api/container/getIndex",
                         {"containerid": f"100103type=1&q={args.kw}", "page_type": "searchall", "page": 1}))

    log("")
    log(f"请求统计：{client.stats}")
    log("说明：ok=-100 通常表示需登录态或该 containerid 不受支持。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
