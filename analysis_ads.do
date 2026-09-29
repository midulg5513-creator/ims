* ============================================================
*  路线 B：微博广告帖影响力 —— 只在广告帖内部（n=211）
*  Y 主口径  ：ln(reposts + 1)                       转发数
*  Y 参考口径：ln(reposts + comments + likes + 1)
*  Y 相对口径：ln(reposts / 每万粉 + 1)
*
*  样本不使用 is_ad，因此不需要「非广告」对照组
*  抽样设计变量 kw_stratum 只进稳健性，不进主模型（它是坏控制）
* ============================================================
clear all
set more off
set linesize 130

import delimited "d:\AI\爬虫\stata_ads.csv", encoding("UTF-8") clear

display "### SAMPLE_N = " _N

* ---------- 因变量 ----------
gen double ln_repost = ln(reposts + 1)
gen double ln_sum    = ln(reposts + comments + likes + 1)
gen double repost_per10k = reposts / (followers/10000 + 1)
gen double ln_rel    = ln(repost_per10k + 1)
label variable ln_repost "ln(转发数+1)"

* ---------- 二次项与类别编码 ----------
gen double logf_sq = log_followers^2
encode appeal_grp,  gen(appeal_n)
encode media_type,  gen(media_n)
encode kw_stratum,  gen(kw_n)
encode region_grp,  gen(region_n)
encode ad_type,     gen(adtype_n)

* ============================================================
*  SECTION DESCRIPTIVES
* ============================================================
display "### SECTION_DESCRIPTIVES"
summarize ln_repost reposts log_followers followers text_len n_images ///
    n_mentions pub_hour is_lottery is_enterprise is_personal_verified ///
    n_promo n_brand
display "### ZERO_SHARE"
count if reposts == 0
display "ZERO_N = " r(N)
display "ZERO_PCT = " %6.2f 100*r(N)/_N

* ============================================================
*  Q1：SSR / SSE / SST / Root MSE / R2 / 调整R2 —— 手算 vs 软件
*  模型取 A0（k=5，df_r=206），便于手工核算
* ============================================================
display "### Q1_MODEL_A0"
regress ln_repost log_followers text_len n_images is_lottery

* --- 先把软件值存成 scalar，避免后续 summarize 覆盖 e() ---
scalar N_s    = e(N)
scalar k_s    = e(df_m)          /* 不含常数项的自变量个数 */
scalar SSR_s  = e(mss)
scalar SSE_s  = e(rss)
scalar SST_s  = e(mss) + e(rss)
scalar R2_s   = e(r2)
scalar ADJ_s  = e(r2_a)
scalar RMSE_s = e(rmse)
scalar MSR_s  = e(mss)/e(df_m)
scalar MSE_s  = e(rss)/e(df_r)

display "Q_N_SOFT    = " N_s
display "Q_DFM_SOFT  = " k_s
display "Q_DFR_SOFT  = " N_s - k_s - 1
display "Q_SSR_SOFT  = " %15.8f SSR_s
display "Q_SSE_SOFT  = " %15.8f SSE_s
display "Q_SST_SOFT  = " %15.8f SST_s
display "Q_MSR_SOFT  = " %15.8f MSR_s
display "Q_MSE_SOFT  = " %15.8f MSE_s
display "Q_ROOTMSE_SOFT = " %15.8f RMSE_s
display "Q_R2_SOFT   = " %15.8f R2_s
display "Q_ADJR2_SOFT = " %15.8f ADJ_s

* --- 真手算：从数据本身算残差与离差，而不是从 e() 反推 ---
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

display "Q_SSR_MAN   = " %15.8f SSR_m
display "Q_SSE_MAN   = " %15.8f SSE_m
display "Q_SST_MAN   = " %15.8f SST_m
display "Q_ROOTMSE_MAN = " %15.8f RMSE_m
display "Q_R2_MAN    = " %15.8f R2_m
display "Q_ADJR2_MAN = " %15.8f ADJ_m

* --- 差异 ---
display "Q_DIFF_SSR    = " %15.10f (SSR_s - SSR_m)
display "Q_DIFF_SSE    = " %15.10f (SSE_s - SSE_m)
display "Q_DIFF_SST    = " %15.10f (SST_s - SST_m)
display "Q_DIFF_ROOTMSE= " %15.10f (RMSE_s - RMSE_m)
display "Q_DIFF_R2     = " %15.10f (R2_s - R2_m)
display "Q_DIFF_ADJR2  = " %15.10f (ADJ_s - ADJ_m)
display "Q_RELDIFF_SSE_PCT = " %12.10f 100*(SSE_s - SSE_m)/SSE_s

