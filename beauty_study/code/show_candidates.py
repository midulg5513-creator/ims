# -*- coding: utf-8 -*-
"""查看某个品牌的账号候选（默认按粉丝数降序，便于人工挑官方号）。

用法
----
python code/show_candidates.py --brand 韩束
python code/show_candidates.py --brand 韩束 --top 30 --min-followers 10000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import load_config, log, resolve_path, read_csv, to_int  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--min-followers", type=int, default=0)
    args = ap.parse_args()

    cfg = load_config()
    rows = [r for r in read_csv(resolve_path(cfg["paths"]["account_candidates"]))
            if r.get("brand") == args.brand]
    rows = [r for r in rows if (to_int(r.get("followers_count")) or 0) >= args.min_followers]
    rows.sort(key=lambda r: -(to_int(r.get("followers_count")) or 0))

    if not rows:
        log(f"没有 {args.brand} 的候选；请先运行 resolve_accounts.py --brands {args.brand}")
        return 1

    log(f"{args.brand} 候选（共 {len(rows)} 个，按粉丝数降序，显示前 {args.top}）")
    log(f"{'uid':<12}{'账号名':<30}{'粉丝':>10}  认证  认证说明")
    log("-" * 92)
    for r in rows[:args.top]:
        log(f"{r['candidate_uid']:<12}{r['screen_name']:<30}"
            f"{(to_int(r['followers_count']) or 0):>10}  {r['verified']:^4}  "
            f"{(r.get('verified_reason') or '')[:30]}")
    log("")
    log(f"确认后执行： python code/resolve_accounts.py --set {args.brand}=<uid>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
