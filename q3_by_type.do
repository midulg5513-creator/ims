* ============================================================
*  q3_by_type.do —— 作业第 3 题：分类型广告帖的完整回归结果
*
*  数据：stata_ads3.csv（变量清理版，211 条广告帖）
*  因变量：ln_repost = ln(转发数 + 1)
*
*  做法：先按 6 个维度把广告帖分类，再对每一类**单独跑同一个回归规格**，
*        输出完整系数表（β / SE / t / p）+ N / R² / Adj R² / F，
*        最后做组间系数差异的正式交互检验（testparm 联合 Wald）。
*
*  统一规格（HC3 稳健标准误）：
*    ln_repost ~ ln_followers + hist_prior_lnengage0 + has_prior_hist
*                + text_len + n_pics + ln_age_hours [+ is_lottery]
*  （「抽奖型 vs 非抽奖型」维度里不能再放 is_lottery，否则完全共线）
*
*  输出格式（便于外部脚本解析）：
*    ROW|维度|组|N=..|R2=..|ADJR2=..|F=..|pF=..
*    COEF|维度|组|变量|b=..|se=..|t=..|p=..
*    DESC|维度|组|N=..|mean_y=..|p50_y=..|zero=..|mean_repost=..
*    INT|维度|检验|F=..|p=..
*
*  用法：StataMP /e do d:\AI\爬虫\q3_by_type.do
* ============================================================
clear all
set more off
set linesize 240

cd "d:\AI\爬虫"
import delimited "stata_ads3.csv", encoding("UTF-8") clear

* ---- 精度修正：import delimited 把含小数的列存成 float，必须 drop+gen double ----
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

* ---- 分类变量编码 ----
encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode ad_type,    gen(adtype_n)
encode link_grp,   gen(link_n)

* 认证身份：三分类（企业认证 / 个人认证 / 无认证）
gen byte acct = 1 if is_enterprise == 1
replace  acct = 2 if is_personal_verified == 1 & is_enterprise == 0
replace  acct = 3 if is_personal_verified == 0 & is_enterprise == 0
label define acctl 1 "企业认证" 2 "个人认证" 3 "无认证", replace
label values acct acctl

* 抽奖型 / 非抽奖型
gen byte lotgrp = is_lottery

display "### SAMPLE"
count
display "N_TOTAL = " r(N)

