# -*- coding: utf-8 -*-
"""人工标注工具：分层抽样本 / 生成标注手册 / 计算 Cohen's Kappa（需求 §6 §7）。

子命令
------
python code/annotate.py sample      # 分层抽 200–300 条 -> data/annotation_sample.csv
python code/annotate.py guideline   # 生成 data/annotation_guideline.md
python code/annotate.py status      # 看两位标注者的完成度
python code/annotate.py kappa       # 计算 kappa / 逐标签 F1-Jaccard -> reports/kappa_report.md

标注列命名规则：a1_* = 标注者1，a2_* = 标注者2；争议只在 r_* 与 adjudication_* 填协商结论，
不覆盖原始编码（需求 §7）。
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    PROJECT_ROOT,
    banner,
    ensure_dirs,
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

DICT_PATH = PROJECT_ROOT / "dictionaries.json"
ANNOTATION_VERSION = "v1.0"

SINGLE = ["commercial_intent"]
MULTI = ["celebrity", "new_product", "discount", "giveaway", "livestream",
         "product_benefit", "usage_tutorial", "usage_scenario", "topic", "interaction", "call_to_action"]
EXPRESSION = ["expression_informational", "expression_emotional", "expression_interactive",
              "expression_authority", "expression_storytelling", "expression_promotional"]
RISK = ["has_evidence", "has_user_scenario", "has_exaggeration", "has_purchase_link"]

ALL_LABELS = SINGLE + MULTI + EXPRESSION + RISK

CONTEXT_FIELDS = ["sample_id", "post_id", "brand", "brand_category", "published_at", "media_type",
                  "repost_count", "comment_count", "like_count", "follower_count",
                  "text_clean", "hashtags_raw", "page_url_ori"]


def annotator_cols(k: int) -> list[str]:
    cols = [f"a{k}_annotator_id"] + [f"a{k}_{c}" for c in ALL_LABELS] + [f"a{k}_note", f"a{k}_annotation_time"]
    return cols


def reconciled_cols() -> list[str]:
    return [f"r_{c}" for c in ALL_LABELS] + ["adjudication_status", "adjudication_note", "annotation_version"]


# ------------------------------------------------------------ 抽样

def eng_bucket(v: int | None, edges: list[float]) -> str:
    if v is None:
        return "na"
    if v <= edges[0]:
        return "l1"
    if v <= edges[1]:
        return "l2"
    if v <= edges[2]:
        return "l3"
    return "l4"


def quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def cmd_sample(cfg: dict, args) -> int:
    rows = read_csv(resolve_path(cfg["paths"]["cleaned_posts"]))
    if not rows:
        log("cleaned_posts.csv 为空，请先运行 features.py")
        return 1

    n_min = int(cfg["annotation"]["pilot_size_min"])
    n_max = int(cfg["annotation"]["pilot_size_max"])
    target = args.size or min(n_max, max(n_min, int(len(rows) * 0.15)))
    target = min(target, len(rows))
    rng = random.Random(int(cfg["annotation"]["random_seed"]))

    reps = sorted((to_int(r.get("repost_count")) or 0) for r in rows)
    edges = [quantile(reps, 0.25), quantile(reps, 0.50), quantile(reps, 0.75)]

    strata: dict[tuple, list[dict]] = {}
    for r in rows:
        pub = parse_weibo_time(r.get("published_at"))
        week = f"{pub.isocalendar()[0]}-W{pub.isocalendar()[1]:02d}" if pub else "na"
        key = (r.get("brand", ""), week, r.get("media_type", ""),
               eng_bucket(to_int(r.get("repost_count")), edges))
        strata.setdefault(key, []).append(r)

    picked: list[dict] = []
    keys = sorted(strata.keys())
    rng.shuffle(keys)
    # 先把每个层至少取 1 条，保证低互动也能入样（需求 §7）
    for k in keys:
        bucket = strata[k]
        rng.shuffle(bucket)
        picked.append(bucket[0])
    # 再按比例补足
    if len(picked) < target:
        rest = [r for k in keys for r in strata[k][1:]]
        rng.shuffle(rest)
        picked.extend(rest[:target - len(picked)])
    picked = picked[:target]

    out_rows = []
    for i, r in enumerate(picked, 1):
        row = {f: r.get(f, "") for f in CONTEXT_FIELDS if f != "sample_id"}
        row["sample_id"] = i
        for k in (1, 2):
            for c in annotator_cols(k):
                row[c] = ""
        for c in reconciled_cols():
            row[c] = ""
        row["annotation_version"] = ANNOTATION_VERSION
        out_rows.append(row)

    fields = CONTEXT_FIELDS + annotator_cols(1) + annotator_cols(2) + reconciled_cols()
    out = resolve_path(cfg["paths"]["annotation_sample"])
    write_csv(out, out_rows, fields)
    banner("分层抽样完成")
    log(f"候选 {len(rows)} 条，分层键 {len(strata)} 个，抽出 {len(out_rows)} 条 -> {out}")
    log(f"分层维度：品牌 × 周 × 媒体类型 × 转发四分位（阈值 {edges}）")
    log(f"annotation_version = {ANNOTATION_VERSION}，随机种子 = {cfg['annotation']['random_seed']}")
    log("")
    log("下一步：两位标注者各自在 Excel 里填 a1_* / a2_* 列（不要互相看），再运行 kappa")
    return 0


# ------------------------------------------------------------ 手册

GUIDELINE = """# 标注手册（{ver}）

