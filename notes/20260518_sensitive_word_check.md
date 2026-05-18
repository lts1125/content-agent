# 敏感词预检功能实现笔记

## 背景/需求

Roadmap P1-10：用户在生成文案前，如果笔记中包含敏感词、广告法极限词或低俗内容，发布到自媒体平台后可能被判违规、限流甚至封号。需要一个预检机制，在生成文案前提醒用户。

## 设计思路

采用 **本地词表 + 可选百度API** 的混合方案：

- **本地词表（默认）**：零成本、零延迟，覆盖 90% 场景。内置政治、黄赌毒、广告法极限词、低俗辱骂四类词表。
- **百度AI内容审核（可选）**：通过环境变量 `BAIDU_CENSOR_API_KEY` / `BAIDU_CENSOR_SECRET_KEY` 启用，深度审核能力更强。

不强制用户再注册一个 API，开箱即用。

## 核心实现

### 1. 敏感词检测模块（content_agent/sensitive_checker.py）

```python
class SensitiveChecker:
    def __init__(self, enable_baidu: bool = False):
        self.words = DEFAULT_SENSITIVE_WORDS  # (word, type) 列表
        self.enable_baidu = enable_baidu

    def check(self, text: str) -> dict:
        # 本地检测 + 可选百度检测
        # 返回 {"has_sensitive": bool, "hits": [...], "local_count": int, "baidu_count": int}
```

**词匹配策略**：
- 纯中文词：前后不能是汉字（避免"学习"误匹配"习"）
- 含英文/数字的词：使用 `\b` word boundary

**本地词表分类**：
- 政治（~50 词）：涉政组织、敏感事件、分裂主义等
- 黄赌毒（~20 词）：卖淫、赌博、毒品相关
- 广告法极限词（~50 词）：最、第一、国家级、包过、稳赚等
- 低俗/骂人（~30 词）：脏话、歧视性用语

**百度API接入**：
```bash
export BAIDU_CENSOR_API_KEY="你的API Key"
export BAIDU_CENSOR_SECRET_KEY="你的Secret Key"
```

### 2. Web UI 集成（web_ui.py）

在 `generate_content` 函数开头插入检测：
- 检测到敏感词 → 在 `status_text` 中显示警告（列出具体词）
- 不阻断生成流程（避免误判导致用户无法使用）

```python
sensitive_check = checker.check(note_text)
if sensitive_check["has_sensitive"]:
    status += f"\n⚠️ 检测到..."
```

### 3. CLI 集成（main.py）

在 `process_single_note` 中，搜索增强之后、生成之前插入检测：
- 终端打印警告信息
- 同样不阻断流程

## 踩坑记录

1. **Gradio generator yield 返回值数量必须匹配 outputs** — 给 `generate_content` 增加 `tags_output` 后，所有早期 yield（如空输入、未选平台等错误退出）也必须返回 8 个值，否则 Gradio 事件绑定会报错。这次修敏感词时顺带把之前漏掉的早期 yield 也补全了。

2. **中文词边界匹配** — 直接用 `in` 会误匹配（如"学习"包含"习"），用正则 `(?<![\u4e00-\u9fff])word(?![\u4e00-\u9fff])` 可以确保纯中文词前后都不是汉字。

3. **百度API失败不应阻断流程** — 封装在 `try/except` 中，即使百度API挂了，本地检测仍然工作，文案生成不受影响。

## 使用方法

Web UI：
1. 输入笔记 → 点击生成
2. 如果检测到敏感词，状态栏会显示警告（如"⚠️ 检测到3个敏感/违规词: 最, 第一, 国家级"）
3. 用户可根据提示修改笔记后重新生成

CLI：
```bash
python main.py -i notes.md
# 终端会打印敏感词预检结果
```

启用百度深度审核：
```bash
export BAIDU_CENSOR_API_KEY=xxx
export BAIDU_CENSOR_SECRET_KEY=xxx
# 修改 SensitiveChecker(enable_baidu=True) 即可启用
```

## 下一步

P1 全部完成！接下来进入 **P2 - 工作流整合**：
- P2-1 定时任务 / Cron 调度
- P2-2 内容日历管理
- P2-3 自动发布到各平台
