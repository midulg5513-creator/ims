# -*- coding: utf-8 -*-
"""验证若干"重复变量"的精确等价性，只读。"""
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MISS = {"", ".", "NA", "nan", "None"}


def rd(name):
    with open(os.path.join(HERE, name), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def f(v):
    v = (v or "").strip()
    if v in MISS:
        return None
    try:
        return float(v)
    except ValueError:
        return None


rows = rd("stata_ads2.csv")
n = len(rows)

def check(name, a_fn, b_fn):
    both = same = diff = 0
    bad = []
    for r in rows:
        a, b = a_fn(r), b_fn(r)
        if a is None or b is None:
            continue
        both += 1
        if a == b:
            same += 1
        else:
            diff += 1
            if len(bad) < 3:
                bad.append((r["post_id"], a, b))
    print("{:<52} 可比 {:>3}  相同 {:>3}  不同 {:>3}  {}".format(
        name, both, same, diff, bad if bad else ""))

print("=== 精确等价性检查 (n=%d) ===" % n)
check("is_lottery  ==  appeal_lottery",
      lambda r: f(r["is_lottery"]), lambda r: f(r["appeal_lottery"]))
check("has_ext_link  ==  (link_grp != none)",
      lambda r: f(r["has_ext_link"]), lambda r: 0.0 if r["link_grp"] == "none" else 1.0)
check("is_video_link  ==  (link_grp==video_weibo)",
      lambda r: f(r["is_video_link"]), lambda r: 1.0 if r["link_grp"] == "video_weibo" else 0.0)
check("is_lottery_link  ==  (link_grp==lottery_weibo)",
      lambda r: f(r["is_lottery_link"]), lambda r: 1.0 if r["link_grp"] == "lottery_weibo" else 0.0)
check("comments  ==  cmt_total",
      lambda r: f(r["comments"]), lambda r: f(r["cmt_total"]))
check("log_followers  ==  log10(followers)",
      lambda r: round(f(r["log_followers"]), 4) if f(r["log_followers"]) is not None else None,
      lambda r: round(math.log10(f(r["followers"])), 4) if f(r["followers"]) and f(r["followers"]) > 0 else None)
check("log_age_hours  ==  ln(1+age_hours)",
      lambda r: round(f(r["log_age_hours"]), 6) if f(r["log_age_hours"]) is not None else None,
      lambda r: round(math.log1p(f(r["age_hours"])), 6) if f(r["age_hours"]) is not None else None)
check("log_followers  ==  ln(followers)",
      lambda r: round(f(r["log_followers"]), 4) if f(r["log_followers"]) is not None else None,
      lambda r: round(math.log(f(r["followers"])), 4) if f(r["followers"]) and f(r["followers"]) > 0 else None)
check("det_pic_num  ==  n_images",
      lambda r: f(r["det_pic_num"]), lambda r: f(r["n_images"]))
check("det_text_len  ==  text_len",
      lambda r: f(r["det_text_len"]), lambda r: f(r["text_len"]))
check("prof_followers  ==  followers",
      lambda r: f(r["prof_followers"]), lambda r: f(r["followers"]))
check("has_prior_hist  ==  (hist_prior_avg_lnengage 非缺失)",
      lambda r: f(r["hist_prior_n"]) if f(r["hist_prior_n"]) is not None else None,
      lambda r: (1.0 if (f(r["hist_prior_avg_lnengage"]) is not None) else 0.0))

print()
print("=== is_weekend 与 pub_dow 的对应 ===")
from collections import Counter
c = Counter((r["pub_dow"], r["is_weekend"]) for r in rows)
for k, v in sorted(c.items()):
    print("   dow={} weekend={}  n={}".format(k[0], k[1], v))

print()
print("=== appeal_type / appeal_grp / 原始哑变量 的一致性 ===")
c = Counter((r["appeal_type"], r["appeal_grp"], r["appeal_lottery"], r["appeal_price"],
             r["appeal_review"], r["appeal_official"], r["appeal_explicit"]) for r in rows)
print("  类型  grp  抽奖 价格 种草 官宣 硬广   n")
for k, v in sorted(c.items(), key=lambda x: -x[1]):
    print("  {:>6} {:>6} {:>4} {:>4} {:>4} {:>4} {:>4}  {:>4}".format(*k, v))

print()
print("=== pd_ok / is_hot_topic / ad_density_strict 的取值分布 ===")
for col in ("pd_ok", "is_hot_topic", "is_lottery_link", "has_ext_link"):
    print("  {:<18} {}".format(col, dict(Counter(r[col] for r in rows))))

print()
print("=== 缺失模式 ===")
for col in ("hist_prior_avg_lnengage", "hist_avg_lnengage", "non_ad_avg_reposts",
            "prof_followers", "cmt_total", "hist_n"):
    k = sum(1 for r in rows if f(r[col]) is None)
    print("  {:<26} 缺失 {:>3} ({:.1f}%)".format(col, k, 100.0 * k / n))

print()
print("=== hist_n == 0 的作者有多少帖 ===")
print("  hist_n=0 的帖子数 =", sum(1 for r in rows if f(r["hist_n"]) == 0))
print("  hist_prior_n=0 的帖子数 =", sum(1 for r in rows if f(r["hist_prior_n"]) == 0))

print()
print("=== age_hours 与 post_id 的关系（是否等于采集批次）===")
s = sorted(rows, key=lambda r: f(r["post_id"]))
print("  按 post_id 升序后可观察 age_hours 是否单调：")
mono = all(f(s[i]["age_hours"]) <= f(s[i + 1]["age_hours"]) for i in range(len(s) - 1))
print("    完全单调递增 =", mono)
print("  age_hours 前 5 =", [round(f(r['age_hours']), 1) for r in s[:5]])
print("  age_hours 后 5 =", [round(f(r['age_hours']), 1) for r in s[-5:]])
