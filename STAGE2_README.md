# 第二阶段：600 条定窗广告帖研究

本目录中的原有 `posts.csv`、`stata_ads2.csv`、`econometric_final.do` 和第一阶段答案不被第二阶段程序覆盖。

## 1. 初始化和账号抽样框

```powershell
python prospective_study.py init
```

当前应急采集模式是 `keyword_quota_fast24h`：程序按六个行业的关键词发现候选帖子，允许首次发现距发布时间最多 24 小时，再按
行业×账号类型配额决定是否纳入，不要求候选作者预先出现在账号表中。

该模式用于在有限时间内完成样本，不再是原先严格的 T0 两小时设计；实际
`discovery_age_hours` 会保留，后续回归必须控制该变量。

`stage2_accounts.csv` 作为人工核实和分类覆盖表使用。`account_type` 只能使用
`brand_official`、`kol_verified`、`media_other`；`roster_role` 使用 `primary` 或
`reserve`。主账号使用 `active=1`；备用账号先使用 `active=0`，只有发生有记录的替换时
才改为 `active=1`。登记结果会优先于程序根据认证信息作出的自动分类。

如需复现原来的固定账号设计，可把 `study.sampling_mode` 改为 `roster`；该模式下正式
发现命令会拒绝账号表之外的作者。`--allow-open-discovery` 仅供前期接口试跑，不得
用于正式 600 条样本。

行业、配额、关键词、时间窗口及人工编码阈值集中保存在
`stage2_config.json`。研究开始后应冻结该文件；任何修改均需在报告中记录日期和原因。
第一次正式运行前必须填写 `study.collection_start_utc`，例如
`2026-09-21T00:00:00Z`；发现命令会在该时点之前和连续 90 天之后停止。

## 2. 前瞻性发现与快照

建议每小时运行一次发现命令：

```powershell
python prospective_study.py discover --pages 3 --delay 2
```

第二阶段默认使用不带登录 Cookie 的公开接口。只有公开接口不可用且研究者明确接受登录态
请求时，才在命令后添加 `--use-cookie`；该选项会把本地微博会话 Cookie 随请求发送给微博。

Windows 计划任务可以每小时调用 `run_stage2_cycle.ps1`。脚本使用进程锁防止重复周期，
依次执行发现、到期快照和审计；采集结束日期由 `stage2_config.json` 与研究日志共同冻结。

程序会记录所有首次发现的候选帖。只有原创、自动判定为广告、首次发现不超过发布后
24 小时、未超过作者上限且所在行业×账号类型配额未满的帖子会进入
`stage2_posts.csv`，并立即写入
不可覆盖的 T0 快照。排除项及原因仍保留在 `sampling_frame.csv`。

建议每小时运行一次到期快照命令：

```powershell
python prospective_study.py snapshots --window all --delay 2
```

成功且处于容差内的窗口不会重复抓取。每次请求尝试都追加到
`post_snapshots.csv`；错误、删除、超窗和真实零互动是不同状态。

## 3. 人工编码和审计

样本数量足够后生成固定随机种子的双人编码表：

```powershell
python prospective_study.py manual-sample
```

两位编码者分别填写 `ad_label`、`appeal_type`、`lottery_label`、
`hard_ad_label`。存在分歧时只在 `reconciled_*` 字段填写协商结论，不覆盖原始编码。
二元标签统一填写 `0` 或 `1`；诉求类型统一填写 `welfare`、`content`、`official`、
`hard_ad` 或 `other`。

```powershell
python prospective_study.py audit
python build_stage2_data.py
```

前一条命令生成配额和流失报告；后一条命令选择合格快照、合并人工标签、构造严格事前
作者特征，并生成 `stage2_analysis.csv`。Cohen's kappa 低于 0.80 时，数据审计会标记
失败，须修订编码规则并完整复编码。

## 4. 计量分析

```powershell
python econometric_stage2.py --power-only
python econometric_stage2.py
stata -b do econometric_stage2.do
```

Python 和 Stata 均以 T+24h 转发计数的 PPML 为主模型，另报告 HC3/作者聚类 OLS、
hurdle、负二项、T+7d 稳健性及诉求类型交互检验。只有重复作者覆盖达到预设门槛时才
运行作者固定效应。任一诉求组少于 80 条时，交互结果自动标记为探索性。

搜索关键词、页码、同期点赞和同期评论不进入转发主模型。所有结果解释为条件相关关系。
