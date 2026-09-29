# Stata 自己算：操作指南

> 配套脚本：`demo_q1.do`（可跟着一步步跑的演示）｜ `regression_final.do`（完整正式版）
> 你的 Stata：`D:\stady_resouce\StataMP-64.exe`（Stata 18 MP）

---

## 一、怎么启动并运行

### 方式 A：图形界面（推荐先用这个，看得见结果）

1. 双击 `D:\stady_resouce\StataMP-64.exe` 打开 Stata
2. 菜单 **File → Do...**（或按 `Ctrl+D`）
3. 选 `d:\AI\爬虫\demo_q1.do`
4. 结果立刻显示在 **Results 窗口**（右上）

> 想边看边改：菜单 **Window → Do-file Editor**（`Ctrl+9`），把 `demo_q1.do` 拖进去，
> 选中若干行按 `Ctrl+D` 只跑选中部分。

### 方式 B：命令行

在 Stata 底部的 **Command 窗口** 输入：

```stata
cd "d:\AI\爬虫"
do "demo_q1.do"
```

### 方式 C：不进界面，批处理跑（就是我刚才用的）

```powershell
Start-Process -FilePath 'D:\stady_resouce\StataMP-64.exe' `
  -ArgumentList '/e','do','d:\AI\爬虫\demo_q1.do' `
  -WorkingDirectory 'd:\AI\爬虫' -Wait
```

> `/e` = 批处理模式，跑完自动退出，并把全部输出写进 `demo_q1.log`。
> ⚠️ 此模式下 Stata **自动**生成 `<脚本名>.log`，所以脚本里**不要**再写
> `log using "demo_q1.log"`，否则报 `r(608)`。

---

## 二、核心：Stata 把回归结果存在哪

跑完 `regress` 之后，结果不是「打印完就没了」，而是存在 **`e()`** 里。这是自己算的关键。

```stata
regress ln_repost ln_followers text_len n_pics is_lottery
ereturn list          // ← 把全部可用项列出来
```

你会看到：

| 存的东西 | 含义 | 本次实测值 |
|---|---|---|
| `e(mss)` | Model SS = **SSR**（回归平方和） | 379.2715610054851 |
| `e(rss)` | Residual SS = **SSE**（残差平方和） | 849.712633822155 |
| `e(r2)` | 判定系数 R² | 0.3086057270725734 |
| `e(r2_a)` | 调整 R² | 0.2951805955594194 |
| `e(rmse)` | Root MSE | 2.030964945730763 |
| `e(df_m)` | 模型自由度 = 自变量个数 k（**不含常数项**） | 4 |
| `e(df_r)` | 残差自由度 | 206 |
| `e(N)` | 样本量 | 211 |
| `e(F)` | F 统计量 | 22.98716603038132 |

> **注意 `e(mss)`/`e(rss)` 的命名陷阱**：OLS 里 `mss` = Model SS = SSR，`rss` = Residual SS = SSE。
> 而很多教材把 `RSS` 写成「Regression SS」（= SSR）。**混用会直接搞反**——范文那份报告就是把这个搞反了。

---

## 三、显示计算结果的三种写法

### 写法 1：直接 display 表达式

```stata
display 379.27156101 / 1228.98419483
```

### 写法 2：带格式（推荐）

```stata
display "R2 = " %18.8f 0.3086057270725734
```

`%18.8f` = 总宽 18 位、小数点后 8 位的定点格式。常用格式：

| 格式 | 含义 | 例 |
|---|---|---|
| `%18.8f` | 定点 8 位小数 | `379.27156101` |
| `%9.6f` | 定点 6 位小数 | `0.308606` |
| `%12.0f` | 整数 | `211` |
| `%20.12e` | 科学计数 | 看极小差异用这个 |

### 写法 3：先存标量再显示（推荐，便于复用）

```stata
scalar SSR = e(mss)
scalar SSE = e(rss)
scalar SST = SSR + SSE
display "SSR = " %18.8f SSR
```

---

## 四、完整可粘贴版（20 行拿到 Q1 全部答案）

打开 Stata，把下面整段贴进 Command 窗口回车：

```stata
import delimited "d:\AI\爬虫\stata_ads3.csv", encoding("UTF-8") clear
drop ln_repost ln_followers lnf_c lnf_c2
gen double ln_repost    = ln(reposts + 1)
gen double ln_followers = ln(followers)
regress ln_repost ln_followers text_len n_pics is_lottery

scalar SSR = e(mss)
scalar SSE = e(rss)
scalar SST = SSR + SSE
scalar K   = e(df_m)
scalar DFR = e(df_r)
scalar N   = e(N)
scalar MSR = SSR / K
scalar MSE = SSE / DFR

display "SSR    = " %18.8f SSR
display "SSE    = " %18.8f SSE
display "SST    = " %18.8f SST
display "MSR    = " %18.8f MSR
display "MSE    = " %18.8f MSE
display "RootMSE= " %18.8f sqrt(MSE)
display "R2     = " %18.8f SSR / SST
display "AdjR2  = " %18.8f 1-(1-SSR/SST)*(N-1)/DFR
```

---

## 五、真正的手算：用 `predict` 从数据算，不从 `e()` 反推

**这一步是作业 Q1 的得分点。** 从 `e()` 反推出来的「手算」与软件差异恒为 0，答不了「分析差异」。

