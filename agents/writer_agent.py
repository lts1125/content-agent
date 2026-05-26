"""
WriterAgent — 文案生成 Agent

由 content_agent/agent_core.py 升级而来，支持：
- 初稿模式：完整 SYSTEM_PROMPT（非并发）或 平台级并发
- 修改模式：精简 prompt，只改最弱平台（或全改）

输出 WriterOutput（包装 MultiPlatformContent + revision_notes）。
"""

import os
from concurrent.futures import ThreadPoolExecutor
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from agents.schemas import WriterOutput

# 复用原 agent_core.py 的 Provider 配置逻辑
# 为了解耦，这里直接内联 ModelConfig，避免 agents/ 依赖 content_agent/

try:
    from pydantic_ai.providers.deepseek import DeepSeekProvider
    HAS_DEEPSEEK = True
except ImportError:
    HAS_DEEPSEEK = False

load_dotenv()


# ---------------------------------------------------------------------------
# Prompt 定义
# ---------------------------------------------------------------------------

DRAFT_SYSTEM_PROMPT = """你是一位全平台内容专家，擅长把技术学习笔记同时改写成三种风格的文案。

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


# 风格画像追加模板
STYLE_PROFILE_APPENDIX = """

【风格画像参考】
根据历史数据分析，该平台高表现内容的特征如下：
- 语气特征：{preferred_tone}
- 高表现模式：{patterns}
- 平均互动分：{avg_score}

请优先采用上述高表现模式，生成符合平台偏好的内容。"""


REFINE_SYSTEM_PROMPT = """你是一位资深编辑，根据审稿意见修改文案。

规则：
- 只修改被指出的最弱平台，其他平台文案保持不变
- 如果审稿意见说"全面不合格"（overall < 60），才重写三平台
- 修改必须精准对应审稿意见中的具体问题
- 输出时附上 revision_notes，说明"按照建议X，修改了Y"

输出格式与初稿相同：小红书、公众号、抖音、推荐标签。"""


# ---------------------------------------------------------------------------
# 平台级并发用 Prompt
# ---------------------------------------------------------------------------

PLATFORM_PROMPTS = {
    "xiaohongshu": """你是一位小红书爆款笔记专家。把技术学习笔记改写成小红书风格：
- 标题吸睛，带emoji和数字
- 开头一句话点出动机
- 正文分步骤，每步带emoji编号，每步简洁明了
- 保留核心概念和踩坑记录，但大白话解释
- 结尾金句总结 + 互动问句
- 添加3-5个话题标签（#xxx 格式）
- 全文300-600字

基于同一份学习笔记生成，不编造内容，不流于表面。

同时输出推荐标签（格式：📱 小红书：#xxx #xxx ...）。""",

    "gongzhonghao": """你是一位公众号长文作者。把技术学习笔记改写成公众号文章：
- 标题正式，可带副标题
- 开头用导言引入背景和动机
- 正文分大章节，用## 标题分隔
- 每个步骤详细展开：原理解释、代码示例、实际场景
- 包含具体的命令行代码块
- 有"总结"和"下一步"部分
- 全文1500-2500字，信息密度高

基于同一份学习笔记生成，不编造内容，不流于表面。

同时输出推荐关键词（格式：💬 公众号：关键词1、关键词2 ...）。""",

    "douyin": """你是一位抖音口播脚本策划。把技术学习笔记改写成口播脚本：
- 开头前3秒必须有强钩子
- 每句话不超过15个字，短句排比
- 口语化，用"我"“你"“大家"等称呼
- 带画面提示（【镜头切到代码】【切换到页面】）
- 中间有转折或悬念，尾部有行动号召
- 全文200-400字，适合2-3分钟口播

基于同一份学习笔记生成，不编造内容，不流于表面。

同时输出推荐话题（格式：🎥 抖音：#话题1 #话题2 ...）。""",
}


# ---------------------------------------------------------------------------
# 平台级输出结构
# ---------------------------------------------------------------------------

class PlatformWriterOutput(BaseModel):
    """PlatformWriterAgent 输出（单平台）"""
    content: str
    recommended_tags: str = ""
    revision_notes: str = ""


# ---------------------------------------------------------------------------
# ModelConfig（从 agent_core.py 复制，保持零依赖）
# ---------------------------------------------------------------------------

class _ModelConfig:
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
                base_url="https://api.moonshot.cn/v1", api_key=key,
            ),
        },
        "minimax": {
            "model": "abab6.5-chat",
            "provider_factory": lambda key: OpenAIProvider(
                base_url="https://api.minimaxi.com/v1", api_key=key,
            ),
        },
        "custom": {
            "model": None,
            "provider_factory": None,
        },
    }

    @classmethod
    def from_env(cls) -> tuple[OpenAIChatModel, str]:
        provider_name = os.getenv("MODEL_PROVIDER", "deepseek").lower().strip()

        if provider_name == "custom":
            base_url = os.getenv("MODEL_BASE_URL", "").strip()
            model_name = os.getenv("MODEL_NAME", "").strip()
            api_key = os.getenv("MODEL_API_KEY", "").strip()
            if not all([base_url, model_name, api_key]):
                raise ValueError("Custom 模式需要设置 MODEL_BASE_URL, MODEL_NAME, MODEL_API_KEY")
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
        api_key = os.getenv(env_key, "").strip() or os.getenv("MODEL_API_KEY", "").strip()
        if not api_key:
            raise ValueError(f"Provider '{provider_name}' 需要设置 {env_key} 环境变量")

        provider = cfg["provider_factory"](api_key)
        return OpenAIChatModel(cfg["model"], provider=provider), provider_name


