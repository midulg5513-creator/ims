# -*- coding: utf-8 -*-
"""Prospective quota sampling and immutable snapshot collection for stage 2.

Commands:
  init             Create empty, schema-only stage-2 CSV interfaces.
  discover         Search recent posts, evaluate eligibility, and capture T0.
  snapshots        Fetch due T+24h/T+7d snapshots without overwriting attempts.
  manual-sample    Draw a deterministic 100-post, two-coder validation sample.
  audit            Write quota, timing, attrition, and coding reliability reports.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import requests

from stage2_common import (
    ACCOUNT_HEADERS, ACCOUNTS, CONFIG_PATH, MANUAL_CODING, MANUAL_HEADERS,
    POST_HEADERS, SAMPLING_FRAME, SAMPLING_HEADERS, SEARCH_HEADERS, SEARCH_LOG,
    SNAPSHOTS, SNAPSHOT_HEADERS,
    STAGE2_POSTS, append_rows, as_bool, as_int, canonical_snapshots,
    classify_account, classify_appeal, ensure_csv, iso, is_hard_ad, is_lottery,
    load_config, media_group, now_utc, parse_dt, quota_available, read_rows,
    stable_attempt_id, within_window,
)
from weibo_ad_collector import (
    LONGTEXT_URL, SEARCH_URL, classify_ad, extract_hashtags, extract_mentions,
    load_brands, load_cookie, make_headers, media_of, strip_html, to_int, to_iso_utc,
)


HERE = Path(__file__).resolve().parent
QUOTA_AUDIT = HERE / "stage2_quota_audit.csv"
ATTRITION_AUDIT = HERE / "stage2_attrition.csv"
KAPPA_AUDIT = HERE / "stage2_coding_reliability.csv"


def initialize() -> None:
    for path, headers in (
        (SAMPLING_FRAME, SAMPLING_HEADERS), (STAGE2_POSTS, POST_HEADERS),
        (SNAPSHOTS, SNAPSHOT_HEADERS), (ACCOUNTS, ACCOUNT_HEADERS),
        (MANUAL_CODING, MANUAL_HEADERS), (SEARCH_LOG, SEARCH_HEADERS),
    ):
        ensure_csv(path, headers)
        print(f"[ready] {path.name}")


def registry_map() -> dict[str, dict]:
    return {
        row["author_id"]: row for row in read_rows(ACCOUNTS)
        if row.get("author_id") and row.get("active", "1") != "0"
    }


class Stage2Client:
    def __init__(self, delay: float, timeout: float, retries: int, use_cookie: bool = False):
        self.delay = max(0.0, delay)
        self.timeout = timeout
        self.retries = max(0, retries)
        self.session = requests.Session()
        self.session.headers.update(make_headers(load_cookie() if use_cookie else ""))

    def get_json(self, url: str) -> tuple[dict | None, str, str]:
        last_status, last_error = "", ""
        for attempt in range(self.retries + 1):
            if self.delay:
                time.sleep(self.delay * (2 ** attempt))
            try:
                response = self.session.get(url, timeout=self.timeout)
                last_status = str(response.status_code)
                if response.status_code != 200:
                    last_error = f"HTTP {response.status_code}"
                    continue
                payload = response.json()
                if payload.get("ok"):
                    return payload, last_status, ""
                last_error = "api_ok_0"
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
        return None, last_status, last_error[:500]

    def search(self, keyword: str, page: int) -> tuple[list[dict], str, str]:
        payload, status, error = self.get_json(SEARCH_URL.format(q=quote(keyword), page=page))
        if not payload:
            return [], status, error
        out = []
        for card in (payload.get("data") or {}).get("cards") or []:
            for group in card.get("card_group") or [card]:
                if group.get("mblog"):
                    out.append(group["mblog"])
        return out, status, ""

    def detail(self, post_id: str) -> tuple[dict | None, str, str]:
        payload, status, error = self.get_json(LONGTEXT_URL.format(id=post_id))
        return ((payload or {}).get("data") if payload else None), status, error


def post_text(mblog: dict, detail: dict | None) -> str:
    return strip_html((detail or {}).get("longText") or (detail or {}).get("text") or mblog.get("text"))


def build_t0_snapshot(post_id: str, created_at: str, observed_at: str,
                      reposts: int, comments: int, likes: int, config: dict) -> dict:
    created, observed = parse_dt(created_at), parse_dt(observed_at)
    valid, delta = within_window(observed, created, "T0", config)
    age = (observed - created).total_seconds() / 3600.0
    return {
        "attempt_id": stable_attempt_id(post_id, "T0", observed_at),
        "post_id": post_id, "scheduled_window": "T0", "target_at": created_at,
        "observed_at": observed_at, "age_hours": f"{age:.6f}",
        "delta_hours": f"{delta:.6f}", "within_tolerance": int(valid),
        "reposts_count": reposts, "comments_count": comments,
        "attitudes_count": likes, "request_status": "success",
        "http_status": "search", "error_type": "", "error_message": "",
    }


def discover(args) -> int:
    initialize()
    config = load_config(Path(args.config))
    registry = registry_map()
    sampling_mode = config["study"].get("sampling_mode", "roster")
    if sampling_mode not in {"keyword_quota", "keyword_quota_fast24h", "roster"}:
        raise ValueError("study.sampling_mode must be keyword_quota, keyword_quota_fast24h, or roster")
    if sampling_mode == "roster" and not registry and not args.allow_open_discovery:
        raise ValueError(
            "stage2_accounts.csv has no active frozen roster. Populate it first, "
            "or pass --allow-open-discovery only for a pilot run."
        )
    study_start = parse_dt(config["study"].get("collection_start_utc"))
    if not args.allow_open_discovery:
        if study_start is None:
            raise ValueError(
                "Set study.collection_start_utc in stage2_config.json before formal collection."
            )
        study_end = study_start + timedelta(days=int(config["study"]["collection_days"]))
        current = now_utc()
        if current < study_start or current >= study_end:
            raise ValueError(
                f"Formal discovery is outside the frozen collection window: "
                f"{iso(study_start)} to {iso(study_end)}"
            )
    client = Stage2Client(args.delay, args.timeout, args.retries, args.use_cookie)
    brands = load_brands()
    existing = read_rows(SAMPLING_FRAME)
    seen = {row["post_id"] for row in existing}
    included = [row for row in existing if row.get("status") == "included"]
    author_counts = Counter(row.get("author_id") for row in included)
    target_total = int(config["study"]["target_posts"])
    max_author = int(config["study"]["max_posts_per_author"])
    max_age = float(config["study"]["max_discovery_age_hours"])
    added = candidates = 0

    industries = config["industries"]
    if args.industry:
        industries = [item for item in industries if item["code"] == args.industry]
        if not industries:
            raise ValueError(f"Unknown industry: {args.industry}")

    for industry in industries:
        for keyword in industry["keywords"]:
            for page in range(1, args.pages + 1):
                requested = now_utc()
                results, http_status, search_error = client.search(keyword, page)
                append_rows(SEARCH_LOG, SEARCH_HEADERS, [{
                    "request_id": stable_attempt_id(industry["code"], keyword, iso(requested) + f"|{page}"),
                    "requested_at": iso(requested), "industry": industry["code"],
                    "keyword": keyword, "page": page,
                    "request_status": "success" if not search_error else "error",
                    "http_status": http_status, "result_count": len(results),
                    "error_message": search_error,
                }])
                if search_error:
                    print(f"[search-error] {industry['code']} {keyword} p{page}: "
                          f"http={http_status or '-'} {search_error}")
                if not results:
                    break
                frame_batch, post_batch, snapshot_batch = [], [], []
                for rank, mblog in enumerate(results, 1):
                    post_id = str(mblog.get("id") or "")
                    if not post_id or post_id in seen:
                        continue
                    seen.add(post_id)
                    candidates += 1
                    observed = now_utc()
                    created_text = to_iso_utc(mblog.get("created_at"))
                    created = parse_dt(created_text)
                    age = ((observed - created).total_seconds() / 3600.0) if created else None
                    user = mblog.get("user") or {}
                    account_type = classify_account(user, registry)
                    author_id = str(user.get("id") or "")
                    original = not bool(mblog.get("retweeted_status"))
                    detail = None
                    if mblog.get("isLongText"):
                        detail, _, _ = client.detail(post_id)
                    text = post_text(mblog, detail)
                    hashtags = extract_hashtags(text)
                    media_type, media_urls, page_url = media_of(mblog)
                    page_info = mblog.get("page_info") or {}
                    # Only url_ori is an external-link advertising signal. Internal
                    # video/topic page URLs must not turn every media post into an ad.
                    product_link = page_info.get("url_ori") or ""
                    is_ad, _, _ = classify_ad(
                        text, hashtags, bool(user.get("verified")), product_link, brands
                    )
                    appeal = classify_appeal(text)
                    reason = ""
                    if not original:
                        reason = "repost_not_original"
                    elif (sampling_mode == "roster" and author_id not in registry
                          and not args.allow_open_discovery):
                        reason = "not_in_frozen_account_roster"
                    elif (author_id in registry and registry[author_id].get("industry")
                          and registry[author_id].get("industry") != industry["code"]):
                        reason = "roster_industry_mismatch"
                    elif created is None:
                        reason = "unparseable_created_at"
                    elif age is None or age < 0 or age > max_age:
                        reason = "discovered_outside_T0"
                    elif not is_ad:
                        reason = "not_ad_by_screening_rule"
                    elif args.media_type and media_group(media_type) != args.media_type:
                        reason = "media_type_target_mismatch"
                    elif author_counts[author_id] >= max_author:
                        reason = "author_cap_reached"
                    elif not quota_available(industry["code"], account_type, included, config):
                        reason = "quota_cell_full"
                    status = "excluded" if reason else "included"
                    frame = {
                        "post_id": post_id, "source_channel": "keyword_search",
                        "industry": industry["code"], "industry_label": industry["label"],
                        "account_type": account_type, "keyword_or_brand": keyword,
                        "search_page": page, "search_rank": rank,
                        "quota_cell": f"{industry['code']}|{account_type}",
                        "discovered_at": iso(observed), "created_at": created_text,
                        "discovery_age_hours": "" if age is None else f"{age:.6f}",
                        "author_id": author_id, "media_type": media_group(media_type),
                        "appeal_auto": appeal, "is_ad_auto": int(is_ad),
                        "is_original": int(original), "status": status,
                        "exclusion_reason": reason,
                    }
                    frame_batch.append(frame)
                    if status != "included":
                        continue
                    included.append(frame)
                    author_counts[author_id] += 1
                    observed_text = iso(observed)
                    reposts = to_int(mblog.get("reposts_count"))
                    comments = to_int(mblog.get("comments_count"))
                    likes = to_int(mblog.get("attitudes_count"))
                    post_batch.append({
                        "post_id": post_id,
                        "post_url": f"https://m.weibo.cn/detail/{post_id}",
                        "created_at": created_text, "discovered_at": observed_text,
                        "text": text, "hashtags": "|".join(hashtags),
                        "mentions": "|".join(extract_mentions(text)),
                        "media_type": media_group(media_type),
                        "media_urls": "|".join(media_urls), "product_link": product_link,
                        "author_id": author_id, "author_name": user.get("screen_name") or "",
                        "author_followers": to_int(user.get("followers_count")),
                        "author_verified": int(bool(user.get("verified"))),
                        "author_verified_type": user.get("verified_type") if user.get("verified_type") is not None else "",
                        "industry": industry["code"], "industry_label": industry["label"],
                        "account_type": account_type, "appeal_auto": appeal,
                        "is_lottery_auto": int(is_lottery(text)),
                        "hard_ad_auto": int(is_hard_ad(text)),
                        "n_images": len(mblog.get("pics") or []),
                        "has_ext_link": int(bool(page_info.get("url_ori"))),
                        "page_type": page_info.get("type") or "",
                        "source_tool": mblog.get("source") or "",
                        "reposts_t0": reposts, "comments_t0": comments, "likes_t0": likes,
                    })
                    snapshot_batch.append(build_t0_snapshot(
                        post_id, created_text, observed_text, reposts, comments, likes, config
                    ))
                    added += 1
                    if len(included) >= target_total or (args.limit and added >= args.limit):
                        break
                append_rows(SAMPLING_FRAME, SAMPLING_HEADERS, frame_batch)
                append_rows(STAGE2_POSTS, POST_HEADERS, post_batch)
                append_rows(SNAPSHOTS, SNAPSHOT_HEADERS, snapshot_batch)
                print(f"[discover] {industry['code']} {keyword} p{page}: candidates={len(frame_batch)} included={len(post_batch)}")
                if len(included) >= target_total or (args.limit and added >= args.limit):
                    print(f"[done] included this run={added}, total included={len(included)}")
                    return 0
    print(f"[done] candidates this run={candidates}, included this run={added}, total included={len(included)}")
    return 0


def snapshots(args) -> int:
    initialize()
    config = load_config(Path(args.config))
    client = Stage2Client(args.delay, args.timeout, args.retries, args.use_cookie)
    frames = [row for row in read_rows(SAMPLING_FRAME) if row.get("status") == "included"]
    attempts = read_rows(SNAPSHOTS)
    canonical = canonical_snapshots(attempts)
    attempt_counts = Counter((row.get("post_id"), row.get("scheduled_window")) for row in attempts)
    current = now_utc()
    written = 0
    for frame in frames:
        created = parse_dt(frame.get("created_at"))
        if created is None:
            continue
        for window in ("T24H", "T7D"):
            if args.window != "all" and args.window != window:
                continue
            key = (frame["post_id"], window)
            if key in canonical or attempt_counts[key] >= args.max_attempts:
                continue
            spec = config["snapshot_windows"][window]
            target = created + timedelta(hours=float(spec["offset_hours"]))
            due = target - timedelta(hours=float(spec["early_hours"]))
            if current < due:
                continue
            observed = now_utc()
            detail, http_status, error = client.detail(frame["post_id"])
            valid, delta = within_window(observed, created, window, config)
            row = {
                "attempt_id": stable_attempt_id(frame["post_id"], window, iso(observed)),
                "post_id": frame["post_id"], "scheduled_window": window,
                "target_at": iso(target), "observed_at": iso(observed),
                "age_hours": f"{(observed-created).total_seconds()/3600.0:.6f}",
                "delta_hours": f"{delta:.6f}", "within_tolerance": int(valid),
                "request_status": "success" if detail is not None else "error",
                "http_status": http_status,
                "error_type": ("" if detail is not None else
                               ("deleted_or_inaccessible" if error in {"api_ok_0", "HTTP 404"}
                                else (error.split(":", 1)[0] or "unknown"))),
                "error_message": error,
            }
            if detail is not None:
                row.update({
                    "reposts_count": to_int(detail.get("reposts_count")),
                    "comments_count": to_int(detail.get("comments_count")),
                    "attitudes_count": to_int(detail.get("attitudes_count")),
                })
            append_rows(SNAPSHOTS, SNAPSHOT_HEADERS, [row])
            written += 1
            print(f"[snapshot] {frame['post_id']} {window} status={row['request_status']} within={int(valid)}")
            if args.limit and written >= args.limit:
                return 0
    print(f"[done] snapshot attempts appended={written}")
    return 0


def proportional_sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    strata = defaultdict(list)
    for row in rows:
        strata[(row.get("industry"), row.get("account_type"))].append(row)
    chosen = []
    for key in sorted(strata):
        group = strata[key]
        take = min(len(group), max(1, round(n * len(group) / max(1, len(rows)))))
        chosen.extend(rng.sample(group, take))
    if len(chosen) > n:
        chosen = rng.sample(chosen, n)
    elif len(chosen) < n:
        chosen_ids = {row["post_id"] for row in chosen}
        pool = [row for row in rows if row["post_id"] not in chosen_ids]
        chosen.extend(rng.sample(pool, min(n - len(chosen), len(pool))))
    return sorted(chosen, key=lambda row: row["post_id"])


def manual_sample(args) -> int:
    initialize()
    config = load_config(Path(args.config))
    existing = read_rows(MANUAL_CODING)
    if existing and not args.replace:
        print("[skip] manual_coding.csv already has rows; pass --replace to redraw")
        return 0
    posts = read_rows(STAGE2_POSTS)
    n = min(int(config["study"]["manual_validation_n"]), len(posts))
    selected = proportional_sample(posts, n, int(config["study"]["manual_validation_seed"]))
    rows = []
    for post in selected:
        for coder in ("coder_1", "coder_2"):
            rows.append({
                "post_id": post["post_id"], "coder_id": coder,
                "industry": post.get("industry"), "account_type": post.get("account_type"),
                "text_excerpt": (post.get("text") or "")[:240],
            })
    mode = "w" if args.replace else "a"
    with MANUAL_CODING.open(mode, encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANUAL_HEADERS, extrasaction="ignore")
        if args.replace or MANUAL_CODING.stat().st_size == 0:
            writer.writeheader()
        writer.writerows(rows)
    print(f"[done] validation posts={n}, coding rows={len(rows)}")
    return 0


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def audit(args) -> int:
    initialize()
    config = load_config(Path(args.config))
    frames = read_rows(SAMPLING_FRAME)
    included = [row for row in frames if row.get("status") == "included"]
    snapshots_all = read_rows(SNAPSHOTS)
    canonical = canonical_snapshots(snapshots_all)
    quota_rows = []
    for industry in config["industries"]:
        for account_type, target in config["account_type_targets_per_industry"].items():
            actual = sum(
                row.get("industry") == industry["code"] and row.get("account_type") == account_type
                for row in included
            )
            quota_rows.append({
                "quota_type": "industry_account", "industry": industry["code"],
                "category": account_type, "target": target, "actual": actual,
                "shortfall": max(0, int(target) - actual),
                "complete": int(actual >= int(target)),
            })
    posts = read_rows(STAGE2_POSTS)
    for media, target in config["global_media_minimums"].items():
        actual = sum(row.get("media_type") == media for row in posts)
        quota_rows.append({
            "quota_type": "global_media", "industry": "all", "category": media,
            "target": target, "actual": actual, "shortfall": max(0, int(target)-actual),
            "complete": int(actual >= int(target)),
        })
    for appeal, actual in Counter(row.get("appeal_auto") for row in posts).items():
        target = int(config["appeal_type_minimum"])
        quota_rows.append({
            "quota_type": "appeal", "industry": "all", "category": appeal,
            "target": target, "actual": actual, "shortfall": max(0, target-actual),
            "complete": int(actual >= target),
        })
    write_csv(QUOTA_AUDIT, ["quota_type", "industry", "category", "target", "actual", "shortfall", "complete"], quota_rows)

    attrition = []
    for window in ("T0", "T24H", "T7D"):
        eligible = len(included)
        valid = sum((row["post_id"], window) in canonical for row in included)
        errors = sum(
            row.get("scheduled_window") == window and row.get("request_status") == "error"
            for row in snapshots_all
        )
        late = sum(
            row.get("scheduled_window") == window and row.get("request_status") == "success"
            and not as_bool(row.get("within_tolerance")) for row in snapshots_all
        )
        attrition.append({
            "window": window, "included_posts": eligible, "valid_snapshots": valid,
            "missing_valid_snapshot": eligible-valid, "error_attempts": errors,
            "successful_out_of_window_attempts": late,
        })
    reasons = Counter(row.get("exclusion_reason") or "included" for row in frames)
    for reason, count in sorted(reasons.items()):
        attrition.append({"window": f"screen:{reason}", "included_posts": count})
    write_csv(ATTRITION_AUDIT, [
        "window", "included_posts", "valid_snapshots", "missing_valid_snapshot",
        "error_attempts", "successful_out_of_window_attempts",
    ], attrition)
    print(f"[done] {QUOTA_AUDIT.name}, {ATTRITION_AUDIT.name}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Stage-2 prospective Weibo study")
    root.add_argument("--config", default=str(CONFIG_PATH))
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    p = commands.add_parser("discover")
    p.add_argument("--industry", default="")
    p.add_argument("--pages", type=int, default=3)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--delay", type=float, default=2.0)
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--use-cookie", action="store_true",
                   help="Explicitly use the local Weibo session cookie")
    p.add_argument("--media-type", choices=["image", "other", "video"], default="",
                   help="Only include posts of this detected media type")
    p.add_argument("--allow-open-discovery", action="store_true",
                   help="Pilot only: accept authors outside a non-empty frozen roster")
    p = commands.add_parser("snapshots")
    p.add_argument("--window", choices=["all", "T24H", "T7D"], default="all")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--delay", type=float, default=2.0)
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--use-cookie", action="store_true",
                   help="Explicitly use the local Weibo session cookie")
    p = commands.add_parser("manual-sample")
    p.add_argument("--replace", action="store_true")
    commands.add_parser("audit")
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "init":
        initialize()
        return 0
    if args.command == "discover":
        return discover(args)
    if args.command == "snapshots":
        return snapshots(args)
    if args.command == "manual-sample":
        return manual_sample(args)
    if args.command == "audit":
        return audit(args)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[x] {exc}")
        raise SystemExit(2)
