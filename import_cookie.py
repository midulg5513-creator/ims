# -*- coding: utf-8 -*-
"""从你粘贴的 cURL 命令 / cookie 字符串中提取 cookie，写入 weiboSpider/config.json。

为什么需要它：
    Chrome 127+ 启用了 App-Bound Encryption(v20)，browser_cookie3 等第三方库
    无法解密，所以只能从开发者工具手动复制。本脚本负责把复制的内容解析成
    规范的 cookie 字符串并安全地写进 config.json，避免手工编辑超长 JSON 出错。

安全说明：绝不打印 cookie 的值，只打印长度和 cookie 名字。

用法（在 d:\\AI\\爬虫 目录下）：
    1) 先用记事本把复制的内容存成 cookie.txt（本目录下）
    2) 运行：.\\weiboSpider\\venv\\Scripts\\python.exe import_cookie.py

支持三种粘贴格式（自动识别）：
    A. 完整 cURL 命令  —— DevTools「复制 -> 以 cURL (bash) 格式复制」
    B. 只有 cookie 头那一行，例如：cookie: SUB=_2A25...; SUBP=...
    C. 纯 cookie 字符串，例如：SUB=_2A25...; SUBP=...
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "weiboSpider", "config.json")
INPUT_CANDIDATES = [
    os.path.join(HERE, "cookie.txt"),
    os.path.join(HERE, "cookie"),
]

# 判断登录态的关键 cookie
REQUIRED_HINT = "SUB"


def find_input_file():
    for p in INPUT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def extract_cookie(text):
    """从各种格式中抽出 cookie 字符串；返回 (cookie或None, 命中的格式说明)。"""
    text = text.strip().lstrip("\ufeff")

    # A. cURL 形式： -H 'cookie: xxx'   或   -H "cookie: xxx"
    patterns = [
        r"-H\s+'cookie:\s*([^']*)'",
        r'-H\s+"cookie:\s*([^"]*)"',
        r"--header\s+'cookie:\s*([^']*)'",
        r'--header\s+"cookie:\s*([^"]*)"',
        # 少数 Chrome 版本把 cookie 放在 -b/--cookie 参数里
        r"-b\s+'([^']*)'",
        r'-b\s+"([^"]*)"',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            return normalize(m.group(1)), "cURL 命令（-H cookie）"

    # 兼容 Windows cmd / PowerShell 里的引号换行续行
    m = re.search(r"cookie:\s*([^'\"\r\n]*)", text, re.IGNORECASE)
    if m and "=" in m.group(1):
        return normalize(m.group(1)), "cookie 头那一行"

    # C. 纯 cookie 字符串
    if "=" in text:
        return normalize(text), "纯 cookie 字符串"

    return None, None


def normalize(cookie):
    """清理换行、多余空格，统一成 'k=v; k=v' 形式。"""
    # curl 的续行：把 反斜杠+换行 变成空格
    cookie = cookie.replace("\\\r\n", " ").replace("\\\n", " ")
    # Windows cmd 的续行： ^ + 换行
    cookie = cookie.replace("^\r\n", " ").replace("^\n", " ")
    cookie = cookie.replace("\r", " ").replace("\n", " ")
    # 压缩空白
    cookie = re.sub(r"\s+", " ", cookie).strip()
    # 去掉首尾可能残留的引号
    cookie = cookie.strip().strip("'\"")
    # 按分号切分，逐项去空格，丢掉空项
    parts = [p.strip() for p in cookie.split(";")]
    parts = [p for p in parts if p and "=" in p]
    return "; ".join(parts)


def cookie_names(cookie):
    names = []
    for p in cookie.split(";"):
        p = p.strip()
        if "=" in p:
            names.append(p.split("=", 1)[0].strip())
    return names


def main():
    src = find_input_file()
    if not src:
        print("[x] 没找到输入文件。请把复制的内容保存为：")
        print("   ", INPUT_CANDIDATES[0])
        return 1

    print("[i] 读取输入文件：", src)
    try:
        with open(src, "r", encoding="utf-8-sig", errors="replace") as f:
            raw = f.read()
    except Exception as e:
        print("[x] 读取失败：", e)
        return 1

    if not raw.strip():
        print("[x] 输入文件是空的。")
        return 1

    cookie, fmt = extract_cookie(raw)
    if not cookie:
        print("[x] 没能从文件里识别出 cookie。")
        print("    请确认粘贴的是 cURL 命令，或形如 'SUB=xxx; SUBP=yyy' 的字符串。")
        return 1

    names = cookie_names(cookie)
    print("[v] 识别格式：{}".format(fmt))
    print("[i] 解析出 {} 个 cookie：{}".format(len(names), ", ".join(sorted(names))))

    if REQUIRED_HINT not in names:
        print("[!] 警告：没有找到 {} 这个关键 cookie。".format(REQUIRED_HINT))
        print("    多半是复制错了行。请在开发者工具里找『请求标头』中")
        print("    以 cookie: 开头的那一行（不要复制『响应标头』里的 set-cookie）。")
        return 1

    # 写入 config.json
    if not os.path.isfile(CONFIG_PATH):
        print("[x] 找不到配置文件：", CONFIG_PATH)
        return 1
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print("[x] config.json 解析失败：", e)
        return 1

    config["cookie"] = cookie
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print("[x] 写入 config.json 失败：", e)
        return 1

    print("[v] 已写入 config.json 的 cookie 字段（{} 字符，未显示明文）。".format(len(cookie)))
    print()
    print("出于安全考虑，建议现在删除输入文件：")
    print("    Remove-Item", src)
    print()
    print("下一步：确认 config.json 里 user_id_list 是你要爬的用户 ID，然后运行：")
    print(r"    cd weiboSpider")
    print(r"    .\venv\Scripts\python.exe -m weibo_spider")
    return 0


if __name__ == "__main__":
    sys.exit(main())
