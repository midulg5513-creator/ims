* 补充：按分类维度看因变量分布（论文描述统计表用）
clear all
set more off
set linesize 200
cd "d:\AI\爬虫"
import delimited "stata_ads3.csv", encoding("UTF-8") clear

* ⚠️ 精度修正：import delimited 会把含小数的列存成 float，用原始整数重算恢复双精度
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

* stata_ads3.csv 已内置 ln_repost
gen byte is_zero = (reposts == 0)

display _n "===== 按诉求类型 ====="
tabstat reposts ln_repost, by(appeal_grp) statistics(n mean p50 max) columns(statistics)
display _n "--- 零转发率 ---"
tab appeal_grp is_zero, row

display _n "===== 按媒体形态 ====="
tabstat reposts ln_repost, by(media_type) statistics(n mean p50 max) columns(statistics)
display _n "--- 零转发率 ---"
tab media_type is_zero, row

display _n "===== 按认证身份 ====="
gen str12 acct = "other"
replace acct = "enterprise" if is_enterprise == 1
replace acct = "personal" if is_personal_verified == 1 & is_enterprise == 0
tabstat reposts ln_repost, by(acct) statistics(n mean p50 max) columns(statistics)
display _n "--- 零转发率 ---"
tab acct is_zero, row

display _n "===== 按抽奖 ====="
tabstat reposts ln_repost, by(is_lottery) statistics(n mean p50 max) columns(statistics)
tab is_lottery is_zero, row

display _n "===== 按广告类型 ====="
tabstat reposts ln_repost, by(ad_type) statistics(n mean p50 max) columns(statistics)
