* ============================================================
*  demo_q1.do —— 在 Stata 里一步步「显示」SSR/SSE/SST/R² 的计算
*
*  用法（二选一）：
*    A. 图形界面：Stata 菜单 File > Do... 选本文件 → 结果窗口直接看
*    B. 命令行  ：在 Stata 命令窗口输入
*                 do "d:\AI\爬虫\demo_q1.do"
*
*  说明：脚本里每一段都用 display 把中间量打出来，
*        所以你能看到每个数字是怎么来的，而不是只看到一个总结表。
* ============================================================
clear all
set more off
set linesize 120

* ------------------------------------------------------------
* 0. 读数据
* ------------------------------------------------------------
display _n "===== 0. 读数据 ====="

import delimited "d:\AI\爬虫\stata_ads3.csv", encoding("UTF-8") clear

* ⚠️ 精度修正：import delimited 会把含小数的列存成 float（4 字节，实测
*    ln_repost 使 SST 差 1.4e-5，见 check_stata_types.do）。用原始整数重算
*    可恢复双精度；口径与 CSV 内完全一致（差异仅浮点）。
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
quietly summarize ln_followers
gen double lnf_c  = ln_followers - r(mean)
gen double lnf_c2 = lnf_c^2

count
display "样本量 N = " r(N)

* ------------------------------------------------------------
* 1. 生成因变量
* ------------------------------------------------------------
display _n "===== 1. 生成因变量 ln(转发数+1) ====="

* stata_ads3.csv 已内置 ln_repost，无需再 gen（保留此行说明历史）
* gen double ln_repost = ln(reposts + 1)

* 看一眼描述统计，确认数据正常
summarize reposts ln_repost, detail

* ------------------------------------------------------------
* 2. 跑多元线性回归（这一步 Stata 会把结果存进 e() 里）
* ------------------------------------------------------------
display _n "===== 2. 多元线性回归 ====="

regress ln_repost ln_followers text_len n_pics is_lottery

* ------------------------------------------------------------
* 3. 看 Stata 到底存了哪些结果（重要：学会自己查）
* ------------------------------------------------------------
display _n "===== 3. ereturn list —— 回归后保存了哪些量 ====="

ereturn list

display _n "你会在上面看到 e(mss)、e(rss)、e(df_m)、e(df_r)、e(N) 等。" 
display "stata 里凡是 e(...) 都是「上一次估计命令」的返回值。"

* ------------------------------------------------------------
* 4. 把平方和取出来存成标量
* ------------------------------------------------------------
display _n "===== 4. 取出平方和 ====="

scalar SSR  = e(mss)              // Model SS   = 回归平方和
scalar SSE  = e(rss)              // Residual SS = 残差平方和
scalar SST  = SSR + SSE           // Total SS    = 总平方和
scalar K    = e(df_m)             // 自变量个数（不含常数项）
scalar DFR  = e(df_r)             // 残差自由度
scalar NN   = e(N)

display "SSR = e(mss)             = " %18.8f SSR
display "SSE = e(rss)             = " %18.8f SSE
display "SST = SSR + SSE          = " %18.8f SST
display "k   = e(df_m)            = " %18.0f K
display "df_r= e(df_r)            = " %18.0f DFR
display "N   = e(N)               = " %18.0f NN

* ------------------------------------------------------------
* 5. 用公式算出其余指标并显示
* ------------------------------------------------------------
display _n "===== 5. 按公式计算并显示 ====="

scalar MSR  = SSR / K             // 回归均方
scalar MSE  = SSE / DFR           // 残差均方
scalar RMSE = sqrt(MSE)           // Root MSE
scalar R2   = SSR / SST           // 判定系数
scalar AR2  = 1 - (1 - R2) * (NN - 1) / DFR   // 调整判定系数

display _n "---- 公式对照 ----"
display "MSR   = SSR / k            = " %18.8f MSR  "   ( = " %18.8f SSR " / " %18.0f K " )"
display "MSE   = SSE / df_r         = " %18.8f MSE  "   ( = " %18.8f SSE " / " %18.0f DFR " )"
display "RMSE  = sqrt(MSE)          = " %18.8f RMSE
display "R2    = SSR / SST          = " %18.8f R2   "   ( = " %18.8f SSR " / " %18.8f SST " )"
display "AdjR2 = 1-(1-R2)(N-1)/df_r = " %18.8f AR2

* 两个恒等式校验
display _n "---- 恒等式校验（应等于 0）----"
display "SSR + SSE - SST      = " %15.8f SSR + SSE - SST
display "1 - SSE/SST - R2     = " %15.8f 1 - SSE / SST - R2

* ------------------------------------------------------------
* 6. 真正「手算」：用 predict 从数据里算，不从 e() 反推
* ------------------------------------------------------------
display _n "===== 6. 用 predict 从数据真算（这才是手算）====="

* 拿拟合值和残差
predict double yhat, xb
predict double resid, residuals

* 样本均值
summarize ln_repost
scalar YBAR = r(mean)
display "因变量均值 ybar = " %18.8f YBAR

* 三项平方和：逐项构造平方，再求和
gen double sq_total = (ln_repost - YBAR)^2
gen double sq_expl  = (yhat       - YBAR)^2
gen double sq_resid = resid^2

summarize sq_total
scalar H_SST = r(sum)
summarize sq_expl
scalar H_SSR = r(sum)
summarize sq_resid
scalar H_SSE = r(sum)

display _n "---- 手算结果 ----"
display "手算 SST = sum((y - ybar)^2)   = " %18.8f H_SST
display "手算 SSR = sum((yhat - ybar)^2)= " %18.8f H_SSR
display "手算 SSE = sum((y - yhat)^2)   = " %18.8f H_SSE
display "手算 R2  = SSR / SST           = " %18.8f H_SSR / H_SST

display _n "---- 与 Stata 的 e() 对比 ----"
display "SSR 差异 = 手算 - e(mss) = " %20.12f H_SSR - SSR
display "SSE 差异 = 手算 - e(rss) = " %20.12f H_SSE - SSE
display "SST 差异 = 手算 - (mss+rss) = " %18.12f H_SST - SST

* 清理临时变量
drop yhat resid sq_total sq_expl sq_resid

* ------------------------------------------------------------
* 7. 一张干净的汇总表
* ------------------------------------------------------------
display _n "===== 7. Q1 结果汇总表 ====="
display "{txt}{hline 46}"
display "{txt}  指标            数值"
display "{txt}{hline 46}"
display "{txt}  SSR        " %18.8f SSR
display "{txt}  SSE        " %18.8f SSE
display "{txt}  SST        " %18.8f SST
display "{txt}  MSR        " %18.8f MSR
display "{txt}  MSE        " %18.8f MSE
display "{txt}  Root MSE   " %18.8f RMSE
display "{txt}  R2         " %18.8f R2
display "{txt}  Adj R2     " %18.8f AR2
display "{txt}{hline 46}"

display _n "===== demo_q1.do 运行结束 ====="
display "提示：以上所有数字也都写在同目录的 demo_q1.log 里。"
