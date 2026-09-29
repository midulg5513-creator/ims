* ============================================================
*  check_stata_types.do —— import delimited 的存储类型与精度判定
*  2026-09-24：找出让 ln_repost 以 double 落地的写法
*  结论：默认 import 会把含小数的列存成 float；recast 也救不回已丢的位数；
*        必须 drop 后 gen double，或用 numericcols() 指定列号。
* ============================================================
clear all
set more off
set linesize 200

display "############ 1) 默认 import"
import delimited "d:\AI\爬虫\stata_ads3.csv", encoding("UTF-8") clear
describe ln_repost
quietly summarize ln_repost
gen double d1 = (ln_repost - r(mean))^2
quietly summarize d1
display "SST_default     = " %18.12f r(sum)

display "############ 2) numericcols(6) 强制列 6 = ln_repost"
import delimited "d:\AI\爬虫\stata_ads3.csv", encoding("UTF-8") numericcols(6) clear
describe ln_repost
quietly summarize ln_repost
gen double d2 = (ln_repost - r(mean))^2
quietly summarize d2
display "SST_numericcols = " %18.12f r(sum)

display "############ 3) 默认 import 后 drop + gen double（用整数 reposts 重算）"
import delimited "d:\AI\爬虫\stata_ads3.csv", encoding("UTF-8") clear
drop ln_repost
gen double ln_repost = ln(reposts + 1)
describe ln_repost
quietly summarize ln_repost
gen double d3 = (ln_repost - r(mean))^2
quietly summarize d3
display "SST_dropgen     = " %18.12f r(sum)

display "############ 4) 参考真值（Python 全精度）"
display "SST_expected    =   1228.98419483"
display "### CHECK_STATA_TYPES DONE"
