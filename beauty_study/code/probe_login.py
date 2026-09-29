# -*- coding: utf-8 -*-
r"""登录态判定：用 m.weibo.cn/api/config 直接看 data.login，判断 cookie 是否有效。

用法
----
python code/probe_login.py
python code/probe_login.py --cookie-file "D:/path/to/config.json"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import banner, ensure_dirs, load_config, log, open_log, resolve_path  # noqa: E402
from mweibo import MWeibo  # noqa: E402


def show(tag: str, data) -> None:
    if not isinstance(data, dict):
        log(f"  [{tag}] 无响应")
        return
    d = data.get("data")
    if isinstance(d, dict):
        keep = {k: d[k] for k in ("login", "uid", "nick", "isLogin", "loginType") if k in d}
        log(f"  [{tag}] ok={data.get('ok')}  login={d.get('login')}  "
            f"{keep if keep else ''}  data.keys={list(d.keys())[:10]}")
    else:
        log(f"  [{tag}] ok={data.get('ok')} data={str(data)[:120]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie-file")
    ap.add_argument("--uid", default="1669879400")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    open_log(resolve_path("data/probe_login.log"))
    banner("登录态判定")

    log("\n[A] 不使用 cookie（仅访客）")
    c1 = MWeibo(cfg, use_cookie=False, log_fn=log)
    show("config", c1._get("/api/config"))
    show("profile", c1._get("/api/container/getIndex", {"containerid": f"100505{args.uid}"}))
    log(f"  stats={c1.stats}")

    if not args.cookie_file:
        log("\n（未提供 --cookie-file，跳过带登录测试）")
        return 0

    log("\n[B] 使用 cookie")
    c2 = MWeibo(cfg, cookie_file=args.cookie_file, use_cookie=True, log_fn=log)
    show("config", c2._get("/api/config"))
    show("profile", c2._get("/api/container/getIndex", {"containerid": f"100505{args.uid}"}))
    log(f"  stats={c2.stats}")

    log("\n结论：config 里 login=true 才说明 cookie 有效；login=false 或 ok=-100 说明已失效，需要重新导出 cookie。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
