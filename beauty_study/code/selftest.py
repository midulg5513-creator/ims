# -*- coding: utf-8 -*-
"""自检 + 端到端小规模试跑（合成数据，不联网）。

用途：在真正采集前验证 features / snapshot / annotate / quality / export_parquet 全链路可跑，
并验证关键函数逻辑（时间解析、计数还原、词典、Kappa）。

安全：若 data/posts_raw.csv 已存在（真实数据），本脚本拒绝运行，除非加 --force。
     运行结束后会删除**本次新建**的合成输入与产出（运行前已存在的文件一律不动）。

用法
----
python code/selftest.py
python code/selftest.py --force
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    PROJECT_ROOT,
    iso,
    load_config,
    parse_weibo_time,
    read_csv,
    resolve_path,
    to_int,
    write_csv,
)

CODE = Path(__file__).resolve().parent
SENTINEL = "__SELFTEST__"
PY = sys.executable

CREATED: list[Path] = []


def touch_new(p: Path) -> None:
    if not p.exists():
        CREATED.append(p)


def run(args: list[str]) -> int:
    log_line(f"$ python {' '.join(args)}")
    import os
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run([PY] + args, cwd=str(CODE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    tail = (r.stdout or "").strip().splitlines()
    for line in tail[-8:]:
        log_line("    " + line)
    if r.returncode != 0 and r.stderr:
        log_line("  STDERR: " + (r.stderr or "")[-500:])
    return r.returncode


LOG_LINES: list[str] = []


def log_line(s: str) -> None:
    LOG_LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(s.encode(enc, "replace").decode(enc, "replace"), flush=True)


# ---------------------------------------------------------------- 单元检查

def unit_checks() -> int:
    log_line("\n[A] 单元检查")
    fails = 0

    def ck(name, got, want):
        nonlocal fails
        ok = got == want
        if not ok:
            fails += 1
        log_line(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got!r} want={want!r}")

    ck("to_int('1.2万')", to_int("1.2万"), 12000)
    ck("to_int('931.2万')", to_int("931.2万"), 9312000)
    ck("to_int('1,234')", to_int("1,234"), 1234)
    ck("to_int(202)", to_int(202), 202)
    ck("to_int('')", to_int(""), None)

    dt = parse_weibo_time("Wed Sep 24 12:34:56 +0800 2026")
    ck("parse_weibo_time year", dt.year if dt else None, 2026)
    ck("parse_weibo_time utc-hour", dt.astimezone(timezone.utc).hour if dt else None, 4)
    ck("parse_weibo_time bad", parse_weibo_time("###"), None)

    from mweibo import clean_text, classify_host, parse_mblog
    ck("clean_text 去链接占位", clean_text("新品上市 O网页链接 快看"), "新品上市 快看")
    ck("classify_host tmall", classify_host("https://detail.tmall.com/x"), "shop")
    ck("classify_host t.cn", classify_host("https://t.cn/abc"), "external")

    fake = {
        "id": "5000000000000001", "mid": "5000000000000001",
        "created_at": "Wed Sep 24 12:34:56 +0800 2026",
        "text": "<a href='x'>#新品#</a> 薇诺娜特护霜来啦！@小美 快看 https://t.cn/AbC O网页链接",
        "pics": [1, 2, 3], "attitudes_count": "1.2万", "comments_count": 300,
        "reposts_count": 0, "source": "iPhone客户端", "region_name": "发布于 上海",
        "page_info": {"type": "webpage", "url_ori": "https://detail.tmall.com/item.htm?id=9", "media_info": None},
        "user": {"id": 123, "screen_name": "薇诺娜", "followers_count": "931.2万", "verified": True},
    }
    row = parse_mblog(fake, "薇诺娜", "cn_functional", {"uid": "123", "screen_name": "薇诺娜", "followers_count": 9312000})
    ck("parse image_count", row["image_count"], 3)
    ck("parse like_count", row["like_count"], 12000)
    ck("parse hashtags", row["hashtags_raw"], "新品")
    ck("parse mentions", row["mentions_count"], 1)
    ck("parse media_type", row["media_type"], "image")
    ck("parse has_shop_link", row["has_shop_link"], True)
    ck("parse account_type", row["account_type"], "brand_official")

    from features import compute_features, load_dict
    f = compute_features(row, load_dict())
    ck("feat hashtag_count", f["hashtag_count"], 1)
    ck("feat pub_hour", f["pub_hour"], 12)
    ck("feat is_weekend", f["is_weekend"], 0)
    ck("feat dict_version", f["dictionary_version"], load_dict()["version"])

    from annotate import cohen_kappa, jaccard_f1
    k, po = cohen_kappa([("0", "0"), ("2", "2"), ("1", "2"), ("3", "3"), ("4", "4")])
    ck("kappa 一致率", round(po, 2), 0.8)
    ck("kappa>0", k > 0, True)
    jac, f1, rec = jaccard_f1([(True, True), (True, False), (False, True), (False, False)])
    ck("jaccard", round(jac, 3), 0.333)

    from snapshot import build_plan
    now = datetime.now(timezone.utc)
    posts = [{"post_id": "p1", "brand": "b", "account_uid": "1", "published_at": iso(now - timedelta(hours=25))}]
    plan = build_plan(posts, [1, 6, 24, 72, 168], {"1": 0.5, "6": 1, "24": 2, "72": 4, "168": 8}, now, {})
    states = [p["_state"] for p in plan]
    ck("build_plan 到期数(due)", states.count("due"), 1)      # 24h 落在 ±2h 容差内
    ck("build_plan 已错过(missed)", states.count("missed"), 2)  # 1h/6h 已超出容差
    ck("build_plan 未到期不生成", len(plan), 3)                 # 72h/168h 尚未到期
    log_line(f"  → 单元检查失败 {fails} 项")
    return fails


# ---------------------------------------------------------------- 合成数据

def gen_posts_raw(cfg: dict, n_per_brand: int = 20) -> int:
    from mweibo import POST_FIELDS
    brands = [("薇诺娜", "cn_functional", "1001", 9312000),
              ("珀莱雅", "cn_functional", "1002", 5120000),
              ("兰蔻", "intl_premium", "1003", 4100000),
              ("自然堂", "cn_mass", "1004", 3000000)]
    media_cycle = ["image", "video", "text", "mixed"]
    now = datetime.now(timezone.utc)
    rows = []
    k = 0
    for brand, cat, uid, fol in brands:
        for j in range(n_per_brand):
            k += 1
            pub = now - timedelta(days=(j * 3) % 58, hours=j % 24)
            mt = media_cycle[j % len(media_cycle)]
            reps = [0, 0, 1, 5, 42, 300][j % 6] if brand != "自然堂" else [0, 1, 2, 7][j % 4]
            text = f"#新品# {brand} 第{j}条 {['补水保湿', '抽奖福利', '代言官宣', '使用教程'][j % 4]} " * 2
            row = {f: "" for f in POST_FIELDS}
            row.update({
                "post_id": f"{SENTINEL}{k:04d}", "mid": f"{SENTINEL}{k:04d}",
                "post_url": f"https://m.weibo.cn/detail/{SENTINEL}{k:04d}",
                "brand": brand, "brand_category": cat, "account_type": "brand_official",
                "account_uid": uid, "account_name": brand,
                "is_original": j % 5 != 0, "parent_post_id": "" if j % 5 != 0 else "999",
                "collection_time": iso(now),
                "text_raw": text, "text_clean": text, "hashtags_raw": "新品",
                "mentions_count": j % 3, "external_link_count": 1 if j % 2 else 0,
                "image_count": 3 if mt in ("image", "mixed") else 0,
                "has_video": mt in ("video", "mixed"), "has_live": j % 7 == 0,
                "media_type": mt,
                "published_at": iso(pub), "like_count": reps * 8, "comment_count": reps * 2,
                "repost_count": reps, "follower_count": fol,
                "post_age_hours": round((now - pub).total_seconds() / 3600, 2),
                "metric_observation_window": "current",
                "fetch_status": "success", "missing_fields": "", "is_duplicate": False,
                "exclusion_reason": "", "author_hash": f"hash{uid}", "region_name": "上海",
                "source": "iPhone客户端", "page_info_type": "webpage",
                "page_url_ori": "https://t.cn/abc" if j % 2 else "",
                "has_external_link": j % 2 == 1, "has_shop_link": False,
            })
            rows.append(row)
    out = resolve_path(cfg["paths"]["posts_raw"])
    touch_new(out)
    write_csv(out, rows, POST_FIELDS)
    log_line(f"  合成 posts_raw.csv：{len(rows)} 行 × {len(POST_FIELDS)} 列")
    return len(rows)


def gen_snapshots(cfg: dict) -> int:
    posts = read_csv(resolve_path(cfg["paths"]["posts_raw"]))
    from snapshot import SNAPSHOT_FIELDS
    now = datetime.now(timezone.utc)
    rows = []
    for i, p in enumerate(posts[:20]):
        base = to_int(p.get("repost_count")) or 0
        for w in (1, 6, 24):
            pub = parse_weibo_time(p.get("published_at"))
            tgt = pub + timedelta(hours=w)
            if tgt > now:
                continue
            rows.append({
                "post_id": p["post_id"], "brand": p["brand"], "account_uid": p["account_uid"],
                "published_at": p["published_at"], "window_hours": w,
                "window_label": {1: "1h", 6: "6h", 24: "24h"}[w], "target_at": iso(tgt),
                "snapshot_at": iso(tgt + timedelta(minutes=5)),
                "age_hours": w + 0.08,
                "like_count": base * 8, "comment_count": base * 2,
                "repost_count": int(base * (1 + w / 24)),
                "fetch_status": "success", "note": "",
            })
        # 造一个 missed 展示状态
        if i == 0:
            rows.append({"post_id": p["post_id"], "brand": p["brand"], "account_uid": p["account_uid"],
                         "published_at": p["published_at"], "window_hours": 72, "window_label": "72h",
                         "target_at": "", "snapshot_at": "", "age_hours": "",
                         "like_count": "", "comment_count": "", "repost_count": "",
                         "fetch_status": "missed", "note": "超过容差窗口未采集"})
    out = resolve_path(cfg["paths"]["snapshots"])
    touch_new(out)
    write_csv(out, rows, SNAPSHOT_FIELDS)
    log_line(f"  合成 engagement_snapshots.csv：{len(rows)} 行")
    return len(rows)


def fake_annotations(cfg: dict) -> int:
    p = resolve_path(cfg["paths"]["annotation_sample"])
    rows = read_csv(p)
    import random
    rng = random.Random(7)
    for r in rows:
        truth = rng.choice(["0", "1", "2", "3"])
        for k in (1, 2):
            r[f"a{k}_annotator_id"] = f"ann{k}"
            # 85% 一致
            r[f"a{k}_commercial_intent"] = truth if rng.random() < 0.85 else rng.choice(["0", "1", "2", "3", "4"])
            for c in ["celebrity", "new_product", "discount", "giveaway", "livestream", "product_benefit",
                      "usage_tutorial", "usage_scenario", "topic", "interaction", "call_to_action",
                      "expression_informational", "expression_emotional", "expression_interactive",
                      "expression_authority", "expression_storytelling", "expression_promotional",
                      "has_evidence", "has_user_scenario", "has_exaggeration", "has_purchase_link"]:
                v = "1" if rng.random() < 0.35 else "0"
                r[f"a{k}_{c}"] = v if rng.random() < 0.85 else ("0" if v == "1" else "1")
            r[f"a{k}_note"] = ""
            r[f"a{k}_annotation_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    fields = list(rows[0].keys())
    write_csv(p, rows, fields)
    log_line(f"  已模拟两位标注者填写 {len(rows)} 条")
    return len(rows)


def cleanup(cfg: dict) -> None:
    log_line("\n[E] 清理本次新建的合成文件（运行前已存在的文件不动）")
    removed = 0
    for p in CREATED:
        try:
            if p.exists():
                p.unlink()
                removed += 1
                log_line(f"  删除 {p.relative_to(PROJECT_ROOT)}")
        except OSError as e:
            log_line(f"  删除失败 {p}: {e}")
    log_line(f"  共删除 {removed} 个文件；日志保留在 data/_selftest_run.log")


def main() -> int:
    ap = argparse.ArgumentParser(description="自检 + 端到端试跑")
    ap.add_argument("--force", action="store_true", help="即使已存在 posts_raw.csv 也运行")
    ap.add_argument("--keep", action="store_true", help="保留合成数据（默认删除）")
    args = ap.parse_args()

    cfg = load_config()
    real = resolve_path(cfg["paths"]["posts_raw"])
    if real.exists() and not args.force:
        print(f"[!!] {real} 已存在（可能是真实数据）。如确要试跑请加 --force。")
        return 1

    log_line("=" * 72)
    log_line("  端到端自检（合成数据，不联网）")
    log_line("=" * 72)

    fails = unit_checks()

    log_line("\n[B] 生成合成数据")
    gen_posts_raw(cfg)
    touch_new(resolve_path(cfg["paths"]["cleaned_posts"]))
    touch_new(resolve_path(cfg["paths"]["cleaned_posts"]).with_suffix(".parquet"))
    touch_new(resolve_path(cfg["paths"]["annotation_sample"]))
    touch_new(resolve_path(cfg["paths"]["annotation_sample"]).with_suffix(".parquet"))
    touch_new(resolve_path(cfg["paths"]["annotation_guideline"]))
    touch_new(resolve_path(cfg["paths"]["snapshots"]))
    touch_new(resolve_path(cfg["paths"]["snapshots"]).with_suffix(".parquet"))
    touch_new(resolve_path(cfg["paths"]["quality_report"]))
    touch_new(resolve_path(cfg["paths"]["sampling_report"]))
    touch_new(resolve_path("reports/kappa_report.md"))
    touch_new(resolve_path("reports/quality_summary.json"))
    touch_new(resolve_path(cfg["paths"]["raw"]) / "_request_budget.json")

    log_line("\n[C] 跑各脚本")
    rc = []
    rc.append(("features", run(["features.py"])))
    rc.append(("annotate guideline", run(["annotate.py", "guideline"])))
    rc.append(("annotate sample", run(["annotate.py", "sample", "--size", "40"])))
    gen_snapshots(cfg)
    fake_annotations(cfg)
    rc.append(("annotate status", run(["annotate.py", "status"])))
    rc.append(("annotate kappa", run(["annotate.py", "kappa"])))
    rc.append(("snapshot report", run(["snapshot.py", "--report"])))
    rc.append(("quality", run(["quality.py"])))
    rc.append(("export_parquet", run(["export_parquet.py"])))

    log_line("\n[D] 结果")
    for name, code in rc:
        log_line(f"  {'OK ' if code == 0 else 'ERR'}  {name} (exit={code})   {'← 非 0 需检查' if code else ''}")
    n_err = sum(1 for _, c in rc if c != 0)

    log_line("")
    log_line(f"单元检查失败：{fails} 项；脚本非 0 退出：{n_err} 个")
    log_line("结论：" + ("全部通过 OK" if fails == 0 and n_err == 0
                        else "存在需要检查的项，见上方标记"))

    out = resolve_path("data/_selftest_run.log")
    out.write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")
    print(f"\n完整日志：{out}")

    if not args.keep:
        cleanup(cfg)

    return 0 if (fails == 0 and n_err == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
