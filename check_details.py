# -*- coding: utf-8 -*-
"""核查批次 A 新变量的信号质量（是否像 ad_marked 一样全无变异）。

用法：D:\\python\\python.exe check_details.py
"""
import collections
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def rd(n):
    p = os.path.join(HERE, n)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    base = {r["post_id"]: r for r in rd("stata_ads.csv")}
    det = rd("post_details.csv")
    lin = {r["src_url"]: r for r in rd("link_resolve.csv")}

    ok = [r for r in det if r.get("ok") == "1"]
    print("stata_ads 行数 = %d | post_details 命中 %d（ok=1: %d，失败 %d）"
          % (len(base), len(det), len(ok), len(det) - len(ok)))

    cnt = collections.Counter()
    page_type = collections.Counter()
    src = collections.Counter()
    for r in ok:
        cnt["has_url_ori"] += 1 if (r.get("page_url_ori") or "").strip() else 0
        cnt["is_hot_topic"] += 1 if r.get("is_hot_topic") == "1" else 0
        cnt["is_video"] += 1 if r.get("is_video") == "1" else 0
        cnt["ad_marked"] += 1 if r.get("ad_marked") == "1" else 0
        page_type[r.get("page_type") or "none"] += 1
        src[r.get("source_tool") or "-"] += 1
    n = len(ok) or 1
    print("\n== 帖级信号（n=%d）==" % len(ok))
    for k in ("has_url_ori", "is_hot_topic", "is_video", "ad_marked"):
        print("   %-14s %3d (%.1f%%)" % (k, cnt[k], 100.0 * cnt[k] / n))
    print("   page_type 分布:", dict(page_type))
    print("   source_tool Top8:", src.most_common(8))

    print("\n== 链接落地（n=%d）==" % len(lin))
    h = collections.Counter(r["final_host"] for r in lin.values() if r.get("ok") == "1")
    for k, v in h.most_common(8):
        print("   %-30s %d" % (k, v))

    # page_type 与「是否真有外链落地」的交叉：区分话题页 vs 真内容页
    cross = collections.Counter()
    for r in ok:
        pt = r.get("page_type") or "none"
        u = (r.get("page_url_ori") or "").strip()
        host = (lin.get(u) or {}).get("final_host") or ("none" if not u else "unresolved")
        cross[(pt, "video" if "video" in host else
               ("lottery" if "lottery" in host else
                ("passport" if "passport" in host else host)))] += 1
    print("\n== page_type × 落地域名 ==")
    for (pt, host), c in sorted(cross.items(), key=lambda x: (-x[1], x[0][0])):
        print("   %-14s %-24s %d" % (pt, host, c))

    # 与基线字段一致性：det_pic_num vs n_images / det_text_len vs text_len
    same = diffs = 0
    big = 0
    pairs = 0
    for r in ok:
        b = base.get(r["post_id"])
        if not b:
            continue
        pairs += 1
        if str(r.get("pic_num")) == str(b.get("n_images")):
            same += 1
        else:
            diffs += 1
        try:
            if abs(int(r.get("text_length") or 0) - int(b.get("text_len") or 0)) > 400:
                big += 1
        except ValueError:
            pass
    print("\n== 与基线一致性（%d 对）==" % pairs)
    print("   pic_num 完全一致 %d / 不一致 %d" % (same, diffs))
    print("   text_len 差异 >400 字符的 %d 条（长文接口差异）" % big)

    # 反复出现的 post_id（重复行）
    ids = collections.Counter(r["post_id"] for r in det)
    dup = {k: v for k, v in ids.items() if v > 1}
    print("\n重复 post_id 行数 =", len(dup))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
