* ============================================================
*  R2 improvement, round 2: exogenous time / region features
*  Y = ln(reposts + comments + likes + 1)
*  Never use Y's own components as regressors.
* ============================================================
clear all
set more off
set linesize 120

import delimited "d:\AI\爬虫\stata_data.csv", encoding("UTF-8") clear
gen influence = ln(reposts + comments + likes + 1)
encode ad_type, gen(ad_type_n)
encode media_type, gen(media_type_n)
encode region, gen(region_n)

display "### BASELINE_REF"
regress influence log_followers text_len n_images is_ad
display "R2_REF = " e(r2)
display "ADJR2_REF = " e(r2_a)

* ---------- M9: + publication time features ----------
display "### M9_TIME"
regress influence log_followers text_len n_images is_ad ///
    pub_hour c.pub_hour#c.pub_hour is_weekend
display "R2_M9 = " e(r2)
display "ADJR2_M9 = " e(r2_a)

* ---------- M10: types + time ----------
display "### M10_TYPES_TIME"
regress influence log_followers text_len n_images is_ad ///
    i.ad_type_n i.media_type_n pub_hour is_weekend
display "R2_M10 = " e(r2)
display "ADJR2_M10 = " e(r2_a)

* ---------- M11: types + region ----------
display "### M11_TYPES_REGION"
regress influence log_followers text_len n_images is_ad ///
    i.ad_type_n i.media_type_n i.region_n
display "R2_M11 = " e(r2)
display "ADJR2_M11 = " e(r2_a)

* ---------- M12: everything legitimate ----------
display "### M12_ALL"
regress influence c.log_followers##c.log_followers ///
    c.text_len##c.text_len c.n_images##c.n_images ///
    n_topics is_ad i.ad_type_n i.media_type_n i.region_n ///
    pub_hour is_weekend c.log_followers#c.is_ad
display "R2_M12 = " e(r2)
display "ADJR2_M12 = " e(r2_a)
display "N_M12 = " e(N)
display "DFRESID_M12 = " e(df_r)
display "ROOTMSE_M12 = " e(rmse)

* ---------- M13: region only (parsimonious) ----------
display "### M13_REGION_ONLY"
regress influence log_followers text_len n_images is_ad i.region_n
display "R2_M13 = " e(r2)
display "ADJR2_M13 = " e(r2_a)

* ---------- M14: types + region + interactions ----------
display "### M14_TYPES_REGION_INTERACT"
regress influence log_followers text_len n_images is_ad ///
    i.ad_type_n i.media_type_n i.region_n ///
    c.log_followers#c.is_ad c.text_len#c.is_ad
display "R2_M14 = " e(r2)
display "ADJR2_M14 = " e(r2_a)
display "N_M14 = " e(N)
display "DFRESID_M14 = " e(df_r)

display "### ROUND2 DONE"
