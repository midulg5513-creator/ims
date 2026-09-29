* ============================================================
*  regression_final.do  —— 纯多元线性回归版（按作业要求更正）
*
*  作业要求：必须使用「多元线性回归模型」
*  ⇒ 本脚本所有估计命令一律只用 regress
*  ⇒ 原 econometric_final.do 里的 poisson(PPML) / nbreg / logit(hurdle)
*     不是多元线性回归，已全部移出
*  ⇒ vce(hc3) 只是换标准误算法，仍属 OLS，保留
*
*  样本：stata_ads3.csv（变量清理版），211 条微博广告帖
*        ← 2026-09-24 由 stata_ads2.csv 切换而来，依据见「变量清理说明.md」
*  因变量：ln_repost = ln(转发数 + 1)（新表已内置，无需再 gen）
*
*  注意：用 StataMP /e 批处理时 Stata 会自动写 <脚本名>.log，
*        所以本脚本不再自带 log using，否则报 r(608)。
* ============================================================
clear all
set more off
set linesize 200

import delimited "d:\AI\爬虫\stata_ads3.csv", encoding("UTF-8") clear

* ⚠️ 精度修正（实测见 check_stata_types.do）：import delimited 会把含小数的列存成
*    float（4 字节）；numericcols() 也是 float，recast 救不回已丢的位数。
*    ⇒ 必须 drop 后用 gen double 重算，口径与 CSV 内完全一致（差异仅浮点）。
*    本块必须在 gen lnf_sq 之前，否则 lnf_sq 会被 float 污染。
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

* ---------------- 变量工程 ----------------
* 新表已内置：ln_repost / ln_followers（真正的自然对数）/ lnf_c / lnf_c2 /
*             hist_prior_lnengage0 / has_prior_hist / text_len100 / n_pics /
*             n_mentions / n_mentions_c / ln_age_hours，因此这里不再重复生成。
gen double lnf_sq = ln_followers^2      // 粉丝对数平方（未中心化口径，与论文主表一致）
gen double tl     = text_len100         // 文本长度（百字），避免 text_len^2 达 1e6 造成病态条件数
gen double tl_sq  = tl^2
gen byte   is_video = (media_type == "video")

encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode region_grp, gen(region_n)

label var ln_repost            "ln(转发数+1)"
label var ln_followers         "ln(粉丝数)"
label var lnf_sq               "ln(粉丝数)平方"
label var lnf_c                "ln(粉丝数)中心化"
label var lnf_c2               "ln(粉丝数)中心化平方"
label var hist_prior_lnengage0 "事前作者互动质量(缺失填0)"
label var text_len             "文本长度"
label var text_len100          "文本长度(百字)"
label var n_pics               "图片数量(已解截断)"
label var is_lottery           "抽奖机制"
label var ln_age_hours         "曝光时长(对数)"
label var n_topics             "话题数量"
label var n_mentions           "@提及数(原始计数)"
label var n_mentions_c         "@提及数(3+截尾，稳健性用)"
label var n_promo              "促销词数量"
label var n_brand              "品牌词数量"

* ============================================================
* 0. 数据说明
* ============================================================
display "### 0_DATA"
count
display "N = " r(N)
egen byte _tag = tag(author_id)
count if _tag
display "N_AUTHORS = " r(N)
drop _tag
count if reposts == 0
display "ZERO_REPOST_SHARE = " %9.6f r(N)/_N
summarize reposts ln_repost ln_followers hist_prior_lnengage0 ///
    text_len n_pics is_lottery ln_age_hours, detail

* ============================================================
* 1. 回归前的前提检验
* ============================================================
display "### 1_DIAGNOSTICS"

display "--- 相关系数矩阵 ---"
corr ln_repost ln_followers hist_prior_lnengage0 text_len ///
     n_pics is_lottery ln_age_hours

