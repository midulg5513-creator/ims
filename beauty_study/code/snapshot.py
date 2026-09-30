# -*- coding: utf-8 -*-
"""多时点互动快照 → data/engagement_snapshots.csv（需求 §4.3 §8）。

- 同一帖子在发布后 1h / 6h / 24h / 72h / 7d 重复抓取互动数。
- 每个窗口只成功记录一次；到期未抓到的窗口记为 missed（不静默填 0）。
- 快照表字段严格按需求 §8：post_id | published_at | snapshot_at | age_hours |
  like_count | comment_count | repost_count（另加 window/状态等辅助列）。
- 互动数必须与抓取时间一起保存（§4.3），所以 snapshot_at / age_hours 必填。

用法
----
python code/snapshot.py --report              # 只看窗口完成度，不发请求
python code/snapshot.py --due                 # 抓所有到期窗口
python code/snapshot.py --due --limit 500     # 限制本次请求数
python code/snapshot.py --due --force         # 忽略已完成记录（重抓）
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    banner,
    ensure_dirs,
    iso,
    load_config,
    log,
    now_utc,
    open_log,
    parse_weibo_time,
    read_csv,
    resolve_path,
    to_int,
    write_csv,
)
from mweibo import BudgetExhausted, MWeibo  # noqa: E402

SNAPSHOT_FIELDS = [
    "post_id", "brand", "account_uid", "published_at",
    "window_hours", "window_label", "target_at", "snapshot_at", "age_hours",
    "like_count", "comment_count", "repost_count",
    "fetch_status", "note",
]

WINDOW_LABEL = {1: "1h", 6: "6h", 24: "24h", 72: "72h", 168: "7d"}


def label_for(hours: int) -> str:
    if hours in WINDOW_LABEL:
        return WINDOW_LABEL[hours]
    return f"{hours}h"


def build_plan(posts: list[dict], windows: list[int], tol: dict, now,
               recorded: dict) -> tuple[list[dict], int]:
    """产出待抓计划。

    返回 (plan, unavailable)：
    - plan 内含 due（窗口内）/ missed（该抓没抓到）；
    - unavailable = 窗口在**首次采集之前**就已结束（历史帖的 1h/6h/24h… 窗口），
      这类无法回溯，不写入行，只在报告里计数。
    """
    plan = []
    unavailable = 0
    for p in posts:
        pid = p.get("post_id")
        pub = parse_weibo_time(p.get("published_at"))
        if not pid or pub is None:
            continue
        ct = parse_weibo_time(p.get("collection_time"))
        for w in windows:
            key = (pid, int(w))
            if key in recorded:
                continue
            target = pub + timedelta(hours=w)
            t_h = float(tol.get(str(w), max(2.0, w * 0.05)))
            due_from = target - timedelta(hours=t_h)
            due_until = target + timedelta(hours=t_h)
            if now < due_from:
                continue                      # 未到期
            if now > due_until and (ct is None or due_until < ct):
                unavailable += 1              # 窗口在首次采集前就结束了
                continue
            state = "due" if now <= due_until else "missed"
            plan.append({
                "post_id": pid, "brand": p.get("brand", ""), "account_uid": p.get("account_uid", ""),
                "published_at": p.get("published_at", ""), "window_hours": int(w),
                "window_label": label_for(int(w)), "target_at": iso(target), "_state": state,
            })
    return plan, unavailable


def main() -> int:
    ap = argparse.ArgumentParser(description="多时点互动快照调度")
    ap.add_argument("--due", action="store_true", help="抓取所有到期窗口")
    ap.add_argument("--report", action="store_true", help="只打印完成度")
    ap.add_argument("--force", action="store_true", help="忽略已成功记录，重抓")
    ap.add_argument("--limit", type=int, default=0, help="本次最多请求数（0=不限）")
    ap.add_argument("--no-cookie", action="store_true", help="强制不使用 cookie")
    ap.add_argument("--cookie-file", help="cookie 文件；缺省用 config.request.cookie_file")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    open_log(resolve_path("data/snapshot.log"))

    posts = read_csv(resolve_path(cfg["paths"]["posts_raw"]))
    if not posts:
        log("posts_raw.csv 为空，请先运行 collect_timeline.py")
        return 1

    windows = [int(w) for w in cfg["study"]["snapshot_windows_hours"]]
    tol = cfg["study"]["snapshot_tolerance_hours"]
    now = now_utc()

    snap_path = resolve_path(cfg["paths"]["snapshots"])
    existing = read_csv(snap_path)
    recorded = {}
    for r in existing:
        if r.get("fetch_status") == "success" and not args.force:
            recorded[(r["post_id"], int(r["window_hours"]))] = r

    plan, unavailable = build_plan(posts, windows, tol, now, recorded)

    # 完成度统计
    def tally():
        done = {(r["post_id"], int(r["window_hours"])) for r in existing if r.get("fetch_status") == "success"}
        miss = {(r["post_id"], int(r["window_hours"])) for r in existing if r.get("fetch_status") == "missed"}
        tot = len(posts) * len(windows)
        pend = tot - len(done) - len(miss)
        return done, miss, pend, tot

    if args.report or not args.due:
        done, miss, pend, tot = tally()
        banner(f"快照完成度：帖子 {len(posts)} × 窗口 {len(windows)} = {tot}")
        log(f"  成功 success : {len(done)}")
        log(f"  错过 missed  : {len(miss)}")
        log(f"  待抓 pending : {pend}")
        log("")
        for w in windows:
            d = sum(1 for (pid, ww) in done if ww == w)
            m = sum(1 for (pid, ww) in miss if ww == w)
            log(f"  窗口 {label_for(w):>4} : success={d:<5} missed={m:<5}")
        log("")
        log("到期待抓：" + str(sum(1 for x in plan if x["_state"] == "due")))
        log("该抓未抓到：" + str(sum(1 for x in plan if x["_state"] == "missed")))
        log(f"历史不可得：{unavailable}（帖子在首次采集前窗口已结束，无法回溯；不写入快照表）")
        if not args.due:
            log("")
            log("加 --due 才会真正抓取。")
            return 0

    due = [x for x in plan if x["_state"] == "due"]
    missed = [x for x in plan if x["_state"] == "missed"]
    if args.limit:
        due = due[:args.limit]

    banner(f"抓取快照：到期 {len(due)} 个，" + (f"（本次限制 {args.limit}）" if args.limit else "")
           + f"；登记 missed {len(missed)} 个；历史不可得 {unavailable} 个")
    client = MWeibo(cfg, cookie_file=args.cookie_file,
                    use_cookie=(False if args.no_cookie else None), log_fn=log)

    new_rows: list[dict] = []
    # 先登记 missed（只写状态，不留假 0）
    for x in missed:
        new_rows.append({
            "post_id": x["post_id"], "brand": x["brand"], "account_uid": x["account_uid"],
            "published_at": x["published_at"], "window_hours": x["window_hours"],
            "window_label": x["window_label"], "target_at": x["target_at"],
            "snapshot_at": "", "age_hours": "", "like_count": "", "comment_count": "",
            "repost_count": "", "fetch_status": "missed", "note": "超过容差窗口未采集",
        })

    stopped = False
    for i, x in enumerate(due, 1):
        try:
            data = client.get_status(x["post_id"])
        except BudgetExhausted as e:
            log(f"  {e}")
            stopped = True
            break
        now2 = now_utc()
        pub = parse_weibo_time(x["published_at"])
        ah = round((now2 - pub).total_seconds() / 3600.0, 4) if pub else ""
        row = {
            "post_id": x["post_id"], "brand": x["brand"], "account_uid": x["account_uid"],
            "published_at": x["published_at"], "window_hours": x["window_hours"],
            "window_label": x["window_label"], "target_at": x["target_at"],
            "snapshot_at": iso(now2), "age_hours": ah, "like_count": "", "comment_count": "",
            "repost_count": "", "fetch_status": "failed", "note": "",
        }
        d = (data or {}).get("data") if isinstance(data, dict) else None
        if isinstance(d, dict) and d.get("id"):
            row["like_count"] = to_int(d.get("attitudes_count"))
            row["comment_count"] = to_int(d.get("comments_count"))
            row["repost_count"] = to_int(d.get("reposts_count"))
            row["fetch_status"] = "success"
        elif data is None:
            row["fetch_status"] = "deleted"
            row["note"] = "帖子不可访问（可能已删除或设为私密）"
        else:
            row["fetch_status"] = "failed"
            row["note"] = f"接口返回异常：{str(data)[:80]}"
        new_rows.append(row)
        if i % 20 == 0 or i == len(due):
            log(f"  [{i}/{len(due)}] {row['post_id']} {row['window_label']} "
                f"-> {row['fetch_status']} 转={row['repost_count']}")

    merged = existing + new_rows
    write_csv(snap_path, merged, SNAPSHOT_FIELDS)
    n_ok = sum(1 for r in new_rows if r["fetch_status"] == "success")
    log("")
    log(f"本次写入 {len(new_rows)} 行（success {n_ok} / missed {len(missed)} / 其他 {len(new_rows)-n_ok-len(missed)}）"
        + ("；额度耗尽提前停止" if stopped else ""))
    log(f"engagement_snapshots.csv 现共 {len(merged)} 行")
    log(f"请求统计：{client.stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
