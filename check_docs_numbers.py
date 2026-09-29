# -*- coding: utf-8 -*-
"""
check_docs_numbers.py —— 文档数字/变量名一致性体检

用途
----
变量清理后（stata_ads2.csv -> stata_ads3.csv），所有文档里的**结果数字**和**变量名**
必须与 stata_ads3.csv 的实测输出一致。本脚本扫描工作区所有 .md 文件：

  A. 禁用列表（旧结果数字）—— 只允许出现在明确标注的"对照/历史"文件里
  B. 必需列表（新结果数字）—— 关键文档里必须出现
  C. 变量名残留 —— 旧变量名只允许出现在"重命名说明"或"口径提示"行

退出码 0 = 通过；1 = 有 FAIL。

可重跑。新增文档后重跑一次即可。
"""
from __future__ import annotations

import os
import re
import sys

WORKDIR = r"d:\AI\爬虫"

# ---------------------------------------------------------------- 允许清单
# 这些文件里出现旧数字/旧变量名是**有意为之**（对照表、变更日志、口径提示）
ALLOW_OLD_NUMBERS = {
    "变量清理说明.md",          # 新旧对照表（第八节）
    "研究设计_v2_重规划.md",    # 立项阶段的“预演”记录，已在文件头声明不作最终结论
}

ALLOW_OLD_NAMES_HINT = (
    "对照", "重命名", "旧表", "旧名", "已弃用", "变更", "口径提示", "旧版",
    "log10", "清理前", "旧变量", "原名", "历史", "->", "→", "（旧", "(旧",
)

# ---------------------------------------------------------------- A. 旧结果数字
OLD_NUMBERS = [
    "0.30797781", "0.307978",      # Q1 R2
    "0.29454049", "0.2945404",     # Q1 Adj R2
    "378.49986350", "378.4999",
    "850.48433133", "850.4843",
    "2.03188698", "2.0319",
    "4.12856472",
    "94.62496587",
    "0.466049",                    # M4 R2
    "0.461967",                    # Q2 目标
    "0.505015",                    # M9 R2
    "0.486855",                    # 主模型 R2
    "0.432840",                    # 主模型 Adj R2
    "0.555360",                    # 品牌官宣分组 R2
    "37.44", "78.87",              # 旧 BP / White
    "22.91957917645729",           # 旧 e(F)
    ".3079778121576361",           # 旧 e(r2)
]

# ---------------------------------------------------------------- B. 新结果数字
NEW_NUMBERS_KEY_DOCS = {
    "作业答案_q1q2q3_v2.md": ["0.308606", "0.295181", "0.462909", "0.465922",
                              "379.27156101", "849.71263382", "1228.98419483"],
    "回归模型_修订版.md": ["0.308606", "0.462909", "0.465922", "0.486908", "0.499844"],
    "Stata复现步骤.md": ["0.308606", "0.462909", "0.465922"],
    "Stata手把手教学.md": ["0.308606", "0.462909", "0.465922",
                           "379.27156101", "849.71263382", "1228.98419483"],
    "论文_微博广告帖子影响力研究.md": ["0.308606", "0.465922", "0.486908"],
    "作业答案_q3_分类型回归.md": ["0.5556", "0.4590", "0.5928", "0.4015"],
    "建模数据说明.md": ["stata_ads3.csv"],
}

# ---------------------------------------------------------------- C. 旧变量名
OLD_VARS = [
    "log_followers", "logf_sq", "log_age_hours",
    "hist_prior_avg_lnengage", "n_images", "kw_stratum",
    "ptype_grp", "prof_followers", "cmt_total",
    "aud_fol_med", "aud_ver_share", "hist_avg_lnengage",
]

# 全工作区都不应再出现旧数据文件名（除非是"旧版/历史"语境）
OLD_DATA = ["stata_ads2.csv"]

# 这些文件整体豁免（早期阶段报告，已在文件头加口径提示）
EXEMPT_FILES = {
    "微博广告帖子影响力研究报告.md",
    "数据特点说明.md",
    "假设体系_结合范文修订版.md",
    "参考文献_文献综述.md",
    "研究设计_v2_重规划.md",
    "计量经济研究方案_最终版.md",
    "STAGE2_README.md",
    "STAGE2_PREREGISTRATION.md",
    "变量清理说明.md",
    "建模数据说明.md",
}


