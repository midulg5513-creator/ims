# -*- coding: utf-8 -*-
"""用 config.json 里的 cookie 真实请求一次 weibo.cn，验证是否有效。

只输出诊断结论，绝不输出 cookie 的值。
用法：.\\weiboSpider\\venv\\Scripts\\python.exe check_cookie.py
"""

import json
import os
import re
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")

# 迪丽热巴的 weibo.cn 主页，用公开可访问的页面做探测
TEST_URL = "https://weibo.cn/u/1669879400"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 未登录时页面里会出现的特征
LOGGED_OUT_MARKERS = [
    "passport.weibo.cn/signin",
    'name="pw"',
    "登录名",
    "请输入密码",
]


def main():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print("[x] 读取 config.json 失败：", e)
        return 1

    cookie = cfg.get("cookie", "")
    if not cookie or cookie == "your cookie":
        print("[x] config.json 里还没有填 cookie。")
        return 1

    names = [p.split("=", 1)[0].strip() for p in cookie.split(";") if "=" in p]
    print("[i] 将使用 {} 个 cookie 字段：{}".format(len(names), ", ".join(names)))

    headers = dict(HEADERS)
    headers["Cookie"] = cookie

    try:
        r = requests.get(TEST_URL, headers=headers, timeout=25, allow_redirects=True)
    except Exception as e:
        print("[x] 请求失败：", type(e).__name__, e)
        print("    如果本机走了代理，确认代理正常工作；或稍后重试。")
        return 1

    print("[i] HTTP 状态码:", r.status_code)
    print("[i] 最终 URL :", r.url)
    print("[i] 响应长度 :", len(r.text), "字符")

    m = re.search(r"<title>(.*?)</title>", r.text, re.S | re.I)
    print("[i] 页面标题 :", m.group(1).strip() if m else "(未找到 title)")

    # 微博条目数量：weibo.cn 每条微博是一个 <div class="c" ...>
    count = len(re.findall(r'<div\s+class="c"', r.text))
    print("[i] 检测到微博条目数:", count)

    hits = [mk for mk in LOGGED_OUT_MARKERS if mk in r.text]
    if hits:
        print("[x] 判定：未登录（命中特征：{}）".format(", ".join(hits)))
        print("    → cookie 无效或已过期，需要重新获取。")
        return 1

    if count > 0:
        print("[v] 判定：cookie 有效，已成功获取到微博列表内容。")
        return 0

    print("[?] 判定：无法确定。页面既没有登录特征，也没有解析到微博条目。")
    print("    可能原因：该用户设置了隐私、被限制访问，或页面结构变化。")
    print("    建议直接试跑主程序观察。")
    return 2


if __name__ == "__main__":
    sys.exit(main())
