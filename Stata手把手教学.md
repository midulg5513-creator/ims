# Stata 手把手教学：从零到跑出结果

> 目标：你能自己一行行敲，并**看懂每一个数字**。
> 全程 10 步，用 **Command 窗口**（不是 do 文件）逐步粘贴，每步都能立刻看到反馈。
> 数据：`d:\AI\爬虫\stata_ads3.csv`（211 条微博广告帖 × 36 变量，2026-09-24 变量清理版）

---

## 第 0 步：打开 Stata，认识 4 个窗口

双击 `D:\stady_resouce\StataMP-64.exe`。你会看到：

| 窗口 | 位置 | 干什么用 |
|---|---|---|
| **Command** | 底部（有 `Command` 字样） | **你在这里打字** |
| **Results** | 右上大片区域 | **命令的结果显示在这里** |
| **Variables** | 左上 | 当前内存里的变量清单 |
| **History** | 左侧 | 你敲过的命令历史，可点击重跑 |

> 💡 关闭 Stata 会**清空内存**。所以下面所有步骤要在**同一次** Stata 会话里连续做完。
> 想跳过打字的麻烦，直接菜单 **File → Do...** 选 `reproduce_all.do` 也一样，但建议先跟着走一遍。

---

## 第 1 步：告诉 Stata 数据在哪个文件夹

**在 Command 窗口输入（含引号）：**
```stata
cd "d:\AI\爬虫"
```

**你会看到：**
```
d:\AI\爬虫
```

**意思**：Stata 的"当前工作目录"设好了。后面读文件可以直接写文件名。
> 为什么不 cd 也行？因为也可以写全路径。但 cd 之后命令短，不容易打错。

---

## 第 2 步：把数据读进来

**输入：**
```stata
import delimited "stata_ads3.csv", encoding("UTF-8") clear
```

**你会看到：**
```
(36 vars, 211 obs)
```

**意思**：
- `36 vars` = 36 个变量（列）
- `211 obs` = 211 条观测（行）
- `encoding("UTF-8")` = 告诉 Stata 中文按 UTF-8 解，否则乱码
- `clear` = 读之前先清空内存（否则会报错说内存里已有数据）

**同时左上 Variables 窗口会列出 36 个变量名**，可以确认读对了。

> ⚠️ 必须用 `stata_ads3.csv`。工作区还有 `stata_ads2.csv`（211×61，变量清理前的旧版）、`stata_ads.csv`（211×34）与 `stata_data.csv`（470×34），用错就复现不出来。

---

## 第 3 步：先看看数据长什么样（养成习惯）

**输入：**
```stata
describe
```
**你会看到**：61 个变量的名字、类型（double/byte/str）、存储格式。

**输入：**
```stata
summarize reposts ln_repost
```
> 会报错说 ln_repost 不存在 —— 因为还没造。先看这个：

```stata
summarize reposts, detail
```

**你会看到：**
```
                           reposts
-------------------------------------------------------------
      Percentiles      Smallest
 1%            0              0
 5%            0              0
10%            0              0       Obs                 211
25%            0              0       Sum of wt.          211
50%            1                      Mean           1303.204
                        Largest       Std. dev.      14165.29
75%           25           6219
90%          172          15173       Variance       2.01e+08
95%          739          31521       Skewness       13.82112
99%        15173         202957       Kurtosis       196.6058
```

**意思（这一段很重要，决定了后面为什么用对数）**：
| 看到的 | 含义 |
|---|---|
| 中位数 50% = **1** | 一半的帖子转发不超过 1 次 |
| 均值 Mean = **1303** | 平均值被少数爆款拉高 |
| 最大值 202957 | 有超爆款帖 |
| **偏度 Skewness = 13.82** | 严重右偏（正态分布是 0） |
| **峰度 Kurtosis = 196.6** | 极端厚尾（正态是 3） |
| 1%/5%/10% 全是 0 | 零转发占比很高 |

👉 **所以因变量要取对数**，否则少数爆款帖会主导整个回归。

---

## 第 4 步：变量工程（★ 一次做完，漏一个后面就报错）

