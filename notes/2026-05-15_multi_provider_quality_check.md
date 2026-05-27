# Content Agent 多 Provider 支持与混合质量检查实现笔记

## 背景

CLI 工具化改造完成后，遇到了两个新问题：

1. **模型锁定在 DeepSeek**：之前只支持 DeepSeek，但朋友提醒 Kimi 也很强，而且有些人可能更习惯用 OpenAI。需要支持多种 LLM Provider 切换。

2. **生成质量不稳定**：同一条笔记跑多次，有时候结果很好，有时候缺 emoji、缺标签、字数不对。需要一个自动评分机制，差的自动重试。

---

## 需求分析

### 多 Provider 支持

目标：通过环境变量切换模型，不改代码。

需要支持的 Provider：
- DeepSeek（默认，性价比最高）
- Kimi / Moonshot（国内优秀模型）
- MiniMax（另一家国内厂商）
- OpenAI（国际标准）
- 自定义 OpenAI-compatible（硅基流动、通义千问、智谱、本地 Ollama 等）

### 质量检查

目标：自动评分，低于阈值自动重试。

关键问题：
- 如何评分？LLM 自己评分又准又贵，纯规则又太笨。
- 重试时如何改进？需要把问题反馈给 LLM，让它知道哪里不好。

---

## 代码结构变化

```
content-agent/
├── content_agent/
│   ├── __init__.py
│   ├── agent_core.py          # 增加多 Provider 支持
│   ├── html_renderer.py
│   └── quality_checker.py     # 新增：混合质量检查
├── main.py                    # 集成质量检查流程
├── .env.example               # 扩展为多 Provider 配置
└── notes/
    └── 本文件
```

---

## 步骤1：多 Provider 支持（agent_core.py 改造）

### 设计思路

之前的代码是写死的 DeepSeekProvider：

```python
model = OpenAIChatModel("deepseek-chat", provider=DeepSeekProvider(api_key=api_key))
```

现在需要根据环境变量动态选择 Provider。观察各家 API，发现它们都是 OpenAI-compatible 的，只是 base_url 和 model_name 不同。

所以统一用 `OpenAIProvider` 包装，通过 `base_url` 区分平台：

```python
from pydantic_ai.providers.openai import OpenAIProvider

# DeepSeek
OpenAIProvider(base_url="https://api.deepseek.com/v1", api_key=key)

# Kimi
OpenAIProvider(base_url="https://api.moonshot.cn/v1", api_key=key)

# MiniMax
OpenAIProvider(base_url="https://api.minimax.chat/v1", api_key=key)

# 自定义
OpenAIProvider(base_url="https://api.siliconflow.cn/v1", api_key=key)
```

DeepSeek 有自己的 `DeepSeekProvider`，但实测用 `OpenAIProvider` 也能跟它通信，且更统一。为了兼容性，代码里先 try 导入 DeepSeekProvider，不行就用 OpenAIProvider 替代。

### 核心实现

新增 `ModelConfig` 类，管理所有 Provider 配置：

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
                base_url="https://api.moonshot.cn/v1", api_key=key
            ),
        },
        "minimax": {
            "model": "abab6.5-chat",
            "provider_factory": lambda key: OpenAIProvider(
                base_url="https://api.minimax.chat/v1", api_key=key
            ),
        },
        "openai": {
            "model": "gpt-4o-mini",
            "provider_factory": lambda key: OpenAIProvider(api_key=key),
        },
        "custom": {
            "model": None,  # 从环境变量读取
            "provider_factory": None,
        },
    }
```

`从环境变量读取配置` 的逻辑：

```python
@classmethod
def from_env(cls) -> tuple[OpenAIChatModel, str]:
    provider_name = os.getenv("MODEL_PROVIDER", "deepseek").lower().strip()

    if provider_name == "custom":
        # 自定义模式：用户自己指定 base_url + model_name
        base_url = os.getenv("MODEL_BASE_URL", "").strip()
        model_name = os.getenv("MODEL_NAME", "").strip()
        api_key = os.getenv("MODEL_API_KEY", "").strip()
        provider = OpenAIProvider(base_url=base_url, api_key=api_key)
        return OpenAIChatModel(model_name, provider=provider), provider_name

    # 预置 Provider，找对应的 API Key
    cfg = cls.PROVIDERS[provider_name]
    env_key = f"{provider_name.upper()}_API_KEY"
    api_key = os.getenv(env_key, "").strip()
    provider = cfg["provider_factory"](api_key)
    return OpenAIChatModel(cfg["model"], provider=provider), provider_name
