* ============================================================
*  diag_m4.do —— 诊断 M4 的系数显著性
*  重点：ln_followers 与 lnf_sq 的 x/x² 共线性
* ============================================================
clear all
set more off
set linesize 200

cd "d:\AI\爬虫"
import delimited "stata_ads3.csv", encoding("UTF-8") clear

* ⚠️ 精度修正：import delimited 把含小数的列存成 float，用原始整数重算恢复双精度
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

* stata_ads3.csv 已内置：ln_repost / hist_prior_lnengage0 / has_prior_hist /
*                      lnf_c / lnf_c2（粉丝对数已中心化），不再重复生成
gen double lnf_sq = ln_followers^2
quietly summarize ln_followers
scalar MLOGF = r(mean)

display _n(2) "{hline 74}"
display "【1】M4 原规格（与你跑的一致）"
display "{hline 74}"
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions

display _n "--- M4 的 VIF（注意：本次检查覆盖 lnf_sq）---"
estat vif

display _n "--- 联合检验：粉丝线性项与二次项一起看 ---"
test ln_followers lnf_sq
display "  粉丝(线性+二次) 联合: F = " %8.4f r(F) "   p = " %8.4f r(p)

display _n "--- 联合检验：话题数与@提及数一起看 ---"
test n_topics n_mentions
display "  信息密度(话题+@) 联合: F = " %8.4f r(F) "   p = " %8.4f r(p)

display _n(2) "{hline 74}"
display "【2】去掉 lnf_sq 后（对照：看粉丝线性项会不会恢复显著）"
display "{hline 74}"
regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions

display _n(2) "{hline 74}"
display "【3】中心化写法（推荐：消除 x 与 x² 的机械共线）"
display "{hline 74}"
regress ln_repost lnf_c lnf_c2 hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions
display "  R2 应与原规格完全相同，但两个粉丝项的 p 值可解释性更好"
display "  ln_followers 均值 = " %9.6f MLOGF

display _n "--- 中心化后的 VIF ---"
estat vif

display _n(2) "{hline 74}"
display "【4】只保留核心假设变量的精简模型"
display "{hline 74}"
regress ln_repost ln_followers hist_prior_lnengage0 is_lottery, vce(hc3)

display _n(2) "{hline 74}"
display "diag_m4.do 完成"
display "{hline 74}"