> ⚠️ **这一步最容易漏。** CSV 里只有原始变量，模型要用的这几个都必须自己生成。
> 漏了就会看到 `variable xxx not found` / `r(111)`。

**输入（建议整段粘贴，一次做完）：**
```stata
* --- ① 精度修正（★ 容易漏，漏了 SST 会差 1.4e-5）---
* import delimited 会把含小数的列存成 float（4 字节）；
* 必须 drop 后用 gen double 重算（recast double 无效）
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)

* --- ② 粉丝规模非线性 ---
gen double lnf_sq = ln_followers^2

* --- ③ 文本长度（以百字为单位，避免平方后条件数病态）---
gen double tl    = text_len100
gen double tl_sq = tl^2

* --- ④ 媒体哑变量 ---
gen byte is_video = (media_type == "video")

* --- ⑤ 分类变量编码（回归里写 i.xxx 需要先 encode）---
encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode region_grp, gen(region_n)
```

**你会看到**：这些命令都没有输出（Stata 默默执行）。

> `hist_prior_lnengage0`（缺失填 0 版）与 `has_prior_hist`（缺失标记）**已内置在新表里**，
> 不需要再 `gen` + `replace` 了。为什么不建议现场填 0，见下方「顺序不能反」。

**各变量清单（对照检查有没有漏）：**

| 新变量 | 从哪来 | 用途 | 出现在哪一步 |
|---|---|---|---|
| `ln_repost` | `reposts`（重算） | 因变量 | 第 5 步起全部 |
| `ln_followers` | `followers`（重算；旧表的 `log_followers` 实为 log10，已弃用） | 粉丝规模 | 第 5 步起全部 |
| `lnf_sq` | `ln_followers` | 粉丝非线性 | 第 8 步 M3 |
| `tl` / `tl_sq` | `text_len100` | 文本长度非线性 | 备用 |
| `is_video` | `media_type` | 媒体形态 | 第 9 步 |
| `appeal_n` / `media_n` / `region_n` | 三个分类变量 | 回归里的 `i.xxx` | 第 8-9 步 |

**确认变量都造好了：**
```stata
summarize ln_repost lnf_sq has_prior_hist, detail
```
✅ 预期：`has_prior_hist` 均值 = 0.8057（170/211）；`ln_repost` 偏度 1.50

### 🔴 顺序不能反：必须先 `gen` 再 `replace`

新表已帮你做完这步，但原则要知道（旧表手改时踩过这个坑）：

```stata
* ✅ 正确
replace hist_prior_lnengage0 = 0 if missing(hist_prior_lnengage0)   // 表里已是这样
* 结果：41 条填 0，再配合 has_prior_hist 标记（0 → 41 条，1 → 170 条）

* ❌ 错误（先填 0 再生成标记）
replace hist_prior_lnengage = 0 if missing(hist_prior_lnengage)
gen byte wrong_hist = !missing(hist_prior_lnengage)
* 结果：wrong_hist 全为 1（211 条）→ 缺失标记彻底失效
```

**实测对照：**

| 顺序 | `has_prior_hist` 分布 | 后果 |
|---|---|---|
| gen → replace ✅ | 0 有 41 条，1 有 170 条 | 模型能区分「真的互动为 0」和「没有历史数据」 |
| replace → gen ❌ | **全为 1**（211 条） | 41 条填进去的假 0 被当成真值，H1c 系数有偏 |

> 为什么会有 41 条缺失？因为那 41 位作者在目标帖发布前没有抓到历史帖。
> 填 0 是为了不丢样本，但必须用 `has_prior_hist` 把这件事标记出来。

### 名词解释

- `gen` = 生成新变量
- `double` = 双精度（避免精度丢失 —— 对 Q1 手算比对很重要）
- `byte` = 1 字节整数，适合 0/1 哑变量
- `ln()` = **自然对数**（底数 e）；`log10()` 才是常用对数。**混用结果完全不同**
- `+ 1` = 零值保护。ln(0) = −∞，加 1 之后 ln(0+1)=0，零转发帖也能留在样本里
- `!missing(x)` = x 非缺失时取 1，否则取 0
- `encode` = 把字符串分类变量转成数字编码（回归里 `i.变量名` 需要先用它）