# ---------------------------------------------------------------------------
# PlatformWriterAgent
# ---------------------------------------------------------------------------

class PlatformWriterAgent:
    """单平台文案生成 Agent。

    只负责一个平台的生成，用于并发模式。
    """

    def __init__(self, platform: str, model: OpenAIChatModel):
        if platform not in PLATFORM_PROMPTS:
            raise ValueError(f"未知平台: {platform}")
        self.platform = platform
        self._agent = Agent(
            model,
            system_prompt=PLATFORM_PROMPTS[platform],
            output_type=PlatformWriterOutput,
        )

    def run(self, raw_notes: str, style: str = "default") -> PlatformWriterOutput:
        """生成单平台初稿"""
        result = self._agent.run_sync(raw_notes)
        return result.output

    def refine(
        self,
        prev_content: str,
        suggestions: List[str],
        raw_notes: str,
    ) -> PlatformWriterOutput:
        """根据审稿意见精修单平台"""
        suggestions_text = "\n".join(f"- {s}" for s in suggestions)
        prompt = (
            f"请修改以下文案，根据审稿意见进行优化。\n\n"
            f"审稿意见：\n{suggestions_text}\n\n"
            f"当前文案：\n{prev_content}\n\n"
            f"原始笔记（供参考）：\n{raw_notes[:1200]}"
        )
        result = self._agent.run_sync(prompt)
        return result.output


# ---------------------------------------------------------------------------
# WriterAgent
# ---------------------------------------------------------------------------

