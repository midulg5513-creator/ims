* ============================================================
*  Weibo advertising post influence - regression analysis
*  Y = ln(reposts + comments + likes + 1)
* ============================================================
clear all
set more off
set linesize 120

import delimited "d:\AI\爬虫\stata_data.csv", encoding("UTF-8") clear

* ---------- dependent variable ----------
gen influence = ln(reposts + comments + likes + 1)
label variable influence "influence = ln(reposts+comments+likes+1)"

* categorical variables for subgroup analysis
encode ad_type, gen(ad_type_n)
encode media_type, gen(media_type_n)

* ---------- descriptive statistics ----------
display "### SECTION DESCRIPTIVES"
summarize influence reposts comments likes followers log_followers ///
    text_len n_images n_topics is_ad is_enterprise is_personal_verified

* ---------- correlation matrix ----------
display "### SECTION CORRELATION"
correlate influence log_followers text_len n_images n_topics ///
    is_ad is_enterprise is_personal_verified

* ============================================================
*  BASELINE MODEL  (all variables with non-zero variance)
* ============================================================
display "### SECTION BASELINE"
regress influence log_followers text_len n_images n_topics ///
    is_ad is_enterprise is_personal_verified

estimates store m_baseline

* variance inflation factors
display "### SECTION VIF"
estat vif

* ---------- quantities required by the assignment ----------
display "### SECTION ANOVA"
display "Q_N        = " e(N)
display "Q_SSR      = " e(mss)
display "Q_SSE      = " e(rss)
display "Q_SST      = " e(mss) + e(rss)
display "Q_DFMODEL  = " e(df_m)
display "Q_DFRESID  = " e(df_r)
display "Q_MSR      = " e(mss)/e(df_m)
display "Q_MSE      = " e(rss)/e(df_r)
display "Q_ROOTMSE  = " e(rmse)
display "Q_R2       = " e(r2)
display "Q_ADJR2    = " e(r2_a)
display "Q_F        = " e(F)

* ---------- hand-calculation check, compared with software ----------
display "### SECTION MANUAL"
scalar sst = e(mss) + e(rss)
scalar n   = e(N)
scalar k   = e(df_m)

scalar r2_manual   = e(mss) / sst
scalar adj_manual  = 1 - (1 - r2_manual) * (n - 1) / (n - k - 1)
scalar rmse_manual = sqrt(e(rss) / (n - k - 1))

display "M_R2_SOFTWARE    = " e(r2)
display "M_R2_MANUAL      = " r2_manual
display "M_R2_DIFF        = " e(r2) - r2_manual
display "M_ADJR2_SOFTWARE = " e(r2_a)
display "M_ADJR2_MANUAL   = " adj_manual
display "M_ADJR2_DIFF     = " e(r2_a) - adj_manual
display "M_ROOTMSE_SOFT   = " e(rmse)
display "M_ROOTMSE_MANUAL = " rmse_manual
display "M_ROOTMSE_DIFF   = " e(rmse) - rmse_manual

* ============================================================
*  IMPROVED MODEL  (log transforms + interaction term)
* ============================================================
display "### SECTION IMPROVED"
gen log_likes   = ln(likes + 1)
gen log_comments = ln(comments + 1)
gen log_textlen = ln(text_len + 1)
gen verified_any = (is_enterprise + is_personal_verified > 0)
gen topic_per_len = n_topics / (text_len + 1)

regress influence log_followers log_textlen log_likes log_comments ///
    n_images n_topics is_ad verified_any

estimates store m_improved
display "I_R2     = " e(r2)
display "I_ADJR2  = " e(r2_a)
display "I_ROOTMSE= " e(rmse)

* ============================================================
*  SUBGROUP REGRESSIONS by ad_type
* ============================================================
display "### SECTION SUBGROUP ADTYPE"
levelsof ad_type, local(levels)
foreach lv of local levels {
    display "--- ADTYPE GROUP: `lv' ---"
    quietly count if ad_type == "`lv'"
    if r(N) >= 12 {
        regress influence log_followers log_textlen n_images ///
            n_topics is_ad is_enterprise is_personal_verified ///
            if ad_type == "`lv'"
        display "G_ADTYPE   = `lv'"
        display "G_N        = " e(N)
        display "G_R2       = " e(r2)
        display "G_ADJR2    = " e(r2_a)
    }
    else {
        display "G_ADTYPE   = `lv'  SKIPPED (n = " r(N) " < 12)"
    }
}

* ============================================================
*  SUBGROUP REGRESSIONS by media_type
* ============================================================
display "### SECTION SUBGROUP MEDIATYPE"
levelsof media_type, local(levels)
foreach lv of local levels {
    display "--- MEDIATYPE GROUP: `lv' ---"
    quietly count if media_type == "`lv'"
    if r(N) >= 12 {
        regress influence log_followers log_textlen n_images ///
            n_topics is_ad is_enterprise is_personal_verified ///
            if media_type == "`lv'"
        display "G_MEDIA    = `lv'"
        display "G_N        = " e(N)
        display "G_R2       = " e(r2)
        display "G_ADJR2    = " e(r2_a)
    }
    else {
        display "G_MEDIA    = `lv'  SKIPPED (n = " r(N) " < 12)"
    }
}

display "### ALL DONE"
