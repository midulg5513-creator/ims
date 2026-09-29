* ============================================================
* Stage 2: 600-post prospective fixed-window econometric study
* Primary outcome: cumulative repost count at T+24h
* Interpretation: conditional associations, not causal effects
* ============================================================
clear all
set more off
set linesize 180
capture log close
log using "econometric_stage2.log", replace text

import delimited "stage2_analysis.csv", encoding("UTF-8") clear

assert inrange(age_hours_24h, 22, 26)
isid post_id
gen double hist_prior = hist_prior_avg_lnengage
gen byte has_prior_hist_st = !missing(hist_prior)
replace hist_prior = 0 if missing(hist_prior)

encode industry, gen(industry_n)
encode account_type, gen(account_n)
encode source_group, gen(source_n)
encode appeal_family, gen(appeal_n)
encode author_id, gen(author_n)

bysort author_id: gen author_posts_n = _N
count if author_posts_n >= 2
scalar repeated_share = r(N)/_N
egen byte author_tag = tag(author_id)
count if author_tag & author_posts_n >= 2
scalar repeated_authors = r(N)
drop author_tag

local olsvce "vce(hc3)"
local countvce "vce(robust)"
if repeated_authors >= 30 & repeated_share >= .30 {
    local olsvce "vce(cluster author_n)"
    local countvce "vce(cluster author_n)"
}
display "OLS_INFERENCE = `olsvce'"
display "COUNT_INFERENCE = `countvce'"

local core log_followers hist_prior has_prior_hist_st text_len_100 text_len_100_sq ///
    n_images is_video is_lottery hard_ad promo_density_100 brand_density_100 ///
    has_ext_link log_age_hours_24h
local controls i.industry_n i.account_n i.pub_dow i.source_n

display "### PRIMARY_PPML_T24H"
poisson reposts_24h `core' `controls', `countvce'
estimates store ppml24

display "### OLS_LOG_ROBUSTNESS"
regress ln_repost_24h `core' `controls', `olsvce'
estimates store olslog

display "### HURDLE_EXTENSIVE"
logit positive_repost_24h `core' `controls', `countvce'
estimates store hurdle_zero

display "### HURDLE_POSITIVE_PPML"
poisson reposts_24h `core' `controls' if reposts_24h > 0, `countvce'
estimates store hurdle_positive

display "### NEGATIVE_BINOMIAL"
capture noisily nbreg reposts_24h `core' `controls', `countvce' iterate(300)
if _rc == 0 estimates store nb2
else display "NBREG_FAILED_RC = " _rc

display "### H5_APPEAL_INTERACTIONS"
regress ln_repost_24h hist_prior has_prior_hist_st text_len_100_sq ///
    hard_ad promo_density_100 brand_density_100 has_ext_link log_age_hours_24h ///
    `controls' i.appeal_n##c.log_followers i.appeal_n##c.text_len_100 ///
    i.appeal_n##c.n_images i.appeal_n##i.is_video ///
    i.appeal_n##i.is_lottery, `olsvce'
testparm i.appeal_n#c.log_followers
display "APPEAL_X_FOLLOWERS_P = " r(p)
testparm i.appeal_n#c.text_len_100
display "APPEAL_X_TEXT_P = " r(p)
testparm i.appeal_n#c.n_images i.appeal_n#i.is_video
display "APPEAL_X_MEDIA_P = " r(p)
testparm i.appeal_n#i.is_lottery
display "APPEAL_X_LOTTERY_P = " r(p)
margins appeal_n, dydx(log_followers text_len_100 n_images is_video is_lottery)
marginsplot, xdimension(appeal_n) recast(scatter) name(stage2_margins, replace)
graph export "stage2_marginal_effects.png", replace width(1800)

tab appeal_family
display "Groups below N=80 must be labelled exploratory in the report."

display "### AUTHOR_FIXED_EFFECTS_IF_SUPPORTED"
count if author_posts_n >= 2
if r(N) >= 100 & repeated_authors >= 30 {
    regress ln_repost_24h text_len_100 text_len_100_sq n_images is_video ///
        is_lottery hard_ad promo_density_100 brand_density_100 has_ext_link ///
        log_age_hours_24h i.pub_dow i.author_n if author_posts_n >= 2, ///
        vce(cluster author_n)
    estimates store author_fe
}
else display "AUTHOR_FE_SKIPPED_INSUFFICIENT_REPEATED_AUTHORS"

display "### T7D_ROBUSTNESS"
count if has_valid_7d == 1
if r(N) >= 30 {
    poisson reposts_7d `core' `controls' if has_valid_7d == 1, `countvce'
    estimates store ppml7
}
else display "T7D_SKIPPED_INSUFFICIENT_VALID_SNAPSHOTS"

display "### STAGE2_DONE"
log close
