* ============================================================
*  reproduce_all.do —— 一键复现全部结果 + 自动核对
*
*  用法（二选一）：
*    A. 图形界面：Stata 菜单 File > Do... 选本文件（或 do-file 编辑器里 Ctrl+D）
*    B. 命令行  ：do "d:\AI\爬虫\reproduce_all.do"
*
*  数据：stata_ads3.csv（211 条广告帖，变量清理版）—— 这是当前建模主数据
*        ← 2026-09-24 由 stata_ads2.csv 切换而来，依据见「变量清理说明.md」
*
*  跑完最后会打印一张「核对清单」，把你算出的值和预期值逐项对比，
*  完全一致会显示 [OK]，不一致显示 [!!] 并给出差异。
* ============================================================

clear all
set more off
set linesize 200

* 说明：本脚本刻意「不自带 log using」。原因：
*   - /e 批处理模式下 Stata 会自动生成 reproduce_all.log；
*     若脚本里再 log using 一个日志，两个日志同时打开会让系数表渲染失败，
*     报 _coef_table(): member _b_stat::set_memat() not found 然后 r(1) 中断。
*   - 图形界面运行时结果直接显示在 Results 窗口，需要存档就右键 Save Results。

* ------------------------------------------------------------
* 0. 读数据 + 变量工程
* ------------------------------------------------------------
display _n(2) "{hline 70}"
display "步骤 0：读入建模数据并生成变量"
display "{hline 70}"

cd "d:\AI\爬虫"
import delimited "stata_ads3.csv", encoding("UTF-8") clear

* ⚠️ 精度修正：import delimited 把含小数的列存成 float，用原始整数重算恢复双精度
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

count
display "样本量 N = " r(N) "   （预期 211）"

* stata_ads3.csv 已内置：ln_repost / ln_followers / lnf_c / lnf_c2 /
*   hist_prior_lnengage0 / has_prior_hist / text_len100 / n_pics /
*   n_mentions / n_mentions_c / ln_age_hours，因此不再重复生成
gen double lnf_sq   = ln_followers^2
gen double tl        = text_len100      // 以百字为单位，避免病态条件数
gen double tl_sq     = tl^2
gen byte   is_video = (media_type == "video")

encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode region_grp, gen(region_n)

display "变量生成完成：lnf_sq / tl / tl_sq / is_video"
display "               appeal_n / media_n / region_n"

* ------------------------------------------------------------
* 1. Q1：教学规格的平方和与 R²
* ------------------------------------------------------------
display _n(2) "{hline 70}"
display "步骤 1：Q1 基准回归"
display "{hline 70}"

regress ln_repost ln_followers text_len n_pics is_lottery

scalar Q_SSR  = e(mss)
scalar Q_SSE  = e(rss)
scalar Q_SST  = e(mss) + e(rss)
scalar Q_MSR  = Q_SSR / e(df_m)
scalar Q_MSE  = Q_SSE / e(df_r)
scalar Q_RMSE = sqrt(Q_MSE)
scalar Q_R2   = Q_SSR / Q_SST
scalar Q_AR2  = 1 - (1 - Q_R2) * (e(N) - 1) / e(df_r)

display _n "---- Q1 手算结果 ----"
display "SSR     = SSR/k? 不, = e(mss)        = " %18.8f Q_SSR
display "SSE     = e(rss)                    = " %18.8f Q_SSE
display "SST     = SSR + SSE                 = " %18.8f Q_SST
display "MSR     = SSR / k                   = " %18.8f Q_MSR
display "MSE     = SSE / (N-k-1)             = " %18.8f Q_MSE
display "RootMSE = sqrt(MSE)                 = " %18.8f Q_RMSE
display "R2      = SSR / SST                 = " %18.8f Q_R2
display "AdjR2   = 1-(1-R2)(N-1)/(N-k-1)     = " %18.8f Q_AR2

* 用 predict 真算残差，和 e() 对比
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

display _n "---- 用 predict 真算（手算）----"
display "手算 SST = " %18.8f H_SST
display "手算 SSR = " %18.8f H_SSR
display "手算 SSE = " %18.8f H_SSE
display _n "---- 手算 vs 软件 ----"
display "SSR 差异 = " %20.12f H_SSR - Q_SSR
display "SSE 差异 = " %20.12f H_SSE - Q_SSE
display "SST 差异 = " %20.12f H_SST - Q_SST
display "(差异应为 1e-12 量级的浮点舍入，不是 0，也不是 1e-3)"

drop yhat_q1 resid_q1 dev_y dev_hat dev_res

* ------------------------------------------------------------
* 2. Q2：多元线性回归阶梯
* ------------------------------------------------------------
display _n(2) "{hline 70}"
display "步骤 2：Q2 逐步提高 R²（目标 = 1.5 × 基准 R²）"
display "{hline 70}"