* --- 差异来源之一：把残差降到 float 精度，看舍入如何放大差异 ---
gen float resid_f = resid_q1
gen double sq_err_f = resid_f^2
quietly summarize sq_err_f
scalar SSE_f   = r(sum)
scalar RMSE_f  = sqrt(SSE_f/(N_m - k_m - 1))
scalar R2_f    = (SST_m - SSE_f)/SST_m
display "Q_SSE_FLOAT    = " %15.8f SSE_f
display "Q_DIFF_SSE_FLOAT = " %15.10f (SSE_s - SSE_f)
display "Q_RELDIFF_SSE_FLOAT_PCT = " %12.10f 100*(SSE_s - SSE_f)/SSE_s

* --- 差异来源之二：自由度口径写错（k 含常数项）会怎样 ---
scalar ADJ_wrong = 1 - (1 - R2_m)*(N_m - 1)/(N_m - k_m)
display "Q_ADJR2_WRONGK = " %15.8f ADJ_wrong
display "Q_DIFF_ADJR2_WRONGK = " %15.10f (ADJ_s - ADJ_wrong)

drop yhat_q1 resid_q1 resid_f sq_reg sq_err sq_tot sq_err_f

* ============================================================
*  Q2：R2 阶梯（A0 -> A9）
*  内容类变量：诉求类型 / 媒体类型 / 认证 / 文本特征
*  结构类变量：抽样关键词层 / 地域（只提拟合，不改结论）
* ============================================================
display "### SECTION_Q2_LADDER"

display "### Q2_A0"
regress ln_repost log_followers text_len n_images is_lottery
scalar r2_A0 = e(r2)
display "STEP A0  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " N=" e(N)

display "### Q2_A1"
regress ln_repost log_followers logf_sq text_len n_images is_lottery
display "STEP A1  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " DR2=" %9.6f (e(r2)-r2_A0)

display "### Q2_A2"
regress ln_repost log_followers logf_sq text_len n_images is_lottery n_mentions
scalar r2_A2 = e(r2)
display "STEP A2  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " DR2=" %9.6f (e(r2)-r2_A0)

display "### Q2_A3"
regress ln_repost log_followers logf_sq text_len n_images is_lottery ///
    n_mentions pub_hour is_weekend
display "STEP A3  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " DR2=" %9.6f (e(r2)-r2_A0)

display "### Q2_A4"
regress ln_repost log_followers logf_sq text_len n_images ///
    n_mentions pub_hour is_weekend i.appeal_n
display "STEP A4  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " DR2=" %9.6f (e(r2)-r2_A0)

display "### Q2_A5"
regress ln_repost log_followers logf_sq text_len n_images ///
    n_mentions pub_hour is_weekend i.appeal_n i.media_n
display "STEP A5  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " DR2=" %9.6f (e(r2)-r2_A0)

display "### Q2_A6"
regress ln_repost log_followers logf_sq text_len n_images ///
    n_mentions pub_hour is_weekend is_enterprise is_personal_verified ///
    i.appeal_n i.media_n
display "STEP A6  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " DR2=" %9.6f (e(r2)-r2_A0)

display "### Q2_A7"
regress ln_repost log_followers logf_sq text_len n_images ///
    n_mentions pub_hour is_weekend is_enterprise is_personal_verified ///
    n_promo n_brand i.appeal_n i.media_n
display "STEP A7  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " DR2=" %9.6f (e(r2)-r2_A0)

display "### Q2_A8"
regress ln_repost log_followers logf_sq text_len n_images ///
    n_mentions pub_hour is_weekend is_enterprise is_personal_verified ///
    n_promo n_brand i.appeal_n i.media_n i.kw_n
scalar r2_A8 = e(r2)
display "STEP A8  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " DR2=" %9.6f (e(r2)-r2_A0)

display "### Q2_A9"
regress ln_repost log_followers logf_sq text_len n_images ///
    n_mentions pub_hour is_weekend is_enterprise is_personal_verified ///
    n_promo n_brand i.appeal_n i.media_n i.kw_n i.region_n
display "STEP A9  R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a) " K=" e(df_m)+1 " DR2=" %9.6f (e(r2)-r2_A0)

display "Q2_TARGET_1P5X = " %9.6f 1.5*r2_A0
display "Q2_CONTENT_ONLY_R2 = " %9.6f r2_A2
display "Q2_STRUCT_R2 = " %9.6f r2_A8
display "Q2_STRUCT_GAIN = " %9.6f (r2_A8 - r2_A2)

