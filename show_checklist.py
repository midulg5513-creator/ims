# -*- coding: utf-8 -*-
"""提取核对清单，标出不通过项。"""
from pathlib import Path
import io
import sys

ROOT = Path(r"d:\AI\爬虫")
sys.stdout = io.TextIOWrapper(
    open(ROOT / "_chk.txt", "wb"), encoding="utf-8", line_buffering=True
)

t = (ROOT / "reproduce_all.log").read_text(encoding="utf-8", errors="replace")
L = t.splitlines()

print("=" * 78)
print("核对清单")
print("=" * 78)
start = next((i for i, l in enumerate(L) if "结果核对清单" in l), 0)
for l in L[start:]:
    print(l)

print()
print("=" * 78)
print("不通过项汇总")
print("=" * 78)
for l in L:
    if " [!!] " in l:
        print("  " + l.strip())
