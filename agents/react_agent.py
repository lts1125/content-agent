"""
ReAct Agent - 推理-行动循环（集成 Editor 评估）

核心流程：
Thought -> Action -> Observation -> Thought -> Action -> Observation -> ...

新增：生成后自动评估，评分低时反思修改
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from pydantic_ai import Agent

from agents.writer_agent import _ModelConfig as ModelConfig
from agents.schemas import WriterOutput
from agents.tools import execute_tool, list_tools


@dataclass
class ReActStep:
    """单个 ReAct 步骤"""
    thought: str = ""
    action: str = ""
    observation: str = ""


@dataclass
class ReActOutput:
    """ReAct 输出"""
    content: WriterOutput = field(default_factory=WriterOutput)
    steps: List[ReActStep] = field(default_factory=list)
    reasoning: str = ""
    final_score: int = 0


REACT_SYSTEM_PROMPT = """你是一个专业的内容创作 Agent，擅长将技术笔记改写成多平台文案。

可用工具：
{tools}

工作流程：
1. 分析笔记内容，判断是否需要搜索补充资料
2. 生成内容
3. 评估内容质量
4. 如果评分低于80分，反思问题并修改
5. 重复步骤3-4直到评分通过

输出格式：
Thought: [你的思考过程]
Action: [工具调用，如 search("关键词") 或 generate(...) 或 evaluate(...)]
"""


class ReActAgent:
    """ReAct Agent：推理-行动循环"""

    def __init__(self, max_steps: int = 5):
        self.max_steps = max_steps
        self.model, _ = ModelConfig.from_env()
        self.tools_prompt = "\n".join(list_tools())

        self._agent = Agent(
            self.model,
            system_prompt=REACT_SYSTEM_PROMPT.format(tools=self.tools_prompt),
        )

    def run(self, raw_notes: str, platforms: List[str]) -> ReActOutput:
        """
        执行完整的 ReAct 循环（含评估-修改）

        Args:
            raw_notes: 原始笔记内容
            platforms: 目标平台列表

        Returns:
            ReActOutput: 包含生成内容、执行步骤、最终评分
        """
        steps: List[ReActStep] = []
        context = f"目标：根据以下笔记生成 {', '.join(platforms)} 平台的内容\n\n笔记内容：\n{raw_notes[:1500]}"

        # ========== Phase 1: 分析 + 搜索（可选）==========
        thought1 = self._think(context)
        step1 = ReActStep(thought=thought1)

        action_name, action_params = self._parse_action(thought1)

        if action_name == "search":
            step1.action = f"search({json.dumps(action_params, ensure_ascii=False)})"
            result = execute_tool("search", **action_params)
            step1.observation = result.data if result.success else f"错误: {result.error}"
            steps.append(step1)

            # 更新上下文
            context += f"\n\n搜索结果：\n{step1.observation[:500]}"
            search_done = True
        else:
            step1.action = "直接生成（无需搜索）"
            step1.observation = "笔记内容充足"
            steps.append(step1)
            search_done = False

        # ========== Phase 2: 生成内容 ==========
        if search_done:
            thought2 = self._think(context + "\n\n基于以上信息，生成内容：")
            step2 = ReActStep(thought=thought2)
            step2.action = f"generate(platforms={platforms})"

            result = execute_tool("generate", raw_notes=context, platforms=platforms)
            step2.observation = "生成完成" if result.success else f"错误: {result.error}"
            steps.append(step2)
        else:
            step2 = step1
            result = execute_tool("generate", raw_notes=raw_notes, platforms=platforms)
            step2.observation = "生成完成" if result.success else f"错误: {result.error}"
            if not search_done:
                steps.append(step2)

        if not result.success or not isinstance(result.data, WriterOutput):
            return ReActOutput(
                content=WriterOutput(),
                steps=steps,
                reasoning="生成失败",
                final_score=0,
            )

        current_content = result.data

        # ========== Phase 3: 评估-反思-修改循环 ==========
        for attempt in range(3):  # 最多修改3次
            # 评估
            eval_step, score = self._evaluate_step(current_content, platforms, attempt + 1)
            steps.append(eval_step)

            if score >= 80:
                # 评分通过
                return ReActOutput(
                    content=current_content,
                    steps=steps,
                    reasoning=f"完成：分析 -> {'搜索 -> ' if search_done else ''}生成 -> 评估通过(评分: {score})",
                    final_score=score,
                )

            # 评分未通过，反思修改
            if attempt < 2:  # 还有修改机会
                modify_step = self._modify_step(
                    current_content, eval_step.observation, platforms, context
                )
                steps.append(modify_step)

                # 执行修改
                if "regenerate" in modify_step.action.lower():
                    # 重新生成
                    result = execute_tool("generate", raw_notes=context, platforms=platforms)
                    if result.success and isinstance(result.data, WriterOutput):
                        current_content = result.data
                elif "refine" in modify_step.action.lower():
                    # 精细化修改（可以扩展）
                    pass

        # 超过最大修改次数，返回最后一次结果
        return ReActOutput(
            content=current_content,
            steps=steps,
            reasoning=f"完成：分析 -> {'搜索 -> ' if search_done else ''}生成 -> 评估({score}分) -> 多次修改未达标",
            final_score=score,
        )

    def _evaluate_step(self, content: WriterOutput, platforms: List[str], attempt: int):
        """执行评估步骤，返回 (step, score)"""
        thought = f"第{attempt}次评估：检查生成内容的质量"
        step = ReActStep(thought=thought)
        step.action = "evaluate(生成内容)"

        # 构建评估内容
        eval_content = {}
        for platform in platforms:
            text = getattr(content, platform, "")
            if text:
                eval_content[platform] = text

        result = execute_tool("evaluate", **eval_content)
        if result.success and hasattr(result.data, 'overall'):
            score = result.data.overall
            step.observation = f"评分: {score}/100"
            if hasattr(result.data, 'suggestions'):
                step.observation += f"\n建议: {', '.join(result.data.suggestions[:3])}"
        else:
            step.observation = f"评估失败: {result.error if hasattr(result, 'error') else '未知错误'}"
            score = 0

        return step, score

    def _modify_step(self, content: WriterOutput, eval_observation: str, platforms: List[str], context: str) -> ReActStep:
        """执行反思修改步骤"""
        reflect_prompt = f"""评估结果：{eval_observation}

