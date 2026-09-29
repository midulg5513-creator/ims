* ============================================================
*  analysis_v2.do —— 重规划后的主分析（路线 B：只在广告帖内部）
*  数据：stata_ads2.csv（211 行，含批次 A/B/C 新变量）
*
*  ⚠️ 2026-09-24 注意：本脚本是「批次 A/B/C 变量探索」的历史脚本，
*     用到 hist_avg_lnengage / cmt_total / aud_* / source_grp / ptype_grp /
*     pd_ok / ad_density_strict 等变量，这些在 stata_ads3.csv 中已按
*     「变量清理说明.md」删除。因此本脚本**只能搭配 stata_ads2.csv 运行**，
*     不要把它改成 stata_ads3.csv（会 variable not found）。
*     正式主脚本用 regression_final.do。
*  Y 主口径 ：ln(转发数 + 1)
*  理论框架 ：IAM（信息质量 × 来源可信度）
*  假设     ：H1a/b 规模与认证、H1c 信源质量、H1d 规模形状、
*             H2 信息质量、H3 ELM 路径替代、H4 说服知识（含 H4d 累积）、
*             H5 类型异质性
*  说明     ：kw_stratum 只进稳健性（设计变量，属坏控制）
* ============================================================
clear all
set more off
set linesize 140
set matsize 1000

import delimited "d:\AI\爬虫\stata_ads2.csv", encoding("UTF-8") clear

* ---------- 因变量与派生 ----------
gen double ln_repost  = ln(reposts + 1)
gen double logf_sq    = log_followers^2
gen byte   pos_repost = reposts > 0
gen double engage_ln  = ln(reposts + comments + likes + 1)
gen double ln_rel     = ln(reposts / (followers/10000 + 1) + 1)

* 新变量缺失标记
* 注意：必须先生成缺失标记，再填充 0；否则「缩样本提 R2」的假象（实测 n=30 时 R2 会虚高到 0.64）
gen byte has_hist = !missing(hist_avg_lnengage)
gen byte has_prior_hist = !missing(hist_prior_avg_lnengage)
gen byte has_aud  = !missing(aud_fol_med)
gen byte has_pd   = pd_ok == 1

* 缺失填充为 0，保证各规格 N 一致（缺失本身由 has_* 哑变量吸收）
replace hist_avg_lnengage = 0 if missing(hist_avg_lnengage)
replace hist_prior_avg_lnengage = 0 if missing(hist_prior_avg_lnengage)
replace hist_avg_reposts  = 0 if missing(hist_avg_reposts)
replace hist_med_reposts  = 0 if missing(hist_med_reposts)
replace ad_density        = 0 if missing(ad_density)
replace ad_density_strict = 0 if missing(ad_density_strict)
replace non_ad_avg_reposts = 0 if missing(non_ad_avg_reposts)
replace aud_fol_med       = 0 if missing(aud_fol_med)
replace aud_ver_share     = 0 if missing(aud_ver_share)
replace cmt_total         = 0 if missing(cmt_total)

* 类别编码
encode source_grp, gen(src_n)
encode link_grp,   gen(link_n)
encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode region_grp, gen(region_n)
encode ptype_grp,  gen(ptype_n)
encode kw_stratum, gen(kw_n)

* ============================================================
*  SECTION 0：样本与新变量描述
* ============================================================
display "### S0_SAMPLE_N = " _N
summarize ln_repost reposts pos_repost log_followers text_len n_images is_lottery
display "### S0_NEWVARS"
summarize hist_n hist_prior_n hist_prior_avg_lnengage hist_avg_lnengage hist_avg_reposts ad_density ad_density_strict ///
    non_ad_n non_ad_avg_reposts has_ext_link is_video_link is_lottery_link ///
    is_hot_topic det_pic_num det_text_len cmt_deep_n aud_fol_med aud_ver_share