> 💡 生成后偏度从 13.82 降到 **1.50**、峰度从 196.6 降到 **5.00** —— 这正是取对数的目的。

### ⚠️ 重复运行会报 `r(110) variable already defined`

**症状**（很常见）：
```
. gen double ln_repost = ln(reposts + 1)
variable ln_repost already defined
r(110);
```

**这不是 bug，含义是：这个变量已经在内存里了，你之前跑过一次。**

**但有一个必须检查的隐患**：

| 上次怎么跑的 | `has_prior_hist` 会变成 | 后果 |
|---|---|---|
| `gen` → `replace` ✅ | 0 有 41 条，1 有 170 条 | 正确 |
| `replace` → `gen` ❌ | **全为 1**（211 条） | 缺失标记失效，H1c 系数有偏 |

而且一旦 `replace` 过，`hist_prior_lnengage0` 里的缺失模式在**当前会话**就再也回不来了
（第 2 次跑 `replace` 会显示 `(0 real changes made)`，因为已经都是 0 了）。

> ✅ 好消息：`stata_ads3.csv` 里已经把 0 填充版单独存成了 `hist_prior_lnengage0`，
> 原始缺失版 `hist_prior_lnengage` 也保留着——**两个字段都在，不会再被 `replace` 破坏**。

**所以最稳的做法：`clear all` 重新读数据，从头造一遍。**

我把这个流程写成了 `vars_build.do`，可反复运行、自带体检：

```stata
do "d:\AI\爬虫\vars_build.do"
```

它会：① `clear all` 重读数据 → ② 生成全部变量 → ③ 体检三项 → ④ 跑 M2 冒烟测试（R² 应为 0.449215）。

> ℹ️ `vars_build.do` 是为**旧表 `stata_ads2.csv`** 写的，适合学习「变量工程怎么做」；
> 当前建模直接用 `stata_ads3.csv` 即可（其中 `hist_prior_lnengage0`、`has_prior_hist`、`ln_pics` 等都已备好）。

**手动检查现有变量对不对**（不想重跑的话）：
```stata
tab has_prior_hist
```
✅ 必须看到：**0 → 41 条，1 → 170 条**。若全是 1，立刻 `clear all` 重做。

**三个常用命令的区别：**

| 命令 | 作用 |
|---|---|
| `describe` | 看内存里现有变量的清单 |
| `capture confirm variable x` | 检查变量 x 是否存在（`_rc==0` 表示存在） |
| `capture drop x` | 存在就删掉，不存在也不报错（便于重跑） |
| `clear all` | **彻底清空内存**，最干净 |

---

## 第 5 步：跑第一个回归，学会读输出表 ★

**输入（这就是 Q1 的教学模型）：**
```stata
regress ln_repost ln_followers text_len n_pics is_lottery
```

### 你会看到上半部分 —— ANOVA 表

```
      Source |       SS           df       MS      Number of obs   =       211
-------------+----------------------------------   F(4, 206)       =     22.99
       Model |  379.271561         4  94.8178903   Prob > F        =    0.0000
    Residual |  849.712634       206  4.12481861   R-squared       =    0.3086
-------------+----------------------------------   Adj R-squared   =    0.2952
       Total |  1228.98419       210  5.85230569   Root MSE        =     2.031
```

**逐项对照（这就是作业 Q1 要的东西）：**

| 表里的格子 | 名称 | 就是 | 本次值 |
|---|---|---|---|
| Model SS | **SSR** 回归平方和 | 模型能解释的变异 | 379.271561 |
| Residual SS | **SSE** 残差平方和 | 模型没解释的变异 | 849.712634 |
| Total SS | **SST** 总平方和 | = SSR + SSE | 1228.98419 |
| Model df | **k** 自变量个数 | **不含常数项** | 4 |
| Residual df | **N−k−1** | 211−4−1 | 206 |
| Total df | **N−1** | 211−1 | 210 |
| Model MS | **MSR** = SSR/k | | 94.8178903 |
| Residual MS | **MSE** = SSE/(N−k−1) | | 4.12481861 |
| **R-squared** | **R²** = SSR/SST | | 0.3086 |
| **Adj R-squared** | **调整 R²** | | 0.2952 |
| **Root MSE** | **√MSE** | | 2.0310 |

