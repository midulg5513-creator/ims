* ============================================================
*  R-squared improvement: LEGITIMATE approaches only
*
*  IMPORTANT: Y = ln(reposts + comments + likes + 1).
*  Therefore reposts / comments / likes and ANY transform of them
*  (log_likes, log_comments, ...) are COMPONENTS of Y and must
*  NEVER be used as regressors -- that is circular and invalid.
*
*  Only genuinely exogenous predictors / functional forms are tested.
* ============================================================
clear all
set more off
set linesize 120

import delimited "d:\AI\爬虫\stata_data.csv", encoding("UTF-8") clear
gen influence = ln(reposts + comments + likes + 1)
encode ad_type, gen(ad_type_n)
encode media_type, gen(media_type_n)

gen log_textlen = ln(text_len + 1)
gen verified_any = (is_enterprise + is_personal_verified > 0)

display "### TARGET"
display "TARGET_R2_FOR_50PCT = 0.41596467 * 1.5"

* ---------- M0: baseline ----------
display "### MODEL M0_BASELINE"
regress influence log_followers text_len n_images n_topics ///
    is_ad is_enterprise is_personal_verified
display "R2_M0 = " e(r2)
display "ADJR2_M0 = " e(r2_a)

* ---------- M1: drop insignificant controls ----------
display "### MODEL M1_PARSIMONIOUS"
regress influence log_followers text_len n_images is_ad
display "R2_M1 = " e(r2)
display "ADJR2_M1 = " e(r2_a)

* ---------- M2: + ad_type dummies (legitimate: type, not volume) ----------
display "### MODEL M2_ADTYPE"
regress influence log_followers text_len n_images is_ad ///
    i.ad_type_n
display "R2_M2 = " e(r2)
display "ADJR2_M2 = " e(r2_a)

* ---------- M3: + media_type dummies ----------
display "### MODEL M3_MEDIATYPE"
regress influence log_followers text_len n_images is_ad ///
    i.media_type_n
display "R2_M3 = " e(r2)
display "ADJR2_M3 = " e(r2_a)

* ---------- M4: + both type dummies ----------
display "### MODEL M4_BOTHTYPES"
regress influence log_followers text_len n_images is_ad ///
    i.ad_type_n i.media_type_n
display "R2_M4 = " e(r2)
display "ADJR2_M4 = " e(r2_a)

* ---------- M5: + interactions with is_ad ----------
display "### MODEL M5_INTERACT"
regress influence log_followers text_len n_images is_ad ///
    i.ad_type_n i.media_type_n ///
    c.log_followers#c.is_ad c.text_len#c.is_ad c.n_images#c.is_ad
display "R2_M5 = " e(r2)
display "ADJR2_M5 = " e(r2_a)

* ---------- M6: + quadratic terms (nonlinear functional form) ----------
display "### MODEL M6_QUADRATIC"
regress influence c.log_followers##c.log_followers text_len ///
    c.text_len##c.text_len n_images n_topics is_ad
display "R2_M6 = " e(r2)
display "ADJR2_M6 = " e(r2_a)

* ---------- M7: combined legitimate specification ----------
display "### MODEL M7_COMBINED"
regress influence c.log_followers##c.log_followers ///
    c.text_len##c.text_len c.n_images##c.n_images ///
    n_topics is_ad i.ad_type_n i.media_type_n ///
    c.log_followers#c.is_ad
display "R2_M7 = " e(r2)
display "ADJR2_M7 = " e(r2_a)
display "ROOTMSE_M7 = " e(rmse)
display "N_M7 = " e(N)

* ---------- M8: log followers replaced by raw followers ----------
display "### MODEL M8_RAWFOLLOWERS"
regress influence followers text_len n_images n_topics is_ad ///
    i.ad_type_n i.media_type_n
display "R2_M8 = " e(r2)
display "ADJR2_M8 = " e(r2_a)

display "### IMPROVE DONE"