请反思以下问题：
1. 为什么评分低于80分？
2. 主要问题是什么？（内容深度、平台适配、结构、语言风格）
3. 如何修改？

请输出修改方案："""

        thought = self._think(reflect_prompt)
        step = ReActStep(thought=thought)

        # 解析修改动作
        if "重新生成" in thought or "regenerate" in thought.lower():
            step.action = "regenerate(基于反馈重新生成)"
            step.observation = "准备重新生成"
        elif "修改" in thought or "refine" in thought.lower():
            step.action = "refine(精细化修改)"
            step.observation = "准备精细化修改"
        else:
            step.action = "adjust(调整内容)"
            step.observation = "准备调整"

        return step

    def _think(self, context: str) -> str:
        """执行思考步骤"""
        prompt = f"{context}\n\n请输出你的 Thought："
        result = self._agent.run_sync(prompt)
        return result.output if isinstance(result.output, str) else str(result.output)

    def _parse_action(self, thought: str) -> tuple:
        """
        从 Thought 中解析 Action

        支持格式：
        - Action: search("query")
        - 我要搜索 -> search
        """
        # 尝试匹配 Action: xxx("yyy")
        action_match = re.search(r'Action:\s*(\w+)\((.*?)\)', thought, re.DOTALL)
        if action_match:
            action_name = action_match.group(1)
            params_str = action_match.group(2).strip()
            try:
                if params_str.startswith('{'):
                    params = json.loads(params_str)
                elif params_str.startswith('"') and params_str.endswith('"'):
                    params = {"query": params_str.strip('"')}
                else:
                    params = {"query": params_str.strip('"')}
                return action_name, params
            except (json.JSONDecodeError, ValueError):
                return action_name, {"query": params_str.strip('"')}

        # 简单关键词匹配
        thought_lower = thought.lower()
        if "搜索" in thought or "search" in thought_lower:
            # 提取搜索关键词
            keywords = re.findall(r'[""""""]([^""""""]+)[""""""]', thought)
            if keywords:
                return "search", {"query": keywords[0]}
            return "search", {"query": "相关技术资料"}

        return "generate", {}

    def _extract_score(self, observation: str) -> int:
        """从评估结果中提取分数"""
        match = re.search(r'(\d+)', observation)
        if match:
            return int(match.group(1))
        return 0