**自己验算一遍**（在 Command 窗口敲）：
```stata
display 379.271561 / 1228.98419
```
→ `0.30860573`，和 R-squared 0.3086 对上 ✅

### 你会看到下半部分 —— 系数表

```
    ln_repost | Coefficient  Std. err.      t    P>|t|     [95% conf. interval]
--------------+----------------------------------------------------------------
ln_followers |   .2254508   .0337575     6.68   0.000     .1588963    .2920053
     text_len |   .0015553   .0005253     2.96   0.003     .0005197    .0025908
       n_pics |   .0192022   .0360045     0.53   0.594    -.0517822    .0901867
   is_lottery |     1.4114   .3651239     3.87   0.000     .6915414    2.131259
        _cons |  -1.136703   .3694291    -3.08   0.002     -1.86505   -.4083561
```

**每列什么意思：**

| 列 | 含义 | 怎么用 |
|---|---|---|
| `Coefficient` | 回归系数 β | 正负号看方向，大小看强度 |
| `Std. err.` | 标准误 | 越小越精确 |
| `t` | = Coef / Std.err | 绝对值 > 1.96 大致对应 p<0.05 |
| `P>\|t\|` | p 值 | **< 0.05 算显著** |
| `[95% conf. interval]` | 95% 置信区间 | **不含 0 就等于显著** |

**逐行读结果：**

| 变量 | 系数 | p | 结论 |
|---|---:|---:|---|
| `ln_followers` | 0.2255 | **0.000** | ✅ 粉丝越多转发越多 |
| `text_len` | 0.00156 | **0.003** | ✅ 文本越长转发略多（但效应很小） |
| `n_pics` | 0.0192 | 0.594 | ❌ 图片数无显著影响 |
| `is_lottery` | 1.4114 | **0.000** | ✅✅ 抽奖帖转发显著更高 |
| `_cons` | −1.1367 | 0.002 | 常数项 |

### 把系数写成方程

```
ln(转发+1) = -1.1367 + 0.2255×ln_followers + 0.00156×text_len
            + 0.01920×n_pics + 1.4114×is_lottery
```

### 系数的实际含义（怎么跟别人解释）

| 变量 | 系数 | 怎么解读 |
|---|---:|---|
| `ln_followers` | 0.2255 | 粉丝数**每增加 1%** → 转发量增加约 **0.23%**；粉丝数**翻倍**（ln 增加 1）→ 转发量增加约 **25.3%** |
| `is_lottery` | 1.4114 | 抽奖帖的转发量约为非抽奖帖的 **4.10 倍**（即高 **310%**） |
| `text_len` | 0.00156 | 每多 **100 字** → 转发增加约 **16.9%**（很小） |
| `n_pics` | 0.0192 | 每多 1 张图 → 转发增加约 1.9%，**但不显著** |

> 换算方法：对数-水平模型里，`exp(系数) − 1` 就是变化百分比。
> 比如抽奖：`exp(1.4114) − 1 = 3.102` = 310%。
> 注意 `ln_followers` 两侧都取了对数，所以系数直接就是**弹性**（1% → 0.23%）。

---

## 第 6 步：把平方和"抓"出来自己算（学会用 `e()`）

**关键概念**：跑完 `regress`，结果不是打印完就消失，而是存在 **`e()`** 里。

**输入（亲眼看看存了什么）：**
```stata
ereturn list
```

**你会看到一大串：**
```
               e(N) =  211
            e(df_m) =  4
            e(df_r) =  206
               e(F) =  22.98716603038132
              e(r2) =  .3086057270725734
            e(rmse) =  2.030964945730763
             e(mss) =  379.2715610054851
             e(rss) =  849.712633822155
            e(r2_a) =  .2951805955594194
```

**这里有个最容易搞混的地方 ——**

