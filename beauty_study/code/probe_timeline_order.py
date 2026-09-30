# -*- coding: utf-8 -*-
r"""诊断时间线翻页顺序：置顶帖是否把「最旧日期」拉低导致提前停止。

用法
----
python code/probe_timeline_order.py --brand 自然堂            # 只看本地已存的原始快照
python code/probe_timeline_order.py --brand 自然堂 --uid 1863495000 --fetch 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ensure_dirs,
    load_config,
    log,
    open_log,
    parse_weibo_time,
    read_jsonl,
    resolve_path,
)
from mweibo import MWeibo, iter_mblogs  # noqa: E402


def safe_name(s: str) -> str:
    import re
    return re.sub(r"[^\w\u4e00-\u9fa5-]", "_", s)


def show_local(brand: str) -> None:
    p = resolve_path("data/raw_snapshots") / f"timeline_{safe_name(brand)}.jsonl"
    rows = read_jsonl(p)
    if not rows:
        log(f"本地无原始快照：{p}")
        return
    log(f"本地原始快照 {len(rows)} 条（{p.name}）")
    log(f"{'#':<4}{'发布时间':<26}{'isTop':<8}{'置顶类字段'}")
    log("-" * 66)
    for i, r in enumerate(rows, 1):
        mb = r.get("mblog") or {}
        dt = parse_weibo_time(mb.get("created_at"))
        keys = [k for k in mb if "top" in k.lower() or k.lower() in ("title", "isTop")]
        log(f"{i:<4}{(dt.strftime('%Y-%m-%d %H:%M') if dt else '?'):<26}"
            f"{str(mb.get('isTop')):<8}{keys}")


def fetch_pages(cfg: dict, uid: str, pages: int) -> None:
    client = MWeibo(cfg, log_fn=log)
    for page in range(1, pages + 1):
        d = client.get_timeline(uid, page=page)
        cards = (d or {}).get("data", {}).get("cards") or []
        mblogs = list(iter_mblogs(cards))
        log("")
        log(f"=== 第 {page} 页：{len(mblogs)} 条 ===")
        log(f"{'#':<4}{'发布时间':<26}{'isTop'}")
        log("-" * 46)
        for i, mb in enumerate(mblogs, 1):
            dt = parse_weibo_time(mb.get("created_at"))
            log(f"{i:<4}{(dt.strftime('%Y-%m-%d %H:%M') if dt else '?'):<26}{mb.get('isTop')}")
    log("")
    log("判断：若「置顶」条目出现在前面且日期很旧，而后面仍有窗口内帖子，"
        "则说明 stop 逻辑需要忽略置顶。")
    log(f"请求统计：{client.stats}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="自然堂")
    ap.add_argument("--uid")
    ap.add_argument("--fetch", type=int, default=0, help="额外实时抓取前 N 页")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    open_log(resolve_path("data/probe_timeline_order.log"))
    show_local(args.brand)
    if args.fetch and args.uid:
        fetch_pages(cfg, args.uid, args.fetch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
