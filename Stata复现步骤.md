# 怎么在 Stata 里跑出同样的结果

> 已完成全流程验证：`reproduce_all.do` 实测 **32 项核对全部 [OK]**，无报错。
> 数据：`stata_ads3.csv`（211 × 36，变量清理版）｜脚本：`reproduce_all.do`｜日志：`reproduce_all.log`

---

## 一、三种跑法，选一个

| 方式 | 怎么做 | 结果去哪 |
|---|---|---|
| **A. 图形界面**（推荐） | 双击 `D:\stady_resouce\StataMP-64.exe` → 菜单 **File → Do...**（`Ctrl+D`）→ 选 `d:\AI\爬虫\reproduce_all.do` | 直接显示在 **Results 窗口**；要存档就右键 **Save Results** |
| **B. 命令行** | Stata 底部 **Command 窗口** 输入：<br>`do "d:\AI\爬虫\reproduce_all.do"` | 同上 |
| **C. 批处理**（不弹界面） | PowerShell 里：<br>`Start-Process -FilePath 'D:\stady_resouce\StataMP-64.exe' -ArgumentList '/e','do','d:\AI\爬虫\reproduce_all.do' -WorkingDirectory 'd:\AI\爬虫' -Wait` | 自动写成 `reproduce_all.log` |

跑完最后会打印一张**核对清单**，把你的值和预期值逐项对比：

```
  [OK]  SSR                      算得       379.27156101 预期       379.27156101
  [OK]  SSE                      算得       849.71263382 预期       849.71263382
  ...
```

---

## 二、如果你想自己一行行敲

下面 12 步是完整链路，每步都给预期值，可逐段自检。

### 步骤 1-2：进目录、读数据

```stata
clear all
set more off
set linesize 200
cd "d:\AI\爬虫"
import delimited "stata_ads3.csv", encoding("UTF-8") clear
count
```
✅ 预期：`(36 vars, 211 obs)`，`count` = **211**

> ⚠️ 必须用 `stata_ads3.csv`（211×36），**不是** `stata_ads2.csv`（211×61，变量清理前的旧版），也不是 `stata_ads.csv`（211×34）或 `stata_data.csv`（470×34）。

### 步骤 3：变量工程（**最容易漏，漏了就复现不出来**）

```stata
* ① 精度修正：import delimited 把含小数的列存成 float（4 字节），
*    必须 drop 后用 gen double 重算，否则 SST 会差 1.4e-5（见 check_stata_types.do）
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)          // 因变量
gen double ln_followers = ln(followers)            // 真正的自然对数
gen double lnf_sq = ln_followers^2                 // 粉丝二次项
gen double tl     = text_len100                    // 文本长度以百字为单位
gen double tl_sq  = tl^2
gen byte   is_video = (media_type == "video")

* ② stata_ads3.csv 已内置 hist_prior_lnengage0（= 旧表 0 填充后的版本）
*    与 has_prior_hist，无需再 replace

encode appeal_grp, gen(appeal_n)
encode media_type, gen(media_n)
encode region_grp, gen(region_n)
```
✅ 预期：`ln_repost` 等四个变量的存储类型为 **double**（用 `describe` 核对）

> `hist_prior_lnengage0` 中的 41 条 0 值是"没有事前历史帖"的观测，已用 `has_prior_hist` 标记。这是 H1c 的口径设计。

### 步骤 4：Q1 基准回归

```stata
regress ln_repost ln_followers text_len n_pics is_lottery
```
✅ 预期：`Number of obs = 211`，`F(4, 206) = 22.99`，`R-squared = 0.3086`

### 步骤 5：取出平方和

```stata
scalar Q_SSR  = e(mss)
scalar Q_SSE  = e(rss)
scalar Q_SST  = Q_SSR + Q_SSE
scalar Q_MSR  = Q_SSR / e(df_m)
scalar Q_MSE  = Q_SSE / e(df_r)
scalar Q_RMSE = sqrt(Q_MSE)
scalar Q_R2   = Q_SSR / Q_SST
scalar Q_AR2  = 1 - (1 - Q_R2) * (e(N) - 1) / e(df_r)

display "SSR  = " %18.8f Q_SSR
display "SSE  = " %18.8f Q_SSE
display "SST  = " %18.8f Q_SST
display "MSR  = " %18.8f Q_MSR
display "MSE  = " %18.8f Q_MSE
display "RMSE = " %18.8f Q_RMSE
display "R2   = " %18.8f Q_R2
display "AdjR2= " %18.8f Q_AR2
```

✅ 预期全部值：

| 指标 | 预期值 |
|---|---:|
| SSR | 379.27156101 |
| SSE | 849.71263382 |
| SST | 1228.98419483 |
| MSR | 94.81789025 |
| MSE | 4.12481861 |
| Root MSE | 2.03096495 |
| R² | 0.30860573 |
| 调整 R² | 0.29518060 |

