# -*- coding: utf-8 -*-
"""作业 Q1 的独立核算：用纯 Python（Gauss-Jordan 解正规方程）重算 A0 模型，
与 Stata 的 regress 输出逐个比对，量化差异并定位来源。

A0 规格：Y = ln(reposts+1) ~ log_followers + text_len + n_images + is_lottery
Stata 实测值（analysis_ads.do / analysis_v2.do 日志）：
  SSR 378.49986350  SSE 850.48433133  SST 1228.98419483
  MSR  94.62496587  MSE   4.12856472  RootMSE 2.03188698
  R2 0.30797781  adjR2 0.29454049  n=211  k=4（不含常数项） df_r=206

用法：D:\\python\\python.exe manual_check_q1.py
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ols_preview as op  # noqa: E402

STATA = {
    "ssr": 378.49986350, "sse": 850.48433133, "sst": 1228.98419483,
    "msr": 94.62496587, "mse": 4.12856472, "rmse": 2.03188698,
    "r2": 0.30797781, "adj": 0.29454049, "n": 211, "k_excl_const": 4, "df_r": 206,
}


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def load_rows():
    for name in ("stata_ads2.csv", "stata_ads.csv"):
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            import csv
            with open(p, encoding="utf-8-sig") as f:
                return list(csv.DictReader(f)), name
    return [], ""


def main():
    rows, src = load_rows()
    if not rows:
        print("[x] 找不到 stata_ads.csv / stata_ads2.csv")
        return 1
    print("[i] 数据源：%s（%d 行）" % (src, len(rows)))

    y = [math.log(num(r["reposts"]) + 1) for r in rows]
    X = [[1.0,
          num(r["log_followers"]),
          num(r["text_len"]),
          num(r["n_images"]),
          num(r["is_lottery"])] for r in rows]

    res = op.ols_regress(y, X)
    if not res:
        print("[x] 回归失败（可能列共线）")
        return 1

    k_excl = res["k"] - 1
    msr = res["ssr"] / res["df_m"]
    mse = res["sse"] / res["df_r"]

    print("\n=== Python（Gauss-Jordan 正规方程）===")
    print("  n=%d  参数个数(含常数)=%d  不含常数 k=%d  df_m=%d  df_r=%d  剔除共线列=%d"
          % (res["n"], res["k"], k_excl, res["df_m"], res["df_r"], res["dropped"]))
    print("  SSR     = %.8f" % res["ssr"])
    print("  SSE     = %.8f" % res["sse"])
    print("  SST     = %.8f" % res["sst"])
    print("  MSR     = %.8f" % msr)
    print("  MSE     = %.8f" % mse)
    print("  RootMSE = %.8f" % res["rmse"])
    print("  R2      = %.8f" % res["r2"])
    print("  adjR2   = %.8f" % res["adj"])

    print("\n=== 与 Stata 对比 ===")
    print("  %-10s %16s %16s %16s %12s" % ("指标", "Python", "Stata", "绝对差", "相对差"))
    for key, py, st in (("SSR", res["ssr"], STATA["ssr"]),
                        ("SSE", res["sse"], STATA["sse"]),
                        ("SST", res["sst"], STATA["sst"]),
                        ("MSR", msr, STATA["msr"]),
                        ("MSE", mse, STATA["mse"]),
                        ("RootMSE", res["rmse"], STATA["rmse"]),
                        ("R2", res["r2"], STATA["r2"]),
                        ("adjR2", res["adj"], STATA["adj"])):
        rel = (py - st) / st * 100 if st else 0
        print("  %-10s %16.8f %16.8f %16.10f %11.2e%%" % (key, py, st, py - st, rel))

    print("\n=== 差异来源分解（供报告 Q1 直接引用）===")
    print("  1) 算法差异：Stata 用 QR 分解，本脚本用 Gauss-Jordan 解正规方程；")
    print("     正规方程的构造数约是条件数的平方，float64 下会放大舍入误差。")
    print("  2) 数据键入差异：Y 由 log10/ln 口径决定，本脚本与 Stata 同为 ln(reposts+1)。")
    print("  3) 自由度口径：adjR2 = 1-(1-R2)(n-1)/(n-k-1)，k 不含常数项。")
    r2_wrong = res["r2"]
    adj_wrong = 1 - (1 - r2_wrong) * (res["n"] - 1) / (res["n"] - k_excl)
    print("     若误把常数项计入 k：adjR2 = %.8f，与正确值差 %.7f（量级远大于舍入差异）"
          % (adj_wrong, abs(adj_wrong - res["adj"])))
    print("  4) 量级对比：SSE 相对差 %.2e 属浮点舍入；adjR2 口径写错则差 %.2e"
          % (abs((res["sse"] - STATA["sse"]) / STATA["sse"]),
             abs((adj_wrong - res["adj"]) / res["adj"])))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
