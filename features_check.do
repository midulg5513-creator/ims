* ============================================================
*  写作计划支撑：样本过滤代价 + 全特征模型的显著性（用于填「特征重要性表」）
* ============================================================
clear all
set more off
set linesize 130

* ---------- 广告帖样本（路线 B）----------
import delimited "d:\AI\爬虫\stata_ads.csv", encoding("UTF-8") clear
count
display "AD_N = " r(N)
count if reposts > 0
display "AD_GT0 = " r(N)
count if reposts > 5
display "AD_GT5 = " r(N)
count if reposts > 10
display "AD_GT10 = " r(N)

gen double ln_repost = ln(reposts + 1)
gen double logf_sq = log_followers^2
encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)

* ---------- 全特征模型：逐个变量取 p 值 ----------
display "### FULL_MODEL"
regress ln_repost log_followers logf_sq text_len n_images n_topics ///
    n_mentions n_promo n_brand pub_hour is_weekend ///
    is_enterprise is_personal_verified i.appeal_n i.media_n
display "FULL_R2 = " %9.6f e(r2)
display "FULL_ADJR2 = " %9.6f e(r2_a)
display "FULL_F = " %9.6f e(F)
display "FULL_N = " e(N)

foreach v in log_followers logf_sq text_len n_images n_topics n_mentions ///
    n_promo n_brand pub_hour is_weekend is_enterprise is_personal_verified {
    test `v'
    display "P_`v' = " %9.6f r(p)
}
testparm i.appeal_n
display "P_APPEAL = " %9.6f r(p)
testparm i.media_n
display "P_MEDIA = " %9.6f r(p)

* ---------- 粉丝量分档：对应模板的「Magnitude of fans」三档 ----------
display "### FANS_BINS"
gen fans_bin = 1 if followers < 10000
replace fans_bin = 2 if followers >= 10000 & followers < 100000
replace fans_bin = 3 if followers >= 100000
label define fb 1 "<1万" 2 "1万-10万" 3 ">10万"
label values fans_bin fb
tabulate fans_bin
table fans_bin, statistic(mean reposts) statistic(mean ln_repost) statistic(frequency)

* 以最低档为基准
display "### FANS_BIN_REGRESS"
regress ln_repost ib1.fans_bin text_len n_images is_lottery

* ---------- 全样本（470）的过滤代价 ----------
import delimited "d:\AI\爬虫\stata_data.csv", encoding("UTF-8") clear
count
display "ALL_N = " r(N)
count if reposts > 0
display "ALL_GT0 = " r(N)
count if reposts > 5
display "ALL_GT5 = " r(N)

display "### FEATURES_DONE"