display "--- 多重共线性 VIF（阈值 10）---"
* 注意：必须把 lnf_sq 也放进来检查！
* 只检查 ln_followers 而不检查 lnf_sq，会漏掉 x 与 x² 的机械共线（实测 VIF 达 15）
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions
estat vif

display "--- 中心化后的 VIF（对照：共线应消失）---"
regress ln_repost lnf_c lnf_c2 hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions
estat vif

* 联合检验：二次项规格下 x 与 x² 应联合检验，不能只看单个系数
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions
test ln_followers lnf_sq
display "FAN_JOINT_LIN+QUAD F=" r(F) " P=" r(p)

display "--- 中心化规格（两个粉丝项应都显著，R2 不变）---"
regress ln_repost lnf_c lnf_c2 hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions

display "--- 异方差：Breusch-Pagan ---"
estat hettest
display "--- 异方差：White ---"
estat imtest, white

* ============================================================
* 2. Q1 —— 教学规格的平方和与 R²
* ============================================================
display "### 2_Q1_TEACHING_OLS"
regress ln_repost ln_followers text_len n_pics is_lottery

scalar Q_SSR  = e(mss)
scalar Q_SSE  = e(rss)
scalar Q_SST  = e(mss) + e(rss)
scalar Q_MSR  = Q_SSR / e(df_m)
scalar Q_MSE  = Q_SSE / e(df_r)
scalar Q_RMSE = sqrt(Q_MSE)
scalar Q_R2   = Q_SSR / Q_SST
scalar Q_AR2  = 1 - (1 - Q_R2) * (e(N) - 1) / e(df_r)

display "### Q1_RESULTS"
display "Q1_N       = " %12.0f e(N)
display "Q1_K       = " %12.0f e(df_m)
display "Q1_DFR     = " %12.0f e(df_r)
display "Q1_SSR     = " %18.8f Q_SSR
display "Q1_SSE     = " %18.8f Q_SSE
display "Q1_SST     = " %18.8f Q_SST
display "Q1_MSR     = " %18.8f Q_MSR
display "Q1_MSE     = " %18.8f Q_MSE
display "Q1_ROOTMSE = " %18.8f Q_RMSE
display "Q1_R2      = " %18.8f Q_R2
display "Q1_ADJR2   = " %18.8f Q_AR2
display "Q1_CHK_SSR_PLUS_SSE_MINUS_SST = " %18.8f Q_SSR + Q_SSE - Q_SST
display "Q1_CHK_1_MINUS_SSE_OVER_SST   = " %18.8f 1 - Q_SSE / Q_SST

* 用 predict 从数据真算，供手算核对（不是从 e() 反推）
predict double yhat_q1, xb
predict double resid_q1, residuals
quietly summarize ln_repost
scalar YBAR = r(mean)
gen double dev_y   = (ln_repost - YBAR)^2
gen double dev_hat = (yhat_q1 - YBAR)^2
gen double dev_res = resid_q1^2
quietly summarize dev_y
scalar H_SST = r(sum)
quietly summarize dev_hat
scalar H_SSR = r(sum)
quietly summarize dev_res
scalar H_SSE = r(sum)
display "### Q1_HAND"
display "HAND_SST = " %18.8f H_SST
display "HAND_SSR = " %18.8f H_SSR
display "HAND_SSE = " %18.8f H_SSE
display "HAND_R2  = " %18.8f H_SSR / H_SST
display "DIFF_SSR = " %18.10f H_SSR - Q_SSR
display "DIFF_SSE = " %18.10f H_SSE - Q_SSE
drop yhat_q1 resid_q1 dev_y dev_hat dev_res

* ============================================================
* 3. Q2 —— 同一 211 样本上的多元线性回归阶梯
* ============================================================
display "### 3_Q2_LADDER"

regress ln_repost ln_followers text_len n_pics is_lottery
scalar BASE_R2 = e(r2)
display "M0        R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
display "Q2_TARGET_1P5X = " %9.6f 1.5 * BASE_R2