```

**关键点：**
- `MODEL_PROVIDER` 环境变量控制切换，不用改代码
- Custom 模式要求同时设置 `MODEL_BASE_URL` + `MODEL_NAME` + `MODEL_API_KEY`
- 配置错误时抛出清晰的 ValueError，告诉用户少了什么

---

## 步骤2：混合质量检查（quality_checker.py 新增）

### 设计思路

三个方案对比：

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| 纯规则校验 | 快、免费 | 只能检查硬性指标 | 快速过滤明显不合格 |
| LLM 自评分 | 准确、维度多 | 花 token、慢 | 精细评估 |
| **混合模式** | **先快后准** | **实现复杂度稍高** | **综合最优** |

选择混合模式：先用规则校验做快速过滤，规则过了再用 LLM 精细评分，低于阈值则带建议重试。

### 规则校验实现

三平台分别定义硬性指标：

**小红书（继承自 CLI 改造时的经验）：**
- 字数 200-800
- 含有 emoji
- 含有标签 `#xxx`
- 含有互动问句
- 分段清晰
- 有数字/步骤编号
- 标题吸睛（数字/表情/悬念）

**公众号：**
- 字数 1000-3000
- 有标题层级 `##`
- 含代码块
- 有总结部分
- 有下一步/行动号召
- 段落数量充足
- 含有实例/场景

**抖音：**
- 字数 150-500
- 开头有强钩子（停/别/你知道/别再...）
- 短句比例 ≥50%
- 有画面提示 `【xxx】`
- 有行动号召（关注/点赞/跟我...）
- 口语化（我/你/大家）
- 有转折/悬念

规则校验代码示例（小红书）：

```python
def check_xiaohongshu(text: str) -> dict:
    checks = {
        "字数达标(200-800)": 200 <= len(text) <= 800,
        "含有emoji": bool(re.search(r'[\U0001F600-\U0001F9FF]', text)),
        "含有标签(#)": bool(re.search(r'#\S+', text)),
        "含有互动问句": bool(re.search(r'[?？]', text)),
        "分段清晰": text.count("\n\n") >= 2,
        "有数字或步骤": bool(re.search(r'\d[一-九]|第\d步', text)),
        "标题吸睛": bool(re.search(r'\d|[❓❗]', text.split("\n")[0])),
    }
    score = sum(checks.values()) / len(checks) * 100
    return {"score": score, "checks": checks}
```

### LLM 评分实现

用 PydanticAI 的结构化输出定义评分结果：

```python
class ScoreResult(BaseModel):
    xiaohongshu: int  # 0-100
    gongzhonghao: int
    douyin: int
    overall: int      # 三平台平均
    weakest: str      # 最弱平台名称
    suggestion: str   # 改进建议，用于重试 prompt
```

LLM 的 system_prompt 要求它担任"资深内容运营总监"，按维度打分。这样的好处是 LLM 对"好内容"的理解比纯规则更深。

**重点：** `suggestion` 字段是重试时的关键。它需要简洁、可执行，例如"小红书缺少 emoji 和标签，结尾加一个互动问句"。

### 混合检查流程

```python
checker = QualityChecker(model)
check = checker.check(xhs_text, gzh_text, dy_text)

if check.passed:
    # 通过，保存
else:
    # 未通过，把 check.retry_suggestion 加入 prompt 重试
```

**合格线设定：**
- 规则校验综合分 ≥ 70
- LLM 综合得分 ≥ 70
- 最多重试 2 次（共 3 次）

### 重试机制

重试时不修改 system_prompt（那是 Agent 的"灵魂"，调好了不动），而是把改进建议加到用户输入里：

```python
current_notes = (
    "【请根据以下改进要求重新输出三平台文案】\n"
    f"{check.retry_suggestion}\n\n"
    f"--- 原始笔记 ---\n{raw_notes}"
)
```

这样 LLM 会把改进要求当作指令执行，但不会破坏 system_prompt 里的核心逻辑。

---

## 步骤3：集成到 main.py

在 `main()` 函数中，生成内容后插入质量检查流程：

```python
# 初始化质量检查器
checker = QualityChecker(agent.model)
result = None
current_notes = raw_notes

for attempt in range(1, 4):
    # 生成
    result = agent.run(current_notes)

    # 检查
    check = checker.check(result.xiaohongshu, result.gongzhonghao, result.douyin)

    if check.passed:
        break

    # 重试
    if attempt < 3:
        current_notes = (
            "【请根据以下改进要求重新输出三平台文案】\n"
            f"{check.retry_suggestion}\n\n"
            f"--- 原始笔记 ---\n{raw_notes}"
        )
```

