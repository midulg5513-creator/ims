# -*- coding: utf-8 -*-
"""md2docx.py —— 把论文 Markdown 转成带 Word 原生公式的 .docx

路线：Markdown → HTML（公式转 MathML）→ Word COM → .docx
说明：Word 会把 MathML 导入为原生公式（OMML），可在 Word 里直接编辑。

用法：
  python md2docx.py 输入.md 输出.html         只生成 HTML
  python md2docx.py 输入.md 输出.html --check 生成并打印统计
"""
from pathlib import Path
import argparse
import html
import re
import sys

import latex2mathml.converter as l2m

# ---------------------------------------------------------------- 公式处理
TAG_RE = re.compile(r"\\tag\{([^}]*)\}")


def _clean_aligned(tex: str):
    """把 aligned 环境拆成多行、去掉对齐符 &，返回 (行列表, tag)"""
    tag = ""
    m = TAG_RE.search(tex)
    if m:
        tag = m.group(1)
        tex = TAG_RE.sub("", tex)

    if "\\begin{aligned}" in tex:
        body = re.sub(r"\\begin\{aligned\}", "", tex)
        body = re.sub(r"\\end\{aligned\}", "", body)
        lines = [ln.strip() for ln in body.split(r"\\")]
    else:
        lines = [tex.strip()]

    out = []
    for ln in lines:
        # 去掉行首的对齐符（如 "&\ \beta_0" 或 "& +"）
        ln = re.sub(r"^&\s*", "", ln)
        ln = re.sub(r"^\\\s+", "", ln)
        ln = ln.replace("&", "")          # 去掉残留的 &
        ln = ln.strip()
        if ln:
            out.append(ln)
    return out, tag


def mathml(tex: str, display: str = "inline") -> str:
    """LaTeX → MathML。失败时退化为等宽文本，保证不中断转换。"""
    try:
        return l2m.convert(tex, display=display)
    except Exception as exc:                                   # noqa: BLE001
        return f'<code>[公式转换失败: {html.escape(tex[:40])}… {exc}]</code>'


def render_block_math(tex: str) -> str:
    """块级公式 → 居中段落；多行公式每行一段；编号放右下角。"""
    lines, tag = _clean_aligned(tex)
    if not lines:
        return ""
    parts = []
    if len(lines) == 1:
        num = f"&nbsp;&nbsp;&nbsp;&nbsp;（{tag}）" if tag else ""
        parts.append(f'<p class="eq">{mathml(lines[0], "block")}{num}</p>')
    else:
        for ln in lines:
            parts.append(f'<p class="eq">{mathml(ln, "block")}</p>')
        if tag:
            parts.append(f'<p class="eqnum">（{tag}）</p>')
    return "\n".join(parts)


# ---------------------------------------------------------------- 行内格式
CODE_RE = re.compile(r"`([^`]+)`")
INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def inline(text: str) -> str:
    """处理行内：先保护公式，再处理粗体/斜体/代码，最后转义。"""
    holds: list[str] = []

    def hold(snippet: str) -> str:
        holds.append(snippet)
        return f"\x00{len(holds) - 1}\x00"

    # 1) 行内公式
    text = INLINE_MATH_RE.sub(lambda m: hold(mathml(m.group(1), "inline")), text)
    # 2) 行内代码
    text = CODE_RE.sub(lambda m: hold(f"<code>{html.escape(m.group(1))}</code>"), text)

    # 3) 转义剩余文本
    text = html.escape(text, quote=False)

    # 4) 粗体 / 斜体
    text = BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = ITALIC_RE.sub(r"<em>\1</em>", text)

    # 5) 还原占位
    def restore(m):
        return holds[int(m.group(1))]

    return re.sub(r"\x00(\d+)\x00", restore, text)


# ---------------------------------------------------------------- 表格
def is_table_sep(line: str) -> bool:
    s = line.strip()
    return bool(s) and set(s) <= set("|-: ") and "-" in s


