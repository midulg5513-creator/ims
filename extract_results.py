# -*- coding: utf-8 -*-
"""从 Stata 日志提取关键结果（Q1/Q2/Q3 + 假设检验），生成紧凑汇总。

不用 PowerShell 过滤：UTF-8 中文会被按 ANSI 解码成乱码（本机已验证）。

用法：D:\\python\\python.exe extract_results.py [--log analysis_v2.log]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

WANT_PREFIX = ("### ", "STEP ", "Q_", "Q1_", "Q2_", "Q3_", "H1", "H4",
               "PPML_", "NBREG_", "ZERO_", "LNREL_", "COVER_", "N_M12", "GROUP_",
               "A_", "B_", "C_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="analysis_v2.log")
    ap.add_argument("--save", default="results_summary.txt")
    args = ap.parse_args()

    p = os.path.join(HERE, args.log)
    if not os.path.exists(p):
        print("[x] 找不到日志 %s" % p)
        return 1
    with open(p, encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()

    print("[i] 日志 %s：%d 行" % (args.log, len(lines)))

    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith(WANT_PREFIX):
            out.append(s)
        elif s.startswith("r(") and s.endswith(";"):
            out.append("!!! Stata 错误: " + s)
        elif "no observations" in s or "not found" in s or "not valid" in s:
            out.append("!!! " + s)

    print("\n".join(out))
    with open(os.path.join(HERE, args.save), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n[out] 已保存 %s" % args.save)

    errs = [o for o in out if o.startswith("!!!")]
    print("[i] 错误/异常行数: %d" % len(errs))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
