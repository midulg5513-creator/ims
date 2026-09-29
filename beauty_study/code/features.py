# -*- coding: utf-8 -*-
"""自动特征 + 词典特征 → data/cleaned_posts.csv（需求 §5）。

在 posts_raw.csv 之上新增：
- 文本：正文长度、问号/感叹号数、表情数、话题数
- 词典：购买引导、折扣、抽奖、新品、明星、产品功效、使用场景、互动引导、直播
- 时间：发帖小时、星期、周末、节假日
- 并且每行写入 dictionary_version

匹配口径为 presence（每个词最多计 1 次），大小写不敏感；词典改动必须提升版本号。

用法
----
python code/features.py
python code/features.py --raw data/posts_raw.csv --out data/cleaned_posts.csv
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    CN_TZ,
    PROJECT_ROOT,
    banner,
    ensure_dirs,
    load_config,
    log,
    open_log,
    parse_weibo_time,
    read_csv,
    resolve_path,
    write_csv,
)

DICT_PATH = PROJECT_ROOT / "dictionaries.json"

EMOJI_RE = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F000-\U0001F2FF"
    "\U00002190-\U000021FF" "\U00002B00-\U00002BFF" "]+"
)
WEIBO_EMOJI_RE = re.compile(r"\[[^\[\]]{1,8}\]")

FEATURE_FIELDS = [
    "text_length", "text_length_no_tag", "q_count", "exclam_count", "emoji_count",
    "hashtag_count", "cta_engage_count", "has_cta_purchase", "n_discount", "has_discount",
    "n_giveaway", "has_giveaway", "n_new_product", "has_new_product",
    "n_celebrity", "has_celebrity", "n_benefit", "has_benefit",
    "n_scenario", "has_scenario", "has_livestream",
    "pub_hour", "pub_dow", "is_weekend", "is_holiday", "holiday_name",
    "ln_followers", "dictionary_version",
]


def load_dict() -> dict:
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def hits(text: str, words: list[str]) -> int:
    """presence 计数：命中的不同词数（每个词最多计 1 次）。"""
    low = text.lower()
    return sum(1 for w in words if w.lower() in low)


def emoji_count(text: str) -> int:
    return len(EMOJI_RE.findall(text)) + len(WEIBO_EMOJI_RE.findall(text))


def compute_features(row: dict, d: dict) -> dict:
    text = row.get("text_clean") or row.get("text_raw") or ""
    tags = [t for t in (row.get("hashtags_raw") or "").split("|") if t]
    no_tag = text
    for t in tags:
        no_tag = no_tag.replace(f"#{t}#", "")
    no_tag = no_tag.strip()

    pub = parse_weibo_time(row.get("published_at"))
    pub_hour = pub_dow = is_weekend = None
    is_holiday, holiday_name = 0, ""
    if pub:
        p = pub.astimezone(CN_TZ)
        pub_hour = p.hour
        pub_dow = p.weekday()
        is_weekend = int(pub_dow >= 5)
        md = p.strftime("%m-%d")
        ymd = p.strftime("%Y-%m-%d")
        if md in d["holidays"]:
            is_holiday, holiday_name = 1, d["holidays"][md]
        elif ymd in d["holidays"]:
            is_holiday, holiday_name = 1, d["holidays"][ymd]

    fol = row.get("follower_count")
    try:
        ln_fol = round(math.log(float(fol)), 6) if fol not in (None, "", 0) else None
    except (TypeError, ValueError):
        ln_fol = None

    return {
        "text_length": len(text),
        "text_length_no_tag": len(no_tag),
        "q_count": sum(text.count(m) for m in d["question_marks"]),
        "exclam_count": sum(text.count(m) for m in d["exclam_marks"]),
        "emoji_count": emoji_count(text),
        "hashtag_count": len(tags),
        "cta_engage_count": hits(text, d["cta_engage"]),
        "has_cta_purchase": int(hits(text, d["cta_purchase"]) > 0),
        "n_discount": hits(text, d["discount"]),
        "has_discount": int(hits(text, d["discount"]) > 0),
        "n_giveaway": hits(text, d["giveaway"]),
        "has_giveaway": int(hits(text, d["giveaway"]) > 0),
        "n_new_product": hits(text, d["new_product"]),
        "has_new_product": int(hits(text, d["new_product"]) > 0),
        "n_celebrity": hits(text, d["celebrity"]),
        "has_celebrity": int(hits(text, d["celebrity"]) > 0),
        "n_benefit": hits(text, d["benefit"]),
        "has_benefit": int(hits(text, d["benefit"]) > 0),
        "n_scenario": hits(text, d["scenario"]),
        "has_scenario": int(hits(text, d["scenario"]) > 0),
        "has_livestream": int(hits(text, d["livestream"]) > 0 or row.get("has_live") in (True, "True", 1, "1")),
        "pub_hour": pub_hour,
        "pub_dow": pub_dow,
        "is_weekend": is_weekend,
        "is_holiday": is_holiday,
        "holiday_name": holiday_name,
        "ln_followers": ln_fol,
        "dictionary_version": d["version"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="自动特征 + 词典特征")
    ap.add_argument("--raw", help="输入 CSV，默认 data/posts_raw.csv")
    ap.add_argument("--out", help="输出 CSV，默认 data/cleaned_posts.csv")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    open_log(resolve_path("data/features.log"))
    d = load_dict()

    in_path = resolve_path(args.raw) if args.raw else resolve_path(cfg["paths"]["posts_raw"])
    out_path = resolve_path(args.out) if args.out else resolve_path(cfg["paths"]["cleaned_posts"])
    rows = read_csv(in_path)
    if not rows:
        log(f"{in_path} 为空，请先运行 collect_timeline.py")
        return 1

    banner(f"特征工程：{len(rows)} 条，词典 {d['version']}")
    out_rows = []
    for r in rows:
        r = dict(r)
        r.update(compute_features(r, d))
        out_rows.append(r)

    fields = list(rows[0].keys())
    for f in FEATURE_FIELDS:
        if f not in fields:
            fields.insert(len(fields), f)
    # 去重保序
    seen, ordered = set(), []
    for f in fields:
        if f not in seen:
            seen.add(f)
            ordered.append(f)

    write_csv(out_path, out_rows, ordered)
    log(f"已写出 {out_path}（{len(out_rows)} 行 × {len(ordered)} 列）")

    n_ok = sum(1 for r in out_rows if r.get("pub_hour") not in (None, ""))
    log("")
    log(f"时间字段可用率：pub_hour {n_ok}/{len(out_rows)}")
    for key in ("has_giveaway", "has_discount", "has_new_product", "has_celebrity",
                "has_benefit", "has_scenario", "has_cta_purchase", "has_livestream", "is_holiday"):
        c = sum(1 for r in out_rows if r.get(key) in (1, "1", True, "True"))
        log(f"  {key:<18}: {c:>5} ({c/len(out_rows)*100:.1f}%)")
    log(f"  is_weekend        : {sum(1 for r in out_rows if r.get('is_weekend') in (1,'1',True))}")
    log("")
    log(f"dictionary_version = {d['version']}")
    log("下一步：python code/snapshot.py --report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
