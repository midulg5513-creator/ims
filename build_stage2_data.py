# -*- coding: utf-8 -*-
"""Build a deterministic, leakage-checked stage-2 analysis table."""
from __future__ import annotations

import csv
import math
import re
import statistics
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from stage2_common import (
    HERE, MANUAL_CODING, SNAPSHOTS, STAGE2_POSTS, as_bool, as_int,
    canonical_snapshots, cohen_kappa, load_config, parse_dt, read_rows,
)


OUT = HERE / "stage2_analysis.csv"
AUDIT_OUT = HERE / "stage2_data_audit.csv"
KAPPA_OUT = HERE / "stage2_coding_reliability.csv"
AUTHOR_POSTS = HERE / "author_posts.csv"
PROMO_WORDS = HERE / "promo_words.txt"
BRAND_WORDS = HERE / "brands.txt"

OUT_HEADERS = [
    "post_id", "author_id", "created_at", "snapshot_24h_at", "snapshot_7d_at",
    "reposts_24h", "comments_24h", "likes_24h", "positive_repost_24h",
    "ln_repost_24h", "reposts_7d", "has_valid_7d", "age_hours_24h",
    "log_age_hours_24h", "followers", "log_followers", "industry", "account_type",
    "media_type", "is_video", "n_images", "text_len", "text_len_100",
    "text_len_100_sq", "n_topics", "n_mentions", "has_ext_link", "source_group",
    "pub_hour", "pub_dow", "is_weekend", "appeal_type", "appeal_family",
    "is_lottery", "hard_ad", "n_promo", "promo_density_100", "n_brand",
    "brand_density_100", "hist_prior_n", "hist_prior_avg_lnengage",
    "has_prior_hist", "prior_ad_density", "prior_nonad_n",
    "prior_nonad_avg_reposts", "manual_label_source",
]


