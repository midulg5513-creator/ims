# -*- coding: utf-8 -*-
"""品牌账号解析：把 brands.json 里的品牌名解析为微博 uid 候选。

用法
-----
# 1) 解析全部未确认品牌，产出候选表
python code/resolve_accounts.py

# 2) 只解析指定品牌
python code/resolve_accounts.py --brands 自然堂,薇诺娜

# 3) 自动回填 top1 候选（confirmed 仍为 false，需人工核对）
python code/resolve_accounts.py --apply

# 4) 手工指定 uid（最可靠，直接写入并置 confirmed=true）
python code/resolve_accounts.py --set 自然堂=1234567890

输出：data/account_candidates.csv（候选表，Excel 可读）
注意：--apply 只写候选，**必须人工核对 brands.json 的 account_name 后再把 confirmed 改为 true**，
      采集器只抓 confirmed=true 的品牌。
"""
from __future__ import annotations

import argparse
import difflib
import sys
from datetime import datetime

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from common import (  # noqa: E402
    banner,
    ensure_dirs,
    load_brands,
    load_config,
    log,
    open_log,
    resolve_path,
    save_brands,
    to_int,
    write_csv,
)
from mweibo import MWeibo, iter_users, parse_user  # noqa: E402


def name_score(brand: dict, screen_name: str) -> float:
    cand = (screen_name or "").strip()
    if not cand:
        return 0.0
    targets = {brand["brand"]}
    if brand.get("brand_en"):
        targets.add(str(brand["brand_en"]).strip())
    low = cand.lower()
    best = 0.0
    for t in targets:
        tl = t.lower()
        if low == tl:
            best = max(best, 100.0)
        elif tl and (tl in low or low in tl):
            best = max(best, 82.0 + min(8.0, abs(len(low) - len(tl))))
        else:
            best = max(best, 60.0 * difflib.SequenceMatcher(None, tl, low).ratio())
    # 认证信息里出现品牌名，加分
    return best


def resolve_brand(client: MWeibo, brand: dict, pages: int = 1) -> list[dict]:
    rows, seen = [], set()
    for term in brand.get("search_terms", [brand["brand"]]):
        for pg in range(1, pages + 1):
            data = client.search_users(term, page=pg)
            if not data:
                continue
            cards = (data.get("data") or {}).get("cards") or []
            for u in iter_users(cards):
                pu = parse_user(u)
                if not pu["uid"] or pu["uid"] in seen:
                    continue
                seen.add(pu["uid"])
                sc = name_score(brand, pu["screen_name"])
                # 认证说明里含品牌名的额外加权
                if brand["brand"] in (pu.get("verified_reason") or ""):
                    sc += 6
                rows.append({
                    "brand": brand["brand"],
                    "category": brand["category"],
                    "search_term": term,
                    "candidate_uid": pu["uid"],
                    "screen_name": pu["screen_name"],
                    "followers_count": pu["followers_count"],
                    "verified": int(bool(pu["verified"])),
                    "verified_type": pu["verified_type"],
                    "verified_reason": pu["verified_reason"],
                    "score": round(sc, 1),
                })
    rows.sort(key=lambda r: (-r["score"], -(r["followers_count"] or 0)))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="解析美妆品牌官方账号 uid")
    ap.add_argument("--brands", help="逗号分隔的品牌名；缺省=所有 uid 为空的品牌")
    ap.add_argument("--pages", type=int, default=1, help="每个搜索词翻页数")
    ap.add_argument("--apply", action="store_true", help="自动回填 top1 候选到 brands.json（confirmed=false）")
    ap.add_argument("--min-score", type=float, default=80.0, help="--apply 的最低分阈值")
    ap.add_argument("--set", action="append", default=[], metavar="品牌=uid",
                    help="手工指定 uid，可重复；直接写入并置 confirmed=true")
    ap.add_argument("--no-cookie", action="store_true", help="强制不使用 cookie")
    ap.add_argument("--cookie-file", help="cookie 文件；缺省用 config.request.cookie_file")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    open_log(resolve_path("data/resolve_accounts.log"))
    brands = load_brands()

    # ---- 手工指定 ----
    if args.set:
        idx = {b["brand"]: b for b in brands["brands"]}
        ok = 0
        for item in args.set:
            if "=" not in item:
                log(f"[WARN] 忽略格式错误：{item}")
                continue
            name, uid = item.split("=", 1)
            b = idx.get(name.strip())
            if not b:
                log(f"[WARN] brands.json 中无此品牌：{name}")
                continue
            b["uid"] = uid.strip()
            b["confirmed"] = True
            b["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ok += 1
            log(f"[SET] {b['brand']} -> uid={b['uid']} (confirmed=true)")
        save_brands(brands)
        log(f"已写入 {ok} 个品牌。")
        return 0

    # ---- 搜索解析 ----
    names = [n.strip() for n in args.brands.split(",")] if args.brands else None
    targets = [b for b in brands["brands"]
               if (names is None or b["brand"] in names) and not b.get("uid")]

    if not targets:
        log("没有待解析的品牌（uid 均已填写）。如需重解析请先清空 uid，或用 --brands 指定。")
        return 0

    banner(f"解析 {len(targets)} 个品牌的账号候选")
    client = MWeibo(cfg, cookie_file=args.cookie_file,
                    use_cookie=(False if args.no_cookie else None), log_fn=log)

    all_rows: list[dict] = []
    for i, b in enumerate(targets, 1):
        log(f"[{i}/{len(targets)}] 搜索：{b['brand']} ({b['category']})")
        rows = resolve_brand(client, b, pages=args.pages)
        log(f"    候选 {len(rows)} 个；top3：" + " | ".join(
            f"{r['screen_name']}({r['candidate_uid']},score={r['score']},粉={r['followers_count']})"
            for r in rows[:3]) if rows else "    候选 0 个")
        all_rows.extend(rows)

    out = resolve_path(cfg["paths"]["account_candidates"])
    fields = ["brand", "category", "search_term", "candidate_uid", "screen_name",
              "followers_count", "verified", "verified_type", "verified_reason", "score", "rank"]
    write_csv(out, all_rows, fields)
    log("")
    log(f"候选表已写出：{out}（{len(all_rows)} 行）")
    log(f"请求统计：{client.stats}")

    if args.apply:
        idx = {b["brand"]: b for b in brands["brands"]}
        applied = 0
        by_brand: dict[str, list[dict]] = {}
        for r in all_rows:
            by_brand.setdefault(r["brand"], []).append(r)
        for name, rows in by_brand.items():
            if not rows:
                continue
            top = rows[0]
            if top["score"] < args.min_score or not top["verified"]:
                log(f"[SKIP] {name}：top1 score={top['score']} verified={top['verified']}，未达阈值，请人工指定")
                continue
            b = idx[name]
            b["uid"] = top["candidate_uid"]
            b["account_name"] = top["screen_name"]
            b["followers"] = top["followers_count"]
            b["verified"] = bool(top["verified"])
            b["confirmed"] = False
            b["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            applied += 1
            log(f"[APPLY] {name} -> {top['screen_name']} ({top['candidate_uid']})  ※仍需人工置 confirmed=true")
        save_brands(brands)
        log(f"自动回填 {applied} 个品牌（confirmed 均为 false）。请打开 brands.json 核对后置 true。")

    log("")
    log("下一步：核对 brands.json 的 account_name，把正确的置 confirmed=true，然后运行 collect_timeline.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
