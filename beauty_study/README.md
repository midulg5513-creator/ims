# 微博美妆品牌内容策略与短期传播效果：数据采集与分析工具

> 需求文档：`docs/weibo_data_collection_requirements.md`（用户 2026-09-28 修订版）
> 标注试验集：`docs/weibo_annotation_pilot.md`
> 主线方案：`项目重构方案.md`　需求对照：`REQUESTS_TRACE.md`

本目录是**新主线**的全部代码与产出。旧的「微博广告帖影响力研究」已归档（文件保留在 `d:\AI\爬虫\` 原位）。

---

## 0. 环境

```powershell
# 真实解释器（本机）
D:\python\python.exe --version        # 3.13
# 或使用本工作区虚拟环境
d:\AI\爬虫\.venv\Scripts\python.exe --version

# 依赖（parquet 导出需要）
d:\AI\爬虫\.venv\Scripts\python.exe -m pip install pandas pyarrow
```

> 采集与特征脚本**只依赖标准库 + requests**；pandas/pyarrow 仅在导出 parquet 时需要。

---

## 1. 一次完整流程

```powershell
cd d:\AI\爬虫\beauty_study
$PY = "d:\AI\爬虫\.venv\Scripts\python.exe"

# ① 解析品牌官方账号 uid（只搜不爬）
& $PY code\resolve_accounts.py
#    → 打开 data\account_candidates.csv 核对
#    → 在 brands.json 填好 uid / account_name，并把 confirmed 改为 true
#    （最可靠：& $PY code\resolve_accounts.py --set 薇诺娜=1234567890）

# ② 采集官方账号时间线
& $PY code\collect_timeline.py --dry-run          # 先探测
& $PY code\collect_timeline.py --days 60 --pages 5

# ③ 自动特征 + 词典特征
& $PY code\features.py

# ④ 多时点互动快照（1h/6h/24h/72h/7d；每小时跑一次）
& $PY code\snapshot.py --report
& $PY code\snapshot.py --due

# ⑤ 人工标注
& $PY code\annotate.py guideline      # 生成标注手册
& $PY code\annotate.py sample         # 分层抽 200–300 条
#   → 两位标注者分别填 a1_* / a2_*
& $PY code\annotate.py status
& $PY code\annotate.py kappa          # 商业意图 Kappa + 逐标签 F1

# ⑥ 质量验收 + 报告
& $PY code\quality.py --strict

# ⑦ 导出 parquet
& $PY code\export_parquet.py
```

---

## 2. 目录

| 路径 | 内容 |
|---|---|
| `config.json` | 品牌/窗口/限速/每日上限/词典版本（研究开始后冻结） |
| `brands.json` | 品牌清单（四类，含 uid 与 confirmed 标记） |
| `dictionaries.json` | 词典特征词表 + **version** |
| `code/` | 全部脚本 |
| `data/raw_snapshots/` | 原始 mblog JSONL（不公开再分发） |
| `data/posts_raw.csv` | 时间线归一化帖子主表 |
| `data/cleaned_posts.csv/.parquet` | 清洗 + 自动特征后的帖子 |
| `data/engagement_snapshots.csv/.parquet` | 多时点互动快照 |
| `data/annotation_sample.csv` | 标注样本（双标注者列 + 协商列） |
| `data/annotation_guideline.md` | 标注手册 |
| `reports/data_quality_report.md` | 质量报告（§9） |
| `reports/sampling_report.md` | 抽样报告 |
| `reports/kappa_report.md` | 一致性报告 |

---

## 3. 合规（需求 §3）

- 只处理公开可见内容；不采集私信、登录后内容、评论者资料。
- **不绕过验证码/访问控制/频率限制**；`config.json` 里写死请求间隔、重试上限、每日上限。
- 原始正文/图片/链接不公开再分发；作者标识只存**本地不可逆哈希** `author_hash`。
- 采集前请自行确认微博服务条款、robots 与数据保护法规。

---

## 4. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `没有可采集的品牌` | `brands.json` 未填 uid 或 `confirmed=false` | 先 `resolve_accounts.py`，再手工确认 |
| 时间线返回空 | 该账号需登录态 | `config.json` 设 `request.use_cookie=true` 并放置 `cookie.txt` |
| `当日请求上限已用尽` | 触发 `daily_request_limit` | 次日自动重置；或调高上限 |
| `未安装 pandas` | 未装依赖 | `pip install pandas pyarrow`（仅 parquet 需要） |
| 快照大量 `missed` | 未按时运行调度 | 提高调度频率；模型中控制 `post_age_hours` |

---

## 5. 关于「≥3 个观察窗口」的重要提示

快照只能在帖子发布**之后**才抓到，因此：

- **历史帖**（采集前已发布）：只有时间线里的**当前累计**互动，记为 `metric_observation_window=current`；
  1h/6h/24h/72h/7d 窗口一律为 `missed`（无法回溯）。
- **新帖**（采集开始后发布）：只要**每小时持续运行** `run_cycle.ps1` 或 `snapshot.py --due`，
  就会自然累积 1h/6h/24h/72h/7d 多窗口数据。

所以若要满足需求 §10 的「至少 3 个互动观察窗口」，必须**在采集期内保持调度常开**，
而不是事后补抓。模型里务必控制 `post_age_hours`，不能把当前累计互动当成统一周期效果。

推荐：先跑 `collect_timeline.py` 拿到历史帖做**横截面相关性分析**，
同时启动 `run_cycle.ps1` 让新帖累积观察窗口，两者分口径报告。

---

## 6. 关于登录 cookie（必读，2026-09-29 实测）

**微博已收紧公开接口**：不带登录态的请求现在一律被拒。

| 现象 | 含义 |
|---|---|
| `HTTP 432`（空 body） | 缺少访客 cookie（`_T_WM` 等）—— 客户端已自动「预热」解决 |
| `{"ok":-100,"url":"...passport.weibo.com/sso/signin..."}` | **需要登录态**，必须提供 cookie |
| `api/config` 返回 `login:false` | cookie 无效或已过期 |

实测（2026-09-29）：`m.weibo.cn` 与 `weibo.com/ajax/*` 的全部资料/时间线入口，
**无 cookie 时全部返回 `ok=-100`**；因此本项目需要一次登录 cookie。

### 6.1 如何取得（约 1 分钟）

1. 浏览器登录微博，打开 `https://m.weibo.cn/`。
2. 按 **F12** → **Network（网络）** → **F5 刷新**（必须先开面板再刷新，否则请求列表为空）。
3. 点任意一条 `m.weibo.cn` 请求 → 右键 → **Copy → Copy as cURL**。
4. 把内容粘贴保存到 **`d:\AI\爬虫\beauty_study\cookie.txt`**（该文件已被 `.gitignore` 忽略，不会入库）。

也支持直接粘贴 `cookie: xxx` 那一行，或纯 `SUB=...; SUBP=...` 字符串。

### 6.2 验证

```powershell
& $PY code\probe_login.py            # 看 config 是否 login=true
& $PY code\probe_public.py           # 看各入口是否可用
```

`login=true` 才说明可用；否则重新导出。

### 6.3 合规说明（需求 §3）

- 本项目使用**你自己的登录会话**读取**公开可见内容**，不绕过验证码、不伪造身份、不提权。
- cookie 是敏感凭据：只存本地 `cookie.txt`，**已被 .gitignore 排除**，切勿提交或分享。
- 仍受 `config.json` 的请求间隔 / 重试上限 / 每日上限约束。
