# -*- coding: utf-8 -*-
"""Integrate project post-level files and retain only posts with positive reposts."""
from pathlib import Path
import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "positive_posts_analysis"
OUT.mkdir(exist_ok=True)


def read(name):
    p = HERE / name
    return pd.read_csv(p, dtype=str) if p.exists() else pd.DataFrame()


def num(s):
    return pd.to_numeric(s, errors="coerce")


def main():
    stage2 = read("stage2_posts.csv")
    old = read("posts.csv")
    stata = read("stata_data.csv")
    snap = read("post_snapshots.csv")
    comments = read("comments.csv")
    deep = read("comments_deep.csv")
    details = read("post_details.csv")
    profiles = read("author_profile.csv")
    frames = []
    if not stage2.empty:
        x = stage2.copy()
        x["reposts"] = x["reposts_t0"]
        x["comments"] = x["comments_t0"]
        x["likes"] = x["likes_t0"]
        x["data_source"] = "stage2_posts"
        frames.append(x)
    if not old.empty:
        x = old.copy()
        x["reposts"] = x["reposts_count"]
        x["comments"] = x["comments_count"]
        x["likes"] = x["attitudes_count"]
        x["data_source"] = "posts"
        frames.append(x)
    if not stata.empty:
        x = stata.copy()
        x["data_source"] = "stata_data"
        frames.append(x)
    all_posts = pd.concat(frames, ignore_index=True, sort=False)
    all_posts["post_id"] = all_posts["post_id"].astype(str)
    # Prefer stage2 > posts > stata when the same post occurs in multiple sources.
    priority = {"stage2_posts": 1, "posts": 2, "stata_data": 3}
    all_posts["_priority"] = all_posts["data_source"].map(priority).fillna(99)
    all_posts = all_posts.sort_values(["post_id", "_priority"]).drop_duplicates("post_id", keep="first")
    all_posts["reposts"] = num(all_posts["reposts"]).fillna(0)
    all_posts["comments"] = num(all_posts["comments"]).fillna(0)
    all_posts["likes"] = num(all_posts["likes"]).fillna(0)
    all_posts["text"] = all_posts.get("text", pd.Series(index=all_posts.index, dtype=str)).fillna("").astype(str)
    all_posts["text_len_clean"] = all_posts["text"].str.replace(r"\s+", "", regex=True).str.len()
    all_posts["ln_reposts"] = np.log1p(all_posts["reposts"])
    all_posts["has_repost"] = (all_posts["reposts"] > 0).astype(int)

    # Add non-duplicated auxiliary aggregates.
    if not snap.empty:
        ss = snap[snap["scheduled_window"].eq("T0")].copy()
        ss = ss.sort_values("observed_at").drop_duplicates("post_id", keep="first")
        ss = ss[[c for c in ["post_id", "observed_at", "age_hours", "within_tolerance", "request_status"] if c in ss]]
        all_posts = all_posts.merge(ss, on="post_id", how="left", suffixes=("", "_snapshot"))
    if not comments.empty:
        cc = comments.groupby("post_id", as_index=False).agg(comment_rows=("comment_id", "count"), comment_likes_sum=("comment_likes", lambda x: num(x).sum()))
        all_posts = all_posts.merge(cc, on="post_id", how="left")
    if not deep.empty:
        dd = deep.groupby("post_id", as_index=False).agg(deep_comment_rows=("comment_id", "count"), deep_comment_likes_sum=("like_count", lambda x: num(x).sum()))
        all_posts = all_posts.merge(dd, on="post_id", how="left")
    if not details.empty:
        keep = [c for c in ["post_id", "ad_marked", "is_paid", "is_hot_topic", "is_shop_link"] if c in details]
        all_posts = all_posts.merge(details[keep].drop_duplicates("post_id"), on="post_id", how="left")
    if not profiles.empty and "author_id" in all_posts and "author_id" in profiles:
        keep = [c for c in ["author_id", "followers", "verified", "verified_type", "statuses_count"] if c in profiles]
        all_posts = all_posts.merge(profiles[keep].drop_duplicates("author_id"), on="author_id", how="left", suffixes=("", "_profile"))
    all_posts = all_posts.drop(columns=["_priority"], errors="ignore")
    all_posts.to_csv(OUT / "all_posts_integrated.csv", index=False, encoding="utf-8-sig")
    positive = all_posts.loc[all_posts["reposts"] > 0].copy()
    positive.to_csv(OUT / "positive_repost_posts.csv", index=False, encoding="utf-8-sig")

    audit = pd.DataFrame([
        {"item": "stage2_posts_raw", "value": len(stage2)},
        {"item": "posts_raw", "value": len(old)},
        {"item": "stata_data_raw", "value": len(stata)},
        {"item": "combined_rows_before_postid_dedup", "value": sum(len(x) for x in frames)},
        {"item": "unique_integrated_posts", "value": len(all_posts)},
        {"item": "positive_repost_posts", "value": len(positive)},
        {"item": "zero_repost_posts_removed", "value": int((all_posts["reposts"] == 0).sum())},
        {"item": "duplicate_post_ids_removed", "value": sum(len(x) for x in frames) - len(all_posts)},
        {"item": "missing_post_id", "value": int(all_posts["post_id"].isna().sum())},
    ])
    audit.to_csv(OUT / "integration_audit.csv", index=False, encoding="utf-8-sig")
    for col in ["data_source", "industry", "account_type", "media_type"]:
        if col in positive:
            positive.groupby(col, dropna=False).agg(n=("post_id", "size"), mean_reposts=("reposts", "mean"), median_reposts=("reposts", "median"), mean_ln_reposts=("ln_reposts", "mean")).reset_index().to_csv(OUT / f"positive_by_{col}.csv", index=False, encoding="utf-8-sig")
    report = f'''# 正转发帖子整合与清洗报告\n\n本次整合保留原始文件不变，合并 `stage2_posts.csv`、`posts.csv` 和 `stata_data.csv`，以 `post_id` 去重，并补充T0快照、评论、帖子详情和作者资料中的可匹配字段。\n\n- 合并前记录数：{sum(len(x) for x in frames)}\n- 去重后帖子数：{len(all_posts)}\n- 保留转发数大于0：{len(positive)}\n- 删除零转发帖子：{int((all_posts['reposts'] == 0).sum())}\n\n## 研究口径变化\n\n该样本只包含已经发生过转发的帖子。因此后续模型只能研究“正转发帖子之间，哪些因素与转发量高低相关”，不能研究“哪些因素提高帖子获得至少一次转发的概率”。若要研究完整传播机制，应保留零转发帖子并使用两部模型或 hurdle 模型。\n\n输出文件：\n- `all_posts_integrated.csv`：去重后的完整整合数据\n- `positive_repost_posts.csv`：仅保留 `reposts > 0` 的研究数据\n- `integration_audit.csv`：合并、去重和删除审计\n'''
    (OUT / "README.md").write_text(report, encoding="utf-8")
    print(f"[done] integrated={len(all_posts)} positive={len(positive)} removed_zero={(all_posts['reposts']==0).sum()}")


if __name__ == "__main__":
    main()
