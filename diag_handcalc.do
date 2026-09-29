* ============================================================
*  诊断：复现 Stata手把手教学.md 第 7 步"手算"代码块的错误
*  用 capture 逐条抓错误码 / 返回值，不中断
* ============================================================
clear all
set more off
set linesize 140
cd "d:\AI\爬虫"

import delimited "stata_ads3.csv", encoding("UTF-8") clear
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)

regress ln_repost ln_followers text_len n_pics is_lottery
predict double yhat, xb
predict double resid, residuals
summarize ln_repost
scalar YBAR = r(mean)

display _n "================ 开始逐条诊断 ================"

* ---------- BUG 1：sq_expl 从未生成就 summarize ----------
display _n "--- BUG1: summarize sq_expl（原文没有 gen）---"
capture noisily summarize sq_expl
display "   >>> rc = " _rc

* ---------- 正确做法：先生成 ----------
display _n "--- 正确做法: gen double sq_expl = (yhat - YBAR)^2 ---"
gen double sq_expl = (yhat - YBAR)^2
gen double sq_total = (ln_repost - YBAR)^2
gen double sq_resid = resid^2
display "   >>> 三条 gen 均成功"

* ---------- BUG 2：普通 summarize 有没有 r(sum)？ ----------
display _n "--- BUG2: 普通 summarize 是否返回 r(sum) ---"
quietly summarize sq_total
scalar A_plain = r(sum)
scalar N_plain = r(N)
display "   summarize sq_total        → r(N) = " %18.0f N_plain
display "   然后 scalar A = r(sum)    → A  = " %18.8f A_plain
display "   （若显示 . 说明普通 summarize 不返回 r(sum)）"

display _n "--- 正确做法: summarize, meanonly 才有 r(sum) ---"
quietly summarize sq_total, meanonly
scalar B = r(sum)
display "   summarize sq_total, meanonly → r(sum) = " %18.8f B

* ---------- 交叉验证：三种口径的 SST ----------
display _n "--- SST 三种口径互验 ---"
quietly summarize sq_total, meanonly
scalar H_SST = r(sum)
scalar H_SSR_tmp = .
quietly summarize sq_expl, meanonly
scalar H_SSR = r(sum)
quietly summarize sq_resid, meanonly
scalar H_SSE = r(sum)

display "   手算 SST（Σ(y-ȳ)²）        = " %18.8f H_SST
display "   手算 SSR（Σ(ŷ-ȳ)²）        = " %18.8f H_SSR
display "   手算 SSE（Σ(y-ŷ)²）        = " %18.8f H_SSE
display "   手算 R2 = SSR/SST          = " %18.8f H_SSR / H_SST
display ""
display "   软件 e(mss)=SSR            = " %18.8f e(mss)
display "   软件 e(rss)=SSE            = " %18.8f e(rss)
display "   软件 e(rss)+e(mss)=SST     = " %18.8f e(mss) + e(rss)
display ""
display "   差异 SSR = " %20.12f H_SSR - e(mss)
display "   差异 SSE = " %20.12f H_SSE - e(rss)
display "   差异 SST = " %20.12f H_SST - (e(mss) + e(rss))

* ---------- 附：total 命令也等价（另一种写法） ----------
display _n "--- 等价写法 3: total 命令 ---"
quietly total sq_total
scalar T_SST = r(table)[1, 1]
display "   total sq_total             → SST = " %18.8f T_SST

* ---------- 附：predict 的残差与 y-yhat 是否一致 ----------
display _n "--- 附：resid 与手算 (y-ŷ) 是否一致 ---"
capture gen double manual_resid = ln_repost - yhat
if _rc == 0 {
    quietly summarize manual_resid, meanonly
    scalar S1 = r(sum)
    quietly summarize resid, meanonly
    scalar S2 = r(sum)
    display "   Σresid = " %18.12f S2 "   Σ(y-ŷ) = " %18.12f S1
    display "   常数项存在时 Σresid 应≈0"
}

display _n "================ 诊断结束 ================"