* ============================================================
*  通用报告程序：把上一次 regress 的完整结果打成可解析的行
* ============================================================
capture program drop report
program define report
    args dim grp cvars
    local dfr = e(df_r)
    display "ROW|`dim'|`grp'|N=" e(N) "|R2=" %9.6f e(r2) ///
        "|ADJR2=" %9.6f e(r2_a) "|F=" %9.4f e(F) "|pF=" %9.5f Ftail(e(df_m), e(df_r), e(F))
    foreach v of local cvars {
        capture scalar bv = _b[`v']
        if _rc continue
        capture scalar sv = _se[`v']
        if _rc continue
        if missing(bv) | missing(sv) | sv == 0 continue
        scalar tv = bv / sv
        scalar pv = 2 * ttail(`dfr', abs(tv))
        display "COEF|`dim'|`grp'|`v'|b=" %10.6f bv "|se=" %10.6f sv ///
            "|t=" %8.3f tv "|p=" %8.5f pv
    }
end

* 描述统计程序（按分组变量取值）
capture program drop descby
program define descby
    args dim gvar gval gname
    quietly count if `gvar' == `gval'
    if r(N) == 0 exit
    local n = r(N)
    * 注意：summarize 不带 detail 时没有 r(p50)，会静默取到缺失
    quietly summarize ln_repost if `gvar' == `gval', detail
    local my = r(mean)
    local f50 = r(p50)
    quietly summarize reposts if `gvar' == `gval'
    local mr = r(mean)
    quietly count if `gvar' == `gval' & reposts == 0
    local z = r(N) / `n'
    display "DESC|`dim'|`gname'|N=`n'|mean_y=" %8.4f `my' "|p50_y=" %8.4f `f50' ///
        "|zero=" %8.5f `z' "|mean_repost=" %10.2f `mr'
end

* 分组回归 + 交互检验的通用过程
capture program drop rungrp
program define rungrp
    args dim gvar gval gname spec
    quietly count if `gvar' == `gval'
    local n = r(N)
    if `n' < 25 {
        display "ROW|`dim'|`gname'|N=`n'|SKIP_N<25"
        exit
    }
    quietly regress ln_repost `spec' if `gvar' == `gval', vce(hc3)
    report "`dim'" "`gname'" "`spec'"
end

* 交互检验（rhs 直接就是完整回归命令，形如 "ln_repost ... , vce(hc3)"）
capture program drop runint
program define runint
    args dim gvar intvar rhs
    quietly regress `rhs'
    quietly testparm `intvar'
    display "INT|`dim'|`intvar'|F=" %9.4f r(F) "|p=" %9.5f r(p)
end

* ============================================================
* 统一规格
* ============================================================
global CORE   ln_followers hist_prior_lnengage0 has_prior_hist text_len n_pics ln_age_hours
global WITHLOT $CORE is_lottery
global WITHOUTLOT $CORE

* ============================================================
* 0. 描述统计：各类型因变量分布
* ============================================================
display "### 0_DESCRIPTIVE_BY_TYPE"

display "--- 按诉求类型 ---"
levelsof appeal_n, local(gs)
foreach g of local gs {
    local nm : label (appeal_n) `g'
    descby "appeal" appeal_n `g' "`nm'"
}
display "--- 按媒体形态 ---"
levelsof media_n, local(gs)
foreach g of local gs {
    local nm : label (media_n) `g'
    descby "media" media_n `g' "`nm'"
}
display "--- 按广告判定来源 ---"
levelsof adtype_n, local(gs)
foreach g of local gs {
    local nm : label (adtype_n) `g'
    descby "adtype" adtype_n `g' "`nm'"
}
display "--- 按认证身份 ---"
forvalues g = 1/3 {
    local nm : label (acct) `g'
    descby "acct" acct `g' "`nm'"
}
display "--- 按外链去向 ---"
levelsof link_n, local(gs)
foreach g of local gs {
    local nm : label (link_n) `g'
    descby "link" link_n `g' "`nm'"
}
display "--- 按是否抽奖 ---"
forvalues g = 0/1 {
    local nm = cond(`g' == 1, "抽奖型", "非抽奖型")
    descby "lottery" lotgrp `g' "`nm'"
}

* ============================================================
* 1. 按诉求类型 分 5 组单独回归
* ============================================================
display "### 1_BY_APPEAL"
levelsof appeal_n, local(gs)
foreach g of local gs {
    local nm : label (appeal_n) `g'
    rungrp "appeal" appeal_n `g' "`nm'" "$WITHLOT"
}

* ============================================================
* 2. 按媒体形态
* ============================================================
display "### 2_BY_MEDIA"
levelsof media_n, local(gs)
foreach g of local gs {
    local nm : label (media_n) `g'
    rungrp "media" media_n `g' "`nm'" "$WITHLOT"
}

* ============================================================
* 3. 按广告判定来源（explicit_ad / brand_campaign / kol_collab）
* ============================================================
display "### 3_BY_ADTYPE"
levelsof adtype_n, local(gs)
foreach g of local gs {
    local nm : label (adtype_n) `g'
    rungrp "adtype" adtype_n `g' "`nm'" "$WITHLOT"
}

* ============================================================
* 4. 按账号认证身份
* ============================================================
display "### 4_BY_ACCT"
forvalues g = 1/3 {
    local nm : label (acct) `g'
    rungrp "acct" acct `g' "`nm'" "$WITHLOT"
}

* ============================================================
* 5. 按外链去向
* ============================================================
display "### 5_BY_LINK"
levelsof link_n, local(gs)
foreach g of local gs {
    local nm : label (link_n) `g'
    rungrp "link" link_n `g' "`nm'" "$WITHLOT"
}

* ============================================================
* 6. 抽奖型 vs 非抽奖型（规格里去掉 is_lottery，否则完全共线）
* ============================================================
display "### 6_BY_LOTTERY"
forvalues g = 0/1 {
    local nm = cond(`g' == 1, "抽奖型", "非抽奖型")
    rungrp "lottery" lotgrp `g' "`nm'" "$WITHOUTLOT"
}

* ============================================================
* 7. 组间差异的正式检验（一个组显著 ≠ 两组显著不同）
* ============================================================
display "### 7_INTERACTION_TESTS"

* --- 诉求类型 ---
runint "appeal" appeal_n "i.appeal_n#c.ln_followers" ///
    "ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n c.n_pics##i.appeal_n $WITHLOT, vce(hc3)"
runint "appeal" appeal_n "i.appeal_n#c.text_len" ///
    "ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n c.n_pics##i.appeal_n $WITHLOT, vce(hc3)"
runint "appeal" appeal_n "i.appeal_n#c.n_pics" ///
    "ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n c.n_pics##i.appeal_n $WITHLOT, vce(hc3)"
runint "appeal" appeal_n "i.appeal_n#c.hist_prior_lnengage0" ///
    "ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n c.n_pics##i.appeal_n c.hist_prior_lnengage0##i.appeal_n has_prior_hist ln_age_hours is_lottery, vce(hc3)"
runint "appeal" appeal_n "i.appeal_n" ///
    "ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n c.n_pics##i.appeal_n $WITHLOT, vce(hc3)"

* --- 媒体形态 ---
runint "media" media_n "i.media_n#c.ln_followers" ///
    "ln_repost c.ln_followers##i.media_n c.text_len##i.media_n c.n_pics##i.media_n $WITHLOT, vce(hc3)"
runint "media" media_n "i.media_n#c.text_len" ///
    "ln_repost c.ln_followers##i.media_n c.text_len##i.media_n c.n_pics##i.media_n $WITHLOT, vce(hc3)"
runint "media" media_n "i.media_n#c.n_pics" ///
    "ln_repost c.ln_followers##i.media_n c.text_len##i.media_n c.n_pics##i.media_n $WITHLOT, vce(hc3)"
runint "media" media_n "i.media_n#i.is_lottery" ///
    "ln_repost ln_followers hist_prior_lnengage0 has_prior_hist text_len n_pics ln_age_hours i.media_n##i.is_lottery, vce(hc3)"
runint "media" media_n "i.media_n" ///
    "ln_repost c.ln_followers##i.media_n c.text_len##i.media_n c.n_pics##i.media_n $WITHLOT, vce(hc3)"

* --- 抽奖型 vs 非抽奖型 ---
runint "lottery" lotgrp "i.lotgrp#c.ln_followers" ///
    "ln_repost c.ln_followers##i.lotgrp c.text_len##i.lotgrp $WITHOUTLOT, vce(hc3)"
runint "lottery" lotgrp "i.lotgrp#c.text_len" ///
    "ln_repost c.ln_followers##i.lotgrp c.text_len##i.lotgrp $WITHOUTLOT, vce(hc3)"
runint "lottery" lotgrp "i.lotgrp" ///
    "ln_repost c.ln_followers##i.lotgrp c.text_len##i.lotgrp $WITHOUTLOT, vce(hc3)"

* --- 认证身份 ---
runint "acct" acct "i.acct#c.ln_followers" ///
    "ln_repost c.ln_followers##i.acct c.text_len##i.acct $WITHLOT, vce(hc3)"
runint "acct" acct "i.acct" ///
    "ln_repost c.ln_followers##i.acct c.text_len##i.acct $WITHLOT, vce(hc3)"

* --- 广告判定来源 ---
runint "adtype" adtype_n "i.adtype_n#c.ln_followers" ///
    "ln_repost c.ln_followers##i.adtype_n c.text_len##i.adtype_n $WITHLOT, vce(hc3)"
runint "adtype" adtype_n "i.adtype_n" ///
    "ln_repost c.ln_followers##i.adtype_n c.text_len##i.adtype_n $WITHLOT, vce(hc3)"

display "### Q3_BY_TYPE DONE"