运行时打印的信息：

```
第 1 次生成三平台文案...

质量检查结果 (第 1 次):
   规则校验: 81.0/100 ✅
   LLM 评分: 小红书=88 公众号=70 抖音=85
   综合得分: 81/100
   最弱平台: 公众号
   总体判定: ✅ 通过

质量检查通过，共尝试 1 次
```

---

## 配置文件变化

`.env.example` 从单一配置扩展为多 Provider 模板：

```bash
# 选择 Provider（默认 deepseek）
MODEL_PROVIDER=deepseek

# 方案 1: DeepSeek（推荐，性价比最高）
DEEPSEEK_API_KEY=sk-xxx

# 方案 2: Kimi
KIMI_API_KEY=sk-xxx

# 方案 3: 自定义
MODEL_PROVIDER=custom
MODEL_BASE_URL=https://api.siliconflow.cn/v1
MODEL_NAME=deepseek-ai/DeepSeek-V3
MODEL_API_KEY=sk-xxx
```

---

## 踩坑记录

### 坑1：Kimi Code API 白名单限制

Kimi 有两套体系：
- **Kimi Code (coding plan)**: `api.kimi.com/coding/v1`，有 User-Agent 白名单，只允许 Kimi CLI、Claude Code 等官方工具调用。第三方脚本调用返回 `403 access_terminated_error`。
- **Kimi 开放平台**: `api.moonshot.cn/v1`，标准 OpenAI-compatible，任何客户端都能用。

**误区**: 以为 Kimi Code 的 key 也能调开放平台 API。结果 401，key 不通用。

**解决**: 在 `.env.example` 里明确注释提醒用户：Kimi Code key 和开放平台 key 是两回事。如需在 content-agent 中用 Kimi，需另外注册开放平台并充值。

### 坑2：规则校验和 LLM 评分的合适线

一开始设的合格线是 80 分，结果很多生成结果都在 75-80 之间，触发重试，花了很多 token 但改进效果不明显。

**解决**: 调低合格线到 70 分。原因是：
- 规则校验是必要条件，低于 70 说明确实有明显缺失
- LLM 评分在 70-80 属于"可用但不完美"，手动微调一下即可
- 重诒的成本很高（额外一次 API 调用），不值得为 5-10 分的差距反复重试

### 坑3：重试时修改 system_prompt vs 修改用户输入

一开始试着重试时动态修改 system_prompt，结果把好的 prompt 模板破坏了，后面越生越差。

**解决**: system_prompt 保持不变，重试时把改进建议加到用户输入里。这样 LLM 把建议当作"预设指令"，而不是改变自身行为准则。

---

## 使用方法

### 切换模型

```bash
# DeepSeek (默认)
MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx

# Kimi
MODEL_PROVIDER=kimi
KIMI_API_KEY=sk-xxx

# 自定义
MODEL_PROVIDER=custom
MODEL_BASE_URL=https://api.siliconflow.cn/v1
MODEL_NAME=deepseek-ai/DeepSeek-V3
MODEL_API_KEY=sk-xxx
```

### 查看质量分数

运行时终端会自动打印分数：

```bash
python main.py -i notes/ai_invades_daily.md

# 输出：
第 1 次生成三平台文案...
质量检查结果 (第 1 次):
   规则校验: 81.0/100 ✅
   LLM 评分: 小红书=88 公众号=70 抖音=85
   综合得分: 81/100
   最弱平台: 公众号
   总体判定: ✅ 通过
```

---

## 下一步计划

1. **观察重试触发率**：跑一段时间后看看有多少次触发重试，评估 70 分的阈值是否合理
2. **收集失败案例**：如果某类文案反复失败，反馈给规则校验和 LLM 评分维度，看是哪个环节出了问题
3. **考虑调优**：根据实际数据调整合格线或增加新的检查项

---

## 总结

这次两个功能是 content-agent 从"能用"到"好用"的关键跳跃：

- **多 Provider** 解锁了模型灵活性，不再被某一家 API 绑死
- **混合质量检查** 保证了输出稳定性，减少了手动筛选的成本

最重要的是，这两个功能都是"无感集成"的——用户不用额外配置，默认就走这套流程。
