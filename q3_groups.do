* ============================================================
*  q3_groups.do —— 分组系数表（回答作业 Q3：不同类型广告帖的重要影响因素）
*
*  统一规格：ln_repost ~ ln_followers + 事前历史互动 + text_len + n_pics + is_lottery + 曝光时长
*  输出格式紧凑（单行一组），便于外部提取：
*    GRP|<组名>|N=|R2=|B/P 各变量
*  注意：分组只作描述性对照；"组间差异是否显著"须看 testparm 交互检验
*        （实测全部不显著，见 q3_compare.do）
*
*  2026-09-24：改用 stata_ads3.csv（变量清理版）。
*              原 ptype_grp（落地页类型）已删，改用 link_grp（外链去向）。
* ============================================================
clear all
set more off
set linesize 200

import delimited "d:\AI\爬虫\stata_ads3.csv", encoding("UTF-8") clear

* ln_repost / hist_prior_lnengage0 / has_prior_hist 已内置
encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode link_grp,   gen(link_n)

* ⚠️ 精度修正：import delimited 会把含小数的列存成 float，用原始整数重算恢复双精度
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

capture program drop grprow
program define grprow
    args grpvar grpval grpname
    quietly count if `grpvar' == `grpval'
    local n = r(N)
    if `n' < 25 {
        display "GRP|`grpname'|N=`n'|SKIP_N<25"
        exit
    }
    quietly regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
        text_len n_pics is_lottery ln_age_hours if `grpvar' == `grpval', vce(hc3)
    local dfr = e(df_r)
    display "GRP|`grpname'|N=`n'|R2=" %6.4f e(r2) ///
        "|BLOGF=" %8.4f _b[ln_followers] "|PLOGF=" %6.3f 2*ttail(`dfr', abs(_b[ln_followers]/_se[ln_followers])) ///
        "|BHIST=" %8.4f _b[hist_prior_lnengage0] "|PHIST=" %6.3f 2*ttail(`dfr', abs(_b[hist_prior_lnengage0]/_se[hist_prior_lnengage0])) ///
        "|BTEXT=" %9.5f _b[text_len] "|PTEXT=" %6.3f 2*ttail(`dfr', abs(_b[text_len]/_se[text_len])) ///
        "|BIMG=" %8.4f _b[n_pics] "|PIMG=" %6.3f 2*ttail(`dfr', abs(_b[n_pics]/_se[n_pics])) ///
        "|BLOT=" %8.4f _b[is_lottery] "|PLOT=" %6.3f 2*ttail(`dfr', abs(_b[is_lottery]/_se[is_lottery]))
end

display "### Q3_GROUPS_BY_APPEAL"
levelsof appeal_n, local(lv)
foreach g of local lv {
    local nm : label (appeal_n) `g'
    grprow appeal_n `g' "`nm'"
}

display "### Q3_GROUPS_BY_MEDIA"
levelsof media_n, local(lm)
foreach g of local lm {
    local nm : label (media_n) `g'
    grprow media_n `g' "`nm'"
}

* ptype_grp（落地页类型）已在变量清理中删除：6 类里 article 3 条 / place 2 条，
* 稀疏到无法分组。改用 link_grp（外链去向：none / video / other），它是有意义的新增变量。
display "### Q3_GROUPS_BY_LINK"
levelsof link_n, local(lp)
foreach g of local lp {
    local nm : label (link_n) `g'
    grprow link_n `g' "`nm'"
}

display "### Q3_GROUPS_DONE"
