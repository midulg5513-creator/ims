# 需求 → 实现 逐条对照

需求文档：`docs/weibo_data_collection_requirements.md`
状态：✅ 已实现　🅿️ 待排期　➖ 非代码（流程/文档）

---

## §1 项目目标
| 需求 | 实现 | 状态 |
|---|---|---|
| 帖子级数据集 | `data/cleaned_posts.csv/.parquet` | ✅ |
| 用于相关性分析与短期预测 | 字段齐备（§4）；建模管线 | 🅿️ |
| 不作严格因果声称 | 报告口径统一写「条件相关」 | ➖ |

## §2 数据范围
| 需求 | 实现 | 状态 |
|---|---|---|
| 10–15 个美妆/护肤/个护品牌官方账号 | `brands.json`（16 候选，四类各 4） | ✅ |
| 四类覆盖 | `brands.json.categories` | ✅ |
| 最近 30–45 天（可先抓 60 天） | `config.study.analysis_window_days=45` / `collection_window_days=60` | ✅ |
| 1,000–2,500 条，每品牌 ≥50 | `quality.py` 三项检查 | ✅ |
| 主窗口 72h；补充 1/6/24/7d | `config.study.snapshot_windows_hours` | ✅ |
| 优先连续抓官方账号时间线 | `collect_timeline.py`（`containerid=107603<uid>`） | ✅ |

## §3 合规边界
| 需求 | 实现 | 状态 |
|---|---|---|
| 只处理公开内容 | 默认不带登录态；`use_cookie` 缺省 false | ✅ |
| 不采集私信/登录后/评论者资料 | 只抓官方账号时间线与帖子详情 | ✅ |
| 不绕过验证码/访问控制/频率限制 | 无验证码绕过代码；串行请求 + 限速 | ✅ |
| 遵守 ToS/robots/法规 | `README.md` §3 提示 | ➖ |
| 请求间隔 / 重试上限 / 每日上限 | `config.request.delay_seconds` / `max_retries` / `daily_request_limit`；`common.RequestBudget` / `RateLimiter` | ✅ |
| 原始内容不公开再分发 | `data/raw_snapshots/` 标注「不公开」；`README.md` | ➖ |
| 作者标识只存不可逆哈希 | `common.author_hash()` → `author_hash` 列 | ✅ |

## §4 必采字段
| 字段 | 位置 | 状态 |
|---|---|---|
| `post_id` `post_url` `brand` `account_type` `is_original` `parent_post_id` `collection_time` | `mweibo.parse_mblog` → `POST_FIELDS` | ✅ |
| `text_raw` `text_clean` `hashtags_raw` `mentions_count` `external_link_count` | 同上 | ✅ |
| `image_count` `has_video` `has_live` `media_type` | 同上 | ✅ |
| `published_at` `like_count` `comment_count` `repost_count` `follower_count` `post_age_hours` `metric_observation_window` | 帖子表 + 快照表 | ✅ |
| `fetch_status` `missing_fields` `is_duplicate` `exclusion_reason` | 同上 | ✅ |
| 互动数与抓取时间一起保存 | `snapshot.py` 的 `snapshot_at` + `age_hours` | ✅ |

## §5 自动生成特征
| 需求 | 实现 | 状态 |
|---|---|---|
| 正文长度 | `text_length` `text_length_no_tag` | ✅ |
| 问号/感叹号 | `q_count` `exclam_count` | ✅ |
| 表情数量 | `emoji_count` | ✅ |
| 话题数 | `hashtag_count` | ✅ |
| 购买引导/折扣/抽奖/新品/明星/功效/场景 | `has_*` / `n_*`（`dictionaries.json`） | ✅ |
| 发帖小时/星期/周末/节假日 | `pub_hour` `pub_dow` `is_weekend` `is_holiday` `holiday_name` | ✅ |
| **词典版本号** | `dictionary_version`（每行写入 + 报告记录） | ✅ |

## §6 人工标注字段
| 需求 | 实现 | 状态 |
|---|---|---|
| 6.1 商业意图（单选 0–4） | `a1_commercial_intent` / `a2_*` / `r_*` | ✅ |
| 6.2 营销策略（多选 11 项） | `a*_celebrity … a*_call_to_action` | ✅ |
| 6.3 表达方式（多选 6 项） | `a*_expression_*` | ✅ |
| 6.4 可信度与风险 4 项 | `a*_has_evidence/user_scenario/exaggeration/purchase_link` | ✅ |
| 「判断整条帖子，不依据单个关键词」 | `annotation_guideline.md` 明示 | ➖ |