| Stata 的 `e()` | 全称 | 中文 | 就是 |
|---|---|---|---|
| `e(mss)` | Model Sum of Squares | 模型平方和 | **SSR** |
| `e(rss)` | Residual Sum of Squares | 残差平方和 | **SSE** |

> 🔴 **陷阱**：很多教材把 `RSS` 写成 Regression Sum of Squares（= SSR）。
> Stata 里 `rss` 是 **Residual**，即 **SSE**。**搞反了 R² 会从 0.3086 变成 0.6914。**
> （范文那份报告就是栽在这个上，把 SSR 和 SSE 的数值写反了。）

**现在把它们存成标量并显示：**
```stata
scalar SSR = e(mss)
scalar SSE = e(rss)
scalar SST = SSR + SSE

display "SSR = " %18.8f SSR
display "SSE = " %18.8f SSE
display "SST = " %18.8f SST
```

**你会看到：**
```
SSR =       379.27156101
SSE =       849.71263382
SST =      1228.98419483
```

**继续算剩下四个 + 校验：**
```stata
scalar MSR  = SSR / e(df_m)
scalar MSE  = SSE / e(df_r)
scalar RMSE = sqrt(MSE)
scalar R2   = SSR / SST
scalar AR2  = 1 - (1 - R2) * (e(N) - 1) / e(df_r)

display "MSR   = " %18.8f MSR
display "MSE   = " %18.8f MSE
display "RMSE  = " %18.8f RMSE
display "R2    = " %18.8f R2
display "AdjR2 = " %18.8f AR2
display "校验 SSR+SSE-SST = " %20.12f SSR + SSE - SST
```

**你会看到：**
```
MSR   =        94.81789025
MSE   =         4.12481861
RMSE  =         2.03096495
R2    =         0.30860573
AdjR2 =         0.29518060
校验 SSR+SSE-SST =       0.000000000000
```

✅ 校验项为 0，说明 `SSR + SSE = SST` 成立，口径没问题。

> ⚠️ `display` 的格式码 `%18.8f` = 总宽 18、小数点后 8 位。
> 想看极小差异用 `%20.12f`（12 位小数）。

> ⚠️ **`e()` 会被下一次估计命令覆盖**。所以要在 `regress` 之后**立刻**存成 `scalar`，
> 否则跑第二个回归后 `e(mss)` 就变了。

---

## 第 7 步：真正的手算（Q1 得分点）★

前面是从 `e()` 里"取"软件算好的值。**真正的手算必须从原始数据算**，
否则手算和软件的差异永远是 0，答不了作业要的"差异分析"。

**输入：**
```stata
predict double yhat, xb
predict double resid, residuals
```
**意思**：`yhat` = 拟合值 ŷ，`resid` = 残差 (y − ŷ)。

**输入：**
```stata
summarize ln_repost
scalar YBAR = r(mean)
display "因变量均值 ybar = " %18.8f YBAR
```
```
因变量均值 ybar =         1.77218987
```
> `summarize` 之后结果存在 **`r()`** 里（`r(mean)`、`r(sd)`、`r(N)`…），注意和 `e()` 区分：
> **`e()` 是估计命令的，`r()` 是统计命令的**。

**输入（逐项构造平方，再求和）：**
```stata
* 三个平方和：每一个都必须先 gen，再 summarize
* （summarize 只能统计已经存在的变量）
gen double sq_total = (ln_repost - YBAR)^2      // (y - ȳ)²
gen double sq_expl  = (yhat      - YBAR)^2      // (ŷ - ȳ)²   ← 这一行不能漏
gen double sq_resid = resid^2                   // (y - ŷ)²

summarize sq_total
scalar H_SST = r(sum)
summarize sq_expl
scalar H_SSR = r(sum)
summarize sq_resid
scalar H_SSE = r(sum)
```

> ⚠️ **最容易踩的坑（静默错误）**：漏写 `gen double sq_expl = (yhat - YBAR)^2` 就直接 `summarize sq_expl`，
> 会报 `variable sq_expl not found` **`r(111)`**。但它**不会在这里停下来**——
> 下一行 `scalar H_SSR = r(sum)` 拿到的是一个空值，最后 `display` 出来全是 `.`，
> 很容易误以为“手算算不出来”而放弃。
>
> 👉 口诀：**先 `gen`，后 `summarize`**。三个平方和对应三个变量：
> `sq_total ← y`、`sq_expl ← yhat`、`sq_resid ← resid`，不能混。