class WriterAgent:
    def __init__(self):
        self.model, self.provider_name = _ModelConfig.from_env()
        self._draft_agent = Agent(
            self.model,
            system_prompt=DRAFT_SYSTEM_PROMPT,
            output_type=WriterOutput,
        )
        self._refine_agent = Agent(
            self.model,
            system_prompt=REFINE_SYSTEM_PROMPT,
            output_type=WriterOutput,
        )
        # 并发模式用的单平台 Agent（情性初始化，避免非并发模式下的额外开销）
        self._platform_agents: dict[str, PlatformWriterAgent] = {}

    def _load_style_profile(self, platform: str) -> str:
        """加载平台风格画像，追加到 system prompt"""
        try:
            from automation.feedback_agent import FeedbackAgent
            agent = FeedbackAgent()
            profile = agent.get_profile(platform)
            if profile and profile.sample_count >= 5:
                patterns = "、".join(profile.high_performing_patterns[:5])
                return STYLE_PROFILE_APPENDIX.format(
                    preferred_tone=profile.preferred_tone,
                    patterns=patterns,
                    avg_score=profile.avg_score,
                )
        except Exception:
            pass
        return ""

    def _build_draft_prompt(self, raw_notes: str, platforms: List[str]) -> str:
        """构建初稿 prompt，包含风格画像"""
        prompt = raw_notes
        for platform in platforms:
            profile_text = self._load_style_profile(platform)
            if profile_text:
                prompt += f"\n\n【{platform} 风格画像】{profile_text}"
        return prompt

    def _get_platform_agent(self, platform: str) -> PlatformWriterAgent:
        if platform not in self._platform_agents:
            self._platform_agents[platform] = PlatformWriterAgent(platform, self.model)
        return self._platform_agents[platform]

    # --------------------- 初稿 ---------------------
    def run(
        self,
        raw_notes: str,
        platforms: List[str],
        style: str = "default",
        concurrent: bool = False,
        feedback: str = "",
    ) -> WriterOutput:
        """生成初稿

        Args:
            concurrent: 是否按平台并发生成。默认 False（单次调用生成三平台）。
            feedback: Editor 的反馈，用于修改
        """
        if feedback:
            # 有反馈，使用 refine 模式
            return self._run_with_feedback(raw_notes, platforms, feedback)

        if not concurrent or len(platforms) <= 1:
            # 非并发模式：保持现有行为，追加风格画像
            prompt = self._build_draft_prompt(raw_notes, platforms)
            result = self._draft_agent.run_sync(prompt)
            return result.output

        # 并发模式：每个平台独立调用
        def _run_platform(platform: str) -> tuple[str, PlatformWriterOutput]:
            agent = self._get_platform_agent(platform)
            output = agent.run(raw_notes, style=style)
            return platform, output

        results = {}
        with ThreadPoolExecutor(max_workers=len(platforms)) as executor:
            futures = {
                executor.submit(_run_platform, p): p for p in platforms
            }
            for future in futures:
                platform, output = future.result()
                results[platform] = output

        # 合并结果
        merged = WriterOutput()
        tags_parts = []
        for platform in platforms:
            out = results[platform]
            setattr(merged, platform, out.content)
            if out.recommended_tags:
                tags_parts.append(out.recommended_tags)
        merged.recommended_tags = "\n".join(tags_parts)
        return merged

    # --------------------- 修改 ---------------------
    def refine(
        self,
        prev_draft: WriterOutput,
        verdict,
        raw_notes: str,
        platforms: List[str],
        concurrent: bool = False,
    ) -> WriterOutput:
        """
        根据 Editor 的 verdict 修改文案。

        策略：
        - 默认只重写最弱平台
        - 如果 overall < 60，重写三平台
        """
        weakest = verdict.weakest
        suggestions_text = "\n".join(f"- {s}" for s in verdict.suggestions)

        if verdict.overall < 60:
            # 全面不合格：重写三平台
            if concurrent and len(platforms) > 1:
                # 并发重写三平台
                def _refine_platform(platform: str) -> tuple[str, PlatformWriterOutput]:
                    agent = self._get_platform_agent(platform)
                    content = getattr(prev_draft, platform, "")
                    out = agent.refine(content, verdict.suggestions, raw_notes)
                    return platform, out

                results = {}
                with ThreadPoolExecutor(max_workers=len(platforms)) as executor:
                    futures = {
                        executor.submit(_refine_platform, p): p for p in platforms
                    }
                    for future in futures:
                        platform, output = future.result()
                        results[platform] = output

                merged = WriterOutput()
                tags_parts = []
                for platform in platforms:
                    out = results[platform]
                    setattr(merged, platform, out.content)
                    if out.recommended_tags:
                        tags_parts.append(out.recommended_tags)
                merged.recommended_tags = "\n".join(tags_parts)
                merged.revision_notes = f"【全面重写】按审稿意见重生成三平台。"
                return merged

            # 非并发：保持现有行为
            prompt = (
                f"审稿意见（全面不合格，需重写三平台）：\n{suggestions_text}\n\n"
                f"原始笔记：\n{raw_notes[:1500]}\n\n"
                f"上一版文案参考（不要照搬）：\n"
                f"小红书：{prev_draft.xiaohongshu[:400]}...\n"
                f"公众号：{prev_draft.gongzhonghao[:400]}...\n"
                f"抖音：{prev_draft.douyin[:300]}..."
            )
            result = self._refine_agent.run_sync(prompt)
            output = result.output
            output.revision_notes = f"【全面重写】按审稿意见重生成三平台。{output.revision_notes}"
            return output

        # 只改最弱平台
        platform_content = {
            "xiaohongshu": prev_draft.xiaohongshu,
            "gongzhonghao": prev_draft.gongzhonghao,
            "douyin": prev_draft.douyin,
        }
        content_to_refine = platform_content.get(weakest, prev_draft.xiaohongshu)

        if concurrent and weakest in PLATFORM_PROMPTS:
            # 用平台级 Agent 精修
            agent = self._get_platform_agent(weakest)
            refined = agent.refine(content_to_refine, verdict.suggestions, raw_notes)

            output = WriterOutput(
                xiaohongshu=refined.content if weakest == "xiaohongshu" else prev_draft.xiaohongshu,
                gongzhonghao=refined.content if weakest == "gongzhonghao" else prev_draft.gongzhonghao,
                douyin=refined.content if weakest == "douyin" else prev_draft.douyin,
                recommended_tags=refined.recommended_tags or prev_draft.recommended_tags,
                revision_notes=f"【{weakest} 精修】按审稿意见修改。{refined.revision_notes}",
            )
            return output

        # 非并发精修
        prompt = (
            f"请只修改【{weakest}】平台的文案，其他两平台保持不变。\n\n"
            f"审稿意见：\n{suggestions_text}\n\n"
            f"需要修改的平台原文：\n{content_to_refine}\n\n"
            f"原始笔记（供参考）：\n{raw_notes[:1200]}"
        )
        result = self._refine_agent.run_sync(prompt)
        refined = result.output

        # 把未修改的平台回填
        output = WriterOutput(
            xiaohongshu=refined.xiaohongshu if weakest == "xiaohongshu" else prev_draft.xiaohongshu,
            gongzhonghao=refined.gongzhonghao if weakest == "gongzhonghao" else prev_draft.gongzhonghao,
            douyin=refined.douyin if weakest == "douyin" else prev_draft.douyin,
            recommended_tags=refined.recommended_tags or prev_draft.recommended_tags,
            revision_notes=f"【{weakest} 精修】按审稿意见修改。{refined.revision_notes}",
        )
        return output

    # --------------------- 带反馈生成 ---------------------
    def _run_with_feedback(
        self,
        raw_notes: str,
        platforms: List[str],
        feedback: str,
    ) -> WriterOutput:
        """根据 Editor 反馈生成"""
        prompt = (
            f"请根据以下反馈修改内容：\n\n"
            f"反馈：\n{feedback}\n\n"
            f"原始笔记：\n{raw_notes[:1500]}\n\n"
            f"请生成 {', '.join(platforms)} 平台的内容。"
        )
        result = self._refine_agent.run_sync(prompt)
        return result.output