### 步骤 6：真正的手算（Q1 得分点）

```stata
predict double yhat, xb
predict double resid, residuals
summarize ln_repost
scalar YBAR = r(mean)

gen double sq_total = (ln_repost - YBAR)^2
gen double sq_expl  = (yhat       - YBAR)^2
gen double sq_resid = resid^2

summarize sq_expl
scalar HAND_SSR = r(sum)
summarize sq_resid
scalar HAND_SSE = r(sum)

display "手算 SSR = " %18.8f HAND_SSR
display "手算 SSE = " %18.8f HAND_SSE
display "SSR 差异 = " %20.12f HAND_SSR - Q_SSR
display "SSE 差异 = " %20.12f HAND_SSE - Q_SSE
```
✅ 预期：`SSR 差异 = -0.000000000000`、`SSE 差异 = 0.000000000000`（均在 10 位小数内为 0）

### 步骤 7-16：Q2 阶梯（目标 0.462909）

```stata
regress ln_repost ln_followers text_len n_pics is_lottery                                  // M0
regress ln_repost ln_followers text_len n_pics is_lottery ln_age_hours                     // M1
regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist text_len n_pics is_lottery ln_age_hours   // M2
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist text_len n_pics is_lottery ln_age_hours   // M3
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist text_len n_pics is_lottery ln_age_hours n_topics n_mentions   // M4
```

✅ 预期 R²：M0 0.308606｜M1 0.312457｜M2 0.449215｜M3 0.460951｜**M4 0.465922（首个达标）**

完整阶梯（M5–M9）见 `reproduce_all.do`。

### 步骤 17：主研究模型（HC3）

```stata
regress ln_repost ln_followers lnf_sq hist_prior_lnengage0 has_prior_hist ///
    text_len n_pics is_lottery ln_age_hours n_topics n_mentions ///
    n_promo n_brand is_enterprise is_personal_verified i.media_n i.appeal_n, vce(hc3)
```
✅ 预期：`R-squared = 0.4869`，`调整 R² = 0.4329`，`hist_prior_lnengage0` 系数 **0.3699（p=0.001）**

> ⚠️ 会出现 `note: 3.appeal_n omitted because of collinearity` —— 这是**正常的**，`抽奖导流` 与 `is_lottery` 完全重合。

### 步骤 18-19：Q3 分组与交互

```stata
forvalues g = 1/5 {
    regress ln_repost ln_followers hist_prior_lnengage0 has_prior_hist ///
        text_len n_pics is_lottery ln_age_hours if appeal_n == `g', vce(hc3)
    display "组 `g'  R2 = " %9.6f e(r2)
}

regress ln_repost c.ln_followers##i.appeal_n c.text_len##i.appeal_n ///
    hist_prior_lnengage0 has_prior_hist n_pics is_lottery ln_age_hours, vce(hc3)