display "### S0_PTYPE"
tab ptype_grp
display "### S0_SOURCE"
tab source_grp
display "### S0_LINKGRP"
tab link_grp
display "### S0_COVERAGE"
count if has_hist == 1
display "COVER_HIST = " r(N)
count if has_prior_hist == 1
display "COVER_PRIOR_HIST = " r(N)
count if has_pd == 1
display "COVER_PD = " r(N)
count if has_aud == 1
display "COVER_AUD = " r(N)

* 新变量与主口径的相关
display "### S0_CORR"
pwcorr ln_repost hist_prior_avg_lnengage ad_density has_ext_link is_lottery_link ///
    log_followers text_len n_images is_lottery

* ============================================================
*  SECTION 1：Q1 —— SSR / SSE / SST / RootMSE / R2 手算 vs 软件
*  沿用 A0 规格（4 个解释变量、5 个参数、df_r=206），保证可手工核算
* ============================================================
display "### Q1_MODEL_A0"
regress ln_repost log_followers text_len n_images is_lottery

scalar N_s    = e(N)
scalar k_s    = e(df_m)
scalar SSR_s  = e(mss)
scalar SSE_s  = e(rss)
scalar SST_s  = e(mss) + e(rss)
scalar R2_s   = e(r2)
scalar ADJ_s  = e(r2_a)
scalar RMSE_s = e(rmse)
scalar MSR_s  = e(mss)/e(df_m)
scalar MSE_s  = e(rss)/e(df_r)

display "Q_N_SOFT        = " N_s
display "Q_DFM_SOFT      = " k_s
display "Q_DFR_SOFT      = " N_s - k_s - 1
display "Q_SSR_SOFT      = " %15.8f SSR_s
display "Q_SSE_SOFT      = " %15.8f SSE_s
display "Q_SST_SOFT      = " %15.8f SST_s
display "Q_MSR_SOFT      = " %15.8f MSR_s
display "Q_MSE_SOFT      = " %15.8f MSE_s
display "Q_ROOTMSE_SOFT  = " %15.8f RMSE_s
display "Q_R2_SOFT       = " %15.8f R2_s
display "Q_ADJR2_SOFT    = " %15.8f ADJ_s

* --- 真手算：从数据算残差与离差（不用 e() 反推）---
predict double yhat_q1, xb
predict double resid_q1, residuals
quietly summarize ln_repost
scalar ybar_q1 = r(mean)
gen double sq_reg = (yhat_q1 - ybar_q1)^2
gen double sq_err = resid_q1^2
gen double sq_tot = (ln_repost - ybar_q1)^2
quietly summarize sq_reg
scalar SSR_m = r(sum)
quietly summarize sq_err
scalar SSE_m = r(sum)
quietly summarize sq_tot
scalar SST_m = r(sum)
scalar N_m    = N_s
scalar k_m    = k_s
scalar R2_m   = SSR_m/SST_m
scalar ADJ_m  = 1 - (1 - R2_m)*(N_m - 1)/(N_m - k_m - 1)
scalar RMSE_m = sqrt(SSE_m/(N_m - k_m - 1))
display "Q_SSR_MAN       = " %15.8f SSR_m
display "Q_SSE_MAN       = " %15.8f SSE_m
display "Q_SST_MAN       = " %15.8f SST_m
display "Q_ROOTMSE_MAN   = " %15.8f RMSE_m
display "Q_R2_MAN        = " %15.8f R2_m
display "Q_ADJR2_MAN     = " %15.8f ADJ_m
display "Q_DIFF_SSR      = " %15.10f (SSR_s - SSR_m)
display "Q_DIFF_SSE      = " %15.10f (SSE_s - SSE_m)
display "Q_DIFF_SST      = " %15.10f (SST_s - SST_m)
display "Q_DIFF_ROOTMSE  = " %15.10f (RMSE_s - RMSE_m)
display "Q_DIFF_R2       = " %15.10f (R2_s - R2_m)
display "Q_DIFF_ADJR2    = " %15.10f (ADJ_s - ADJ_m)

