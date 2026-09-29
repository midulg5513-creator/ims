* ============================================================
*  vars_build.do —— 变量工程（可重复运行 + 自带体检）
*
*  为什么需要这个脚本：
*    在同一个 Stata 会话里重复 gen 同一个变量会报
*        variable xxx already defined
*        r(110);
*    这不是 bug，是 Stata 提示"你造过了"。但有一种情况很危险：
*    如果上次是「先 replace 后 gen」，has_prior_hist 会全是 1（缺失标记失效），
*    而且一旦 replace 过，hist_prior_avg_lnengage 的缺失模式就再也回不来了。
*    ⇒ 所以最稳的做法是 clear all 重新读数据，从头造一遍。
*
*  用法：
*    图形界面：Ctrl+D 运行整个文件（或选中后 Ctrl+D）
*    命令行  ：do "d:\AI\爬虫\vars_build.do"
* ============================================================

clear all
set more off
set linesize 200

display _n(2) "{hline 72}"
display "第 1 步：重新读数据（clear all 保证是干净的原始状态）"
display "{hline 72}"

cd "d:\AI\爬虫"
import delimited "stata_ads2.csv", encoding("UTF-8") clear

* ⚠️ 2026-09-24：本脚本逐项校验 stata_ads2.csv 的变量构建过程（含hist_prior_n /
* hist_avg_lnengage 等已删变量），**只能搭配 stata_ads2.csv 运行**。
* 新表 stata_ads3.csv 的变量字典见「变量清理说明.md」第五节。

count
display "样本量 N = " r(N) "   （预期 211）"

* ------------------------------------------------------------
display _n(2) "{hline 72}"
display "第 2 步：造变量前的准备检查"
display "{hline 72}"

display "原始 CSV 里 hist_prior_avg_lnengage 的缺失条数："
count if missing(hist_prior_avg_lnengage)
display "  缺失 = " r(N) "   （预期 41）"
if r(N) != 41 {
    display "  [!] 不是 41 —— 可能读错了数据文件（必须用 stata_ads2.csv）"
}

* ------------------------------------------------------------
display _n(2) "{hline 72}"
display "第 3 步：生成全部建模变量"
display "{hline 72}"

* ---- 因变量 ----
gen double ln_repost = ln(reposts + 1)
display "  + ln_repost        ln(转发数+1)"

* ---- 粉丝规模非线性 ----
gen double logf_sq = log_followers^2
display "  + logf_sq          粉丝数(对数)的平方"

* ---- 文本长度（以百字为单位）----
gen double tl    = text_len / 100
gen double tl_sq = tl^2
display "  + tl / tl_sq       文本长度(百字) 及其平方"

* ---- 事前历史缺失标记（★ 顺序绝不能反）----
gen byte has_prior_hist = !missing(hist_prior_avg_lnengage)
display "  + has_prior_hist   缺失标记 = " %4.0f r(N) " ... 见下一步"

replace hist_prior_avg_lnengage = 0 if missing(hist_prior_avg_lnengage)
display "  + 把缺失的事前互动质量填为 0"

* ---- 媒体哑变量 ----
gen byte is_video = (media_type == "video")
display "  + is_video         1=视频帖"

* ---- 分类变量编码（回归里 i.xxx 需要）----
encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode region_grp, gen(region_n)
display "  + appeal_n / media_n / region_n   分类变量编码"

* ------------------------------------------------------------
display _n(2) "{hline 72}"
display "第 4 步：体检（这三项必须通过）"
display "{hline 72}"

display _n "体检 1：has_prior_hist 的分布"
tab has_prior_hist
display "  ✅ 合格标准：0 → 41 条，1 → 170 条"
display "  ❌ 若全是 1，说明上次「先 replace 后 gen」，缺失标记失效，H1c 系数会有偏"

display _n "体检 2：因变量的取对数效果"
summarize reposts ln_repost, detail
display "  ✅ 合格标准：ln_repost 偏度 ≈ 1.50（原始 reposts 偏度 ≈ 13.82）"

display _n "体检 3：变量都齐了吗"
foreach v in ln_repost logf_sq tl tl_sq has_prior_hist is_video ///
             appeal_n media_n region_n {
    capture confirm variable `v'
    if _rc == 0 {
        display "  [有] `v'"
    }
    else {
        display "  [缺] `v'   <== 需要重新运行本脚本"
    }
}

* ------------------------------------------------------------
display _n(2) "{hline 72}"
display "第 5 步：冒烟测试 —— 跑一下 M2，R² 应该是 0.449542"
display "{hline 72}"

regress ln_repost log_followers hist_prior_avg_lnengage has_prior_hist ///
    text_len n_images is_lottery log_age_hours
display "M2 R2 = " %9.6f e(r2) "    （预期 0.449542）"

if abs(e(r2) - 0.449542) < 0.0001 {
    display "  [OK] 变量工程正确，可以继续做 Q1/Q2/Q3"
}
else {
    display "  [!!] 不一致。请确认：1) 用的是 stata_ads2.csv  2) 是从 clear all 重头跑的"
}

display _n(2) "{hline 72}"
display "vars_build.do 完成。"
display "接下来可以跑： do d:\AI\爬虫\reproduce_all.do"
display "{hline 72}"
