# -*- coding: utf-8 -*-
"""统计批次 A/B/C 新数据对建模样本（211 帖）的覆盖率。"""
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
    base = rd("stata_ads.csv")
    n = len(base)
    base_authors = {r["author_id"] for r in base}
    base_posts = {r["post_id"] for r in base}

    prof = rd("author_profile.csv")
    ok_authors = {r["author_id"] for r in prof if r.get("ok") == "1"}

    ap = rd("author_posts.csv")
    ap_authors = {r["author_id"] for r in ap}
    ap_posts = {r["post_id"] for r in ap}

    det = rd("post_details.csv")
    det_posts = {r["post_id"] for r in det if r.get("ok") == "1"}

    cd = rd("comments_deep.csv")
    cd_posts = {r["post_id"] for r in cd}

    merged = rd("stata_ads2.csv")
    prior_rows = [r for r in merged if str(r.get("hist_prior_n", "")).strip() not in ("", ".")
                  and float(r.get("hist_prior_n", 0)) > 0]

    print("建模样本：%d 帖 / %d 位作者" % (n, len(base_authors)))
    print("")
    print("[批次A 帖详情]  覆盖 %d/%d 帖 (%.1f%%)"
          % (len(base_posts & det_posts), n, 100.0 * len(base_posts & det_posts) / n))
    print("[批次B 作者资料] ok 作者 %d/%d (%.1f%%)"
          % (len(base_authors & ok_authors), len(base_authors),
             100.0 * len(base_authors & ok_authors) / len(base_authors)))
    cov_b = sum(1 for r in base if r["author_id"] in ap_authors)
    print("[批次B 历史帖]   有历史数据的帖 %d/%d (%.1f%%)，历史帖行数 %d"
          % (cov_b, n, 100.0 * cov_b / n, len(ap)))
    if merged:
        print("[批次B 事前历史] 严格早于目标帖的可用记录 %d/%d (%.1f%%)"
              % (len(prior_rows), n, 100.0 * len(prior_rows) / n))
    print("[批次C 评论]     覆盖 %d/%d 帖 (%.1f%%)，评论行数 %d"
          % (len(base_posts & cd_posts), n, 100.0 * len(base_posts & cd_posts) / n, len(cd)))
    print("")
    miss_b = sorted(base_authors - {r["author_id"] for r in base if r["author_id"] in ap_authors})
    print("无历史数据的作者数：%d" % len(base_authors - ap_authors))
    miss_c = sorted(base_posts - cd_posts)
    print("无评论数据的帖数：%d（多为无评论/评论关闭，非必然失败）" % len(miss_c))
    dup_prof = len(prof) - len({r["author_id"] for r in prof})
    dup_ap = len(ap) - len({(r["author_id"], r["post_id"]) for r in ap})
    dup_cd = len(cd) - len({(r["post_id"], r["comment_id"]) for r in cd})
    print("重复行：author_profile %d / author_posts %d / comments_deep %d" % (dup_prof, dup_ap, dup_cd))
    if merged:
        ages = [float(r["age_hours"]) for r in merged if r.get("age_hours") not in ("", ".")]
        if ages:
            ages.sort()
            print("曝光时长：min %.2f / median %.2f / max %.2f 小时"
                  % (ages[0], ages[len(ages) // 2], ages[-1]))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
