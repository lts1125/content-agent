# 三平台内容输出功能实现笔记

## 背景/需求
前面花了几个小时搭建了一个内容改写agent，可以正常生成内容，但是输出内容或者格式比较单一，因此增加多平台内容输出格式，具体为：用户输入一份技术学习笔记，需要同时生成小红书、微信公众号、抖音三个平台的文案。三个平台的受众、风格、格式完全不同，手动改写耗时耗力。

## 设计思路

利用 PydanticAI 的结构化输出能力，一次 API 调用生成三平台文案 + 推荐标签。核心思路：

1. **Pydantic Model 定义输出结构** — `MultiPlatformContent` 包含三个平台字段 + `recommended_tags`
2. **System Prompt 精确定义三平台风格** — 用详细的格式要求引导 LLM 生成差异化内容
3. **多 Provider 兼容** — 通过 `ModelConfig` 统一封装 DeepSeek / Kimi / MiniMax / OpenAI / 自定义

## 核心实现

### 1. Pydantic Model（agent_core.py）

```python
class MultiPlatformContent(BaseModel):
    xiaohongshu: str
    """小红书笔记：emoji多、段落短、要点化、语气轻松，适合手机阅读"""

    gongzhonghao: str
    """公众号文章：深度长文、结构完整、有代码块和技术细节，适合桌面阅读"""

    douyin: str
    """抖音口播脚本：开头有钩子、短句、口语化、带画面提示，适合视频拍摄"""

    recommended_tags: str
    """基于笔记内容生成的各平台推荐标签/话题"""
```

### 2. System Prompt 设计

System Prompt 分为四个章节，每个平台一个，外加推荐标签：

- **小红书笔记**：emoji、数字标题、步骤化、互动问句、300-600字
- **公众号文章**：正式标题、导言引入、`##` 章节分隔、代码块、1500-2500字
- **抖音口播脚本**：前3秒钩子、短句排比、画面提示、200-400字
- **推荐标签/话题**：按平台分类，高度相关

### 3. 多 Provider 配置（ModelConfig）

```python
class ModelConfig:
    PROVIDERS = {
        "deepseek": {
            "model": "deepseek-chat",
            "provider_factory": lambda key: DeepSeekProvider(api_key=key),
        },
        "kimi": {
            "model": "kimi-k2-6",
            "provider_factory": lambda key: OpenAIProvider(
                base_url="https://api.moonshot.cn/v1", api_key=key,
            ),
        },
        # ... openai / minimax / custom
    }
```

### 4. Agent 初始化

```python
agent = Agent(
    model=OpenAIChatModel(model_name=config["model"], provider=config["provider"]),
    system_prompt=SYSTEM_PROMPT,
    output_type=MultiPlatformContent,
)
```

## 踩坑记录

1. **PydanticAI 0.8 API 变动** — `OpenAIModel` 改名为 `OpenAIChatModel`，`base_url` 不能直传，需用 `OpenAIProvider` 包装。DeepSeek 有专门的 `DeepSeekProvider`。

2. **Kimi 的 base_url 必须用 `platform.moonshot.cn`** — 不是 `api.moonshot.cn`，这是开放平台 API 的地址。

3. **Kimi Code key 不能用于本项目** — Kimi Code 有 User-Agent 白名单，非官方客户端无法调用。需要另外申请 Moonshot 开放平台的 API key。

4. **output_type 参数名** — PydanticAI 使用 `output_type` 而非 `result_type` 指定结构化输出模型。

5. **Provider 的惰性导入** — DeepSeekProvider 可能不存在（旧版本 pydantic-ai），用 try/except 包裹，fallback 到 OpenAIProvider。

## 使用方法

CLI：
```bash
python main.py -i notes/my_note.md
# 输出三平台文案到 output/2026xxxxx/
```

Web UI：
1. 粘贴笔记 → 选择平台（可多选）→ 点击生成
2. 在右侧 Tabs 查看小红书/公众号/抖音文案

## 下一步

- P1-2 内容预览（小红书 HTML 卡片）
- P1-4 用户反馈与评分
