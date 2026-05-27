# P0 Trend Scheduler 实现笔记

## 实现时间
2026-05-24

## 涉及提交
- 924225b feat: P0 trend scheduler - 热点监控 + 自动选题
- 6b5cfd6 feat: 新增知乎、掘金热榜源
- 78b1033 feat: TrendScheduler 接入 TopicPicker 自动生成选题
- 77e7953 feat: LLM 评估过滤热点，只跟进高质量匹配
- dcb5b10 feat: 选题 accepted 后自动触发生成内容
- 64678e9 fix: 修复LLM评估器误判技术趋势 + 封装热点流水线命令
- 36978dd feat: RAG 向量检索（Chroma + BGE-small-zh），接入 TopicExecutor
- 3a91691 fix: RAG 过滤逻辑修复，按文件名匹配排除当前笔记
- d08c172 fix: RAG 双策略检索（内容+标题），增加调试输出
- 4f792b2 fix: RAG 三问题修复（本地模型加载 + PersistentClient + 自动索引）

## 新增模块

```
content_agent/trend_watcher/
  ├── __init__.py          # 导出所有组件
  ├── base.py              # TrendItem, TrendSource 抽象基类
  ├── weibo_hot.py         # 微博热搜（JSON API）
  ├── zhihu_hot.py         # 知乎热榜（需 ZHIHU_COOKIE）
  ├── juejin_hot.py        # 稀土掘金热榜（JSON API，已验证可用）
  └── evaluator.py         # TrendEvaluator: LLM 评估热点价值

automation/
  ├── trend_scheduler.py   # TrendScheduler: 定时检查→匹配→评估→选题
  └── topic_executor.py    # TopicExecutor: accepted→生成内容→入队
```

## 核心流程

```
[1] TrendScheduler.check_trends()
    ├── 拉取多源热榜（weibo/juejin/zhihu）
    ├── 关键词匹配（AGENT_TREND_KEYWORDS）
    ├── LLM 评估（只评前 N 条，防超时）
    └── 调用 TopicPicker 生成选题

[2] TopicPicker.pick_topics(trending_hint=...)
    ├── 扫描 Vault 笔记
    ├── 结合热点文本生成选题
    └── 保存到 topic_suggestions 表

[3] 人工 accept / 自动 --trend-auto
    └── TopicPicker.accept() → 自动触发 TopicExecutor

[4] TopicExecutor.execute()
    ├── 读取对应笔记
    ├── Orchestrator.run() 生成内容
    └── PublishQueue.add() 入队
```

## 关键配置

```bash
# 必需
export VAULT_PATH=/Users/lee/content-agent/notes
export DEEPSEEK_API_KEY=sk-...

# 热点监控
export AGENT_TREND_SOURCES="weibo,juejin"      # 热榜源
export AGENT_TREND_KEYWORDS="AI,Agent,LLM"     # 监控关键词
export AGENT_TREND_MAX_EVAL=5                  # 每次最多评估条数
export AGENT_TREND_MIN_CONFIDENCE=60           # 评估阈值
```

## CLI 命令

```bash
# 半自动：检查热点 → 生成选题 → 打印 ID 等你确认
python main.py --trend-pipeline

# 全自动：检查 → 生成 → 接受 → 生成内容 → 入队
python main.py --trend-pipeline --trend-auto --trend-limit=2

# 查看待发队列
python main.py --queue

# 接受指定选题（自动触发生成）
python main.py --accept-topic topic_xxx
```

## 踩坑记录

### 1. 微博反爬
- 问题：微博 HTML 页面有反爬，直接请求返回登录页
- 解决：改用微博公开 JSON API `https://weibo.com/ajax/side/hotSearch`

### 2. LLM 评估误判技术文章
- 问题：掘金热榜是技术文章，评估器按"突发热点"标准打分，大量过滤
- 解决：修改 prompt，区分"突发热点"和"技术趋势"，技术趋势重点评估实战价值

### 3. 超时
- 问题：完整流程 LLM 调用次数多（评估5条+生成选题），单次超过60秒
- 解决：
  - 限制评估数量 `AGENT_TREND_MAX_EVAL`（默认5条）
  - 选题生成限制 `trend-limit`（默认3条）
  - 建议生产环境用异步或增加超时

### 4. 数据库迁移
- 问题：新增 `generated_task_id` 字段，旧数据库不兼容
- 解决：修改 `agents/store.py` 建表语句，重建数据库（会丢失旧数据）

### 5. 笔记路径解析
- 问题：TopicPicker 生成的 `note_file` 是相对路径，TopicExecutor 找不到
- 解决：TopicExecutor._resolve_note_path() 增加递归查找，匹配文件名

### 6. RAG 检索失效（三连击）
- **问题1：BGE 联网卡住**
  - 现象：`SentenceTransformer('BAAI/bge-small-zh-v1.5')` 每次都要访问 HuggingFace，离线时抛错被 TopicExecutor 吞掉，表现为 RAG 内容为空
  - 解决：优先加载本地缓存，`local_files_only=True`，自动查找 `~/.cache/huggingface/hub/`
- **问题2：Chroma 非持久化**
  - 现象：`chromadb.Client()` 在当前版本下是内存模式，数据丢失
  - 解决：改用 `chromadb.PersistentClient()`，存储到 `data/chroma_db`
- **问题3：索引库为空**
  - 现象：`count=0`，即使检索链路正常也没有内容可取
  - 解决：TopicExecutor 增加自动索引，索引为空时自动调用 `index_vault()`
- **根因**：三个问题叠加，表现为"RAG 检索返回 0 条"
- **环境变量**：`AGENT_RAG_AUTO_INDEX=true` 控制自动索引（默认开启）

## 验证结果

| 环节 | 状态 |
|------|------|
| 掘金热榜抓取 | 正常，50条，匹配11条AI相关 |
| 微博热榜抓取 | 正常，51条，匹配1条 |
| LLM 评估 | 正常，技术趋势识别准确率提升 |
| 选题生成 | 正常，基于热点+vault笔记 |
| 接受选题自动触发 | 正常，accept后自动调用TopicExecutor |
| 内容生成入队 | 正常，公众号+小红书双平台 |
| RAG 向量检索 | 正常，3条相关笔记融合到生成内容 |
| 微信公众号发布 | 正常，已发布1篇（4479字） |

## 待优化

- [ ] 知乎热榜需要 ZHIHU_COOKIE，当前不可用
- [ ] 全自动模式 `--trend-auto` 生产环境建议加风控
- [ ] 热点效果追踪（发布后的阅读量/互动数据回流）
- [ ] 支持定时调度（目前 CLI 单次执行）
