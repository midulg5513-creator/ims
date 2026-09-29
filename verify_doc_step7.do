* ============================================================
*  验证：Stata手把手教学.md 第 7 步修正后的代码块，原样照抄能否跑通
*  预期输出见文档"你会看到"区块
* ============================================================
clear all
set more off
set linesize 140
cd "d:\AI\爬虫"

* ---- 第 2 步：导入（含精度修正）----
import delimited "stata_ads3.csv", encoding("UTF-8") clear
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)

* ---- 第 5 步：基准回归 ----
regress ln_repost ln_followers text_len n_pics is_lottery
scalar SSR = e(mss)
scalar SSE = e(rss)
scalar SST = SSR + SSE

* ---- 第 7 步：手算（修正版）----
predict double yhat, xb
predict double resid, residuals

summarize ln_repost
scalar YBAR = r(mean)
display "因变量均值 ybar = " %18.8f YBAR

* 三个平方和：每一个都必须先 gen，再 summarize
gen double sq_total = (ln_repost - YBAR)^2      // (y - ybar)^2
gen double sq_expl  = (yhat      - YBAR)^2      // (yhat - ybar)^2
gen double sq_resid = resid^2                   // (y - yhat)^2

summarize sq_total
scalar H_SST = r(sum)
summarize sq_expl
scalar H_SSR = r(sum)
summarize sq_resid
scalar H_SSE = r(sum)

display "手算 SST = " %18.8f H_SST
display "手算 SSR = " %18.8f H_SSR
display "手算 SSE = " %18.8f H_SSE
display "手算 R2  = " %18.8f H_SSR / H_SST
display ""
display "SSR 差异 = " %20.12f H_SSR - SSR
display "SSE 差异 = " %20.12f H_SSE - SSE
display "SST 差异 = " %20.12f H_SST - SST

display _n "=== 照抄结果：无 error 即通过 ==="