* 参考口径（含评论与点赞）
display "### Q2_REF_LNSUM_A0"
regress ln_sum log_followers text_len n_images is_lottery
display "REFA0 R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a)

* ============================================================
*  Q3：不同类型广告帖的影响因素
*  分组回归（去掉 is_lottery，避免与「抽奖导流」组完全共线）
* ============================================================
display "### SECTION_Q3_SUBGROUP"

display "### Q3_BY_APPEAL"
levelsof appeal_grp, local(levels)
foreach lv of local levels {
    quietly count if appeal_grp == "`lv'"
    if r(N) >= 25 {
        display "### Q3_GROUP_START " "`lv'"
        regress ln_repost log_followers text_len n_images n_mentions ///
            pub_hour is_weekend if appeal_grp == "`lv'"
        display "G_NAME=" "`lv'" " G_N=" e(N) " G_R2=" %9.6f e(r2)
        display "### Q3_GROUP_END " "`lv'"
    }
    else {
        display "### Q3_GROUP_SKIP " "`lv'" " N=" r(N) " (< 25)"
    }
}

display "### Q3_BY_MEDIA"
levelsof media_type, local(levels)
foreach lv of local levels {
    quietly count if media_type == "`lv'"
    if r(N) >= 25 {
        display "### Q3_MEDIA_START " "`lv'"
        regress ln_repost log_followers text_len n_images n_mentions ///
            pub_hour is_weekend if media_type == "`lv'"
        display "M_NAME=" "`lv'" " M_N=" e(N) " M_R2=" %9.6f e(r2)
        display "### Q3_MEDIA_END " "`lv'"
    }
    else {
        display "### Q3_MEDIA_SKIP " "`lv'" " N=" r(N) " (< 25)"
    }
}

* --- 组间差异检验：交互项 F 检验（不能直接比分组系数） ---
display "### Q3_INTERACTION_APPEAL"
regress ln_repost log_followers text_len n_images n_mentions ///
    pub_hour is_weekend i.appeal_n
display "INT_APPEAL_F      = " %9.6f e(F)
display "INT_APPEAL_P      = " %9.6f Ftail(e(df_m), e(df_r), e(F))
display "INT_APPEAL_R2     = " %9.6f e(r2)

display "### Q3_INTERACTION_MEDIA"
regress ln_repost log_followers text_len n_images n_mentions ///
    pub_hour is_weekend i.media_n
display "INT_MEDIA_F       = " %9.6f e(F)
display "INT_MEDIA_P       = " %9.6f Ftail(e(df_m), e(df_r), e(F))

* --- 抽奖机制的独立效应（H1）---
display "### Q3_LOTTERY_EFFECT"
regress ln_repost log_followers logf_sq text_len n_images is_lottery n_mentions
display "LOT_BETA  = " %12.6f _b[is_lottery]
display "LOT_SE    = " %12.6f _se[is_lottery]
display "LOT_T     = " %12.6f _b[is_lottery]/_se[is_lottery]
display "LOT_IRR   = " %12.6f exp(_b[is_lottery])

* --- 剔除抽奖组后，内容类变量还有没有解释力 ---
display "### Q3_NO_LOTTERY_SUBSAMPLE"
regress ln_repost log_followers text_len n_images n_mentions ///
    pub_hour is_weekend if is_lottery == 0
display "NOLOT_N   = " e(N)
display "NOLOT_R2  = " %9.6f e(r2)

* ============================================================
*  SECTION ROBUSTNESS
* ============================================================
display "### ROB_CLUSTER_AUTHOR"
regress ln_repost log_followers logf_sq text_len n_images is_lottery ///
    n_mentions, vce(cluster author_id)
display "ROBCL_R2 = " %9.6f e(r2)
display "ROBCL_B_LOT = " %12.6f _b[is_lottery]

display "### ROB_RELATIVE_DV"
regress ln_rel log_followers logf_sq text_len n_images is_lottery n_mentions
display "RELDV_R2 = " %9.6f e(r2)

display "### ROB_DROP_TOP1PCT"
quietly summarize ln_repost, detail
scalar p99 = r(p99)
regress ln_repost log_followers logf_sq text_len n_images is_lottery ///
    n_mentions if ln_repost <= p99
display "DTOP1_N  = " e(N)
display "DTOP1_R2 = " %9.6f e(r2)

display "### ROB_LINKTEST"
quietly regress ln_repost log_followers logf_sq text_len n_images is_lottery n_mentions
linktest
display "ROB_DONE"
display "### ALL DONE"