regress ln_repost ln_followers text_len n_pics is_lottery ln_age_hours
display "M1_AGE    R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
test ln_age_hours
display "  dF_AGE  F=" r(F) " p=" r(p)

regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours
display "M2_HIST   R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
test hist_prior_lnengage0 has_prior_hist
display "  dF_HIST F=" r(F) " p=" r(p)

regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours
display "M3_QUAD   R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
test lnf_sq
display "  dF_QUAD F=" r(F) " p=" r(p)

regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions
display "M4_INFO   R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
test n_topics n_mentions
display "  dF_INFO F=" r(F) " p=" r(p)

regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand
display "M5_PROMO  R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
test n_promo n_brand
display "  dF_PROMO F=" r(F) " p=" r(p)

regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified
display "M6_VERIFY R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
test is_enterprise is_personal_verified
display "  dF_VERIFY F=" r(F) " p=" r(p)

regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n
display "M7_MEDIA  R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
testparm i.media_n
display "  dF_MEDIA F=" r(F) " p=" r(p)

regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n i.appeal_n
display "M8_APPEAL R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
testparm i.appeal_n
display "  dF_APPEAL F=" r(F) " p=" r(p)

regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n i.appeal_n ///
    i.region_n
display "M9_REGION R2=" %9.6f e(r2) "  ADJR2=" %9.6f e(r2_a) "  k=" e(df_m)
testparm i.region_n
display "  dF_REGION F=" r(F) " p=" r(p)

* ---------------- 主研究模型：HC3 稳健标准误（仍是多元线性回归）--------
display "### 4_MAIN_OLS_HC3"
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n i.appeal_n, ///
    vce(hc3)
display "MAIN_R2 = " %9.6f e(r2) "  MAIN_ADJR2 = " %9.6f e(r2_a)

display "### 4B_MAIN_OLS_BETA"
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n i.appeal_n, ///
    vce(hc3) beta

* ============================================================
* 5. Q3 —— 不同类型的多元线性回归
* ============================================================
display "### 5_Q3_GROUPS"

levelsof appeal_n, local(gs)
foreach g of local gs {
    quietly count if appeal_n == `g'
    local nn = r(N)
    if `nn' >= 25 {
        display "--- appeal group `g'  n=`nn' ---"
        regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
            text_len n_pics is_lottery ln_age_hours if appeal_n == `g', vce(hc3)
        display "GROUP_appeal`g'_N=" e(N) " R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a)
    }
    else {
        display "GROUP appeal `g' SKIPPED (n=`nn' < 25)"
    }
}

levelsof media_n, local(ms)
foreach m of local ms {
    quietly count if media_n == `m'
    local nn = r(N)
    if `nn' >= 25 {
        display "--- media group `m'  n=`nn' ---"
        regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
            text_len n_pics is_lottery ln_age_hours if media_n == `m', vce(hc3)
        display "GROUP_media`m'_N=" e(N) " R2=" %9.6f e(r2) " ADJR2=" %9.6f e(r2_a)
    }
    else {
        display "GROUP media `m' SKIPPED (n=`nn' < 25)"
    }
}

display "### 5_Q3_INTERACTIONS"
regress ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n ///
    hist_prior_lnengage0 has_prior_hist n_pics is_lottery ln_age_hours, vce(hc3)
testparm i.appeal_n#c.ln_followers
display "APPEAL_X_FOLLOWERS_F=" r(F) " P=" r(p)
testparm i.appeal_n#c.text_len
display "APPEAL_X_TEXT_F=" r(F) " P=" r(p)

regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics ln_age_hours i.is_video##i.is_lottery, vce(hc3)
testparm i.is_video#i.is_lottery
display "VIDEO_X_LOTTERY_F=" r(F) " P=" r(p)

display "### REGRESSION_FINAL DONE"