> 生成时间：{ts}　词典版本：{dict_ver}
> 判断整条帖子，**不能依据单个关键词**（需求 §6.4）。

## 一、可选标签与其边界

### 1. 商业意图（单选，`commercial_intent`）
| 值 | 含义 | 判据要点 |
|---|---|---|
| 0 | 非商业内容 | 无品牌方推广意图，纯资讯/互动/祝福 |
| 1 | 软性种草 | 有推荐/体验，但**没有**明确购买动作或价格 |
| 2 | 明确促销或转化 | 有折扣/价格/链接/下单/抢购等转化导向 |
| 3 | 品牌公关或品牌形象 | 品牌故事/公益/代言官宣，不以即时转化为目的 |
| 4 | 无法判断 | 信息不足或自相矛盾 |

### 2. 营销策略（多选，0/1）
`celebrity` 明星或代言 · `new_product` 新品发布 · `discount` 折扣/优惠/赠品 · `giveaway` 抽奖或有奖转发 ·
`livestream` 直播或直播引流 · `product_benefit` 功效/成分/参数 · `usage_tutorial` 使用教程 ·
`usage_scenario` 使用场景 · `topic` 话题或挑战 · `interaction` 提问/征集/粉丝互动 · `call_to_action` 购买/点击/评论/转发引导

### 3. 表达方式（多选，0/1）
`expression_informational` 信息说明 · `expression_emotional` 情绪感染 · `expression_interactive` 互动对话 ·
`expression_authority` 专业或证据 · `expression_storytelling` 故事或场景 · `expression_promotional` 促销

### 4. 可信度与风险（0/1）
`has_evidence` 有检测报告/成分表/资质等证据 · `has_user_scenario` 有真实使用场景 ·
`has_exaggeration` 有夸大或绝对化表述（如"立刻见效""永久"）· `has_purchase_link` 含可购买链接

## 二、流程（需求 §7）

1. 先抽 200–300 条，**两名标注者独立试标**（互不可见）。
2. 商业意图算 **Cohen's Kappa**；多标签算**逐标签 F1 或 Jaccard**。
3. Kappa **< 0.60** → 先修订定义再重标；**0.60–0.75** → 记录边界规则；**> 0.75** → 扩大标注。
4. 正式样本 **10%–15%** 进行双人复核。
5. 保存 `annotator_id`、`annotation_time`、`adjudication_status`、`annotation_version`。

## 三、填写规则

- 单选列填 `0`–`4`；多选与风险列统一填 `0`/`1`；不确定的填 `9` 并在 `a*_note` 写原因。
- 分歧只在 `r_*` 与 `adjudication_*` 填**协商结论**，**不要覆盖** `a1_*`/`a2_*` 原始编码。
- `adjudication_status` 取值：`pending` / `agreed` / `resolved` / `unresolved`。

## 四、常见边界（与旧试标集一致）

- **普通用户体验帖**：若研究"品牌官方广告"，应排除或单独记录账号类型；本研究只收品牌官方账号帖。
- **转发链**：品牌账号转发他人内容时，`is_original=0`，`parent_post_id` 非空。
- **强功效表述**（"补水神器""第二天痘痘就瘪掉"）：`has_exaggeration=1`，不与普通功效说明混同。
- **抽奖帖**：即使文案简短，只要规则含"转发+抽奖/有奖"即 `giveaway=1`，且商业意图多为 2。

## 五、词典参考（自动特征，仅供辅助判断）