> 💡 另一个小知识（已实测）：普通的 `summarize x` **就会**返回 `r(sum)`，
> 不必非得写 `summarize x, meanonly`。后者只是让屏幕不输出汇总表而已。

**输入（显示并与软件对比）：**
```stata
display "手算 SST = " %18.8f H_SST
display "手算 SSR = " %18.8f H_SSR
display "手算 SSE = " %18.8f H_SSE
display "手算 R2  = " %18.8f H_SSR / H_SST
display ""
display "SSR 差异 = " %20.12f H_SSR - SSR
display "SSE 差异 = " %20.12f H_SSE - SSE
display "SST 差异 = " %20.12f H_SST - SST
```

**你会看到：**
```
手算 SST =      1228.98419483
手算 SSR =       379.27156101
手算 SSE =       849.71263382
手算 R2  =         0.30860573

SSR 差异 =      -0.000000000001
SSE 差异 =       0.000000000000
SST 差异 =      -0.000000000000
```

### 🎯 这就是 Q1 的答案，怎么理解

| 看到的现象 | 说明什么 |
|---|---|
| 在 Stata 内部手算，差异在 **1×10⁻¹²** 量级（SSR）与 **0**（SSE/SST） | 两边用的是同一份变量，但**求和顺序不同**：手算是 211 项顺序累加，Stata 用 QR 分解。所以不是恰好 0，而是 12 位小数才看得出 |
| 改用 **Python 以正规方程独立复算**，差异是 −4.51×10⁻⁹（SSR）与 +2.16×10⁻⁹（SSE） | 完全不同的算法路径，**这才是真正的“算法差异”** |
| 量级 10⁻⁹ ～ 10⁻¹² | 纯粹是**浮点舍入误差**，完全不影响结论 |
| 如果差异是 10⁻³ 量级 | 那就**不是**舍入，而是**口径错**了（比如调整 R² 分母误用 `n−k`） |

👉 报告里可以这样写：
> 手算/独立复算与 Stata 输出的差异在 10⁻⁹ 量级，属浮点舍入误差；若将调整 R² 的分母误写为 n−k，差异会达到 0.00340492，比舍入误差大 6 个数量级，因此口径校验是必要的。

---

## 第 8 步：Q2 —— 逐步把 R² 提到 1.5 倍

**先记下基准和目标：**
```stata
display "基准 R2 = " %9.6f R2
display "目标 1.5x = " %9.6f 1.5 * R2
```
```
基准 R2 =  0.308606
目标 1.5x =  0.462909
```

**然后逐个加变量，每次看 R² 涨多少：**

```stata
* M1：加曝光时长（帖子从发布到采集的小时数取对数）
regress ln_repost ln_followers text_len n_pics is_lottery ln_age_hours
display "M1 R2 = " %9.6f e(r2)

* M2：加事前作者互动质量（H1c）
regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist text_len n_pics is_lottery ln_age_hours
display "M2 R2 = " %9.6f e(r2)

* M3：加粉丝规模二次项（检验非线性）
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist text_len n_pics is_lottery ln_age_hours
display "M3 R2 = " %9.6f e(r2)

* M4：加话题数、@提及数
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist text_len n_pics is_lottery ln_age_hours n_topics n_mentions
display "M4 R2 = " %9.6f e(r2)
```

> ⚠️ 这一步用到 `lnf_sq`（第 4 步生成）、`hist_prior_lnengage0` / `has_prior_hist` / `n_topics` / `n_mentions`（CSV 自带）。
> 如果报 `variable lnf_sq not found`，回去补第 4 步。

**你会看到：**
```
M1 R2 =  0.312457
M2 R2 =  0.449215
M3 R2 =  0.460951
M4 R2 =  0.465922     ← 超过 0.462909，达标 ✅
```

**读这段结果：**