* 差异来源一：残差降精度（舍入累积）
gen float resid_f = resid_q1
gen double sq_err_f = resid_f^2
quietly summarize sq_err_f
scalar SSE_f  = r(sum)
scalar RMSE_f = sqrt(SSE_f/(N_m - k_m - 1))
scalar R2_f   = (SST_m - SSE_f)/SST_m
display "Q_SSE_FLOAT     = " %15.8f SSE_f
display "Q_RELDIFF_SSE_FLOAT_PCT = " %12.10f 100*(SSE_s - SSE_f)/SSE_s

* 差异来源二：调整 R2 的自由度口径写错（k 误含常数项）
scalar ADJ_wrong = 1 - (1 - R2_m)*(N_m - 1)/(N_m - k_m)
display "Q_ADJR2_WRONGK = " %15.8f ADJ_wrong
display "Q_DIFF_ADJR2_WRONGK = " %15.10f (ADJ_s - ADJ_wrong)

drop yhat_q1 resid_q1 resid_f sq_reg sq_err sq_tot sq_err_f

* ============================================================
*  SECTION 2：Q2 —— R² 阶梯（含新变量）
*  锚点：以当前样本重估的同一模型为基线（A0），目标 1.5×
* ============================================================
display "### SECTION_Q2_LADDER_REFIT_ANCHOR"

display "### Q2_B0_BASE"
regress ln_repost log_followers text_len n_images is_lottery
scalar r2_B0 = e(r2)
display "STEP B0  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N)
display "Q2_TARGET_1P5X = " %9.6f 1.5*r2_B0

* H1c：信源质量（作者历史互动率）
display "### Q2_B1_HIST"
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery
display "STEP B1  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N) " DR2=" %9.6f (e(r2)-r2_B0)

* H1d：规模形状
display "### Q2_B2_SQ"
regress ln_repost log_followers logf_sq hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery
display "STEP B2  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N) " DR2=" %9.6f (e(r2)-r2_B0)

* 帖级新变量：外链 / 热搜 / 发布工具
display "### Q2_B3_POSTVARS"
regress ln_repost log_followers logf_sq hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    has_ext_link is_lottery_link i.ptype_n i.src_n
display "STEP B3  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N) " DR2=" %9.6f (e(r2)-r2_B0)

* 受众特征
display "### Q2_B4_AUDIENCE"
regress ln_repost log_followers logf_sq hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    has_ext_link is_lottery_link i.ptype_n i.src_n aud_fol_med aud_ver_share
display "STEP B4  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N) " DR2=" %9.6f (e(r2)-r2_B0)

* 诉求类型与媒体（H3/H5 的解释变量）
display "### Q2_B5_TYPE"
regress ln_repost log_followers logf_sq hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    has_ext_link is_lottery_link i.ptype_n i.src_n aud_fol_med aud_ver_share i.appeal_n i.media_n
scalar r2_B5 = e(r2)
display "STEP B5  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N) " DR2=" %9.6f (e(r2)-r2_B0)

* 促销/品牌密度（H4）
display "### Q2_B6_PROMO"
regress ln_repost log_followers logf_sq hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    has_ext_link is_lottery_link i.ptype_n i.src_n aud_fol_med aud_ver_share i.appeal_n i.media_n ///
    n_promo n_brand
display "STEP B6  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N) " DR2=" %9.6f (e(r2)-r2_B0)

* 地域（结构类）
display "### Q2_B7_REGION"
regress ln_repost log_followers logf_sq hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    has_ext_link is_lottery_link i.ptype_n i.src_n aud_fol_med aud_ver_share i.appeal_n i.media_n ///
    n_promo n_brand i.region_n
display "STEP B7  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N) " DR2=" %9.6f (e(r2)-r2_B0)