```stata
* 1) 拿到拟合值和残差
predict double yhat, xb
predict double resid, residuals

* 2) 拿因变量均值
summarize ln_repost
scalar YBAR = r(mean)

* 3) 逐项构造平方，再求和
gen double sq_total = (ln_repost - YBAR)^2
gen double sq_expl  = (yhat       - YBAR)^2
gen double sq_resid = resid^2

* 4) summarize 之后用 r(sum) 取总和
summarize sq_total
scalar HAND_SST = r(sum)
summarize sq_expl
scalar HAND_SSR = r(sum)
summarize sq_resid
scalar HAND_SSE = r(sum)

* 5) 显示并与 e() 对比
display "手算 SST = " %18.8f HAND_SST
display "手算 SSR = " %18.8f HAND_SSR
display "手算 SSE = " %18.8f HAND_SSE
display "SSR 差异 = " %20.12f HAND_SSR - e(mss)
display "SSE 差异 = " %20.12f HAND_SSE - e(rss)
```

### 本次实测结果（可直接写进报告）

| 指标 | 手算（predict） | Stata `e()` | 差异 |
|---|---:|---:|---:|
| SSR | 379.27156101 | 379.27156101 | **0** |
| SSE | 849.71263382 | 849.71263382 | **0** |
| SST | 1228.98419483 | 1228.98419483 | **0** |

> **✅ 这就是 Q1 要的「差异分析」素材**：
> 在 Stata 内部（同一份变量）手算 SSR/SSE 与 `e(mss)`/`e(rss)` 的差异均为 **0**（10 位小数内）；
> 若改用 **Python 以正规方程独立复算**，差异为 −4.51×10⁻⁹（SSR）与 +2.16×10⁻⁹（SSE），量级是**浮点舍入误差**，不是口径错误。
> 而如果是口径错（比如调整 R² 的分母误用 `n-k`），差异会到 **10⁻³** 量级（0.00340492，差 6 个数量级）。
> 报告里就写这一条对比。

> ⚠️ **另有一个真实陷阱（2026-09-24 实测）**：`import delimited` 会把含小数的列存成 **float（4 字节）**。
> 若直接读 CSV 里预先算好的 `ln_repost`，SST 会变成 1228.98420922（差 1.4e-5）。
> **`recast double` 无效**，必须 `drop` 后 `gen double` 重算。证据：`check_stata_types.do`。

---

## 六、双精度技巧：让差异看得见

Stata 默认 `float` 只有约 7 位有效数字，存平方和会掉精度。要看真实差异：

```stata
* 把关键变量强制成双精度
gen double sq_resid = resid^2          // 用 double
* 显示用 12 位有效数字的格式
display %20.12f HAND_SSE - e(rss)
```

---

## 七、把结果导出来交作业

### 7.1 最简单的：存 log（最稳）

```stata
log using "d:\AI\爬虫\我的结果.log", replace text
* ... 跑你的命令 ...
log close
```

> ⚠️ 如果用 `/e` 批处理模式，**别写这段**（Stata 已自动写日志，会 `r(608)`）。

### 7.2 从 Results 窗口复制

Results 窗口里选中内容 → 右键 → **Copy as table / Copy**，可直接粘进 Word。

### 7.3 存成 Excel（需要 Stata 内置 `putexcel`，无需装插件）

```stata
regress ln_repost ln_followers text_len n_pics is_lottery
putexcel set "d:\AI\爬虫\结果.xlsx", replace
putexcel A1 = "SSR"  B1 = e(mss)
putexcel A2 = "SSE"  B2 = e(rss)
putexcel A3 = "SST"  B3 = e(mss) + e(rss)
putexcel A4 = "R2"   B4 = e(r2)
putexcel A5 = "AdjR2" B5 = e(r2_a)
putexcel A6 = "RootMSE" B6 = e(rmse)
```

### 7.4 输出回归表到 Word（需先装 `estout`）

```stata
ssc install estout, replace
esttab using "d:\AI\爬虫\表1.rtf", replace ///
    b(%9.3f) se(%9.3f) star(* 0.10 ** 0.05 *** 0.01) ///
    stats(N r2 r2_a rmse, labels("样本量" "R2" "调整R2" "RootMSE"))
```

---

## 八、常见坑（我实际踩过的）

| 现象 | 原因 | 解法 |
|---|---|---|
| `r(608) file cannot be modified` | `/e` 模式已自动写 `<脚本名>.log`，脚本里又 `log using` 同名文件 | 删掉脚本内的 `log using`，或换文件名 |
| 读日志读到**两份不同结果** | 上一个 Stata 进程没退出，新日志被追加 | 先 `Stop-Process -Name StataMP-64 -Force` 再跑 |
| 运行中读 `.log` 报「文件正由另一进程使用」 | Stata 运行期间**独占**日志 | 等进程退出后再读 |
| 多行命令被截断 | PowerShell 把多行 `-c` 只留第一行 | 写成 `.py` / `.do` 文件再跑 |
| 中文乱码 | `Get-Content` 按 ANSI 解码无 BOM 的 UTF-8 | 用 Python 读文件 |
| `text_len^2` 报条件数过大 | 原始字符数平方达 10⁶ | 先除以 100 再平方 |
| 交互项全被 omit | 完全共线（如 `is_lottery` 与 `appeal=抽奖导流` 重合） | 二者只放一个 |

---

## 九、分三步走的建议路径

| 步骤 | 做什么 | 看什么 |
|---|---|---|
| **第 1 步** | 图形界面打开 `demo_q1.do`，`Ctrl+D` 跑一遍 | Results 窗口里 7 个 `=====` 分段，每段的中间量都能看到 |
| **第 2 步** | 把第五节那段 `predict` 手算**自己敲一遍** | 关注最后的「SSR 差异」是不是 10⁻¹² 量级 |
| **第 3 步** | 图形界面跑 `regression_final.do` | 得到 Q1/Q2/Q3 的完整正式结果，存 log 交作业 |

**自检标准**：如果你在 Results 里能看到
`SSR 差异 = -0.000000000001`，
说明你的手算和软件口径完全一致，这一问就答完了。
