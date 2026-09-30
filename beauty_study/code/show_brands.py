# -*- coding: utf-8 -*-
"""查看品牌清单状态（uid / 账号名 / 粉丝 / 认证 / 是否已确认）。

用法
----
python code/show_brands.py
python code/show_brands.py --confirm-all    # 把所有已填 uid 的品牌置 confirmed=true
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import load_brands, log, save_brands  # noqa: E402

CAT = {
    "cn_mass": "国产大众",
    "cn_functional": "国产功效护肤",
    "intl_mass": "国际大众",
    "intl_premium": "国际高端",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm-all", action="store_true",
                    help="把所有已填 uid 的品牌置 confirmed=true")
    args = ap.parse_args()

    data = load_brands()
    brands = data["brands"]

    if args.confirm_all:
        n = 0
        for b in brands:
            if b.get("uid"):
                b["confirmed"] = True
                b.setdefault("resolved_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                n += 1
        save_brands(data)
        log(f"已把 {n} 个已填 uid 的品牌置为 confirmed=true")
    log(f"{'品牌':<12}{'类别':<14}{'uid':<12}{'选用账号':<26}{'粉丝':>9}  {'认证':<5}{'已确认'}")
    log("-" * 96)
    for b in brands:
        log(f"{b['brand']:<12}{CAT.get(b['category'], b['category']):<14}"
            f"{(b.get('uid') or '—'):<12}{(b.get('account_name') or '—'):<26}"
            f"{(str(b.get('followers')) if b.get('followers') else '—'):>9}  "
            f"{('是' if b.get('verified') else '否'):<5}"
            f"{'Y' if b.get('confirmed') else '-'}")
    ready = [b for b in brands if b.get("uid") and b.get("confirmed") and b.get("active", True)]
    log("")
    log(f"可采集（uid + confirmed=true + active）：{len(ready)} / {len(brands)} 个")
    if ready:
        log("  " + ", ".join(f"{b['brand']}({b['uid']})" for b in ready))
    pending = [b["brand"] for b in brands if not (b.get("uid") and b.get("confirmed"))]
    if pending:
        log(f"待处理：{', '.join(pending)}")
        log("  → 用 show_candidates.py 查候选，再用 resolve_accounts.py --set 品牌=uid 指定")
    log("")
    log("全部确认后： python code/collect_timeline.py --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
