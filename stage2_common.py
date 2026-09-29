# -*- coding: utf-8 -*-
"""Shared schemas and deterministic helpers for the prospective stage-2 study."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "stage2_config.json"

SAMPLING_FRAME = HERE / "sampling_frame.csv"
STAGE2_POSTS = HERE / "stage2_posts.csv"
SNAPSHOTS = HERE / "post_snapshots.csv"
SEARCH_LOG = HERE / "stage2_search_log.csv"
ACCOUNTS = HERE / "stage2_accounts.csv"
MANUAL_CODING = HERE / "manual_coding.csv"

SAMPLING_HEADERS = [
    "post_id", "source_channel", "industry", "industry_label", "account_type",
    "keyword_or_brand", "search_page", "search_rank", "quota_cell",
    "discovered_at", "created_at", "discovery_age_hours", "author_id",
    "media_type", "appeal_auto", "is_ad_auto", "is_original", "status",
    "exclusion_reason",
]

POST_HEADERS = [
    "post_id", "post_url", "created_at", "discovered_at", "text", "hashtags",
    "mentions", "media_type", "media_urls", "product_link", "author_id",
    "author_name", "author_followers", "author_verified", "author_verified_type",
    "industry", "industry_label", "account_type", "appeal_auto", "is_lottery_auto",
    "hard_ad_auto", "n_images", "has_ext_link", "page_type", "source_tool",
    "reposts_t0", "comments_t0", "likes_t0",
]

SNAPSHOT_HEADERS = [
    "attempt_id", "post_id", "scheduled_window", "target_at", "observed_at",
    "age_hours", "delta_hours", "within_tolerance", "reposts_count",
    "comments_count", "attitudes_count", "request_status", "http_status",
    "error_type", "error_message",
]

SEARCH_HEADERS = [
    "request_id", "requested_at", "industry", "keyword", "page",
    "request_status", "http_status", "result_count", "error_message",
]

ACCOUNT_HEADERS = [
    "author_id", "author_name", "industry", "account_type", "roster_role",
    "active", "notes",
]

MANUAL_HEADERS = [
    "post_id", "coder_id", "industry", "account_type", "text_excerpt",
    "ad_label", "appeal_type", "lottery_label", "hard_ad_label", "coded_at",
    "coder_notes", "reconciled_ad_label", "reconciled_appeal_type",
    "reconciled_lottery_label", "reconciled_hard_ad_label",
]

APPEAL_PATTERNS = {
    "welfare": ("抽奖", "福利", "中奖", "转发抽", "免费送", "优惠", "折扣", "满减", "券"),
    "content": ("测评", "实测", "种草", "开箱", "教程", "攻略", "推荐"),
    "official": ("官宣", "新品", "首发", "上市", "联名", "发布会"),
    "hard_ad": ("广告", "赞助", "推广合作", "商务合作", "立即购买", "点击购买"),
}


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dt(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_rows(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def append_rows(path: Path, headers: list[str], rows: Iterable[dict]) -> int:
    materialized = list(rows)
    if not materialized:
        return 0
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def ensure_csv(path: Path, headers: list[str]) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.DictWriter(f, fieldnames=headers).writeheader()


def as_int(value, default=0) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def as_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def media_group(value: str | None) -> str:
    value = (value or "").lower()
    if value == "image":
        return "image"
    if value == "video":
        return "video"
    return "other"


def classify_account(user: dict, registry: dict[str, dict] | None = None) -> str:
    author_id = str(user.get("id") or "")
    override = (registry or {}).get(author_id, {}).get("account_type")
    if override in {"brand_official", "kol_verified", "media_other"}:
        return override
    verified = bool(user.get("verified"))
    verified_type = user.get("verified_type")
    reason = str(user.get("verified_reason") or "")
    if verified_type in {2, 3, 4, 5, 6, 7} or any(
        word in reason for word in ("官方", "公司", "企业", "品牌", "机构")
    ):
        return "brand_official"
    if verified:
        return "kol_verified"
    return "media_other"


def classify_appeal(text: str | None) -> str:
    blob = text or ""
    scores = {name: sum(word in blob for word in words) for name, words in APPEAL_PATTERNS.items()}
    priority = ("welfare", "content", "official", "hard_ad")
    winner = max(priority, key=lambda name: (scores[name], -priority.index(name)))
    return winner if scores[winner] else "other"


def is_lottery(text: str | None) -> bool:
    return any(word in (text or "") for word in ("抽奖", "中奖", "转发抽", "评论区抽", "开奖"))


def is_hard_ad(text: str | None) -> bool:
    return any(word in (text or "") for word in APPEAL_PATTERNS["hard_ad"])


def target_time(created_at: datetime, window: str, config: dict) -> datetime:
    hours = float(config["snapshot_windows"][window]["offset_hours"])
    return created_at + timedelta(hours=hours)


def within_window(observed: datetime, created: datetime, window: str, config: dict) -> tuple[bool, float]:
    spec = config["snapshot_windows"][window]
    target = created + timedelta(hours=float(spec["offset_hours"]))
    delta = (observed - target).total_seconds() / 3600.0
    return (-float(spec["early_hours"]) <= delta <= float(spec["late_hours"]), delta)


def canonical_snapshots(rows: Iterable[dict]) -> dict[tuple[str, str], dict]:
    """Choose the closest successful in-tolerance attempt for each post/window."""
    chosen: dict[tuple[str, str], dict] = {}
    for row in rows:
        if row.get("request_status") != "success" or not as_bool(row.get("within_tolerance")):
            continue
        key = (str(row.get("post_id") or ""), str(row.get("scheduled_window") or ""))
        distance = abs(float(row.get("delta_hours") or math.inf))
        old = chosen.get(key)
        old_distance = abs(float(old.get("delta_hours") or math.inf)) if old else math.inf
        if distance < old_distance or (distance == old_distance and row.get("observed_at", "") < old.get("observed_at", "")):
            chosen[key] = row
    return chosen


def stable_attempt_id(post_id: str, window: str, observed_at: str) -> str:
    raw = f"{post_id}|{window}|{observed_at}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def quota_counts(rows: Iterable[dict]) -> Counter:
    return Counter(
        (row.get("industry"), row.get("account_type"))
        for row in rows if row.get("status") == "included"
    )


def quota_available(industry: str, account_type: str, included: list[dict], config: dict) -> bool:
    targets = config["account_type_targets_per_industry"]
    return quota_counts(included)[(industry, account_type)] < int(targets[account_type])


def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("Kappa requires two non-empty label vectors of equal length")
    n = len(labels_a)
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / n
    ca, cb = Counter(labels_a), Counter(labels_b)
    expected = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    return 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1.0 - expected)
