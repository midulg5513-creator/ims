# -*- coding: utf-8 -*-
"""只读体检：对 stata_ads2.csv 的 61 个变量做方差/缺失/共线/稀疏类诊断。

用法： D:\\python\\python.exe profile_vars.py
不写任何文件，只打印。
"""
import csv
import math
import os
import statistics as st
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "stata_ads2.csv")
MISSING = {"", ".", "NA", "na", "NaN", "nan", "null", "None"}


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        cols = list(rd.fieldnames)
        rows = list(rd)
    return cols, rows


def as_float(v):
    if v is None:
        return None
    v = str(v).strip()
    if v in MISSING:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def is_numeric_series(vals):
    nonmiss = [v for v in vals if str(v).strip() not in MISSING]
    if not nonmiss:
        return False
    ok = sum(1 for v in nonmiss if as_float(v) is not None)
    return ok / len(nonmiss) >= 0.95


def corr(xs, ys):
    pair = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
    if len(pair) < 3:
        return None
    a = [p[0] for p in pair]
    b = [p[1] for p in pair]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((v - ma) ** 2 for v in a))
    sb = math.sqrt(sum((v - mb) ** 2 for v in b))
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in pair) / (sa * sb)


def main():
    cols, rows = read(SRC)
    n = len(rows)
    print("=" * 78)
    print("文件：{}    行数 n={}    列数 k={}".format(os.path.basename(SRC), n, len(cols)))
    print("=" * 78)

    numeric = {}
    print("\n【A】逐列体检：缺失 / 唯一值 / 极值 / 是否零方差")
    print("{:<24} {:>6} {:>7} {:>8} {:>12} {:>12} {:>7} {:>7} {:>7} {:>7}".format(
        "变量", "nMiss", "缺失%", "nUnique", "min", "max", "mean", "sd", "p50", "偏度"))
    for c in cols:
        vals = [r.get(c, "") for r in rows]
        miss = sum(1 for v in vals if str(v).strip() in MISSING)
        nonmiss = [v for v in vals if str(v).strip() not in MISSING]
        uniq = len(set(nonmiss))
        num = is_numeric_series(vals)
        numeric[c] = num
        if num:
            fv = [as_float(v) for v in vals]
            fv_nm = [v for v in fv if v is not None]
            mean = sum(fv_nm) / len(fv_nm)
            sd = st.pstdev(fv_nm) if len(fv_nm) > 1 else 0.0
            med = st.median(fv_nm)
            if sd > 0:
                sk = sum(((v - mean) / sd) ** 3 for v in fv_nm) / len(fv_nm)
            else:
                sk = 0.0
            flag = "  <== 零方差" if sd == 0 else ""
            print("{:<24} {:>6} {:>7.1f} {:>8} {:>12.4g} {:>12.4g} {:>7.3g} {:>7.3g} {:>7.3g} {:>7.2f}{}".format(
                c, miss, 100.0 * miss / n, uniq, min(fv_nm), max(fv_nm), mean, sd, med, sk, flag))
        else:
            print("{:<24} {:>6} {:>7.1f} {:>8} {:>12} {:>12}".format(
                c, miss, 100.0 * miss / n, uniq, "-", "-"))

    print("\n【B】类别变量的水平分布（含 <5 条的空桶风险）")
    for c in cols:
        if numeric[c]:
            continue
        cnt = Counter(str(r.get(c, "")).strip() for r in rows)
        small = [k for k, v in cnt.items() if v < 5]
        print("\n  -- {}  （{} 个水平，其中 {} 个 <5 条）".format(c, len(cnt), len(small)))
        for k, v in cnt.most_common():
            mark = "   <== n<5" if v < 5 else ""
            print("       {:<14} {:>4}{}".format(k if k else "(空)", v, mark))

    print("\n【C】数值变量两两相关系数 > |0.80| 的疑似重复对")
    numcols = [c for c in cols if numeric[c]]
    series = {c: [as_float(r.get(c, "")) for r in rows] for c in numcols}
    pairs = []
    for i in range(len(numcols)):
        for j in range(i + 1, len(numcols)):
            a, b = numcols[i], numcols[j]
            rho = corr(series[a], series[b])
            if rho is not None and abs(rho) > 0.80:
                pairs.append((abs(rho), a, b, rho))
    for _, a, b, rho in sorted(pairs, reverse=True):
        print("  {:<26} {:<26} rho = {:+.4f}".format(a, b, rho))
    if not pairs:
        print("  （无）")

    print("\n【D】与因变量相关的候选冗余（|rho| > 0.80 已在 C 列）")


if __name__ == "__main__":
    main()
