# -*- coding: utf-8 -*-
"""校验 .do 脚本与 stata_ads3.csv 的变量兼容性（只读）。

对每个脚本：
  1) 检查 import delimited 用的是哪个 CSV
  2) 逐行找出仍引用「已删除」或「已改名」变量的**非注释**行

用法：D:\\python\\python.exe check_do_vars.py
"""
import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_NEW = os.path.join(HERE, "stata_ads3.csv")

# 已在 stata_ads3.csv 中删除的 33 个变量
DELETED = [
    "is_ad", "pd_ok", "is_hot_topic", "has_ext_link", "is_video_link",
    "is_lottery_link", "appeal_lottery", "appeal_price", "appeal_review",
    "appeal_official", "appeal_explicit", "appeal_type", "pub_dow",
    "det_text_len", "det_pic_num", "cmt_total", "cmt_deep_n", "aud_fol_med",
    "aud_ver_share", "hist_avg_lnengage", "hist_avg_reposts",
    "hist_med_reposts", "hist_n", "hist_prior_n", "non_ad_n",
    "non_ad_avg_reposts", "prof_followers", "prof_statuses",
    "ad_density_wide", "ad_density_strict", "source_grp", "ptype_grp",
    "region",
]

# 已改名的 5 个旧名 -> 新名（n_mentions 保留原名，不计入此处）
RENAMED = {
    "log_followers": "ln_followers",
    "log_age_hours": "ln_age_hours",
    "hist_prior_avg_lnengage": "hist_prior_lnengage0",
    "n_images": "n_pics",
    "kw_stratum": "kw_grp",
}

# 已切到新表的脚本（其余为历史脚本，固定搭配旧表）
SWITCHED = [
    "regression_final.do", "reproduce_all.do", "demo_q1.do", "diag_m4.do",
    "q3_groups.do", "q3_compare.do", "paper_stats.do", "paper_desc2.do",
    "dbg.do",
]
LEGACY = ["analysis_v2.do", "econometric_final.do", "vars_build.do"]
STAY_OLD = ["analysis.do", "analysis2.do", "analysis3.do", "analysis_ads.do",
            "features_check.do", "econometric_stage2.do"]


def header_of(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def scan(path, names):
    """返回 (行号, 行内容, 命中的名字) 列表，跳过纯注释行。"""
    hits = []
    with open(path, encoding="utf-8-sig") as f:
        for i, line in enumerate(f, 1):
            stripped = line.lstrip()
            if stripped.startswith("*") or stripped.startswith("//"):
                continue
            body = re.split(r"//(?!/)", line)[0]      # 去掉行尾注释，但保住 ///
            for n in names:
                if re.search(r"\b" + re.escape(n) + r"\b", body):
                    hits.append((i, line.rstrip(), n))
    return hits


def main():
    cols = set(header_of(CSV_NEW))
    print("=" * 78)
    print("新表 stata_ads3.csv 变量数 = {}".format(len(cols)))
    print("=" * 78)

    files = SWITCHED + LEGACY + STAY_OLD
    ok = True
    for fn in files:
        p = os.path.join(HERE, fn)
        if not os.path.isfile(p):
            print("\n[?] 找不到 {}".format(fn))
            continue
        with open(p, encoding="utf-8-sig") as f:
            text = f.read()
        imports = re.findall(r"import delimited\s+\"([^\"]+)\"", text)
        tag = "SWITCHED" if fn in SWITCHED else ("LEGACY " if fn in LEGACY else "OLD-DATA")
        print("\n[{}] {}".format(tag, fn))
        print("    import -> {}".format(", ".join(os.path.basename(x) for x in imports) or "无"))

        hits = scan(p, DELETED + list(RENAMED))
        # 过滤掉本身就是新名的假命中（如 n_mentions_c 里的 n_mentions 不会命中，\b 已挡住）
        if not hits:
            print("    ✔ 无已删除/已改名变量的残留引用")
            continue
        if fn in STAY_OLD or fn in LEGACY:
            print("    （历史脚本，固定搭配旧表，不计入失败：{} 处）".format(len(hits)))
            continue
        ok = False
        print("    ✘ 仍有 {} 处残留：".format(len(hits)))
        for ln, txt, name in hits:
            print("        L{:<4} [{}] {}".format(ln, name, txt.strip()[:90]))

    print("\n" + "=" * 78)
    print("结论：{}".format("全部已切换脚本通过 ✔" if ok else "存在残留，见上 ✘"))
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
