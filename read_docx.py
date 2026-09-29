# -*- coding: utf-8 -*-
"""从 .docx 提取纯文本（仅用标准库，不依赖 python-docx）。

用法：
    python read_docx.py <输入.docx> [输出.txt]
"""

import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_text(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "word/document.xml" not in names:
            raise ValueError("不是有效的 .docx（缺少 word/document.xml）")
        xml = z.read("word/document.xml")

    root = ET.fromstring(xml)
    lines = []

    for node in root.iter():
        tag = node.tag
        if tag == W + "p":
            # 段落：拼接所有文本 run，制表符/换行符单独处理
            parts = []
            for child in node.iter():
                if child.tag == W + "t":
                    parts.append(child.text or "")
                elif child.tag == W + "tab":
                    parts.append("\t")
                elif child.tag in (W + "br", W + "cr"):
                    parts.append("\n")
            line = "".join(parts).rstrip()
            lines.append(line)
        elif tag == W + "tbl":
            # 表格：在后面统一由 p 节点产出，这里只做标记
            lines.append("")

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else None

    text = extract_text(src)
    if dst:
        with open(dst, "w", encoding="utf-8") as f:
            f.write(text)
        print("[v] 已提取 {} 字符 -> {}".format(len(text), dst))
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
