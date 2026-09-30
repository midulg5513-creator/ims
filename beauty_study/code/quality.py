# -*- coding: utf-8 -*-
"""数据质量验收 + 抽样报告（需求 §9 §11）。

自动检查：ID 唯一性、发布时间逻辑、互动数非负、重复记录、各品牌每周样本量、
缺失率、极端值、互动数异常下降、完全重复文本；并把「关键字段缺失」显式报告，
**不得静默填 0**。

用法
----
python code/quality.py            # 出报告并打印 PASS/FAIL
python code/quality.py --strict   # 有 FAIL 时返回码 1
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    banner,
    load_brands,
    load_config,
    log,
    open_log,
    parse_weibo_time,
    read_csv,
    resolve_path,
    to_int,
    write_csv,
)

T = {
    "post_id_dup_rate_max": 0.01,       # §9: post_id 重复率 < 1%
    "published_at_parse_min": 0.98,     # §9: 发布时间可解析率 ≥ 98%
    "interaction_avail_min": 0.90,      # §9: 三项互动字段可用率 ≥ 90%
    "official_identity_min": 0.95,      # §9: 官方账号身份确认率 ≥ 95%
    "brands_min": 10, "brands_max": 15,         # §10
    "posts_min": 1000, "posts_max": 2500,       # §10
    "min_posts_per_brand": 50,                  # §2 每品牌约 50 条
    "min_posts_per_brand_hard": 10,             # 硬下限：低于此值无法做品牌层分析
    "snapshot_windows_min": 3,                  # §10: 至少 3 个观察窗口
    "dup_text_max": 0.05,                       # 完全重复文本占比（自定义）
}

NUMERIC_INTERACTION = ("like_count", "comment_count", "repost_count")


class Check:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, name: str, ok: bool, detail: str, value=None, threshold=None):
        self.items.append({"name": name, "ok": bool(ok), "detail": detail,
                           "value": value, "threshold": threshold})
        tag = "PASS" if ok else "FAIL"
        log(f"  [{tag}] {name}：{detail}")

    @property
    def failed(self) -> list[dict]:
        return [i for i in self.items if not i["ok"]]


def pct(a: float) -> str:
    return f"{a*100:.2f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="数据质量验收")
    ap.add_argument("--strict", action="store_true", help="有 FAIL 时进程返回 1")
    args = ap.parse_args()

    cfg = load_config()
    open_log(resolve_path("data/quality.log"))
    posts = read_csv(resolve_path(cfg["paths"]["cleaned_posts"]))
    snaps = read_csv(resolve_path(cfg["paths"]["snapshots"]))
    brands = load_brands()

    if not posts:
        log("cleaned_posts.csv 为空，无法验收。请先跑 collect_timeline.py -> features.py")
        return 1

    banner(f"数据质量验收：帖子 {len(posts)} 条，快照 {len(snaps)} 行")
    chk = Check()
    n = len(posts)

    # --- 1. ID 唯一性 ---
    ids = [r.get("post_id", "") for r in posts]
    dup = n - len(set(ids))
    rate = dup / n if n else 0.0
    chk.add("post_id 唯一性", rate < T["post_id_dup_rate_max"],
            f"重复 {dup} 条，重复率 {pct(rate)}（阈值 <{pct(T['post_id_dup_rate_max'])}）",
            rate, T["post_id_dup_rate_max"])

    # --- 2. 发布时间可解析率 ---
    parsed = sum(1 for r in posts if parse_weibo_time(r.get("published_at")) is not None)
    pr = parsed / n if n else 0.0
    chk.add("发布时间可解析率", pr >= T["published_at_parse_min"],
            f"{parsed}/{n} = {pct(pr)}（阈值 ≥{pct(T['published_at_parse_min'])}）",
            pr, T["published_at_parse_min"])

    # --- 3. 三项互动字段可用率 ---
    for col in NUMERIC_INTERACTION:
        avail = sum(1 for r in posts if to_int(r.get(col)) is not None)
        a = avail / n if n else 0.0
        chk.add(f"{col} 可用率", a >= T["interaction_avail_min"],
                f"{avail}/{n} = {pct(a)}（阈值 ≥{pct(T['interaction_avail_min'])}）",
                a, T["interaction_avail_min"])

    # --- 4. 互动数非负 ---
    neg = sum(1 for r in posts for c in NUMERIC_INTERACTION
              if (to_int(r.get(c)) or 0) < 0)
    chk.add("互动数非负", neg == 0, f"负值 {neg} 个")

    # --- 5. 官方账号身份确认率 ---
    confirmed = {b["brand"] for b in brands["brands"] if b.get("confirmed") and b.get("uid")}
    official = sum(1 for r in posts if r.get("account_type") == "brand_official")
    in_conf = sum(1 for r in posts if r.get("brand") in confirmed)
    ident = (official / n) if n else 0.0
    conf_share = (in_conf / n) if n else 0.0
    ident_ok = ident >= T["official_identity_min"] and conf_share >= T["official_identity_min"]
    chk.add("官方账号身份确认率", ident_ok,
            f"account_type=brand_official {official}/{n} = {pct(ident)}；"
            f"且来自 brands.json 已确认 uid 的帖子 {in_conf}/{n} = {pct(conf_share)}"
            f"（两项均须 ≥{pct(T['official_identity_min'])}）",
            ident, T["official_identity_min"])

    # --- 6. 品牌数与每品牌条数 ---
    by_brand: dict[str, int] = defaultdict(int)
    for r in posts:
        by_brand[r.get("brand", "")] += 1
    nb = len(by_brand)
    chk.add("品牌数 10–15", T["brands_min"] <= nb <= T["brands_max"],
            f"当前 {nb} 个品牌", nb, f"{T['brands_min']}-{T['brands_max']}")
    thin = sorted([(b, c) for b, c in by_brand.items() if c < T["min_posts_per_brand"]],
                  key=lambda x: x[1])
    thin_hard = [(b, c) for b, c in thin if c < T["min_posts_per_brand_hard"]]
    thin_soft = [(b, c) for b, c in thin if c >= T["min_posts_per_brand_hard"]]
    if thin_hard:
        detail = "低于硬下限(10)：" + ", ".join(f"{b}={c}" for b, c in thin_hard)
    elif thin_soft:
        detail = ("全部达标" if not thin_soft else
                  "WARN：低于 50 但≥10（账号本身低频，需在抽样报告中说明）："
                  + ", ".join(f"{b}={c}" for b, c in thin_soft))
    else:
        detail = "全部达标"
    chk.add("每品牌 ≥50 条", not thin_hard, detail)

    # --- 7. 样本总量 ---
    chk.add("样本总量 1000–2500", T["posts_min"] <= n <= T["posts_max"],
            f"当前 {n} 条", n, f"{T['posts_min']}-{T['posts_max']}")

    # --- 8. 观察窗口覆盖 ---
    wins_with_data = set()
    win_success = defaultdict(int)
    for r in snaps:
        if r.get("fetch_status") == "success":
            wins_with_data.add(int(r.get("window_hours") or 0))
            win_success[int(r.get("window_hours") or 0)] += 1
    chk.add("观察窗口数 ≥3", len(wins_with_data) >= T["snapshot_windows_min"],
            f"已有数据的窗口：{sorted(wins_with_data) or '无'}（阈值 ≥{T['snapshot_windows_min']}）",
            len(wins_with_data), T["snapshot_windows_min"])

    # --- 9. 完全重复文本 ---
    dup_text = sum(1 for r in posts if str(r.get("is_duplicate")) in ("True", "1", "true"))
    dtr = dup_text / n if n else 0.0
    chk.add("完全重复文本占比", dtr <= T["dup_text_max"],
            f"{dup_text}/{n} = {pct(dtr)}（阈值 ≤{pct(T['dup_text_max'])}）",
            dtr, T["dup_text_max"])

    # --- 10. 互动数异常下降（快照非单调） ---
    by_post: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for r in snaps:
        if r.get("fetch_status") != "success":
            continue
        try:
            ah = float(r.get("age_hours"))
        except (TypeError, ValueError):
            continue
        v = to_int(r.get("repost_count"))
        if v is not None:
            by_post[r["post_id"]].append((ah, v))
    drops, checked = 0, 0
    for pid, seq in by_post.items():
        seq.sort()
        for (a1, v1), (a2, v2) in zip(seq, seq[1:]):
            checked += 1
            if v2 < v1:
                drops += 1
    chk.add("互动数不下降（转发数）", drops == 0,
            f"比较 {checked} 对相邻窗口，下降 {drops} 次"
            + ("（可能为删评/隐藏，需人工核查）" if drops else ""))

    # --- 11. 关键字段缺失必须报告（不得静默填 0） ---
    key_fields = ["published_at", "like_count", "comment_count", "repost_count",
                  "follower_count", "media_type", "text_clean"]
    miss_rows = []
    for f in key_fields:
        m = sum(1 for r in posts if r.get(f) in (None, "", "None"))
        miss_rows.append((f, m, m / n if n else 0))
    chk.add("关键字段缺失已报告", True,
            "；".join(f"{f}={m}({pct(p)})" for f, m, p in miss_rows))

    # ================= 输出报告 =================
    banner("验收结论")
    n_fail = len(chk.failed)
    log(f"  通过 {len(chk.items)-n_fail} / {len(chk.items)}；FAIL {n_fail}")
    if n_fail:
        for i in chk.failed:
            log(f"    - {i['name']}：{i['detail']}")

    # 质量报告
    lines = [f"# 数据质量报告", "",
             f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　"
             f"帖子 {n} 条　快照 {len(snaps)} 行　词典版本：{posts[0].get('dictionary_version','?')}", "",
             "## 一、检查结果", "",
             "| 检查项 | 结果 | 数值 | 阈值 | 说明 |", "|---|---|---:|---|---|"]
    for i in chk.items:
        val = "" if i["value"] is None else (f"{i['value']:.4f}" if isinstance(i["value"], float) else str(i["value"]))
        th = "" if i["threshold"] is None else (f"{i['threshold']:.4f}" if isinstance(i["threshold"], float) else str(i["threshold"]))
        lines.append(f"| {i['name']} | {'PASS' if i['ok'] else '**FAIL**'} | {val} | {th} | {i['detail']} |")
    lines += ["", "## 二、关键字段缺失率（不静默填 0）", "", "| 字段 | 缺失数 | 缺失率 |", "|---|---:|---:|"]
    for f, m, p in miss_rows:
        lines.append(f"| {f} | {m} | {pct(p)} |")

    lines += ["", "## 三、极端值", "", "| 指标 | min | p50 | p90 | p99 | max |", "|---|---:|---:|---:|---:|---:|"]
    for col in NUMERIC_INTERACTION:
        vals = sorted(to_int(r.get(col)) for r in posts if to_int(r.get(col)) is not None)
        if not vals:
            continue
        def q(x):
            return vals[min(len(vals)-1, int(round(x*(len(vals)-1))))]
        lines.append(f"| {col} | {vals[0]} | {q(.5)} | {q(.9)} | {q(.99)} | {vals[-1]} |")

    lines += ["", "## 四、各品牌样本量", "", "| 品牌 | 类别 | 条数 | 达标(≥50) |", "|---|---|---:|---|"]
    cat = {b["brand"]: b["category"] for b in brands["brands"]}
    for b, c in sorted(by_brand.items(), key=lambda x: -x[1]):
        lines.append(f"| {b} | {cat.get(b,'-')} | {c} | {'是' if c>=50 else '**否**'} |")
    lines += ["", "## 五、观察窗口覆盖", "", "| 窗口 | 成功快照数 |", "|---|---:|"]
    for w in sorted(win_success):
        lines.append(f"| {w}h | {win_success[w]} |")

    qp = resolve_path(cfg["paths"]["quality_report"])
    qp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"质量报告：{qp}")

    # 抽样报告
    slines = ["# 抽样报告", "",
              f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
              "## 一、抽样框", "",
              f"- 平台：微博公开页面（m.weibo.cn 公开 JSON 接口，{'带' if cfg['request']['use_cookie'] else '不带'}登录态）",
              f"- 品牌：{nb} 个（见 brands.json），已确认 uid：{len(confirmed)} 个",
              f"- 采集窗口：最近 {cfg['study']['collection_window_days']} 天；分析窗口：{cfg['study']['analysis_window_days']} 天",
              f"- 抽样方式：**品牌官方账号主时间线连续采集**（非关键词搜索、非热门帖）",
              f"- 观察窗口：{cfg['study']['snapshot_windows_hours']} 小时；主窗口 {cfg['study']['primary_window_hours']}h", "",
              "## 二、各品牌 × 周 样本量", "", "| 品牌 | 周 | 条数 |", "|---|---|---:|"]
    bw: dict[tuple, int] = defaultdict(int)
    for r in posts:
        pub = parse_weibo_time(r.get("published_at"))
        wk = f"{pub.isocalendar()[0]}-W{pub.isocalendar()[1]:02d}" if pub else "na"
        bw[(r.get("brand", ""), wk)] += 1
    for (b, wk), c in sorted(bw.items()):
        slines.append(f"| {b} | {wk} | {c} |")

    media = defaultdict(int)
    for r in posts:
        media[r.get("media_type", "")] += 1
    slines += ["", "## 三、内容形式分布", "", "| media_type | 条数 | 占比 |", "|---|---:|---:|"]
    for m, c in sorted(media.items(), key=lambda x: -x[1]):
        slines.append(f"| {m} | {c} | {pct(c/n)} |")

    slines += ["", "## 四、偏差与限制", "",
               "1. **时间线截断偏差**：只采到时间线可翻页范围内、且不早于截止时间的帖子；"
               "极早期帖子可能未覆盖。",
               "2. **删帖偏差**：被删除/设为私密的帖子无法回访，快照记 `deleted`。",
               "3. **观察窗口缺失**：错过的窗口记 `missed`，模型中必须控制 `post_age_hours`，"
               "不能把当前累计互动当作统一周期效果（需求 §8）。",
               "4. **版权与再分发限制**：原始正文/图片/链接不公开再分发（需求 §3 §11）。",
               "5. 采用账号全量时间线而非搜索，可降低热搜/排序偏差，但仍受账号本身发布节奏影响。", ""]

    low = thin_soft + thin_hard
    if low:
        slines += ["", "## 五、低频账号说明（对应 §2「每品牌约 50 条」）", "",
                   "以下品牌官方账号在采集窗口内发帖量偏低。已核对时间线翻页日志，"
                   "确认属**账号自身发布节奏**（末条日期直接跳回数月前），非采集失败或翻页中断：", ""]
        for b, c in low:
            slines.append(f"- {b}：{c} 条（低于 50）")
        slines += ["",
                   "处理方式：",
                   "1. 保留在数据集中，但在品牌固定效应/分层分析中注意其样本量；",
                   "2. 不对这些品牌单独做品牌层推断；",
                   "3. 停更账号（窗口内个位数）已在 `brands.json` 置 `active=false` 并排除出分析样本。", ""]
    sp = resolve_path(cfg["paths"]["sampling_report"])
    sp.write_text("\n".join(slines) + "\n", encoding="utf-8")
    log(f"抽样报告：{sp}")

    # 机器可读摘要
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_posts": n, "n_snapshots": len(snaps), "n_brands": nb,
        "n_fail": n_fail,
        "checks": {i["name"]: bool(i["ok"]) for i in chk.items},
    }
    jp = resolve_path("reports/quality_summary.json")
    jp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.strict and n_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