自动特征由 `dictionaries.json`（{dict_ver}）生成，见 `cleaned_posts.csv` 的 `has_*` / `n_*` 列。
**自动特征不是标签**，人工标签需以整条帖子的意图为准。
"""


def cmd_guideline(cfg: dict, args) -> int:
    import json as _json
    d = _json.loads(DICT_PATH.read_text(encoding="utf-8"))
    text = GUIDELINE.format(ver=ANNOTATION_VERSION,
                            ts=datetime.now().strftime("%Y-%m-%d %H:%M"),
                            dict_ver=d.get("version", "?"))
    out = resolve_path(cfg["paths"]["annotation_guideline"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    log(f"标注手册已生成：{out}")
    return 0


# ------------------------------------------------------------ 状态 / Kappa

def _filled(v) -> bool:
    return v is not None and str(v).strip() != ""


def cmd_status(cfg: dict, args) -> int:
    rows = read_csv(resolve_path(cfg["paths"]["annotation_sample"]))
    if not rows:
        log("annotation_sample.csv 为空，请先运行 sample")
        return 1
    n = len(rows)
    banner(f"标注进度（样本 {n} 条）")
    for k in (1, 2):
        c = sum(1 for r in rows if _filled(r.get(f"a{k}_commercial_intent")))
        log(f"  标注者{k}：{c}/{n} ({c/n*100:.1f}%)")
    both = sum(1 for r in rows if _filled(r.get("a1_commercial_intent")) and _filled(r.get("a2_commercial_intent")))
    log(f"  双人已完成（可算 kappa）：{both}/{n}")
    adj = sum(1 for r in rows if _filled(r.get("adjudication_status")))
    log(f"  已裁决：{adj}/{n}")
    return 0


def cohen_kappa(pairs: list[tuple[str, str]]) -> tuple[float, float]:
    """返回 (kappa, 观察一致率)。"""
    if not pairs:
        return float("nan"), float("nan")
    n = len(pairs)
    agree = sum(1 for a, b in pairs if a == b)
    po = agree / n
    cats = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    pe = 0.0
    for c in cats:
        pa = sum(1 for a, _ in pairs if a == c) / n
        pb = sum(1 for _, b in pairs if b == c) / n
        pe += pa * pb
    kappa = (po - pe) / (1 - pe) if abs(1 - pe) > 1e-12 else float("nan")
    return kappa, po


def jaccard_f1(pairs: list[tuple[bool, bool]]) -> tuple[float, float, float]:
    tp = sum(1 for a, b in pairs if a and b)
    fp = sum(1 for a, b in pairs if a and not b)
    fn = sum(1 for a, b in pairs if b and not a)
    union = tp + fp + fn
    jac = tp / union if union else float("nan")
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    rec = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = (2 * prec * rec / (prec + rec)) if (prec and rec and not math.isnan(prec) and not math.isnan(rec)
                                              and (prec + rec) > 0) else float("nan")
    return jac, f1, rec


def cmd_kappa(cfg: dict, args) -> int:
    rows = read_csv(resolve_path(cfg["paths"]["annotation_sample"]))
    if not rows:
        log("annotation_sample.csv 为空，请先运行 sample")
        return 1
    banner("一致性检验（Cohen's Kappa / 逐标签 Jaccard-F1）")
    lines = [f"# 标注一致性报告（{ANNOTATION_VERSION}）", "",
             f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　样本：{len(rows)} 条", ""]

    # 商业意图（单选）
    pairs = [(str(r.get("a1_commercial_intent", "")).strip(), str(r.get("a2_commercial_intent", "")).strip())
             for r in rows
             if _filled(r.get("a1_commercial_intent")) and _filled(r.get("a2_commercial_intent"))]
    if pairs:
        k, po = cohen_kappa(pairs)
        verdict = ("可扩大标注（>0.75）" if k > 0.75 else
                   "记录边界规则（0.60–0.75）" if k >= 0.60 else "先修订定义（<0.60）")
        log(f"商业意图：n={len(pairs)}  一致率={po:.3f}  Kappa={k:.3f}  → {verdict}")
        lines += ["## 商业意图（单选）", "",
                  f"- 双人完成：{len(pairs)} 条",
                  f"- 观察一致率：{po:.4f}",
                  f"- **Cohen's Kappa：{k:.4f}**",
                  f"- 判定：**{verdict}**", ""]
    else:
        log("商业意图：暂无双人完成数据")
        lines += ["## 商业意图（单选）", "", "- 暂无双人完成数据", ""]

    # 多标签 + 表达 + 风险
    lines += ["## 逐标签一致性（多标签）", "", "| 标签 | 双人完成 | Jaccard | F1 | 召回 | 支持数 |",
              "|---|---:|---:|---:|---:|---:|"]
    for c in MULTI + EXPRESSION + RISK:
        prs = [(str(r.get(f"a1_{c}", "")).strip() in ("1", "1.0", "True"),
                str(r.get(f"a2_{c}", "")).strip() in ("1", "1.0", "True"))
               for r in rows if _filled(r.get(f"a1_{c}")) and _filled(r.get(f"a2_{c}"))]
        if not prs:
            lines.append(f"| {c} | 0 | – | – | – | – |")
            continue
        jac, f1, rec = jaccard_f1(prs)
        sup = sum(1 for a, _ in prs if a)
        lines.append(f"| {c} | {len(prs)} | {jac:.3f} | {f1:.3f} | {rec:.3f} | {sup} |")
        log(f"  {c:<24} n={len(prs):<4} Jaccard={jac:.3f} F1={f1:.3f}")

    out = resolve_path("reports/kappa_report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("")
    log(f"报告已写出：{out}")
    log("判定阈值（需求 §7）：<0.60 修订定义；0.60–0.75 记录边界规则；>0.75 扩大标注")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="人工标注工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("sample"); p1.add_argument("--size", type=int, help="抽样条数")
    sub.add_parser("guideline")
    sub.add_parser("status")
    sub.add_parser("kappa")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    open_log(resolve_path("data/annotate.log"))

    if args.cmd == "sample":
        return cmd_sample(cfg, args)
    if args.cmd == "guideline":
        return cmd_guideline(cfg, args)
    if args.cmd == "status":
        return cmd_status(cfg, args)
    if args.cmd == "kappa":
        return cmd_kappa(cfg, args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
