# -*- coding: utf-8 -*-
"""确认当前建模数据 stata_ads2.csv 的完整结构与可用性。只读。"""
from pathlib import Path
import io
import sys
import hashlib
import numpy as np
import pandas as pd

ROOT = Path(r"d:\AI\爬虫")
sys.stdout = io.TextIOWrapper(
    open(ROOT / "_model_data.txt", "wb"), encoding="utf-8", line_buffering=True
)

for name in ("stata_data.csv", "stata_ads.csv", "stata_ads2.csv"):
    p = ROOT / name
    raw = p.read_bytes()
    print("=" * 84)
    print(f"{name}   字节={len(raw)}   BOM={raw[:3] == b'\\xef\\xbb\\xbf'}   "
          f"md5={hashlib.md5(raw).hexdigest()[:12]}")
    print("=" * 84)
    d = pd.read_csv(p, dtype=str, low_memory=False)
    print(f"行数={len(d)}  列数={len(d.columns)}")
    print("列：")
    for i, c in enumerate(d.columns, 1):
        nn = d[c].notna().sum()
        blank = (d[c].astype(str).str.strip() == "").sum()
        u = d[c].nunique()
        miss = len(d) - nn + blank
        flag = ""
        if miss > 0.3 * len(d):
            flag = "  <== 缺失率高"
        if u <= 1:
            flag = "  <== 零方差"
        print(f"  {i:>3d}. {c:<30s} 非空={len(d)-miss:>4d}/{len(d)}  唯一={u:>5d}{flag}")
    print()

print("=" * 84)
print("regression_final.do 需要的变量是否齐备")
print("=" * 84)
d = pd.read_csv(ROOT / "stata_ads2.csv", dtype=str, low_memory=False)
need = ["reposts", "log_followers", "text_len", "n_images", "is_lottery",
        "log_age_hours", "hist_prior_avg_lnengage", "n_topics", "n_mentions",
        "n_promo", "n_brand", "is_enterprise", "is_personal_verified",
        "media_type", "appeal_grp", "region_grp", "author_id", "post_id"]
for c in need:
    ok = "OK " if c in d.columns else "缺失"
    print(f"  [{ok}] {c}")
