# -*- coding: utf-8 -*-
"""一次性修订 analysis_v2.do：把无变异的 is_hot_topic 换成有信号的
is_lottery_link + i.ptype_n，并补 ptype 相关描述与分组估计。

依据（实测，见 check_details.py 输出）：
  is_hot_topic 仅 3/208 (1.4%) → 近无效变量，剔出模型
  ad_marked    0/208 (0%)      → 完全无效，已弃用
  page_type    video 63 / topic+search_topic 105 / webpage 14 / article 3 / none 21 → 有价值
"""
import os
import sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis_v2.do")

OLD_SET = "has_ext_link is_hot_topic"
NEW_SET = "has_ext_link is_lottery_link i.ptype_n"

# 1) pwcorr 不支持因子变量，单独先替换
FIXES = [
    ("pwcorr ln_repost hist_avg_lnengage ad_density has_ext_link is_hot_topic ///",
     "pwcorr ln_repost hist_avg_lnengage ad_density has_ext_link is_lottery_link ///"),
    # 2) 编码：补 ptype
    ("encode region_grp, gen(region_n)",
     "encode region_grp, gen(region_n)\nencode ptype_grp,  gen(ptype_n)"),
    # 3) 描述统计：补 ptype/source/link 分布
    ('display "### S0_COVERAGE"',
     'display "### S0_PTYPE"\ntab ptype_grp\ndisplay "### S0_SOURCE"\ntab source_grp\ndisplay "### S0_LINKGRP"\ntab link_grp\ndisplay "### S0_COVERAGE"'),
    # 4) 补按渠道类型的分组估计
    ('display "### Q3_BY_MEDIA"',
     '* 按详情页类型（内容承载方式）分组\n'
     'display "### Q3_BY_PTYPE"\n'
     'levelsof ptype_n, local(lp)\n'
     'foreach g of local lp {\n'
     '    quietly levelsof ptype_grp if ptype_n == `g\', local(nm)\n'
     '    quietly count if ptype_n == `g\'\n'
     '    display "--- GROUP ptype_n=`g\' (`nm\') N=" r(N) " ---"\n'
     '    if r(N) >= 25 {\n'
     '        quietly regress ln_repost log_followers text_len n_images is_lottery if ptype_n == `g\'\n'
     '        display "GROUP_R2 = " %9.6f e(r2) " ADJR2 = " %9.6f e(r2_a)\n'
     '    }\n'
     '    else {\n'
     '        display "GROUP_SKIPPED (n<25)"\n'
     '    }\n'
     '}\n\n'
     '* 组间系数差异：详情页类型 × 核心变量\n'
     'display "### Q3_INTERACT_PTYPE"\n'
     'regress ln_repost c.log_followers##i.ptype_n c.text_len##i.ptype_n n_images is_lottery\n'
     'testparm i.ptype_n#c.log_followers\n'
     'display "Q3_PTYPE_X_LOGF_F = " r(F) " P = " r(p)\n'
     'testparm i.ptype_n#c.text_len\n'
     'display "Q3_PTYPE_X_TEXT_F = " r(F) " P = " r(p)\n\n'
     'display "### Q3_BY_MEDIA"'),
]


def main():
    with open(P, encoding="utf-8") as f:
        s = f.read()

    for old, new in FIXES:
        if old not in s:
            print("[!] 未找到锚点: %s" % old[:48])
            continue
        s = s.replace(old, new, 1)

    n = s.count(OLD_SET)
    s = s.replace(OLD_SET, NEW_SET)

    with open(P, "w", encoding="utf-8") as f:
        f.write(s)
    print("[done] 替换 %d 处 `%s` -> `%s`" % (n, OLD_SET, NEW_SET))
    print("       剩余 is_hot_topic 引用 %d 处（应仅剩描述统计与注释）" % s.count("is_hot_topic"))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