scalar TARGET = 1.5 * Q_R2
display _n "目标 R² = 1.5 × " %9.6f Q_R2 " = " %9.6f TARGET

* ---- M0 基准（= Q1 规格）----
scalar R2_M0 = Q_R2
scalar A2_M0 = Q_AR2
display _n "M0  基准             R2=" %9.6f R2_M0 "  AdjR2=" %9.6f A2_M0

* ---- M1 + 曝光时长 ----
regress ln_repost ln_followers text_len n_pics is_lottery ln_age_hours
scalar R2_M1 = e(r2)
scalar A2_M1 = e(r2_a)
display "M1  +曝光时长         R2=" %9.6f R2_M1 "  AdjR2=" %9.6f A2_M1

* ---- M2 + 事前作者互动质量 ----
regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours
scalar R2_M2 = e(r2)
scalar A2_M2 = e(r2_a)
display "M2  +事前互动质量     R2=" %9.6f R2_M2 "  AdjR2=" %9.6f A2_M2

* ---- M3 + 粉丝规模二次项 ----
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours
scalar R2_M3 = e(r2)
scalar A2_M3 = e(r2_a)
display "M3  +粉丝二次项       R2=" %9.6f R2_M3 "  AdjR2=" %9.6f A2_M3

* ---- M4 + 话题数、@提及数 ----
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions
scalar R2_M4 = e(r2)
scalar A2_M4 = e(r2_a)
display "M4  +话题数/@数       R2=" %9.6f R2_M4 "  AdjR2=" %9.6f A2_M4

* ---- M5 + 促销词、品牌词 ----
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions n_promo n_brand
scalar R2_M5 = e(r2)
scalar A2_M5 = e(r2_a)
display "M5  +促销词/品牌词    R2=" %9.6f R2_M5 "  AdjR2=" %9.6f A2_M5

* ---- M6 + 认证身份 ----
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified
scalar R2_M6 = e(r2)
scalar A2_M6 = e(r2_a)
display "M6  +认证身份         R2=" %9.6f R2_M6 "  AdjR2=" %9.6f A2_M6

* ---- M7 + 媒体形态 ----
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n
scalar R2_M7 = e(r2)
scalar A2_M7 = e(r2_a)
display "M7  +媒体形态         R2=" %9.6f R2_M7 "  AdjR2=" %9.6f A2_M7

* ---- M8 + 诉求类型 ----
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n i.appeal_n
scalar R2_M8 = e(r2)
scalar A2_M8 = e(r2_a)
display "M8  +诉求类型         R2=" %9.6f R2_M8 "  AdjR2=" %9.6f A2_M8

* ---- M9 + 地域 ----
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n i.appeal_n ///
    i.region_n
scalar R2_M9 = e(r2)
scalar A2_M9 = e(r2_a)
display "M9  +地域             R2=" %9.6f R2_M9 "  AdjR2=" %9.6f A2_M9

display _n "M4 是首个达标模型：R2 = " %9.6f R2_M4 " ≥ " %9.6f TARGET

* ------------------------------------------------------------
* 3. 主研究模型（HC3 稳健标准误，仍是多元线性回归）
* ------------------------------------------------------------
display _n(2) "{hline 70}"
display "步骤 3：主研究模型（HC3）"
display "{hline 70}"

regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n i.appeal_n, ///
    vce(hc3)
scalar MAIN_R2 = e(r2)
scalar MAIN_A2 = e(r2_a)
display "主模型 R2 = " %9.6f MAIN_R2 "   AdjR2 = " %9.6f MAIN_A2

* 保存主模型系数，供核对
scalar B_HIST = _b[hist_prior_lnengage0]

* ------------------------------------------------------------
* 4. Q3：分组回归
* ------------------------------------------------------------
display _n(2) "{hline 70}"
display "步骤 4：Q3 分类型回归（只报 n ≥ 25 的组）"
display "{hline 70}"

* 诉求类型（按 encode 后的编号 1-5，标签见下方）
scalar R2_G1 = .
scalar R2_G2 = .
scalar R2_G3 = .
scalar R2_G4 = .
scalar R2_G5 = .
forvalues g = 1/5 {
    quietly count if appeal_n == `g'
    if r(N) >= 25 {
        quietly regress ln_repost ln_followers hist_prior_lnengage0 ///
            has_prior_hist text_len n_pics is_lottery ln_age_hours ///
            if appeal_n == `g', vce(hc3)
        scalar R2_G`g' = e(r2)
        display "诉求组 `g'  n=" %4.0f e(N) "   R2=" %9.6f e(r2) "   AdjR2=" %9.6f e(r2_a)
    }
    else {
        display "诉求组 `g'  跳过（n<25）"
    }
}

