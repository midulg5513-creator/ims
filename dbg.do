* 最小诊断：ad_density 的类型与分位数
clear all
set more off
import delimited "d:\AI\爬虫\stata_ads3.csv", encoding("UTF-8") clear

display "### DESCRIBE"
describe ad_density n_promo hist_prior_lnengage

display "### SUMMARIZE"
summarize ad_density, detail

display "### R_P50"
display "P50 = " r(p50)
display "N   = " r(N)

display "### GEN_AD_HI"
gen byte ad_hi = ad_density > r(p50)
tab ad_hi, missing

display "### MISSING_COUNT"
count if missing(ad_density)
display "MISS_N = " r(N)

* ⚠️ 精度修正：import delimited 会把含小数的列存成 float，用原始整数重算恢复双精度
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

display "### REPLACE_THEN_AGAIN"
replace ad_density = 0 if missing(ad_density)
quietly summarize ad_density
display "P50_AFTER = " r(p50)
gen byte ad_hi2 = ad_density > r(p50)
tab ad_hi2

display "### DBG DONE"
