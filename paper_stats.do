* ============================================================
*  paper_stats.do —— 收集论文所需的全部描述统计与分组系数
* ============================================================
clear all
set more off
set linesize 200

cd "d:\AI\爬虫"
import delimited "stata_ads3.csv", encoding("UTF-8") clear

* stata_ads3.csv 已内置 ln_repost / ln_followers / hist_prior_lnengage0 /
*   has_prior_hist / text_len100 / n_pics / n_mentions / n_mentions_c / ln_age_hours
gen byte is_video = (media_type == "video")
encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode region_grp, gen(region_n)

* ⚠️ 精度修正：import delimited 会把含小数的列存成 float，用原始整数重算恢复双精度
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

display _n(2) "######## 1. 样本概况 ########"
count
display "N = " r(N)
egen byte _tag = tag(author_id)
count if _tag
display "作者数 = " r(N)
drop _tag
count if reposts == 0
display "零转发数 = " r(N) "   占比 = " %6.4f r(N)/211

display _n "######## 2. 因变量与核心变量描述统计 ########"
summarize reposts comments likes ln_repost ///
    ln_followers followers text_len n_pics n_topics n_mentions n_mentions_c ///
    n_promo n_brand age_hours ln_age_hours hist_prior_lnengage, detail

display _n "######## 3. 分类变量分布 ########"
display "--- appeal_grp ---"
tab appeal_grp
display "--- media_type ---"
tab media_type
display "--- ad_type ---"
tab ad_type
display "--- 认证身份交叉 ---"
tab is_enterprise is_personal_verified
display "--- is_lottery ---"
tab is_lottery
display "--- region_grp ---"
tab region_grp
display "--- kw_grp（抽样关键词归并层）---"
tab kw_grp

display _n "######## 4. 事前历史覆盖率 ########"
count if has_prior_hist == 1
display "有事前历史帖的作者帖数 = " r(N) "   (" %6.4f r(N)/211 ")"
summarize hist_prior_lnengage if has_prior_hist == 1, detail
tab has_prior_hist

display _n "######## 5. Q1 教学模型（论文用）########"
regress ln_repost ln_followers text_len n_pics is_lottery
display "SSR=" %18.8f e(mss)
display "SSE=" %18.8f e(rss)
display "SST=" %18.8f e(mss)+e(rss)
display "MSR=" %18.8f e(mss)/e(df_m)
display "MSE=" %18.8f e(rss)/e(df_r)

display _n "######## 6. Q3 分组系数（诉求类型）########"
foreach g in 价格促销 品牌官宣 抽奖导流 硬广标识 软植入 {
    display _n "===== 组：`g' ====="
    quietly count if appeal_grp == "`g'"
    local nn = r(N)
    display "n = `nn'"
    regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
        text_len n_pics is_lottery ln_age_hours if appeal_grp == "`g'", vce(hc3)
    display "R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a)
}

display _n "######## 7. Q3 分组系数（媒体形态）########"
foreach g in image video {
    display _n "===== 组：`g' ====="
    quietly count if media_type == "`g'"
    display "n = " r(N)
    regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
        text_len n_pics is_lottery ln_age_hours if media_type == "`g'", vce(hc3)
    display "R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a)
}

display _n "######## 8. Q3 分组系数（认证身份）########"
display "===== 企业认证 ====="
quietly count if is_enterprise == 1
display "n = " r(N)
regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours if is_enterprise == 1, vce(hc3)
display "R2=" %9.6f e(r2)

display _n "===== 个人认证（非企业）====="
quietly count if is_personal_verified == 1 & is_enterprise == 0
display "n = " r(N)
regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours ///
    if is_personal_verified == 1 & is_enterprise == 0, vce(hc3)
display "R2=" %9.6f e(r2)

display _n "===== 无认证 ====="
quietly count if is_personal_verified == 0 & is_enterprise == 0
display "n = " r(N)
capture regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours ///
    if is_personal_verified == 0 & is_enterprise == 0, vce(hc3)
if _rc == 0 display "R2=" %9.6f e(r2)

display _n "######## 9. 各变量均值（做表用）########"
tabstat reposts ln_repost ln_followers text_len n_pics n_topics ///
    n_mentions n_mentions_c n_promo n_brand is_lottery ln_age_hours ///
    hist_prior_lnengage, statistics(mean sd p50 min max) columns(statistics)

display _n(2) "######## paper_stats.do 完成 ########"
