* ============================================================
*  econometric_final.do -- final econometric workflow
*  Teaching model: OLS for Q1/Q2 arithmetic.
*  Research models: HC3 OLS, PPML, negative binomial, hurdle, Wald tests.
*  数据：stata_ads2.csv（**本脚本固定用旧表**）
*
*  ⚠️ 2026-09-24 说明：本脚本已被 regression_final.do 取代（它混用了 poisson /
*     nbreg / logit+hurdle，不是「多元线性回归」），且用到 ptype_grp /
*     source_grp / hist_prior_n / has_ext_link / is_lottery_link 等已在
*     stata_ads3.csv 中删除的变量。保留它只为存档，不要切到新表。
* ============================================================
clear all
set more off
set linesize 160
capture log close
log using "d:\AI\爬虫\econometric_final.log", replace text

import delimited "d:\AI\爬虫\stata_ads2.csv", encoding("UTF-8") clear

gen double ln_repost = ln(reposts + 1)
gen byte positive_repost = reposts > 0
gen double ln_positive_repost = ln(reposts) if reposts > 0
gen double logf_sq = log_followers^2
gen byte has_prior_hist = !missing(hist_prior_avg_lnengage)
replace hist_prior_avg_lnengage = 0 if missing(hist_prior_avg_lnengage)

encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode ptype_grp, gen(ptype_n)
encode source_grp, gen(source_n)
encode region_grp, gen(region_n)

* ---------- Data audit ----------
display "### DATA_AUDIT"
count
display "N_POSTS = " r(N)
egen byte author_tag = tag(author_id)
count if author_tag
display "N_AUTHORS = " r(N)
drop author_tag
count if reposts == 0
display "ZERO_SHARE = " %9.6f r(N)/_N
summarize reposts age_hours log_age_hours hist_prior_n, detail
tab appeal_grp
tab media_type

* ---------- Q1: fixed teaching specification ----------
display "### Q1_TEACHING_OLS"
regress ln_repost log_followers text_len n_images is_lottery
scalar Q_SSR = e(mss)
scalar Q_SSE = e(rss)
scalar Q_SST = e(mss) + e(rss)
scalar Q_R2 = Q_SSR/Q_SST
scalar Q_ADJR2 = 1-(1-Q_R2)*(e(N)-1)/e(df_r)
scalar Q_RMSE = sqrt(Q_SSE/e(df_r))
display "Q_SSR = " %15.8f Q_SSR
display "Q_SSE = " %15.8f Q_SSE
display "Q_SST = " %15.8f Q_SST
display "Q_ROOTMSE = " %15.8f Q_RMSE
display "Q_R2 = " %15.8f Q_R2
display "Q_ADJR2 = " %15.8f Q_ADJR2

* ---------- Q2: same-sample model ladder ----------
display "### Q2_MODEL_LADDER"
regress ln_repost log_followers text_len n_images is_lottery
scalar base_r2 = e(r2)
display "M0 R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " TARGET=" %9.6f 1.5*base_r2

regress ln_repost log_followers text_len n_images is_lottery log_age_hours
display "M1_AGE R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a)

regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours
display "M2_SOURCE R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a)

regress ln_repost log_followers logf_sq hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours
display "M3_NONLINEAR R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a)

regress ln_repost log_followers logf_sq hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours has_ext_link is_lottery_link ///
    i.ptype_n i.source_n
display "M4_PLATFORM R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a)

* ---------- Main OLS: robust inference, not causal language ----------
display "### MAIN_OLS_HC3"
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours, vce(hc3)

* ---------- Count outcome robustness ----------
display "### PPML_ROBUST"
poisson reposts log_followers hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours, vce(robust)

display "### NBREG_ROBUST"
capture noisily nbreg reposts log_followers hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours, vce(robust) iterate(200)
if _rc == 0 {
    display "NB_ALPHA = " e(alpha)
}
else {
    display "NBREG_FAILED_RC = " _rc
}

* ---------- Hurdle model: extensive and intensive margins ----------
display "### HURDLE_EXTENSIVE_LOGIT"
logit positive_repost log_followers hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours, vce(robust)

display "### HURDLE_INTENSIVE_OLS"
regress ln_positive_repost log_followers hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours if positive_repost, vce(hc3)

* ---------- Heterogeneity: interactions + joint Wald tests ----------
display "### HET_APPEAL"
regress ln_repost c.log_followers##i.appeal_n c.text_len##i.appeal_n ///
    hist_prior_avg_lnengage has_prior_hist n_images is_lottery log_age_hours, vce(hc3)
testparm i.appeal_n#c.log_followers
display "APPEAL_X_FOLLOWERS_F = " r(F) " P = " r(p)
testparm i.appeal_n#c.text_len
display "APPEAL_X_TEXT_F = " r(F) " P = " r(p)

display "### HET_MEDIA_LOTTERY"
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images log_age_hours i.media_n##i.is_lottery ///
    if inlist(media_type, "image", "video"), vce(hc3)
testparm i.media_n#i.is_lottery
display "MEDIA_X_LOTTERY_F = " r(F) " P = " r(p)

* ---------- Diagnostics and sensitivity ----------
display "### DIAGNOSTICS"
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours
vif
estat hettest
predict double cooksd, cooksd
summarize cooksd, detail
count if cooksd > 4/e(N)
display "HIGH_INFLUENCE_N = " r(N)
drop cooksd

* Relative diffusion outcome: results should not be compared by raw R2 to count models.
gen double ln_repost_per_10k = ln(reposts/(followers/10000 + 1) + 1)
regress ln_repost_per_10k hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours, vce(hc3)

display "### ECONOMETRIC_FINAL_DONE"
log close
