# -*- coding: utf-8 -*-
"""共享工具：路径、配置、日志、时间解析、限速与每日请求预算、CSV/JSONL、哈希。

所有脚本都从这里取基础设施，保证口径一致。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------- 路径

CODE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_DIR.parent          # beauty_study/
CONFIG_PATH = PROJECT_ROOT / "config.json"
BRANDS_PATH = PROJECT_ROOT / "brands.json"

CN_TZ = timezone(timedelta(hours=8))    # 微博显示时间为北京时间

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_WEEKDAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}

_LOG_LOCK = threading.Lock()
_LOG_FILE: Path | None = None


# ---------------------------------------------------------------- 配置

def load_config(path: Path | str | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    with open(p, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["_root"] = str(PROJECT_ROOT)
    return cfg


def load_brands(path: Path | str | None = None) -> dict:
    p = Path(path) if path else BRANDS_PATH
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_brands(data: dict, path: Path | str | None = None) -> None:
    """原子写回 brands.json（先写临时文件再替换），避免中断损坏。"""
    p = Path(path) if path else BRANDS_PATH
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)


def resolve_path(rel: str) -> Path:
    """把 config 中的相对路径解析为 beauty_study 下的绝对路径。"""
    p = Path(rel)
    return p if p.is_absolute() else PROJECT_ROOT / p


def ensure_dirs(cfg: dict) -> None:
    for key in ("raw",):
        resolve_path(cfg["paths"][key]).mkdir(parents=True, exist_ok=True)
    for key in ("cleaned_posts", "snapshots", "annotation_sample", "annotation_guideline",
                "quality_report", "sampling_report"):
        resolve_path(cfg["paths"][key]).parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- 日志

def open_log(rel_or_abs: str | Path) -> Path:
    global _LOG_FILE
    p = Path(rel_or_abs)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    _LOG_FILE = p
    return p


def log(msg: str = "", also_print: bool = True) -> None:
    line = msg
    with _LOG_LOCK:
        if also_print:
            try:
                print(line, flush=True)
            except UnicodeEncodeError:
                # 控制台为 GBK 等窄编码时，把不可编码字符换成 '?' 再打印
                enc = getattr(sys.stdout, "encoding", None) or "ascii"
                print(line.encode(enc, "replace").decode(enc, "replace"), flush=True)
        if _LOG_FILE is not None:
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def banner(title: str) -> None:
    log("")
    log("=" * 72)
    log(f"  {title}")
    log("=" * 72)


# ---------------------------------------------------------------- 时间

def parse_weibo_time(s: Any) -> datetime | None:
    """解析微博时间。支持绝对格式与相对格式，返回带北京时区的 datetime。"""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()

    # 绝对格式：Wed Sep 24 12:34:56 +0800 2026
    m = re.match(
        r"^([A-Za-z]{3})\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})\s+([+-]\d{4})\s+(\d{4})$",
        s,
    )
    if m:
        _wd, mon, day, hh, mm, ss, tz, year = m.groups()
        if mon in _MONTHS:
            off_h = int(tz[1:3])
            off_m = int(tz[3:5])
            sign = 1 if tz[0] == "+" else -1
            tzinfo = timezone(sign * timedelta(hours=off_h, minutes=off_m))
            try:
                return datetime(int(year), _MONTHS[mon], int(day), int(hh), int(mm), int(ss), tzinfo=tzinfo)
            except ValueError:
                return None

    # ISO 8601（本项目自己写出的 published_at / snapshot_at / target_at）
    m = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(Z|[+-]\d{2}:?\d{2})?$", s)
    if m:
        y, mo, d, hh, mi, ss, tzs = m.groups()
        if tzs in (None, "Z"):
            tzinfo = timezone.utc
        else:
            tz2 = tzs.replace(":", "")
            sign = 1 if tz2[0] == "+" else -1
            tzinfo = timezone(sign * timedelta(hours=int(tz2[1:3]), minutes=int(tz2[3:5])))
        try:
            return datetime(int(y), int(mo), int(d), int(hh), int(mi), int(ss or 0), tzinfo=tzinfo)
        except ValueError:
            return None

    now = datetime.now(CN_TZ)
    if s in ("刚刚", "just now"):
        return now
    m = re.match(r"^(\d+)\s*秒前$", s)
    if m:
        return now - timedelta(seconds=int(m.group(1)))
    m = re.match(r"^(\d+)\s*分钟前$", s)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = re.match(r"^(\d+)\s*小时前$", s)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.match(r"^今天\s*(\d{1,2}):(\d{2})$", s)
    if m:
        return now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    m = re.match(r"^昨天\s*(\d{1,2}):(\d{2})$", s)
    if m:
        d = now - timedelta(days=1)
        return d.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    m = re.match(r"^(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$", s)
    if m:
        try:
            return datetime(now.year, int(m.group(1)), int(m.group(2)),
                            int(m.group(3)), int(m.group(4)), tzinfo=CN_TZ)
        except ValueError:
            return None
    return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_hours(published: datetime, at: datetime) -> float:
    return round((at - published).total_seconds() / 3600.0, 4)


# ---------------------------------------------------------------- 数值/文本

_NUM_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(万|亿)?$")


def to_int(v: Any) -> int | None:
    """把 '1.2万' / '931.2万' / 1234 / '1234' 还原为整数。"""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "").replace("+", "")
    m = _NUM_RE.match(s)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        num *= 10_000
    elif unit == "亿":
        num *= 100_000_000
    return int(round(num))


_TAG_RE = re.compile(r"#([^#\[\]]{1,40}?)#")
_MENTION_RE = re.compile(r"@([A-Za-z0-9\u4e00-\u9fa5_\-]{1,30})")
_URL_RE = re.compile(r"https?://[^\s\u4e00-\u9fa5，。！？；：\"'）】]+")


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'")):
        s = s.replace(a, b)
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def extract_hashtags(text: str | None) -> list[str]:
    if not text:
        return []
    return [t.strip() for t in _TAG_RE.findall(text)]


def count_mentions(text: str | None) -> int:
    if not text:
        return 0
    return len(set(_MENTION_RE.findall(text)))


def extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    return _URL_RE.findall(text)


def sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()


def author_hash(uid: Any) -> str:
    """作者标识的本地不可逆哈希（需求 §3）。"""
    return sha1_hex(f"weibo-uid:{uid}")


def text_fingerprint(text_clean: str) -> str:
    """文本指纹，用于完全重复文本检测（需求 §9）。"""
    norm = re.sub(r"\s+", "", text_clean or "")
    return sha1_hex(norm)


# ---------------------------------------------------------------- 存储

def read_jsonl(path: Path | str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_jsonl(path: Path | str, rows: Iterable[dict]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(p, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_csv(path: Path | str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path | str, rows: list[dict], fieldnames: list[str] | None = None,
              bom: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    enc = "utf-8-sig" if bom else "utf-8"
    with open(p, "w", encoding=enc, newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})


# ---------------------------------------------------------------- 限速 / 预算

class RequestBudget:
    """每日请求上限，按 UTC 日期持久化到 data/raw_snapshots/_request_budget.json。"""

    def __init__(self, cfg: dict):
        self.limit = int(cfg["request"]["daily_request_limit"])
        self.path = resolve_path(cfg["paths"]["raw"]) / "_request_budget.json"
        self._lock = threading.Lock()
        self._date, self._count = self._load()

    def _load(self) -> tuple[str, int]:
        today = now_utc().strftime("%Y-%m-%d")
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                if d.get("date") == today:
                    return today, int(d.get("count", 0))
            except Exception:
                pass
        return today, 0

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"date": self._date, "count": self._count, "limit": self.limit}),
            encoding="utf-8")

    def remaining(self) -> int:
        with self._lock:
            self._rollover()
            return max(0, self.limit - self._count)

    def _rollover(self) -> None:
        today = now_utc().strftime("%Y-%m-%d")
        if today != self._date:
            self._date, self._count = today, 0

    def take(self, n: int = 1) -> bool:
        """申请 n 次额度。成功返回 True 并记账，否则 False。"""
        with self._lock:
            self._rollover()
            if self._count + n > self.limit:
                return False
            self._count += n
            self._flush()
            return True


class RateLimiter:
    """请求间隔 + 抖动，满足需求 §3「设置请求间隔」。"""

    def __init__(self, cfg: dict):
        r = cfg["request"]
        self.delay = float(r.get("delay_seconds", 3.0))
        self.jitter = float(r.get("jitter_seconds", 0.0))
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            gap = self.delay + random.uniform(0, self.jitter)
            sleep_for = self._last + gap - now
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last = time.monotonic()


# ---------------------------------------------------------------- 通用小工具

def progress(i: int, n: int, every: int = 1) -> bool:
    return i % max(1, every) == 0 or i == n


def dedup_by(rows: Iterable[dict], key: str) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = r.get(key)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def green(t: str) -> str:
    return f"[OK] {t}"


def red(t: str) -> str:
    return f"[!!] {t}"


def warn(t: str) -> str:
    return f"[??] {t}"
