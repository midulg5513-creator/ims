# -*- coding: utf-8 -*-
"""清点工作区所有 CSV：规模、编码、是否为建模输入。只读。"""
from pathlib import Path
import io
import sys

ROOT = Path(r"d:\AI\爬虫")
sys.stdout = io.TextIOWrapper(
    open(ROOT / "_data_inv.txt", "wb"), encoding="utf-8", line_buffering=True
)

rows = []
for p in sorted(ROOT.glob("*.csv")):
    raw = p.read_bytes()
    bom = raw[:3] == b"\xef\xbb\xbf"
    # 行数
    try:
        with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
            n = sum(1 for _ in f) - 1
        header = open(p, "r", encoding="utf-8-sig", errors="replace").readline().strip()
        ncol = len(header.split(","))
    except Exception as e:                       # noqa: BLE001
        n, ncol, header = -1, -1, str(e)
    rows.append((p.name, len(raw), n, ncol, "BOM" if bom else "no-BOM", header[:110]))

# 子目录
for sub in ("positive_posts_analysis", "t0_analysis", "tests"):
    d = ROOT / sub
    if d.exists():
        for p in sorted(d.glob("*.csv")):
            raw = p.read_bytes()
            bom = raw[:3] == b"\xef\xbb\xbf"
            try:
                with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
                    n = sum(1 for _ in f) - 1
                header = open(p, "r", encoding="utf-8-sig",
                              errors="replace").readline().strip()
                ncol = len(header.split(","))
            except Exception as e:               # noqa: BLE001
                n, ncol, header = -1, -1, str(e)
            rows.append((f"{sub}/{p.name}", len(raw), n, ncol,
                         "BOM" if bom else "no-BOM", header[:110]))

print(f"{'文件':<48s} {'字节':>9s} {'行':>6s} {'列':>4s}  {'编码':<7s}")
print("-" * 100)
for name, size, n, ncol, enc, _ in rows:
    print(f"{name:<48s} {size:>9d} {n:>6d} {ncol:>4d}  {enc:<7s}")

print()
print("=" * 100)
print("表头明细")
print("=" * 100)
for name, size, n, ncol, enc, header in rows:
    print(f"\n--- {name}  ({n} 行 × {ncol} 列, {enc}) ---")
    print(f"  {header}")