## §7 抽样和标注流程
| 需求 | 实现 | 状态 |
|---|---|---|
| 按品牌×日期/周×内容形式×初始互动分层抽样 | `annotate.py sample`（四维分层 + 每层保底） | ✅ |
| 不能只标高互动帖 | 分层含转发四分位，每层保底 1 条 | ✅ |
| 先抽 200–300 双人试标 | `config.annotation.pilot_size_*` | ✅ |
| 商业意图 Cohen's Kappa | `annotate.py kappa` | ✅ |
| 多标签逐标签 F1/Jaccard | 同上 | ✅ |
| Kappa<0.60 修订；0.60–0.75 记录；>0.75 扩大 | `kappa` 输出判定 | ✅ |
| 正式样本 10%–15% 双人复核 | `config.annotation.double_review_share=0.15` | ✅ |
| 保存 `annotation_version/annotator_id/annotation_time/adjudication_status` | 标注表列 | ✅ |

## §8 互动快照机制
| 需求 | 实现 | 状态 |
|---|---|---|
| 1h/6h/24h/72h/7d 重复抓取 | `snapshot.py` | ✅ |
| 快照表字段 | `SNAPSHOT_FIELDS`（含 §8 全部字段） | ✅ |
| 无法回访时只纳入观察期充分的帖子 + 控制 `post_age_hours` | `missed` 显式标记 + 报告提示 | ✅ |
| 不把当前累计互动称为统一周期效果 | 报告口径 | ➖ |

## §9 数据质量验收
| 需求 | 实现 | 状态 |
|---|---|---|
| ID 唯一性、发布时间逻辑、互动数非负、重复记录、各品牌每周样本量、缺失率、极端值、互动数异常下降、完全重复文本 | `quality.py` 11 项检查 | ✅ |
| post_id 重复率 <1% | 检查 1 | ✅ |
| 发布时间可解析率 ≥98% | 检查 2 | ✅ |
| 三项互动可用率 ≥90% | 检查 3 | ✅ |
| 官方账号身份确认率 ≥95% | 检查 5 | ✅ |
| 关键字段缺失必须报告，不得静默填 0 | 检查 11 + 报告第二节 | ✅ |

## §10 建模最低要求
| 需求 | 实现 | 状态 |
|---|---|---|
| 10–15 品牌 / 1,000–2,500 帖 / ≥200 试标 / ≥3 观察窗口 / 每策略 ≥30 | `quality.py` 覆盖数据侧；策略样本量 | 🅿️ 部分 |
| 负二项回归（点赞/评论/转发） | 建模管线 | 🅿️ |
| 品牌固定效应/随机效应 | 建模管线 | 🅿️ |
| 策略交互项 | 建模管线 | 🅿️ |
| CatBoost/LightGBM 预测高转发 | 建模管线 | 🅿️ |
| 按时间切分测试集 | 建模管线 | 🅿️ |
| 加人工标签前后消融实验 | 建模管线 | 🅿️ |

## §11 输出文件
| 需求路径 | 本项目路径 | 状态 |
|---|---|---|
| `data/raw_snapshots/` | `data/raw_snapshots/` | ✅ |
| `data/cleaned_posts.parquet` | 同名（`export_parquet.py`） | ✅ |
| `data/engagement_snapshots.parquet` | 同名 | ✅ |
| `data/annotation_sample.csv` | 同名 | ✅ |
| `data/annotation_guideline.md` | 同名 | ✅ |
| `reports/data_quality_report.md` | 同名 | ✅ |
| `reports/sampling_report.md` | 同名 | ✅ |
| 对外只发布脱敏/聚合/代码/标签/质量报告 | `README.md` 声明 | ➖ |

## §12 完成标准
| 需求 | 实现 | 状态 |
|---|---|---|
| 字段/账号范围/观察期符合文档 | `quality.py` | ✅ |
| 每条记录有抓取时间 | `collection_time` / `snapshot_at` | ✅ |
| 帖子 ID 去重 | `collect_timeline.py` 增量去重 | ✅ |
| 互动数与帖子年龄可对应 | `age_hours` | ✅ |
| 排除和缺失原因有记录 | `exclusion_reason` / `missing_fields` / `fetch_status` | ✅ |
| 抽样偏差/搜索排序偏差/版权限制写入报告 | `reports/sampling_report.md` §四 | ✅ |
| 支持至少一个统计模型 + 一个时间外预测实验 | 建模管线 | 🅿️ |
