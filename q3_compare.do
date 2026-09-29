* ============================================================
*  q3_compare.do —— 诉求类型的调节效应：加不加「信源质量」的对照
*
*  背景：旧规格（analysis_ads.do）实测 appeal 交互 F=10.858、media 交互 F=9.462
*        新规格加入 hist_prior_lnengage（目标帖发布前的作者互动率）后检验类型差异
*  → 若交互在"不含 hist"时显著、在"含 hist"时消失，
*     说明原先观察到的「类型调节」在很大程度上是遗漏信源质量造成的伪相关。
*
*  这一对照直接决定 H3（ELM 路径替代）与 H5（类型异质性）的结论。
* ============================================================
clear all
set more off
set linesize 140

import delimited "d:\AI\爬虫\stata_ads3.csv", encoding("UTF-8") clear

* ln_repost / hist_prior_lnengage0 / has_prior_hist 已内置
replace ad_density = 0 if missing(ad_density)

encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode link_grp,   gen(link_n)      // 原 ptype_grp 已删（6 类里 2 类 n<5），改用外链去向

* ⚠️ 精度修正：import delimited 会把含小数的列存成 float，用原始整数重算恢复双精度
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

* ------------------------------------------------------------
*  A. 旧规格：不含信源质量
* ------------------------------------------------------------
display "### A_NO_HIST_APPEAL"
regress ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n ///
    n_pics is_lottery ln_age_hours, vce(hc3)
testparm i.appeal_n#c.ln_followers
display "A_APPEAL_X_LOGF_F = " r(F) " P = " r(p)
testparm i.appeal_n#c.text_len
display "A_APPEAL_X_TEXT_F = " r(F) " P = " r(p)
testparm i.appeal_n
display "A_APPEAL_MAIN_F = " r(F) " P = " r(p)

display "### A_NO_HIST_MEDIA"
regress ln_repost c.ln_followers##i.media_n c.text_len##i.media_n ///
    n_pics is_lottery ln_age_hours, vce(hc3)
testparm i.media_n#c.ln_followers
display "A_MEDIA_X_LOGF_F = " r(F) " P = " r(p)
testparm i.media_n#c.text_len
display "A_MEDIA_X_TEXT_F = " r(F) " P = " r(p)

display "### A_NO_HIST_LINK"
regress ln_repost c.ln_followers##i.link_n c.text_len##i.link_n ///
    n_pics is_lottery ln_age_hours, vce(hc3)
testparm i.link_n#c.ln_followers
display "A_LINK_X_LOGF_F = " r(F) " P = " r(p)

* ------------------------------------------------------------
*  B. 新规格：含信源质量
* ------------------------------------------------------------
display "### B_WITH_HIST_APPEAL"
regress ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n ///
    n_pics is_lottery hist_prior_lnengage0 has_prior_hist ln_age_hours, vce(hc3)
testparm i.appeal_n#c.ln_followers
display "B_APPEAL_X_LOGF_F = " r(F) " P = " r(p)
testparm i.appeal_n#c.text_len
display "B_APPEAL_X_TEXT_F = " r(F) " P = " r(p)
testparm i.appeal_n
display "B_APPEAL_MAIN_F = " r(F) " P = " r(p)

display "### B_WITH_HIST_MEDIA"
regress ln_repost c.ln_followers##i.media_n c.text_len##i.media_n ///
    n_pics is_lottery hist_prior_lnengage0 has_prior_hist ln_age_hours, vce(hc3)
testparm i.media_n#c.ln_followers
display "B_MEDIA_X_LOGF_F = " r(F) " P = " r(p)
testparm i.media_n#c.text_len
display "B_MEDIA_X_TEXT_F = " r(F) " P = " r(p)

* ------------------------------------------------------------
*  C. 诊断：诉求类型与信源质量是否相关（伪相关的来源）
* ------------------------------------------------------------
display "### C_APPEAL_VS_HIST"
tabstat hist_prior_lnengage0 ln_followers reposts, by(appeal_grp) stat(mean p50 n) format(%9.4f)
display "### C_APPEAL_ANOVA"
oneway hist_prior_lnengage0 appeal_n
display "C_ANOVA_HIST_F = " r(F) " P = " r(p)
oneway ln_followers appeal_n
display "C_ANOVA_LOGF_F = " r(F) " P = " r(p)

* 分组显著/不显著不能替代正式差异检验：直接检验媒体形态 × 抽奖。
display "### D_MEDIA_X_LOTTERY_IMAGE_VIDEO"
regress ln_repost c.ln_followers hist_prior_lnengage0 has_prior_hist text_len n_pics ///
    ln_age_hours i.media_n##i.is_lottery if inlist(media_type, "image", "video"), vce(hc3)
testparm i.media_n#i.is_lottery
display "D_MEDIA_X_LOTTERY_F = " r(F) " P = " r(p)

display "### Q3_COMPARE DONE"
