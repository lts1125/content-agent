import os
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

try:
    from pydantic_ai.providers.deepseek import DeepSeekProvider
    HAS_DEEPSEEK = True
except ImportError:
    HAS_DEEPSEEK = False

load_dotenv()


class MultiPlatformContent(BaseModel):
    xiaohongshu: str
    """小红书笔记：emoji多、段落短、要点化、语气轻松，适合手机阅读"""

    gongzhonghao: str
    """公众号文章：深度长文、结构完整、有代码块和技术细节，适合桌面阅读"""

    douyin: str
    """抖音口播脚本：开头有钩子、短句、口语化、带画面提示，适合视频拍摄"""

    recommended_tags: str
    """基于笔记内容生成的各平台推荐标签/话题，按平台分类列出，用户可直接复制使用"""


SYSTEM_PROMPT = """你是一位全平台内容专家，擅长把技术学习笔记同时改写成三种风格的文案。

输入是程序员的学习笔记，输出必须包含三个平台的文案和推荐标签，分别符合以下要求：

【小红书笔记】
- 标题吸睛，带emoji和数字
- 开头一句话点出动机
- 正文分步骤，每步带emoji编号，每步简洁明了
- 保留核心概念和踩坑记录，但大白话解释
- 结尾金句总结 + 互动问句
- 添加3-5个话题标签（#xxx 格式）
- 全文300-600字

【公众号文章】
- 标题正式，可带副标题
- 开头用导言引入，讲背景和动机
- 正文分大章节，用## 标题分隔
- 每个步骤详细展开：有原理解释、代码示例、实际场景
- 包含具体的命令行代码块
- 有"总结"和"下一步"部分
- 全文1500-2500字，信息密度高

【抖音口播脚本】
- 开头前3秒必须有强钩子
- 每句话不超过15个字，短句排比
- 口语化，用"我""你""大家"等称呼
- 带画面提示（【镜头切到代码】【切换到页面】）
- 中间有转折或悬念，尾部有行动号召
- 全文200-400字，适合2-3分钟口播

【推荐标签/话题】
请基于笔记内容，额外输出各平台的推荐标签/话题，格式如下：

📱 小红书（5-8个）：
#标签1 #标签2 #标签3 ...

💬 公众号（3-5个关键词）：
关键词1、关键词2、关键词3 ...

🎥 抖音（3-5个）：
#话题1 #话题2 #话题3 ...

要求：标签必须与笔记内容高度相关，避免泛泛而谈的热门词。

核心原则：三个平台都必须基于同一份学习笔记，不编造内容，不流于表面，读者看完能复现学习路径。"""


class ModelConfig:
    """模型配置，支持多种 Provider"""

    PROVIDERS = {
        "deepseek": {
            "model": "deepseek-chat",
            "provider_factory": lambda key: DeepSeekProvider(api_key=key),
        },
        "openai": {
            "model": "gpt-4o-mini",
            "provider_factory": lambda key: OpenAIProvider(api_key=key),
        },
        "kimi": {
            "model": "kimi-k2-6",
            "provider_factory": lambda key: OpenAIProvider(
                base_url="https://api.moonshot.cn/v1",
                api_key=key,
            ),
        },
        "minimax": {
            "model": "abab6.5-chat",
            "provider_factory": lambda key: OpenAIProvider(
                base_url="https://api.minimax.chat/v1",
                api_key=key,
            ),
        },
        "custom": {
            "model": None,  # 从环境变量读取
            "provider_factory": None,  # 从环境变量构造
        },
    }

    @classmethod
    def from_env(cls) -> tuple[OpenAIChatModel, str]:
        """
        从环境变量读取配置，返回 (model, provider_name)
        环境变量优先级：
        1. MODEL_PROVIDER - provider 名称
        2. MODEL_NAME / MODEL_BASE_URL / MODEL_API_KEY - custom 模式
        3. 各类特定 API Key（DEEPSEEK_API_KEY / OPENAI_API_KEY / KIMI_API_KEY / MINIMAX_API_KEY）
        """
        provider_name = os.getenv("MODEL_PROVIDER", "deepseek").lower().strip()

        # Custom 模式：用户自己指定 base_url + model
        if provider_name == "custom":
            base_url = os.getenv("MODEL_BASE_URL", "").strip()
            model_name = os.getenv("MODEL_NAME", "").strip()
            api_key = os.getenv("MODEL_API_KEY", "").strip()

            if not all([base_url, model_name, api_key]):
                raise ValueError(
                    "Custom 模式需要设置 MODEL_BASE_URL, MODEL_NAME, MODEL_API_KEY"
                )

            provider = OpenAIProvider(base_url=base_url, api_key=api_key)
            return OpenAIChatModel(model_name, provider=provider), provider_name

        # 预置 Provider
        cfg = cls.PROVIDERS.get(provider_name)
        if not cfg:
            valid = ", ".join(cls.PROVIDERS.keys())
            raise ValueError(f"未知 Provider: {provider_name}，有效选项: {valid}")

        # 找 API Key
        env_key_map = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
            "kimi": "KIMI_API_KEY",
            "minimax": "MINIMAX_API_KEY",
        }
        env_key = env_key_map.get(provider_name, f"{provider_name.upper()}_API_KEY")
        api_key = os.getenv(env_key, "").strip()

        if not api_key:
            # 尝试 MODEL_API_KEY 作为通用 fallback
            api_key = os.getenv("MODEL_API_KEY", "").strip()

        if not api_key:
            raise ValueError(
                f"Provider '{provider_name}' 需要设置 {env_key} 环境变量\n"
                f"或者设置 MODEL_PROVIDER=custom + MODEL_BASE_URL + MODEL_NAME + MODEL_API_KEY"
            )

        # 构建 model
        provider = cfg["provider_factory"](api_key)
        model_name = cfg["model"]
        return OpenAIChatModel(model_name, provider=provider), provider_name


class ContentAgent:
    def __init__(self):
        self.model, self.provider_name = ModelConfig.from_env()
        self.agent = Agent(
            self.model,
            system_prompt=SYSTEM_PROMPT,
            output_type=MultiPlatformContent,
        )

    def run(self, raw_notes: str) -> MultiPlatformContent:
        result = self.agent.run_sync(raw_notes)
        return result.output