| 模型 | R² | 涨了多少 | 这个变量为什么加 |
|---|---:|---:|---|
| M0 基准 | 0.308606 | — | Q1 规格 |
| M1 +曝光时长 | 0.312457 | +0.0039 | 老帖天然累计更多转发，**必须控制**，否则对比不公平 |
| M2 +事前互动质量 | 0.449215 | **+0.1368** | **涨幅最大**。作者发帖前的历史互动质量，代表既有传播能力 |
| M3 +粉丝二次项 | 0.460951 | +0.0117 | 检验粉丝规模的边际效应是否递减 |
| M4 +话题数/@数 | **0.465922** | +0.0050 | 信息分发渠道。**首个达标** |

👉 **关键结论**：M4 只加了两个**有理论依据**的变量就达标了，提高幅度 = (0.465922 − 0.308606)/0.308606 = **+50.98%**。

> ⚠️ 别为了凑 R² 乱加变量。加地域哑变量能到 0.4998，但**调整 R² 反而从 0.4392 掉到 0.4261**，
> 说明已经过拟合了 —— 这是"堆变量"的典型信号。

---

## 第 9 步：Q3 —— 不同类型广告帖分组跑

**先看分组变量有哪些值：**
```stata
tab appeal_grp
```
```
    appeal_grp |      Freq.     Percent        Cum.
---------------+-----------------------------------
   价格促销     |         28       13.27       13.27
   品牌官宣     |         66       31.28       44.55
   抽奖导流     |         41       19.43       63.98
   硬广标识     |         46       21.80       85.78
   软植入       |         30       14.22      100.00
---------------+-----------------------------------
         Total |        211      100.00
```

**按诉求类型分组回归：**
```stata
regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours if appeal_grp == "品牌官宣", vce(hc3)
display "品牌官宣 R2 = " %9.6f e(r2)
```
> `///` 是 Stata 的换行续行符。

**你会看到**：R² = 0.555561，且 `hist_prior_lnengage0` 系数 0.6138（p=0.005）

**逐个换组名试**（价格促销 / 抽奖导流 / 硬广标识 / 软植入）：

| 组 | N | R² | 显著的变量 |
|---|---:|---:|---|
| 品牌官宣 | 66 | 0.5556 | 事前互动质量 p=0.005 |
| 软植入 | 30 | 0.4701 | 无 |
| 硬广标识 | 46 | 0.4590 | 事前互动质量 p=0.048 |
| 价格促销 | 28 | 0.4299 | 无 |
| 抽奖导流 | 41 | 0.2959 | 无 |

> 💡 `vce(hc3)` = 用 HC3 异方差稳健标准误。数据存在异方差（Breusch-Pagan χ²=44.92，p<0.001），
> 所以要用稳健标准误。**注意：`vce()` 只改标准误，不改 R²，模型还是多元线性回归。**

**组间差异要正式检验，不能"比星号"：**
```stata
test appeal_grp
```
不行 —— 要用交互项 + 联合检验：

```stata
encode appeal_grp, gen(appeal_n)

regress ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n ///
    hist_prior_lnengage0 has_prior_hist n_pics is_lottery ln_age_hours, vce(hc3)

testparm i.appeal_n#c.ln_followers
testparm i.appeal_n#c.text_len
```

**你会看到：**
```
诉求 × 粉丝规模  F = 0.6246   p = 0.6455
诉求 × 文本长度  F = 0.1396   p = 0.9674
```

**意思**：**p > 0.05 → 组间差异不显著。**

👉 所以**不能**说"不同类型的决定机制不同"。即使某一组显著、另一组不显著，
**只要交互检验不显著，就不能断言两组有差别**。（范文用"比星号多少"下结论，方法上是错的。）

---

## 第 10 步：存档交作业

**最稳的做法 —— 开日志（图形界面下用）：**
```stata
log using "d:\AI\爬虫\我的结果.log", replace text
* ... 跑你的命令 ...
log close
```

**或者直接复制**：Results 窗口里选中 → 右键 → **Copy as table** → 粘进 Word。

