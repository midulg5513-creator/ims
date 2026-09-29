# -*- coding: utf-8 -*-
"""把批次 A/B/C 的新变量合并进建模数据表，生成 stata_ads2.csv（不覆盖原表）。

输入：
  stata_ads.csv       基线 32 列（211 行）
  post_details.csv    批次 A：帖级详情（外链/热搜/发布工具/图片数/文本长度）
  link_resolve.csv    批次 A：外链落地域名
  author_posts.csv    批次 B：作者历史帖
  author_profile.csv  批次 B：作者资料
  comments_deep.csv   批次 C：深评论（可选；缺失时跳过）

新增变量（全部 ASCII 命名，便于 Stata import）：
  帖级
    pd_ok            帖详情是否采到
    has_ext_link     page_info.url_ori 非空
    link_grp         none / video_weibo / lottery_weibo / passport / other
    is_video_link    落地页为微博视频页
    is_lottery_link  落地页为抽奖活动页（客观抽奖信号）
    is_hot_topic     详情中含 hot_rank_darwin 标识（进过热搜池）
    det_pic_num      详情返回的图片数
    det_text_len     详情返回的文本长度
    source_grp       发布工具分组（video_channel/super_topic/client/web/other）
  作者级（H1c 信源质量、H4d 说服知识累积）
    hist_n                 抓到的历史帖数
    hist_avg_lnengage      主页时间线全部帖均值（仅保留作泄漏诊断）
    hist_prior_n           严格早于目标帖发布的作者帖子数
    hist_prior_avg_lnengage 事前帖子 mean(ln(转发+评论+赞+1)) ← H1c 主口径
    hist_avg_reposts       转发均值
    hist_med_reposts       转发中位数
    ad_density             疑似广告占比（宽松：含外链）
    ad_density_strict      疑似广告占比（严格：广告标签或合作话术）
    non_ad_n               非疑似广告帖数
    non_ad_avg_reposts     非疑似广告帖转发均值       ← 作者内对照基准
  受众级（批次 C，文件存在时才加）
    cmt_total              帖子评论总量（hotflow total_number）
    cmt_deep_n             深挖到的评论条数
    aud_fol_med            评论者粉丝数中位
    aud_ver_share          评论者认证占比

用法：D:\\python\\python.exe merge_features.py
"""
import csv
import datetime as dt
import math
import os
import re
import statistics as st
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "stata_ads.csv")
OUT = os.path.join(HERE, "stata_ads2.csv")