def split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def render_table(rows: list[str]) -> str:
    head = split_row(rows[0])
    aligns = []
    if len(rows) > 1 and is_table_sep(rows[1]):
        for c in split_row(rows[1]):
            if c.startswith(":") and c.endswith(":"):
                aligns.append("center")
            elif c.endswith(":"):
                aligns.append("right")
            else:
                aligns.append("left")
        body = rows[2:]
    else:
        aligns = ["left"] * len(head)
        body = rows[1:]

    out = ['<table border="1" cellspacing="0" cellpadding="4">']
    out.append("<thead><tr>")
    for i, c in enumerate(head):
        al = aligns[i] if i < len(aligns) else "left"
        out.append(f'<th style="text-align:{al}">{inline(c)}</th>')
    out.append("</tr></thead><tbody>")
    for r in body:
        cells = split_row(r)
        out.append("<tr>")
        for i, c in enumerate(cells):
            al = aligns[i] if i < len(aligns) else "left"
            out.append(f'<td style="text-align:{al}">{inline(c)}</td>')
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


# ---------------------------------------------------------------- 主转换
def convert(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        s = line.strip()

        # 空行
        if not s:
            i += 1
            continue

        # 分隔线
        if re.fullmatch(r"-{3,}", s):
            out.append("<hr/>")
            i += 1
            continue

        # 块级公式 $$ ... $$
        if s.startswith("$$"):
            buf = [s[2:]]
            # 同一行闭合
            if s.count("$$") >= 2 and len(s) > 4:
                tex = s[2:-2] if s.endswith("$$") else s[2:]
                out.append(render_block_math(tex))
                i += 1
                continue
            i += 1
            while i < n and "$$" not in lines[i]:
                buf.append(lines[i])
                i += 1
            if i < n:
                buf.append(lines[i].replace("$$", ""))
                i += 1
            out.append(render_block_math("\n".join(buf)))
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        # 表格
        if s.startswith("|") and i + 1 < n and is_table_sep(lines[i + 1]):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(render_table(rows))
            continue

        # 引用
        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + "<br/>".join(
                inline(b) for b in buf) + "</blockquote>")
            continue

        # 无序列表
        if re.match(r"^[-*]\s+", s):
            out.append("<ul>")
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                out.append("<li>" + inline(
                    re.sub(r"^[-*]\s+", "", lines[i].strip())) + "</li>")
                i += 1
            out.append("</ul>")
            continue

        # 有序列表
        if re.match(r"^\d+\.\s+", s):
            out.append("<ol>")
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                out.append("<li>" + inline(
                    re.sub(r"^\d+\.\s+", "", lines[i].strip())) + "</li>")
                i += 1
            out.append("</ol>")
            continue

        # 普通段落（合并连续行）
        buf = [s]
        i += 1
        while i < n:
            t = lines[i].strip()
            if (not t or t.startswith(("#", "|", ">", "$$", "---"))
                    or re.match(r"^[-*]\s+", t) or re.match(r"^\d+\.\s+", t)):
                break
            buf.append(t)
            i += 1
        out.append("<p>" + inline(" ".join(buf)) + "</p>")

    body = "\n".join(out)
    css = """
    <style>
      body { font-family: "宋体", SimSun, serif; font-size: 12pt; line-height: 1.6; }
      h1 { font-family: "黑体", SimHei, sans-serif; font-size: 18pt; text-align: center; }
      h2 { font-family: "黑体", SimHei, sans-serif; font-size: 15pt; }
      h3 { font-family: "黑体", SimHei, sans-serif; font-size: 13.5pt; }
      h4 { font-family: "楷体", KaiTi, serif; font-size: 12.5pt; }
      table { border-collapse: collapse; font-size: 10.5pt; width: 100%; }
      th { background: #f2f2f2; font-family: "黑体", SimHei, sans-serif; }
      th, td { border: 1px solid #000; padding: 3px 6px; vertical-align: top; }
      p.eq { text-align: center; margin: 8pt 0; }
      p.eqnum { text-align: right; margin: 0 0 8pt 0; }
      blockquote { margin-left: 1.5em; padding-left: .8em;
                   border-left: 3px solid #bbb; color: #333; }
      code { font-family: Consolas, monospace; font-size: 10.5pt;
             background: #f5f5f5; }
    </style>
    """
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>论文</title>{css}</head><body>{body}</body></html>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    args = ap.parse_args()

    src = Path(args.src)
    md = src.read_text(encoding="utf-8")
    doc = convert(md)
    Path(args.dst).write_text(doc, encoding="utf-8")

    n_tables = doc.count("<table")
    n_math = doc.count("<math")
    n_fail = doc.count("公式转换失败")
    print(f"[ok] {src.name} -> {args.dst}")
    print(f"     正文字符 {len(md)}   表格 {n_tables} 个   "
          f"公式 {n_math} 处   转换失败 {n_fail} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