testparm i.appeal_n#c.ln_followers
testparm i.appeal_n#c.text_len
```
✅ 预期分组 R²：组1 0.4299｜组2 0.5556｜组3 0.2959｜组4 0.4590｜组5 0.4701

---

## 三、32 项预期值总表（自检用）

### Q1（公式推导，非回归规格）

| # | 指标 | 预期 | |
|---|---|---|---:|
| 1 | SSR | 379.27156101 | |
| 2 | SSE | 849.71263382 | |
| 3 | SST | 1228.98419483 | |
| 4 | MSR | 94.81789025 | |
| 5 | MSE | 4.12481861 | |
| 6 | Root MSE | 2.03096495 | |
| 7 | R² | 0.30860573 | |
| 8 | 调整 R² | 0.29518060 | |

### Q2 阶梯

| # | 模型 | 预期 R² | |
|---|---|---|---:|
| 9 | M0 基准 | 0.30860573 | |
| 10 | M1 +曝光时长 | 0.312457 | |
| 11 | M2 +事前互动 | 0.449215 | |
| 12 | M3 +粉丝二次项 | 0.460951 | |
| 13 | **M4 +话题/@数** | **0.465922** | ← 首个达标 |
| 14 | M5 +促销/品牌 | 0.474817 | |
| 15 | M6 +认证 | 0.479310 | |
| 16 | M7 +媒体 | 0.479460 | |
| 17 | M8 +诉求类型 | 0.486908 | |
| 18 | M9 +地域 | 0.499844 | |
| 19 | 目标 1.5× | 0.462909 | |

### 主模型（HC3）

| # | 指标 | 预期 |
|---|---|---:|
| 20 | R² | 0.486908 |
| 21 | 调整 R² | 0.432898 |
| 22 | `hist_prior_lnengage0` 系数 | 0.3699421 |

### Q3 分组 R²

| # | 组 | 预期 R² | N |
|---|---|---|---:|---:|
| 23 | 价格促销 | 0.429904 | 28 |
| 24 | 品牌官宣 | 0.555561 | 66 |
| 25 | 抽奖导流 | 0.295932 | 41 |
| 26 | 硬广标识 | 0.458982 | 46 |
| 27 | 软植入 | 0.470109 | 30 |
| 28 | image | 0.401505 | 121 |
| 29 | video | 0.592762 | 63 |

### Q3 交互检验（联合 Wald）

| # | 交互项 | 预期 F | 预期 p |
|---|---|---:|---:|
| 30 | 诉求 × 粉丝规模 | 0.6245679 | 0.6455 |
| 31 | 诉求 × 文本长度 | 0.1395726 | 0.9674 |
| 32 | 视频 × 抽奖 | 0.0881961 | 0.7668 |

### 编码顺序（`encode` 自动按字符排序，会影响组号）

```stata
label list appeal_n     // 1=价格促销 2=品牌官宣 3=抽奖导流 4=硬广标识 5=软植入
label list media_n      // 1=image 2=link 3=text 4=video
```

---

## 四、跑不出来的排错表（都是我实际踩过的）

| 症状 | 原因 | 解法 |
|---|---|---|
| 结果窗口**没有 [OK] 那一节** | 用错了数据文件 | 确认 import 的是 `stata_ads3.csv` |
| **N 不是 211**（比如 470 或 329） | 用错数据文件 | 同上 |
| 提示 `variable ln_repost not found` | 漏了步骤 3 的变量工程（新表需 drop 后 gen double） | 补上 `drop ln_repost ln_followers lnf_c lnf_c2` 与 `gen double ln_repost = ln(reposts + 1)` |
| **SST 比预期多 1.4e-5** | 直接用了 CSV 里的 ln_repost（import 时被存成 float） | 必须 **`drop` 后 `gen double`**；`recast double` **无效**（见 `check_stata_types.do`） |
| `regress` 报 `_coef_table(): member _b_stat::set_bmat() not found` + `r(1)` | 上一次 Stata 进程没退出，或日志文件被占用 | 先全部关掉 Stata（PowerShell：`Stop-Process -Name StataMP-64 -Force`）再重跑 |
| `r(608) file cannot be modified` | 脚本里自带 `log using` 同名文件 | 删掉脚本内的 `log using`（`/e` 模式已自动写日志） |
| 结果读到**两份不同 N** | 旧进程还在写同一个日志 | 杀进程 → 删日志 → 重跑 |
| 中文乱码 | 用 PowerShell 读日志（按 ANSI 解码） | 用 Python 读，或直接在 Stata 窗口看 |
| `.do` 文件第一行报语法错 | 文件存成了 **UTF-8 with BOM** | 用记事本「另存为 → UTF-8（无 BOM）」，或直接用工作区里现成的脚本 |
| `note: 3.appeal_n omitted` | `抽奖导流` 与 `is_lottery` 完全共线 | **正常现象**，不用管 |

---

## 五、一键核对自己有没有跑对

```stata
* 跑完 reproduce_all.do 后，结果窗口最下方的「步骤 6：结果核对清单」
* 逐行出现 [OK] 就说明完全一致；出现 [!!] 说明该项不符，按上面排错表查
```

也可以在跑完后单独查：

```stata
display "Q1 SSR  = " %18.8f Q_SSR  "   (预期 379.27156101)"
display "Q1 R2   = " %18.8f Q_R2   "   (预期 0.30860573)"
display "M4 R2   = " %9.6f R2_M4   "   (预期 0.465922，首个达标)"
display "主模型R2= " %9.6f MAIN_R2 "   (预期 0.486908)"
```

> 上面这些 `Q_*` / `R2_M*` / `MAIN_R2` 标量只有在**同一次 Stata 会话里**跑过 `reproduce_all.do` 之后才存在。关了 Stata 就没了。

---

## 六、相关文件

| 文件 | 用途 |
|---|---|
| `reproduce_all.do` | **一键复现全部结果 + 自动核对**（本次验证通过） |
| `reproduce_all.log` | 复现的完整输出（49,796 字节） |
| `demo_q1.do` | 只演示 Q1 手算过程，逐段带 `display` 讲解 |
| `regression_final.do` | 正式版脚本（含前提检验、VIF、异方差、beta 标准化） |
| `Stata操作指南.md` | Stata 基础操作（`e()` 机制、`display` 格式、`predict`、导出结果） |
| `建模数据说明.md` | 数据在哪、生成链条、变量齐备性 |
| `回归模型_修订版.md` | 全部结果的解读与报告写法 |