* 抽样关键词层（坏控制，仅作对照，不计入合法提升）
* 注：kw_stratum 与 hist/ad_density 等新变量同时入模时矩阵奇异（实测 r(111)），
*     故只在"基线 + 诉求类型 + kw"的小规格里演示其虚假增益。
display "### Q2_B8_KWSTRAW_BADCONTROL"
regress ln_repost log_followers text_len n_images is_lottery i.appeal_n i.kw_n
display "STEP B8  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N) " DR2=" %9.6f (e(r2)-r2_B0)

* ============================================================
*  SECTION 3：假设检验
* ============================================================
display "### SECTION_HYPOTHESES"

* H1c 信源质量 vs H1a 规模（并列系数比较）
display "### H1_MAIN"
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist is_enterprise is_personal_verified ///
    text_len n_images is_lottery, vce(cluster author_id)
display "H1_DONE"
* 标准化系数比较（规模 vs 质量谁更强）
display "### H1_BETA_COMPARE"
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery, beta

* H1d 规模形状
display "### H1D_SHAPE"
regress ln_repost log_followers logf_sq hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery
test logf_sq
display "H1D_P = " r(p)

* H4d 说服知识累积（调节）
display "### H4D_INTERACTION"
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist ad_density n_promo n_brand ///
    c.ad_density#c.n_promo text_len n_images is_lottery, vce(cluster author_id)
test c.ad_density#c.n_promo
display "H4D_P = " r(p)
* 简单斜率：按广告密度中位数分组，直接对比两组内促销密度的系数
* 注意：Stata 的 summarize 必须加 detail 才有 r(p50)，否则 r(p50) 为缺失（实测踩坑）
quietly summarize ad_density, detail
gen byte ad_hi = ad_density > r(p50)
display "H4D_SLOPE_DIFF: 见下两组回归中 n_promo 系数与显著性对比"
* 两组各自斜率（描述性对照，供报告解释交互方向）
display "### H4D_SLOPE_LOW_DENSITY"
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist n_promo n_brand text_len n_images is_lottery if ad_hi == 0
display "### H4D_SLOPE_HIGH_DENSITY"
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist n_promo n_brand text_len n_images is_lottery if ad_hi == 1

* ============================================================
*  SECTION 4：稳健性——计数模型（处理 47% 零值）
* ============================================================
display "### SECTION_COUNT_MODELS"

* PPML（泊松伪极大似然，对零值与异方差稳健）
display "### PPML_MAIN"
poisson reposts log_followers hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    has_ext_link is_lottery_link i.ptype_n i.appeal_n, vce(robust)
display "PPML_R2 = " e(r2_p)

* 负二项
display "### NBREG_MAIN"
nbreg reposts log_followers hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    has_ext_link is_lottery_link i.ptype_n i.appeal_n
display "NBREG_ALPHA = " e(alpha)

* Hurdle 两步：先"有没有转发"，再"转发多少"
display "### HURDLE_STEP1_LOGIT"
logit pos_repost log_followers hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    has_ext_link is_lottery_link i.ptype_n i.appeal_n, vce(robust)
display "HURDLE_STEP2_NBREG"
nbreg reposts log_followers hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    has_ext_link is_lottery_link i.ptype_n i.appeal_n if pos_repost == 1, vce(robust)

* 零值占比与 Y 口径敏感性
display "### ZERO_SHARE"
count if reposts == 0
display "ZERO_PCT = " %6.2f 100*r(N)/_N
display "### Y_ALT_LNREL"
regress ln_rel log_followers hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery
display "LNREL_R2 = " %9.6f e(r2)

* ============================================================
*  SECTION 5：Q3 —— 类型异质性（H5）
* ============================================================
display "### SECTION_Q3_HETEROGENEITY"

