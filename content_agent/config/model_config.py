import os
from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

try:
    from pydantic_ai.providers.deepseek import DeepSeekProvider
    HAS_DEEPSEEK = True
except ImportError:
    HAS_DEEPSEEK = False

load_dotenv()


class ModelConfig:
    """统一模型配置，支持多种 Provider。

    所有 Agent、工具、旧核心均从此入口读取模型配置。
    """

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
            "model": None,
            "provider_factory": None,
        },
    }

    @classmethod
    def from_env(cls) -> tuple[OpenAIChatModel, str]:
        """
        从环境变量读取配置，返回 (model, provider_name)
        """
        provider_name = os.getenv("MODEL_PROVIDER", "deepseek").lower().strip()

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

        cfg = cls.PROVIDERS.get(provider_name)
        if not cfg:
            valid = ", ".join(cls.PROVIDERS.keys())
            raise ValueError(f"未知 Provider: {provider_name}，有效选项: {valid}")

        env_key_map = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
            "kimi": "KIMI_API_KEY",
            "minimax": "MINIMAX_API_KEY",
        }
        env_key = env_key_map.get(provider_name, f"{provider_name.upper()}_API_KEY")
        api_key = os.getenv(env_key, "").strip()

        if not api_key:
            api_key = os.getenv("MODEL_API_KEY", "").strip()

        if not api_key:
            raise ValueError(
                f"Provider '{provider_name}' 需要设置 {env_key} 环境变量\n"
                f"或者设置 MODEL_PROVIDER=custom + MODEL_BASE_URL + MODEL_NAME + MODEL_API_KEY"
            )

        provider = cfg["provider_factory"](api_key)
        model_name = cfg["model"]
        return OpenAIChatModel(model_name, provider=provider), provider_name
