# 微博美妆品牌内容数据抓取要求

## 1. 项目目标

建立用于研究“微博美妆品牌内容策略与短期传播效果”的帖子级数据集。核心问题是：最近一个营销周期内，哪些内容形式和营销策略更容易获得点赞、评论和转发？数据用于相关性分析和短期预测，不用于声称广告投放的严格因果效果。

## 2. 数据范围

- 平台：微博公开页面。
- 账号：10–15个美妆、护肤或个护品牌官方账号。
- 品牌应覆盖国产大众/新消费、国产功效护肤、国际大众和国际高端四类。
- 时间：最近30–45天；可先抓最近60天，再筛选观察期充分的帖子。
- 目标规模：1,000–2,500条帖子，每个品牌至少约50条。
- 主结果窗口：发布后72小时；补充窗口：1小时、6小时、24小时和7天。
- 优先连续抓取官方账号时间线，不只抓热门帖或搜索结果。

## 3. 合规边界

- 只处理公开可见内容。
- 不采集私信、登录后才可见内容、评论者资料或非必要个人识别信息。
- 不绕过验证码、访问控制、频率限制或其他安全措施。
- 遵守微博服务条款、robots规则、数据保护法规和数据来源许可。
- 设置请求间隔、失败重试上限和每日请求上限。
- 原始正文、图片和链接不公开再分发；作者标识如确有必要只保存本地不可逆哈希。

## 4. 必采字段

### 4.1 帖子和账号

| 字段 | 说明 |
|---|---|
| `post_id` | 帖子唯一标识，必填 |
| `post_url` | 公开链接，仅内部使用 |
| `brand` | 品牌名称 |
| `account_type` | `brand_official`、`media`、`KOL`、`individual`或`unknown` |
| `is_original` | 是否原创微博 |
| `parent_post_id` | 转发或回复链原帖ID，可为空 |
| `collection_time` | 本次抓取时间 |

### 4.2 正文和媒体

| 字段 | 说明 |
|---|---|
| `text_raw` | 原始正文，内部保存 |
| `text_clean` | 清洗后的正文 |
| `hashtags_raw` | 话题标签 |
| `mentions_count` | @数量 |
| `external_link_count` | 外链数量 |
| `image_count` | 图片数量 |
| `has_video` | 是否含视频 |
| `has_live` | 是否含直播或直播预告 |
| `media_type` | `text`、`image`、`video`或`mixed` |

### 4.3 时间和互动

| 字段 | 说明 |
|---|---|
| `published_at` | 发帖时间，尽量精确到分钟 |
| `like_count` | 抓取时点赞数 |
| `comment_count` | 抓取时评论数 |
| `repost_count` | 抓取时转发数 |
| `follower_count` | 抓取时粉丝数，如公开可见 |
| `post_age_hours` | `collection_time - published_at` |
| `metric_observation_window` | `1h`、`6h`、`24h`、`72h`、`7d`或`current` |

互动指标必须和抓取时间一起保存，不能只保存没有时间含义的累计数。

### 4.4 抓取状态

保存`fetch_status`（`success`、`partial`或`failed`）、`missing_fields`、`is_duplicate`和`exclusion_reason`。

## 5. 自动生成特征

生成正文长度、问号/感叹号标记、表情数量、话题数、购买引导、折扣、抽奖、新品、明星、产品功效、使用场景、发帖小时、星期、周末和节假日等字段。词典特征必须记录版本号，例如`dictionary_version = v1.0`。

## 6. 人工标注字段

### 6.1 商业意图（单选）

- `0`：非商业内容。
- `1`：软性种草。
- `2`：明确促销或转化。
- `3`：品牌公关或品牌形象。
- `4`：无法判断。

### 6.2 营销策略（多选）

- `celebrity`：明星或代言。
- `new_product`：新品发布。
- `discount`：折扣、优惠或赠品。
- `giveaway`：抽奖或有奖转发。
- `livestream`：直播或直播引流。
- `product_benefit`：功效、成分或参数。
- `usage_tutorial`：使用教程。
- `usage_scenario`：使用场景。
- `topic`：话题或挑战。
- `interaction`：提问、征集或粉丝互动。
- `call_to_action`：购买、点击、评论或转发引导。

### 6.3 表达方式（多选）

- `informational`：信息说明型。
- `emotional`：情绪感染型。
- `interactive`：互动对话型。
- `authority`：专业或证据型。
- `storytelling`：故事或场景型。
- `promotional`：促销型。

### 6.4 可信度与风险

保存`has_evidence`、`has_user_scenario`、`has_exaggeration`和`has_purchase_link`。

判断整条帖子，不能依据单个关键词。普通用户体验帖只有在研究“整体种草传播”时纳入；若只研究官方广告，应排除或单独记录账号类型。

## 7. 抽样和标注流程

按品牌、日期/周、内容形式和初始互动水平分层抽样，不能只标高互动帖子。

1. 先抽200–300条，由两名标注者独立试标。
2. 商业意图计算Cohen's Kappa，多标签计算逐标签F1或Jaccard。
3. Kappa低于0.60时先修订定义；0.60–0.75记录边界规则；高于0.75再扩大标注。
4. 正式样本的10%–15%进行双人复核。
5. 保存`annotation_version`、`annotator_id`、`annotation_time`和`adjudication_status`。

## 8. 互动快照机制

同一帖子尽量在发布后约1小时、6小时、24小时、72小时和7天重复抓取。互动快照表至少包含：

```text
post_id | published_at | snapshot_at | age_hours | like_count | comment_count | repost_count
```

无法回访时，只纳入观察期充分的帖子，并在模型中控制`post_age_hours`，不能把当前累计互动称为统一周期效果。

## 9. 数据质量验收

自动检查ID唯一性、发布时间逻辑、互动数非负、重复记录、各品牌每周样本量、缺失率、极端值、互动数异常下降和完全重复文本。

建议阈值：

- `post_id`重复率小于1%。
- 发布时间可解析率不低于98%。
- 三项互动字段可用率不低于90%。
- 官方账号身份确认率不低于95%。
- 关键字段缺失必须报告，不得静默填0。

## 10. 建模最低要求

- 10–15个品牌。
- 1,000–2,500条帖子。
- 至少200条人工试标。
- 至少3个互动观察窗口。
- 每个主要内容策略至少30条样本。

推荐实验包括：负二项回归解释点赞、评论和转发；品牌固定效应或随机效应；策略交互项；CatBoost或LightGBM预测高转发；按时间切分测试集；比较加入人工标签前后的消融实验。

## 11. 输出文件

```text
data/raw_snapshots/                 原始快照，不公开
data/cleaned_posts.parquet          清洗后的帖子
data/engagement_snapshots.parquet   互动快照
data/annotation_sample.csv          标注样本
data/annotation_guideline.md        标注手册
reports/data_quality_report.md      质量报告
reports/sampling_report.md          抽样报告
```

对外只发布脱敏特征、聚合统计、模型代码、标签定义和质量报告，不发布用户识别信息、评论者信息、未授权图片或大规模原始正文。

## 12. 完成标准

字段、账号范围和观察期符合本文档；每条记录有抓取时间；帖子ID去重完成；互动数与帖子年龄可对应；排除和缺失原因有记录；抽样偏差、搜索排序偏差和版权限制写入报告；数据支持至少一个统计模型和一个时间外预测实验。