* 组间系数差异：诉求类型 × 核心变量
display "### Q3_INTERACT_APPEAL"
* 注：不写 if 条件，避免缩样本造成 R2 虚高（事前历史缺失已填充 0 并由 has_prior_hist 吸收）
regress ln_repost c.log_followers##i.appeal_n c.text_len##i.appeal_n ///
    n_images is_lottery hist_prior_avg_lnengage has_prior_hist
testparm i.appeal_n#c.log_followers
display "Q3_APPEAL_X_LOGF_F = " r(F) " P = " r(p)
testparm i.appeal_n#c.text_len
display "Q3_APPEAL_X_TEXT_F = " r(F) " P = " r(p)
testparm i.appeal_n
display "Q3_APPEAL_MAIN_F = " r(F) " P = " r(p)

* 组间系数差异：媒体形态
display "### Q3_INTERACT_MEDIA"
regress ln_repost c.log_followers##i.media_n c.text_len##i.media_n n_images is_lottery
testparm i.media_n#c.log_followers
display "Q3_MEDIA_X_LOGF_F = " r(F) " P = " r(p)
testparm i.media_n#c.text_len
display "Q3_MEDIA_X_TEXT_F = " r(F) " P = " r(p)

* 分组估计（组内 R² 与组内显著变量）
display "### Q3_BY_APPEAL"
levelsof appeal_n, local(lv)
foreach g of local lv {
    local nm : label (appeal_n) `g'
    display "--- GROUP appeal_n=`g' (`nm') ---"
    quietly count if appeal_n == `g'
    display "N_GROUP = " r(N)
    quietly regress ln_repost log_followers text_len n_images is_lottery if appeal_n == `g'
    display "GROUP_R2 = " %9.6f e(r2) " ADJR2 = " %9.6f e(r2_a) " F = " %9.4f e(F) " P = " %9.6f Ftail(e(df_m), e(df_r), e(F))
}

* 按详情页类型（内容承载方式）分组
display "### Q3_BY_PTYPE"
levelsof ptype_n, local(lp)
foreach g of local lp {
    local nm : label (ptype_n) `g'
    quietly count if ptype_n == `g'
    display "--- GROUP ptype_n=`g' (`nm') N=" r(N) " ---"
    if r(N) >= 25 {
        quietly regress ln_repost log_followers text_len n_images is_lottery if ptype_n == `g'
        display "GROUP_R2 = " %9.6f e(r2) " ADJR2 = " %9.6f e(r2_a)
    }
    else {
        display "GROUP_SKIPPED (n<25)"
    }
}

* 组间系数差异：详情页类型 × 核心变量
display "### Q3_INTERACT_PTYPE"
regress ln_repost c.log_followers##i.ptype_n c.text_len##i.ptype_n n_images is_lottery
testparm i.ptype_n#c.log_followers
display "Q3_PTYPE_X_LOGF_F = " r(F) " P = " r(p)
testparm i.ptype_n#c.text_len
display "Q3_PTYPE_X_TEXT_F = " r(F) " P = " r(p)

display "### Q3_BY_MEDIA"
levelsof media_n, local(lm)
foreach g of local lm {
    local nm : label (media_n) `g'
    quietly count if media_n == `g'
    display "--- GROUP media_n=`g' (`nm') N=" r(N) " ---"
    quietly regress ln_repost log_followers text_len n_images is_lottery if media_n == `g'
    display "GROUP_R2 = " %9.6f e(r2) " ADJR2 = " %9.6f e(r2_a)
}

* ============================================================
*  SECTION 6：设定检验
* ============================================================
display "### SECTION_SPEC"
* 多重共线性
regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist text_len n_images is_lottery ///
    n_promo n_brand has_ext_link is_lottery_link
vif
* 异方差
estat hettest
* 残差正态性（先 predict，再跑 linktest，否则 e() 会被 linktest 覆盖）
predict double resid_v2, residuals
sktest resid_v2
* 函数形式
linktest
drop resid_v2

display "### ANALYSIS_V2 DONE"
