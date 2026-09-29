# -*- coding: utf-8 -*-
"""导出 parquet（需求 §11）：data/cleaned_posts.csv -> .parquet，engagement_snapshots.csv -> .parquet。

依赖 pandas + pyarrow。若未安装，脚本会给出安装提示并降级为「不改动 CSV」，不会写坏数据。

用法
----
python code/export_parquet.py
python code/export_parquet.py --strict   # 缺依赖时返回码 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import banner, load_config, log, open_log, read_csv, resolve_path  # noqa: E402

NUMERIC_HINT = [
    "mentions_count", "external_link_count", "image_count", "like_count", "comment_count",
    "repost_count", "follower_count", "post_age_hours", "text_length", "text_length_no_tag",
    "q_count", "exclam_count", "emoji_count", "hashtag_count", "cta_engage_count",
    "has_cta_purchase", "n_discount", "has_discount", "n_giveaway", "has_giveaway",
    "n_new_product", "has_new_product", "n_celebrity", "has_celebrity", "n_benefit",
    "has_benefit", "n_scenario", "has_scenario", "has_livestream", "pub_hour", "pub_dow",
    "is_weekend", "is_holiday", "ln_followers", "window_hours", "age_hours",
]
BOOL_HINT = ["is_original", "has_video", "has_live", "is_duplicate", "has_external_link", "has_shop_link"]


def main() -> int:
    ap = argparse.ArgumentParser(description="CSV -> parquet")
    ap.add_argument("--strict", action="store_true", help="缺少 pandas/pyarrow 时返回码 2")
    args = ap.parse_args()

    cfg = load_config()
    open_log(resolve_path("data/export_parquet.log"))

    try:
        import pandas as pd
    except ImportError:
        log("未安装 pandas，无法导出 parquet。请运行：")
        log('  .venv\\Scripts\\python.exe -m pip install pandas pyarrow')
        log("（CSV 数据不受影响，可继续用 Excel / Stata 分析。）")
        return 2 if args.strict else 0

    try:
        import pyarrow  # noqa: F401
    except ImportError:
        log("未安装 pyarrow（parquet 引擎）。请运行：")
        log('  .venv\\Scripts\\python.exe -m pip install pyarrow')
        return 2 if args.strict else 0

    banner("导出 parquet")
    pairs = [
        (cfg["paths"]["cleaned_posts"], "cleaned_posts.parquet"),
        (cfg["paths"]["snapshots"], "engagement_snapshots.parquet"),
        (cfg["paths"]["annotation_sample"], "annotation_sample.parquet"),
    ]
    for src_rel, out_name in pairs:
        src = resolve_path(src_rel)
        if not src.exists() or not read_csv(src):
            log(f"  跳过（空或不存在）：{src}")
            continue
        df = pd.read_csv(src, encoding="utf-8-sig", dtype=str)
        for c in df.columns:
            if c in NUMERIC_HINT:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            elif c in BOOL_HINT:
                df[c] = df[c].map({"True": True, "False": False, "1": True, "0": False})
        out = src.parent / out_name
        df.to_parquet(out, engine="pyarrow", index=False)
        log(f"  {src.name} -> {out.name}  ({len(df)} 行 × {len(df.columns)} 列)")

    log("")
    log("完成。对外只发布脱敏特征/聚合统计/模型代码/标签定义/质量报告（需求 §11）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