def parse_datetime(value):
    """Parse target ISO timestamps and Weibo's RFC-like timestamps as UTC."""
    value = (value or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        try:
            return dt.datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError:
            return None
    try:
        parsed = dt.datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def rd(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def source_grp(s):
    s = s or ""
    if "视频" in s or "秒拍" in s:
        return "video_channel"
    if "超话" in s:
        return "super_topic"
    if "微博" in s or "iPhone" in s or "Android" in s or "HUAWEI" in s or "小米" in s:
        return "client"
    if "网页" in s or "Web" in s or "web" in s:
        return "web"
    return "other"


def main():
    base = rd("stata_ads.csv")
    if not base:
        print("[x] 缺少 stata_ads.csv")
        return 1
    base_cols = list(base[0].keys())

    # Target timestamps are needed to keep author-history features strictly pre-treatment.
    target_time = {
        r.get("post_id", ""): parse_datetime(r.get("created_at"))
        for r in rd("posts.csv")
    }

    # ---------- 帖级：批次 A（去重：同一 post_id 优先保留 ok=1 的行）----------
    pd = {}
    for r in rd("post_details.csv"):
        pid = r["post_id"]
        old = pd.get(pid)
        if old and old.get("ok") == "1" and r.get("ok") != "1":
            continue
        pd[pid] = r
    lr = {r["src_url"]: r for r in rd("link_resolve.csv")}

    def link_grp_of(pid):
        d = pd.get(pid)
        if not d:
            return "none"
        u = (d.get("page_url_ori") or "").strip()
        if not u:
            return "none"
        r = lr.get(u)
        host = (r or {}).get("final_host") or ""
        if not host:
            return "other"
        if "video.weibo" in host:
            return "video_weibo"
        if "lottery" in host:
            return "lottery_weibo"
        if "passport" in host:
            return "passport"
        return "other"

    # ---------- 作者级：批次 B ----------
    # 去重：同一作者多行时优先保留 ok=1；历史帖按 post_id 去重（重复运行会追加行）
    prof = {}
    for r in rd("author_profile.csv"):
        aid = r["author_id"]
        old = prof.get(aid)
        if old and old.get("ok") == "1" and r.get("ok") != "1":
            continue
        prof[aid] = r
    aposts = defaultdict(dict)
    for r in rd("author_posts.csv"):
        aposts[r["author_id"]][r["post_id"]] = r

    # ---------- 受众级：批次 C（按 comment_id 去重）----------
    cdeep = defaultdict(dict)
    for r in rd("comments_deep.csv"):
        cdeep[r["post_id"]][r["comment_id"]] = r

    extra = ["pd_ok", "has_ext_link", "link_grp", "is_video_link", "is_lottery_link",
             "is_hot_topic", "det_pic_num", "det_text_len", "source_grp", "ptype_grp",
             "hist_n", "hist_avg_lnengage", "hist_avg_reposts", "hist_med_reposts",
             "hist_prior_n", "hist_prior_avg_lnengage",
             "ad_density_wide", "ad_density", "ad_density_strict", "non_ad_n",
             "non_ad_avg_reposts",
             "cmt_total", "cmt_deep_n", "aud_fol_med", "aud_ver_share"]

    n_pd = n_au = n_cm = 0
    rows = []
    for r in base:
        o = dict(r)
        aid, pid = r["author_id"], r["post_id"]

        # 帖级
        d = pd.get(pid)
        o["pd_ok"] = 1 if (d or {}).get("ok") == "1" else 0
        if d and d.get("ok") == "1":
            n_pd += 1
            o["has_ext_link"] = 1 if (d.get("page_url_ori") or "").strip() else 0
            o["det_pic_num"] = int(num(d.get("pic_num")))
            o["det_text_len"] = int(num(d.get("text_length")))
            o["is_hot_topic"] = int(num(d.get("is_hot_topic")))
            o["source_grp"] = source_grp(d.get("source_tool"))
            pt = (d.get("page_type") or "none").strip()
            o["ptype_grp"] = "topic" if pt in ("topic", "search_topic") else (pt or "none")
        else:
            o.update({"has_ext_link": 0, "det_pic_num": 0, "det_text_len": 0,
                      "is_hot_topic": 0, "source_grp": "other", "ptype_grp": "none"})
        g = link_grp_of(pid)
        o["link_grp"] = g
        o["is_video_link"] = 1 if g == "video_weibo" else 0
        o["is_lottery_link"] = 1 if g == "lottery_weibo" else 0

        # 作者级
        ps = list(aposts.get(aid, {}).values())
        o["hist_n"] = len(ps)
        if ps:
            n_au += 1
            eng = [math.log(float(num(p["reposts"])) + float(num(p["comments"]))
                            + float(num(p["attitudes"])) + 1.0) for p in ps]
            rps = [float(num(p["reposts"])) for p in ps]
            o["hist_avg_lnengage"] = round(sum(eng) / len(eng), 6)
            o["hist_avg_reposts"] = round(sum(rps) / len(rps), 4)
            o["hist_med_reposts"] = round(st.median(rps), 4)
            # 广告密度三版（实测：has_link 单独会失真 —— 主页时间线 37.9% 的帖带
            # 视频/话题卡片链接，并非广告。故中版剔除 video 卡片的伪外链）
            wide = [p for p in ps if num(p["ad_tag"]) or num(p["kol_kw"]) or num(p["has_link"])]
            mid = [p for p in ps if num(p["ad_tag"]) or num(p["kol_kw"])
                   or (num(p["has_link"]) and not num(p["has_video"]))]
            strict = [p for p in ps if num(p["ad_tag"]) or num(p["kol_kw"])]
            o["ad_density_wide"] = round(len(wide) / len(ps), 6)
            o["ad_density"] = round(len(mid) / len(ps), 6)
            o["ad_density_strict"] = round(len(strict) / len(ps), 6)
            nonad = [p for p in ps if not (num(p["ad_tag"]) or num(p["kol_kw"])
                                          or (num(p["has_link"]) and not num(p["has_video"])))]
            o["non_ad_n"] = len(nonad)
            o["non_ad_avg_reposts"] = (round(sum(float(num(p["reposts"])) for p in nonad)
                                             / len(nonad), 4) if nonad else ".")
            o["prof_followers"] = int(num((prof.get(aid) or {}).get("followers")))
            o["prof_statuses"] = int(num((prof.get(aid) or {}).get("statuses_count")))
        else:
            o.update({"hist_avg_lnengage": ".", "hist_avg_reposts": ".", "hist_med_reposts": ".",
                      "ad_density_wide": ".", "ad_density": ".", "ad_density_strict": ".",
                      "non_ad_n": 0,
                      "non_ad_avg_reposts": ".", "prof_followers": ".", "prof_statuses": "."})

        # Leakage-free source quality: only posts published strictly before this target post.
        # This excludes the target itself and all future posts returned by the profile timeline.
        cutoff = target_time.get(pid)
        prior = []
        if cutoff is not None:
            for p in ps:
                published = parse_datetime(p.get("created_at"))
                if published is not None and published < cutoff and p.get("post_id") != pid:
                    prior.append(p)
        o["hist_prior_n"] = len(prior)
        if prior:
            prior_eng = [math.log(float(num(p["reposts"])) + float(num(p["comments"]))
                                  + float(num(p["attitudes"])) + 1.0) for p in prior]
            o["hist_prior_avg_lnengage"] = round(sum(prior_eng) / len(prior_eng), 6)
        else:
            o["hist_prior_avg_lnengage"] = "."

        # 受众级（可选）
        cs = list(cdeep.get(pid, {}).values())
        o["cmt_deep_n"] = len(cs)
        if cs:
            n_cm += 1
            fol = [float(num(c["author_followers"])) for c in cs]
            ver = [num(c["author_verified"]) for c in cs]
            o["cmt_total"] = int(num(cs[0].get("total_number")))
            o["aud_fol_med"] = round(st.median(fol), 4)
            o["aud_ver_share"] = round(sum(ver) / len(ver), 6)
        else:
            o.update({"cmt_total": ".", "aud_fol_med": ".", "aud_ver_share": "."})

        rows.append(o)

    cols = base_cols + extra + ["prof_followers", "prof_statuses"]
    seen, cols2 = set(), []
    for c in cols:
        if c not in seen:
            seen.add(c)
            cols2.append(c)

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols2, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print("[done] 输出 %d 行 × %d 列 -> %s" % (len(rows), len(cols2), OUT))
    print("  帖级详情命中 %d/%d | 作者历史命中 %d/%d | 深评论命中 %d/%d"
          % (n_pd, len(rows), n_au, len(rows), n_cm, len(rows)))
    # 新变量概览
    for c in ["has_ext_link", "is_video_link", "is_lottery_link", "is_hot_topic",
              "hist_n", "hist_prior_n", "ad_density", "ad_density_wide", "ad_density_strict",
              "hist_avg_lnengage", "hist_prior_avg_lnengage", "cmt_deep_n"]:
        vals = [r.get(c) for r in rows if r.get(c) not in ("", None)]
        if not vals:
            print("  %-18s 全空" % c)
            continue
        nums = [float(v) for v in vals if str(v).replace(".", "").replace("-", "").isdigit()]
        if nums:
            print("  %-18s n=%3d 均值=%.4f 中位=%.4f 非零=%d"
                  % (c, len(nums), sum(nums) / len(nums), st.median(nums),
                     sum(1 for x in nums if x != 0)))
        else:
            print("  %-18s 非数值 n=%d" % (c, len(vals)))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
