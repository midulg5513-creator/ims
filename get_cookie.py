# -*- coding: utf-8 -*-
"""从本地浏览器读取 weibo.cn 的 cookie，并写入 weiboSpider/config.json。

背景：weibo_spider/config_util.py 里写死了 browser_cookie3.chrome()，
      但本机并未安装 Chrome（实际使用 Microsoft Edge），所以项目的自动
      提取功能不会生效。本脚本改为依次尝试多个 Chromium 内核浏览器。

安全说明：只打印 cookie 的「名称」和数量，绝不打印 cookie 的值。

用法（在 d:\\AI\\爬虫 目录下）：
    .\\weiboSpider\\venv\\Scripts\\python.exe get_cookie.py
"""

import json
import os
import sys

import browser_cookie3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "weiboSpider")
CONFIG_PATH = os.path.join(REPO, "config.json")

LOGIN_URL = ("https://passport.weibo.com/sso/signin"
             "?entry=wapsso&source=wapssowb&url=https://m.weibo.cn/")

DOMAIN = "weibo.cn"

# 依次尝试的浏览器；weibo.cn 域的 cookie 是跨浏览器不共享的，
# 你在哪个浏览器里登录了微博，就写哪个。
CANDIDATES = [
    ("Edge", "edge"),
    ("Chrome", "chrome"),
    ("Brave", "brave"),
    ("Chromium", "chromium"),
    ("Vivaldi", "vivaldi"),
    ("Opera", "opera"),
]


def read_cookies():
    """依次尝试各浏览器，返回 (浏览器名或None, [(name,value)...], 诊断信息列表)。"""
    notes = []
    for label, func_name in CANDIDATES:
        func = getattr(browser_cookie3, func_name, None)
        if func is None:
            notes.append("{}: 该库不支持".format(label))
            continue
        try:
            raw = list(func(domain_name=DOMAIN))
        except Exception as e:
            notes.append("{}: {} -> {}".format(label, type(e).__name__, e))
            continue
        if raw:
            return label, [(c.name, c.value) for c in raw], notes
        notes.append("{}: 读到了浏览器数据，但 {} 域下没有 cookie".format(label, DOMAIN))
    return None, [], notes


def print_manual_fallback(notes=None):
    if notes and any("RequiresAdminError" in n for n in notes):
        print()
        print("=" * 62)
        print("重要：诊断里出现了 RequiresAdminError，说明 Chrome/Edge 的 cookie")
        print("      解密需要管理员权限（Chromium 127+ 的 App-Bound Encryption）。")
        print("      请【以管理员身份】打开一个 PowerShell 窗口，再执行一次本脚本：")
        print(r"          cd d:\AI\爬虫")
        print(r"          .\weiboSpider\venv\Scripts\python.exe get_cookie.py")
        print("=" * 62)
    print()
    print("改用手动方式（Chrome / Edge 开发者工具，不需要管理员权限）：")
    print("  1) 在 Chrome 里打开并登录：")
    print("    ", LOGIN_URL)
    print("  2) 按 F12 -> 切到「网络」标签")
    print("  3) 保持「网络」标签打开，按 F5 刷新页面   <-- 关键！")
    print("     （若先开页面后开 DevTools，列表会是空的）")
    print("  4) 找到「类型」为「文档」的那条请求（名称就是 weibo.cn）")
    print("  5) 点它 -> 右侧「标头」-> 滚到「请求标头」-> 复制 cookie: 后面整行")
    print("     小技巧：右键该请求 -> 复制 -> 以 cURL 格式复制，")
    print("              里面的 -H 'cookie: ...' 就是完整值（含 HttpOnly）")
    print("  6) 粘贴到 weiboSpider/config.json 第 14 行 \"cookie\" 字段（保持单行）")


def main():
    if not os.path.isfile(CONFIG_PATH):
        print("[x] 找不到配置文件：", CONFIG_PATH)
        print("    请先在 weiboSpider 目录运行一次 python -m weibo_spider 生成它。")
        return 1

    label, pairs, notes = read_cookies()

    if not pairs:
        print("[x] 未能从任何浏览器读到 weibo.cn 的 cookie。")
        print()
        print("--- 各浏览器诊断 ---")
        for n in notes:
            print("  " + n)
        print_manual_fallback(notes)
        return 1

    names = sorted(n for n, _ in pairs)
    print("[i] 成功来源：{}".format(label))
    print("[i] 共读取到 {} 个 cookie：{}".format(len(pairs), ", ".join(names)))

    # 检查登录状态（MLOGIN 是微博的登录态标记）
    mlogin = dict(pairs).get("MLOGIN", "0")
    if mlogin == "0":
        print("[x] MLOGIN 为空或为 0，说明 {} 里当前未登录微博。".format(label))
        print("    请在 {} 中打开并登录：".format(label))
        print("   ", LOGIN_URL)
        print("    登录后（会停在 m.weibo.cn）重新运行本脚本。")
        return 1
    print("[v] MLOGIN 有效，已登录。")

    # 写入 config.json
    cookie_string = "; ".join("{}={}".format(n, v) for n, v in pairs)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print("[x] config.json 解析失败（请检查 JSON 格式）：", e)
        return 1

    config["cookie"] = cookie_string
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print("[x] 写入 config.json 失败：", e)
        return 1

    print("[v] 已把 cookie 写入 config.json（{} 字符，未显示明文）。".format(
        len(cookie_string)))
    print()
    print("下一步：确认 config.json 里 user_id_list 是你要爬的用户 ID，然后运行：")
    print(r"    cd weiboSpider")
    print(r"    .\venv\Scripts\python.exe -m weibo_spider")
    return 0


if __name__ == "__main__":
    sys.exit(main())
