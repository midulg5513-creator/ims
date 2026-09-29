# -*- coding: utf-8 -*-
"""品牌官方账号时间线采集 → data/posts_raw.csv（需求 §2 §4.1 §4.2）。

- 连续抓官方账号主页时间线（containerid=107603<uid>），不按关键词搜索，不挑热门帖。
- 倒序时间线：遇到早于截止时间的帖子即停止翻页。
- 原始 mblog 落盘到 data/raw_snapshots/timeline_<brand>.jsonl（可复现、可回溯）。
- 增量安全：已存在的 post_id 不重复抓取；按文本指纹标记完全重复文本。

用法
----
python code/collect_timeline.py --dry-run          # 只探测首页条数与时间跨度
python code/collect_timeline.py --brands 自然堂 --pages 2
python code/collect_timeline.py --days 60 --pages 5
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    banner,
    ensure_dirs,
    load_brands,
    load_config,
    log,
    now_utc,
    open_log,
    parse_weibo_time,
    read_csv,
    read_jsonl,
    resolve_path,
    text_fingerprint,
    write_csv,
)
from mweibo import POST_FIELDS, BudgetExhausted, MWeibo, iter_mblogs, parse_mblog, parse_user  # noqa: E402


def safe_name(s: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fa5-]", "_", s)


def collect_brand(client: MWeibo, brand: dict, cfg: dict, cutoff, pages: int,
                  original_only: bool, dry_run: bool) -> tuple[list[dict], dict]:
    uid = brand["uid"]
    name = brand["brand"]
    raw_path = resolve_path(cfg["paths"]["raw"]) / f"timeline_{safe_name(name)}.jsonl"

    rows: list[dict] = []
    raw_objs: list[dict] = []
    stats = {"pages": 0, "mblogs": 0, "in_window": 0, "stopped": False, "errors": 0}

    for page in range(1, pages + 1):
        try:
            data = client.get_timeline(uid, page=page)
        except BudgetExhausted as e:
            log(f"    {e}")
            stats["stopped"] = True
            break
        if not data:
            stats["errors"] += 1
            break
        cards = (data.get("data") or {}).get("cards") or []
        mblogs = list(iter_mblogs(cards))
        if not mblogs:
            log(f"    第 {page} 页无 mblog（可能已到末页或需登录态）")
            break

        stats["pages"] += 1
        stats["mblogs"] += len(mblogs)
        oldest = None
        for mb in mblogs:
            pub = parse_weibo_time(mb.get("created_at"))
            if pub is None:
                continue
            if oldest is None or pub < oldest:
                oldest = pub
            if pub < cutoff:
                continue
            if original_only and mb.get("retweeted_status"):
                continue
            stats["in_window"] += 1
            u = parse_user(mb.get("user"))
            account = {
                "uid": u["uid"] or uid,
                "screen_name": u["screen_name"] or brand.get("account_name") or name,
                "followers_count": u["followers_count"] if u["followers_count"] is not None
                                   else brand.get("followers"),
            }
            rows.append(parse_mblog(mb, name, brand["category"], account))
            raw_objs.append({"brand": name, "uid": uid, "page": page, "mblog": mb})

        log(f"    第 {page} 页：{len(mblogs)} 条，窗口内累计 {stats['in_window']} 条"
            + (f"，最旧 {oldest.strftime('%Y-%m-%d %H:%M')}" if oldest else ""))

        if oldest is not None and oldest < cutoff:
            stats["stopped"] = True
            break

    if not dry_run and raw_objs:
        from common import append_jsonl
        append_jsonl(raw_path, raw_objs)
        log(f"    原始快照追加 {len(raw_objs)} 条 -> {raw_path.name}")

    return rows, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="美妆品牌官方账号时间线采集")
    ap.add_argument("--brands", help="逗号分隔的品牌名（须已 confirmed）")
    ap.add_argument("--days", type=int, help="采集窗口天数，默认取 config.collection_window_days")
    ap.add_argument("--pages", type=int, help="每品牌翻页数，默认取 config.pages_per_run")
    ap.add_argument("--original-only", action="store_true", help="只保留原创帖")
    ap.add_argument("--dry-run", action="store_true", help="只探测首页，不写文件")
    ap.add_argument("--no-cookie", action="store_true", help="强制不使用 cookie")
    ap.add_argument("--cookie-file", help="cookie 文件；缺省用 config.request.cookie_file")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    open_log(resolve_path("data/collect_timeline.log"))
    brands_data = load_brands()

    days = args.days or int(cfg["study"]["collection_window_days"])
    pages = args.pages or int(cfg["collection"]["pages_per_run"])
    original_only = args.original_only or bool(cfg["collection"]["original_only"])
    cutoff = now_utc() - timedelta(days=days)

    targets = [b for b in brands_data["brands"] if b.get("active", True) and b.get("uid") and b.get("confirmed")]
    if args.brands:
        want = {n.strip() for n in args.brands.split(",")}
        targets = [b for b in targets if b["brand"] in want]

    if not targets:
        log("没有可采集的品牌：请先运行 resolve_accounts.py，并在 brands.json 中把 uid 与 confirmed=true 填好。")
        return 1

    banner(f"时间线采集：{len(targets)} 个品牌，窗口 {days} 天（截止 {cutoff.strftime('%Y-%m-%d %H:%M')} UTC），"
           f"每品牌 {pages} 页" + ("  [DRY-RUN]" if args.dry_run else ""))
    client = MWeibo(cfg, cookie_file=args.cookie_file,
                    use_cookie=(False if args.no_cookie else None), log_fn=log)

    all_rows: list[dict] = []
    brand_report = []
    for i, b in enumerate(targets, 1):
        log(f"[{i}/{len(targets)}] {b['brand']} (uid={b['uid']})")
        rows, st = collect_brand(client, b, cfg, cutoff, pages, original_only, args.dry_run)
        all_rows.extend(rows)
        brand_report.append((b["brand"], st["in_window"], st["pages"], st["stopped"]))
        log(f"    → 窗口内 {st['in_window']} 条（{st['pages']} 页）")

    if args.dry_run:
        log("")
        log("DRY-RUN 结束，未写入任何文件。")
        for name, n, pg, _ in brand_report:
            log(f"  {name}: {n} 条 / {pg} 页")
        log(f"请求统计：{client.stats}")
        return 0

    # 合并已有 posts_raw.csv
    out_path = resolve_path(cfg["paths"]["posts_raw"])
    existing = read_csv(out_path)
    seen_ids = {r["post_id"] for r in existing if r.get("post_id")}
    seen_fp = set()
    for r in existing:
        fp = text_fingerprint(r.get("text_clean", ""))
        if fp:
            seen_fp.add(fp)

    kept, dup = [], 0
    for r in all_rows:
        pid = r.get("post_id")
        if not pid or pid in seen_ids:
            continue
        seen_ids.add(pid)
        fp = text_fingerprint(r.get("text_clean", ""))
        if fp and fp in seen_fp:
            r["is_duplicate"] = True
            dup += 1
        elif fp:
            seen_fp.add(fp)
        kept.append(r)

    merged = existing + kept
    write_csv(out_path, merged, POST_FIELDS)
    log("")
    log(f"新增 {len(kept)} 条（完全重复文本 {dup} 条已标记），posts_raw.csv 现共 {len(merged)} 条")
    log(f"请求统计：{client.stats}  剩余额度：{client.budget.remaining()}")

    total = len(merged)
    log(f"进度：{total} / 目标 {cfg['study']['target_posts_min']}–{cfg['study']['target_posts_max']} 条")
    log("")
    log("下一步：python code/features.py  然后 python code/snapshot.py --due")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
