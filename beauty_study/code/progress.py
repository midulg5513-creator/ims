# -*- coding: utf-8 -*-
"""采集进度速览：帖子数 / 品牌分布 / 时间跨度 / 快照窗口 / 采集日志尾部。

用法
----
python code/progress.py
python code/progress.py --log-tail 15
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    PROJECT_ROOT,
    load_brands,
    load_config,
    log,
    parse_weibo_time,
    read_csv,
    resolve_path,
    to_int,
)


def tail(path: Path, n: int) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-n:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-tail", type=int, default=10)
    args = ap.parse_args()

    cfg = load_config()
    brands = {b["brand"]: b for b in load_brands()["brands"]}
    target = [b["brand"] for b in brands.values() if b.get("confirmed") and b.get("uid")]

    posts = read_csv(resolve_path(cfg["paths"]["posts_raw"]))
    snaps = read_csv(resolve_path(cfg["paths"]["snapshots"]))

    log("=" * 60)
    log(f"  采集进度  {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)
    log(f"待采品牌：{len(target)} 个")

    if not posts:
        log("posts_raw.csv 还没有数据（采集可能刚开始，或尚未写入）")
    else:
        n = len(posts)
        lo = min((p.get("published_at", "") for p in posts), default="")
        hi = max((p.get("published_at", "") for p in posts), default="")
        log(f"已采集帖子：{n} 条（目标 {cfg['study']['target_posts_min']}–{cfg['study']['target_posts_max']}）")
        log(f"发布时间范围：{lo[:10]} ~ {hi[:10]}")
        dup = sum(1 for p in posts if str(p.get("is_duplicate")) in ("True", "1", "true"))
        log(f"完全重复文本：{dup} 条")

        by_brand = defaultdict(int)
        for p in posts:
            by_brand[p.get("brand", "")] += 1
        log("")
        log(f"  {'品牌':<12}{'帖子数':>7}   {'≥50 达标'}")
        log("  " + "-" * 34)
        for b in sorted(target, key=lambda x: -by_brand.get(x, 0)):
            c = by_brand.get(b, 0)
            mark = "OK" if c >= cfg["study"]["min_posts_per_brand"] else ""
            log(f"  {b:<12}{c:>7}   {mark}")
        missing = [b for b in target if by_brand.get(b, 0) == 0]
        if missing:
            log(f"  尚未采集：{', '.join(missing)}")

    log("")
    if snaps:
        win = defaultdict(int)
        for r in snaps:
            if r.get("fetch_status") == "success":
                win[int(r.get("window_hours") or 0)] += 1
        log(f"快照成功数：{sum(win.values())}（窗口 {dict(sorted(win.items()))}）")
    else:
        log("快照：暂无（需运行 snapshot.py --due）")

    for name in ("collect_timeline.log", "collect_timeline.out.log", "collect_timeline.err.log"):
        p = resolve_path("data") / name
        lines = tail(p, args.log_tail)
        if lines:
            log("")
            log(f"--- {name} 末尾 {len(lines)} 行 ---")
            for line in lines:
                log("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