def md_files() -> list[str]:
    out = []
    for name in sorted(os.listdir(WORKDIR)):
        if name.lower().endswith(".md"):
            out.append(name)
    return out


def main() -> int:
    fails: list[str] = []
    warns: list[str] = []
    checks = 0

    texts: dict[str, list[str]] = {}
    for name in md_files():
        path = os.path.join(WORKDIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                texts[name] = f.read().splitlines()
        except UnicodeDecodeError:
            with open(path, encoding="gbk", errors="replace") as f:
                texts[name] = f.read().splitlines()

    # ---- A. 旧结果数字
    print("=" * 72)
    print("A. 旧结果数字残留检查")
    print("=" * 72)
    for name, lines in texts.items():
        if name in ALLOW_OLD_NUMBERS:
            continue
        for i, line in enumerate(lines, 1):
            for tok in OLD_NUMBERS:
                if tok in line:
                    checks += 1
                    msg = f"[FAIL] {name}:{i}  旧数字 {tok!r}  →  {line.strip()[:110]}"
                    fails.append(msg)
                    print(msg)

    # ---- B. 新结果数字必须出现
    print()
    print("=" * 72)
    print("B. 关键文档新数字完整性检查")
    print("=" * 72)
    for name, needed in NEW_NUMBERS_KEY_DOCS.items():
        if name not in texts:
            checks += 1
            fails.append(f"[FAIL] 缺少关键文档 {name}")
            print(f"[FAIL] 缺少关键文档 {name}")
            continue
        joined = "\n".join(texts[name])
        for tok in needed:
            checks += 1
            if tok not in joined:
                fails.append(f"[FAIL] {name} 缺少新数字 {tok!r}")
                print(f"[FAIL] {name} 缺少新数字 {tok!r}")
            else:
                print(f"[ ok ] {name}  含 {tok}")

    # ---- C. 旧变量名
    print()
    print("=" * 72)
    print("C. 旧变量名残留检查（带语境豁免）")
    print("=" * 72)
    for name, lines in texts.items():
        if name in EXEMPT_FILES:
            print(f"[skip] {name}（已加口径提示 / 属对照文档）")
            continue
        for i, line in enumerate(lines, 1):
            for var in OLD_VARS:
                if var not in line:
                    continue
                checks += 1
                if any(h in line for h in ALLOW_OLD_NAMES_HINT):
                    print(f"[warn] {name}:{i}  {var}（语境豁免）: {line.strip()[:100]}")
                    warns.append(f"{name}:{i} {var}")
                else:
                    fails.append(f"[FAIL] {name}:{i} 旧变量名 {var}  →  {line.strip()[:110]}")
                    print(f"[FAIL] {name}:{i} 旧变量名 {var}  →  {line.strip()[:110]}")

    # ---- D. 旧数据文件名
    print()
    print("=" * 72)
    print("D. 旧数据文件名残留检查")
    print("=" * 72)
    for name, lines in texts.items():
        if name in EXEMPT_FILES:
            continue
        for i, line in enumerate(lines, 1):
            for tok in OLD_DATA:
                if tok in line:
                    checks += 1
                    if any(h in line for h in ALLOW_OLD_NAMES_HINT) or "不是" in line:
                        print(f"[warn] {name}:{i}  {tok}（语境豁免）: {line.strip()[:100]}")
                        warns.append(f"{name}:{i} {tok}")
                    else:
                        fails.append(f"[FAIL] {name}:{i} 出现 {tok}  →  {line.strip()[:110]}")
                        print(f"[FAIL] {name}:{i} 出现 {tok}  →  {line.strip()[:110]}")

    # ---- 汇总
    print()
    print("=" * 72)
    print(f"共执行检查 {checks} 项；FAIL {len(fails)}；豁免 WARN {len(warns)}")
    print("结论：" + ("全部一致 ✔" if not fails else "存在未同步的数字/变量名 ✘"))
    print("=" * 72)
    if fails:
        print("\n未通过项：")
        for m in fails:
            print("  " + m)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
