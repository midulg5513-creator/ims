# -*- coding: utf-8 -*-
"""从 regression_final.log 抽取关键结果行。"""
from pathlib import Path
import io
import re
import sys

ROOT = Path(r"d:\AI\爬虫")
sys.stdout = io.TextIOWrapper(
    open(ROOT / "_r2.txt", "wb"), encoding="utf-8", line_buffering=True
)

txt = (ROOT / "regression_final.log").read_text(encoding="utf-8", errors="replace")
lines = [l.rstrip() for l in txt.splitlines()]

KEYS = ("###", "M0 ", "M1_", "M2_", "M3_", "M4_", "M5_", "M6_", "M7_", "M8_", "M9_",
        "Q1_", "HAND_", "DIFF_", "Q2_", "MAIN_", "GROUP_", "APPEAL_X", "VIDEO_X",
        "ZERO_REPOST", "N_AUTHORS", "N = ", "  dF_")

print("=" * 80)
print("A. 关键标记行")
print("=" * 80)
for l in lines:
    s = l.strip()
    if s.startswith("###") or any(s.startswith(k) for k in KEYS if k != "###"):
        print(s)

print()
print("=" * 80)
print("B. Q1 教学模型完整输出")
print("=" * 80)
i = next(i for i, l in enumerate(lines) if "2_Q1_TEACHING_OLS" in l)
for l in lines[i:i + 60]:
    print(l)

print()
print("=" * 80)
print("C. VIF 表")
print("=" * 80)
j = next((i for i, l in enumerate(lines) if "多重共线性" in l), None)
if j:
    for l in lines[j:j + 22]:
        print(l)

print()
print("=" * 80)
print("D. 异方差检验")
print("=" * 80)
for mark in ("Breusch-Pagan", "White"):
    j = next((i for i, l in enumerate(lines) if mark in l), None)
    if j:
        for l in lines[j:j + 12]:
            print(l)
        print("-" * 40)

print()
print("=" * 80)
print("E. 主研究模型（HC3）")
print("=" * 80)
j = next(i for i, l in enumerate(lines) if "4_MAIN_OLS_HC3" in l)
for l in lines[j:j + 55]:
    print(l)

print()
print("=" * 80)
print("F. Q3 分组回归输出（节选 R²行）")
print("=" * 80)
for l in lines:
    if "GROUP_" in l and "N=" in l:
        print(l.strip())

print()
print("=" * 80)
print("G. Q3 组间交互检验")
print("=" * 80)
j = next(i for i, l in enumerate(lines) if "5_Q3_INTERACTIONS" in l)
for l in lines[j:j + 90]:
    if any(k in l for k in ("APPEAL_X", "VIDEO_X", "Prob > F", "testparm")):
        print(l.strip())
