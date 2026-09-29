# -*- coding: utf-8 -*-
"""按标记提取 Stata 日志片段（用于读取系数表）。

用法：
  D:\\python\\python.exe extract_blocks.py --log analysis_v2.log --tag "### H1_MAIN" --lines 30
  D:\\python\\python.exe extract_blocks.py --log analysis_v2.log --tag "### H4D_SLOPE_LOW_DENSITY" --lines 22
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="analysis_v2.log")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--lines", type=int, default=25)
    ap.add_argument("--all", type=int, default=1, help="1=匹配所有同名标记")
    args = ap.parse_args()

    p = os.path.join(HERE, args.log)
    with open(p, encoding="utf-8", errors="ignore") as f:
        s = f.read().splitlines()

    hits = [i for i, l in enumerate(s) if args.tag in l]
    if not hits:
        print("[x] 未找到标记 %s" % args.tag)
        return 1
    for k, i in enumerate(hits if args.all else hits[:1]):
        if k:
            print("\n" + "=" * 70)
        print("\n".join(s[i:i + args.lines]))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