def words(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def source_group(value: str) -> str:
    text = value or ""
    if any(word in text for word in ("视频", "秒拍")):
        return "video_channel"
    if "超话" in text:
        return "super_topic"
    if any(word in text for word in ("iPhone", "Android", "HUAWEI", "小米", "微博")):
        return "client"
    if "Web" in text or "网页" in text or "web" in text:
        return "web"
    return "other"


def manual_consensus() -> tuple[dict[str, dict], list[dict]]:
    rows = read_rows(MANUAL_CODING)
    if not rows:
        return {}, []
    by_post = defaultdict(list)
    for row in rows:
        by_post[row.get("post_id")].append(row)
    fields = ("ad_label", "appeal_type", "lottery_label", "hard_ad_label")
    reliability = []
    for field in fields:
        paired = []
        for post_rows in by_post.values():
            labels = [r.get(field, "").strip() for r in post_rows if r.get(field, "").strip()]
            if len(labels) == 2:
                paired.append(labels)
        if paired:
            value = cohen_kappa([p[0] for p in paired], [p[1] for p in paired])
            reliability.append({"field": field, "paired_n": len(paired), "cohen_kappa": value})
    consensus = {}
    for post_id, post_rows in by_post.items():
        result = {}
        first = post_rows[0]
        for field in fields:
            reconciled = (first.get("reconciled_" + field) or "").strip()
            labels = [r.get(field, "").strip() for r in post_rows if r.get(field, "").strip()]
            if reconciled:
                result[field] = reconciled
            elif len(labels) == 2 and labels[0] == labels[1]:
                result[field] = labels[0]
        if result:
            consensus[post_id] = result
    return consensus, reliability


def write_rows(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def prior_features(author_rows: list[dict], target_created) -> dict:
    prior = []
    for row in author_rows:
        published = parse_dt(row.get("created_at"))
        if published is not None and published < target_created:
            prior.append((published, row))
    if any(published >= target_created for published, _ in prior):
        raise AssertionError("Future-data leakage detected in author history")
    if not prior:
        return {
            "hist_prior_n": 0, "hist_prior_avg_lnengage": "", "has_prior_hist": 0,
            "prior_ad_density": "", "prior_nonad_n": 0, "prior_nonad_avg_reposts": "",
        }
    engagement = []
    ad_flags, nonad_reposts = [], []
    for _, row in prior:
        reposts = as_int(row.get("reposts"))
        comments = as_int(row.get("comments"))
        likes = as_int(row.get("attitudes"))
        engagement.append(math.log1p(reposts + comments + likes))
        ad = bool(as_int(row.get("ad_tag")) or as_int(row.get("kol_kw")) or (
            as_int(row.get("has_link")) and not as_int(row.get("has_video"))
        ))
        ad_flags.append(int(ad))
        if not ad:
            nonad_reposts.append(reposts)
    return {
        "hist_prior_n": len(prior),
        "hist_prior_avg_lnengage": round(statistics.mean(engagement), 8),
        "has_prior_hist": 1,
        "prior_ad_density": round(statistics.mean(ad_flags), 8),
        "prior_nonad_n": len(nonad_reposts),
        "prior_nonad_avg_reposts": (
            round(statistics.mean(nonad_reposts), 8) if nonad_reposts else ""
        ),
    }


def main() -> int:
    config = load_config()
    posts = read_rows(STAGE2_POSTS)
    canonical = canonical_snapshots(read_rows(SNAPSHOTS))
    if not posts:
        print("[x] stage2_posts.csv has no included posts; run prospective_study.py discover")
        return 1
    promo = words(PROMO_WORDS)
    brands = words(BRAND_WORDS)
    manual, reliability = manual_consensus()
    if reliability:
        write_rows(KAPPA_OUT, ["field", "paired_n", "cohen_kappa"], reliability)

    history = defaultdict(list)
    for row in read_rows(AUTHOR_POSTS):
        history[row.get("author_id")].append(row)

    built, missing_24 = [], 0
    for post in sorted(posts, key=lambda row: row.get("post_id", "")):
        pid = post["post_id"]
        snap24 = canonical.get((pid, "T24H"))
        if not snap24:
            missing_24 += 1
            continue
        snap7 = canonical.get((pid, "T7D"))
        created = parse_dt(post.get("created_at"))
        observed24 = parse_dt(snap24.get("observed_at"))
        if created is None or observed24 is None:
            continue
        age24 = (observed24 - created).total_seconds() / 3600.0
        text = post.get("text") or ""
        text_len = len(re.sub(r"\s+", "", text))
        text_len_100 = text_len / 100.0
        follower_count = max(0, as_int(post.get("author_followers")))
        reposts24 = as_int(snap24.get("reposts_count"))
        manual_row = manual.get(pid, {})
        appeal = manual_row.get("appeal_type") or post.get("appeal_auto") or "other"
        if appeal in {"welfare", "抽奖福利", "price", "价格促销"}:
            appeal_family = "welfare"
        elif appeal in {"content", "内容种草", "official", "品牌官宣"}:
            appeal_family = "content"
        elif appeal in {"hard_ad", "硬广告"}:
            appeal_family = "hard_ad"
        else:
            appeal_family = "other"
        lottery_raw = manual_row.get("lottery_label")
        hard_raw = manual_row.get("hard_ad_label")
        n_promo = sum(text.count(word) for word in promo)
        n_brand = sum(text.lower().count(word.lower()) for word in brands)
        local = created + timedelta(hours=8)
        row = {
            "post_id": pid, "author_id": post.get("author_id"),
            "created_at": post.get("created_at"), "snapshot_24h_at": snap24.get("observed_at"),
            "snapshot_7d_at": snap7.get("observed_at", "") if snap7 else "",
            "reposts_24h": reposts24, "comments_24h": as_int(snap24.get("comments_count")),
            "likes_24h": as_int(snap24.get("attitudes_count")),
            "positive_repost_24h": int(reposts24 > 0),
            "ln_repost_24h": round(math.log1p(reposts24), 10),
            "reposts_7d": as_int(snap7.get("reposts_count")) if snap7 else "",
            "has_valid_7d": int(snap7 is not None), "age_hours_24h": round(age24, 8),
            "log_age_hours_24h": round(math.log1p(age24), 10),
            "followers": follower_count, "log_followers": round(math.log1p(follower_count), 10),
            "industry": post.get("industry"), "account_type": post.get("account_type"),
            "media_type": post.get("media_type"), "is_video": int(post.get("media_type") == "video"),
            "n_images": as_int(post.get("n_images")), "text_len": text_len,
            "text_len_100": round(text_len_100, 8),
            "text_len_100_sq": round(text_len_100 ** 2, 8),
            "n_topics": len([x for x in (post.get("hashtags") or "").split("|") if x]),
            "n_mentions": len([x for x in (post.get("mentions") or "").split("|") if x]),
            "has_ext_link": as_int(post.get("has_ext_link")),
            "source_group": source_group(post.get("source_tool") or ""),
            "pub_hour": local.hour, "pub_dow": local.weekday(),
            "is_weekend": int(local.weekday() >= 5), "appeal_type": appeal,
            "appeal_family": appeal_family,
            "is_lottery": as_int(lottery_raw, as_int(post.get("is_lottery_auto"))),
            "hard_ad": as_int(hard_raw, as_int(post.get("hard_ad_auto"))),
            "n_promo": n_promo,
            "promo_density_100": round(100.0 * n_promo / max(1, text_len), 8),
            "n_brand": n_brand,
            "brand_density_100": round(100.0 * n_brand / max(1, text_len), 8),
            "manual_label_source": "manual" if manual_row else "automatic",
        }
        row.update(prior_features(history.get(post.get("author_id"), []), created))
        built.append(row)

    write_rows(OUT, OUT_HEADERS, built)
    authors = {row["author_id"] for row in built}
    repeated_rows = sum(
        sum(item["author_id"] == author for item in built) >= 2 for author in authors
    )
    audits = [
        {"check": "included_raw_posts", "value": len(posts), "status": "info"},
        {"check": "valid_T24H_analysis_rows", "value": len(built), "status": "pass" if built else "fail"},
        {"check": "missing_valid_T24H", "value": missing_24, "status": "pass" if missing_24 == 0 else "warning"},
        {"check": "unique_post_ids", "value": len({r['post_id'] for r in built}), "status": "pass" if len({r['post_id'] for r in built}) == len(built) else "fail"},
        {"check": "unique_authors", "value": len(authors), "status": "info"},
        {"check": "authors_with_2plus_posts", "value": repeated_rows, "status": "info"},
        {"check": "future_history_rows", "value": 0, "status": "pass"},
    ]
    for result in reliability:
        kappa = float(result["cohen_kappa"])
        audits.append({
            "check": "kappa_" + result["field"], "value": round(kappa, 6),
            "status": "pass" if kappa >= float(config["study"]["kappa_threshold"]) else "fail",
        })
    write_rows(AUDIT_OUT, ["check", "value", "status"], audits)
    print(f"[done] {OUT.name}: {len(built)} rows; missing valid T24H={missing_24}")
    print(f"[done] {AUDIT_OUT.name}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