**存 Excel：**
```stata
regress ln_repost ln_followers text_len n_pics is_lottery
putexcel set "d:\AI\爬虫\结果.xlsx", replace
putexcel A1 = "指标" B1 = "数值"
putexcel A2 = "SSR"  B2 = e(mss)
putexcel A3 = "SSE"  B3 = e(rss)
putexcel A4 = "SST"  B4 = e(mss) + e(rss)
putexcel A5 = "R2"   B5 = e(r2)
putexcel A6 = "AdjR2" B6 = e(r2_a)
putexcel A7 = "RootMSE" B7 = e(rmse)
```

---

## 附：完整可粘贴版（一次拿到 Q1 全部答案）

```stata
cd "d:\AI\爬虫"
import delimited "stata_ads3.csv", encoding("UTF-8") clear
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
regress ln_repost ln_followers text_len n_pics is_lottery

scalar SSR = e(mss)
scalar SSE = e(rss)
scalar SST = SSR + SSE
display "SSR   = " %18.8f SSR
display "SSE   = " %18.8f SSE
display "SST   = " %18.8f SST
display "MSR   = " %18.8f SSR / e(df_m)
display "MSE   = " %18.8f SSE / e(df_r)
display "RMSE  = " %18.8f sqrt(SSE / e(df_r))
display "R2    = " %18.8f SSR / SST
display "AdjR2 = " %18.8f 1 - (1 - SSR/SST) * (e(N)-1) / e(df_r)
```

---

## 附：排错速查

| 报错/现象 | 原因 | 解法 |
|---|---|---|
| **`variable hist_prior_lnengage0 not found` (r111)** | 用错了数据文件（旧表没有这一列） | 确认 import 的是 `stata_ads3.csv` |
| `variable lnf_sq not found` | 漏了第 4 步 | 同上 |
| `variable ln_repost not found` | 漏了第 4 步的 `drop` + `gen double` | 同上 |
| **SSR/SST 比预期多 1.4e-5** | 直接用了 CSV 里的 `ln_repost`（import 时被存成 float） | 必须 **`drop` 后 `gen double`**；`recast double` 无效（见 `check_stata_types.do`） |
| **`variable sq_expl not found` `r(111)`，且后面 `display` 全是 `.`** | 第 7 步手算漏了 `gen double sq_expl = (yhat - YBAR)^2` —— `summarize` 只能统计**已存在**的变量 | 补齐三条 `gen`：`sq_total ← ln_repost`、`sq_expl ← yhat`、`sq_resid ← resid`。**先 gen，后 summarize** |
| `no observations` | `summarize` 不带 `detail` 时没有 `r(p50)` | 用 `summarize x, detail` |
| `r(111) variable not found`（用 `i.xxx` 时） | 没先 `encode` | 先 `encode appeal_grp, gen(appeal_n)` |
| `variable xxx already defined` **`r(110)`** | 重复 `gen` 了 CSV 里已有的变量（如 `ln_age_hours` / `has_prior_hist` / `ln_repost`） | **CSV 已有的 → 直接用**；若想重算必须 **`drop` 后再 `gen double`** |
| `r(198) invalid syntax` | 续行符写错 | 用 `///`（三个斜杠），下一行要缩进 |
| 系数表渲染失败 `_coef_table()...` | Stata 进程残留 | 全部关掉 Stata 重开 |
| `r(608)` | 脚本里 `log using` 同名文件 | 改日志文件名 |
| 结果全乱 / 中文乱码 | 文件存成了 UTF-8 **带 BOM** | 另存为「UTF-8 无 BOM」 |
| 关了 Stata 后 `scalar` 找不到 | 内存已清空 | 从头重跑；或把命令存成 .do 文件复用 |

---

## 附：和我给你的脚本的关系

| 文件 | 定位 |
|---|---|
| **本文档** | **教学**：每步教你敲什么、看到什么、什么意思 |
| `demo_q1.do` | 只演示 Q1 过程，逐段带 `display` 讲解 |
| `reproduce_all.do` | **一键复现全部 + 自动核对 34 项**，跑完直接看 [OK] |
| `regression_final.do` | 正式版（多 VIF、异方差检验、标准化 beta） |
| `Stata复现步骤.md` | 快速复现路径 + 34 项预期值总表 |