* 媒体形态
scalar R2_MI = .
scalar R2_MV = .
forvalues m = 1/4 {
    quietly count if media_n == `m'
    if r(N) >= 25 {
        quietly regress ln_repost ln_followers hist_prior_lnengage0 ///
            has_prior_hist text_len n_pics is_lottery ln_age_hours ///
            if media_n == `m', vce(hc3)
        local nm : label (media_n) `m'
        display "媒体组 `m' (`nm')  n=" %4.0f e(N) "   R2=" %9.6f e(r2)
        if "`nm'" == "image"  scalar R2_MI = e(r2)
        if "`nm'" == "video"  scalar R2_MV = e(r2)
    }
}

display _n "诉求类型编码对照（encode 结果）："
label list appeal_n
display "媒体类型编码对照："
label list media_n

* ------------------------------------------------------------
* 5. Q3：组间差异的正式检验
* ------------------------------------------------------------
display _n(2) "{hline 70}"
display "步骤 5：组间交互（联合 Wald 检验）"
display "{hline 70}"

regress ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n ///
    hist_prior_lnengage0 has_prior_hist n_pics is_lottery ln_age_hours, vce(hc3)
testparm i.appeal_n#c.ln_followers
scalar F_ALOGF = r(F)
scalar P_ALOGF = r(p)
display "诉求 × 粉丝规模   F=" %8.6f r(F) "  p=" %8.6f r(p)

testparm i.appeal_n#c.text_len
scalar F_ATEXT = r(F)
scalar P_ATEXT = r(p)
display "诉求 × 文本长度   F=" %8.6f r(F) "  p=" %8.6f r(p)

regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics ln_age_hours i.is_video##i.is_lottery, vce(hc3)
testparm i.is_video#i.is_lottery
scalar F_VLOT = r(F)
scalar P_VLOT = r(p)
display "视频 × 抽奖       F=" %8.6f r(F) "  p=" %8.6f r(p)

* ------------------------------------------------------------
* 6. 核对清单：自动比对预期值
* ------------------------------------------------------------
display _n(2) "{hline 70}"
display "步骤 6：结果核对清单"
display "{hline 70}"
display "  [OK] = 与预期一致（容差 1e-5）   [!!] = 不一致，请检查数据或变量工程"
display ""

* 定义核对宏
capture program drop chknum
program define chknum
    args label got want
    scalar _d = abs(`got' - `want')
    local flag = cond(_d < 1e-5, "[OK]", "[!!]")
    display "  `flag'  `label'" _col(34) "算得 " %18.8f `got' _col(58) "预期 " %18.8f `want'
end

display _n "（下列预期值为 stata_ads3.csv 实测值，2026-09-24）"
display "---- Q1 ----"
chknum "SSR"          Q_SSR  379.27156101
chknum "SSE"          Q_SSE  849.71263382
chknum "SST"          Q_SST  1228.98419483
chknum "MSR"          Q_MSR  94.81789025
chknum "MSE"          Q_MSE  4.12481861
chknum "Root MSE"     Q_RMSE 2.03096495
chknum "R2"           Q_R2   0.30860573
chknum "Adj R2"       Q_AR2  0.29518060

display _n "---- Q2 阶梯 ----"
chknum "M0 基准"        R2_M0 0.30860573
chknum "M1 +曝光时长"   R2_M1 0.312457
chknum "M2 +事前互动"   R2_M2 0.449215
chknum "M3 +粉丝二次项" R2_M3 0.460951
chknum "M4 +话题/@数"   R2_M4 0.465922
chknum "M5 +促销/品牌"  R2_M5 0.474817
chknum "M6 +认证"       R2_M6 0.479310
chknum "M7 +媒体"       R2_M7 0.479460
chknum "M8 +诉求类型"   R2_M8 0.486908
chknum "M9 +地域"       R2_M9 0.499844
chknum "目标 1.5x"      TARGET 0.462909

display _n "---- 主模型 ----"
chknum "主模型 R2"      MAIN_R2 0.486908
chknum "主模型 Adj R2"  MAIN_A2 0.432898
chknum "hist_prior 系数" B_HIST 0.3699421

display _n "---- Q3 分组 R2 ----"
chknum "诉求组1 价格促销" R2_G1 0.429904
chknum "诉求组2 品牌官宣" R2_G2 0.555561
chknum "诉求组3 抽奖导流" R2_G3 0.295932
chknum "诉求组4 硬广标识" R2_G4 0.458982
chknum "诉求组5 软植入"   R2_G5 0.470109
chknum "媒体 image"       R2_MI 0.401505
chknum "媒体 video"       R2_MV 0.592762

display _n "---- Q3 交互检验 ----"
chknum "诉求×粉丝 F"      F_ALOGF 0.6245679
chknum "诉求×文本 F"      F_ATEXT 0.13957261
chknum "视频×抽奖 F"      F_VLOT  0.08819609

display _n(2) "{hline 70}"
display "全部步骤完成。"
display "  图形界面运行：结果在上面 Results 窗口，可右键 Save Results 存档"
display "  /e 批处理运行：完整输出已写入 reproduce_all.log"
display "{hline 70}"
