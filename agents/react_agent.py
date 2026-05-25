"""
ReAct Agent - 推理-行动循环

核心流程：
Thought -> Action -> Observation -> Thought -> ...

优化：
- 最多 3 步
- 第 1 步分析需求
- 第 2 步补充资料（可选）
- 第 3 步生成内容
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from pydantic import BaseModel
from pydantic_ai import Agent

from agents.schemas import WriterOutput
from agents.tools import execute_tool, list_tools
from content_agent.agent_core import ModelConfig


class ReActStep(BaseModel):
    """ReAct 单步记录"""
    thought: str = ""
    action: str = ""
    observation: str = ""


class ReActOutput(BaseModel):
    """ReAct 最终输出"""
    content: WriterOutput = field(default_factory=WriterOutput)
    steps: List[ReActStep] = field(default_factory=list)
    reasoning: str = ""


REACT_SYSTEM_PROMPT = """你是一个内容创作 Agent。请分析用户需求，决定是否需要补充资料，然后生成内容。

可用工具：
{tools}

规则：
- 分析笔记内容，判断是否需要搜索补充资料
- 如果需要，调用 search 工具
- 最后调用 generate 工具生成内容
- 最多执行 3 步

请用以下格式输出：
Thought: [你的分析]
Action: [工具名称](参数)
"""


class ReActAgent:
    """ReAct 内容创作 Agent"""
    
    def __init__(self, max_steps: int = 3):
        self.max_steps = max_steps
        self.model, _ = ModelConfig.from_env()
        self.tools_prompt = "\n".join(list_tools())
        
        self._agent = Agent(
            self.model,
            system_prompt=REACT_SYSTEM_PROMPT.format(tools=self.tools_prompt),
        )
    
    def run(self, raw_notes: str, platforms: List[str]) -> ReActOutput:
        """
        执行 ReAct 循环
        
        Args:
            raw_notes: 原始笔记内容
            platforms: 目标平台列表
            
        Returns:
            ReActOutput: 包含生成内容和执行步骤
        """
        steps: List[ReActStep] = []
        context = f"目标：根据以下笔记生成 {', '.join(platforms)} 平台的内容\n\n笔记内容：\n{raw_notes[:1500]}"
        
        # 第 1 步：分析需求
        thought = self._think(context)
        step1 = ReActStep(thought=thought)
        
        # 解析是否需要搜索
        action_name, action_params = self._parse_action(thought)
        
        if action_name == "search":
            # 需要搜索补充资料
            step1.action = f"search({json.dumps(action_params, ensure_ascii=False)})"
            result = execute_tool("search", **action_params)
            step1.observation = result.data if result.success else f"错误: {result.error}"
            steps.append(step1)
            
            # 更新上下文，加入搜索结果
            context += f"\n\n搜索结果：\n{step1.observation[:500]}"
            
            # 第 2 步：基于搜索结果生成
            thought2 = self._think(context + "\n\n基于以上信息，生成内容：")
            step2 = ReActStep(thought=thought2)
            step2.action = f"generate({{'raw_notes': '{raw_notes[:500]}...', 'platforms': {platforms}}})"
            
            result = execute_tool("generate", raw_notes=context, platforms=platforms)
            step2.observation = "生成完成" if result.success else f"错误: {result.error}"
            steps.append(step2)
            
            if result.success and isinstance(result.data, WriterOutput):
                return ReActOutput(
                    content=result.data,
                    steps=steps,
                    reasoning="完成：分析 -> 搜索 -> 生成",
                )
        else:
            # 不需要搜索，直接生成
            step1.action = f"generate({{'raw_notes': '...', 'platforms': {platforms}}})"
            result = execute_tool("generate", raw_notes=raw_notes, platforms=platforms)
            step1.observation = "生成完成" if result.success else f"错误: {result.error}"
            steps.append(step1)
            
            if result.success and isinstance(result.data, WriterOutput):
                return ReActOutput(
                    content=result.data,
                    steps=steps,
                    reasoning="完成：分析 -> 直接生成",
                )
        
        # 失败返回
        return ReActOutput(
            content=WriterOutput(),
            steps=steps,
            reasoning="生成失败",
        )
    
    def _think(self, context: str) -> str:
        """执行思考步骤"""
        prompt = f"{context}\n\n请输出你的 Thought 和 Action："
        result = self._agent.run_sync(prompt)
        return result.output if isinstance(result.output, str) else str(result.output)
    
    def _parse_action(self, thought: str) -> tuple:
        """从 Thought 中解析 Action"""
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
        
        # 根据关键词判断
        if "搜索" in thought or "查找" in thought or "补充" in thought:
            # 提取关键词
            keywords = re.findall(r'["""](.+?)["""]', thought)
            if keywords:
                return "search", {"query": keywords[0]}
            # 从笔记中提取关键概念
            lines = thought.split('\n')
            for line in lines:
                if any(kw in line for kw in ["关于", "主题", "话题"]):
                    return "search", {"query": line.strip()[:50]}
        
        return "generate", {}
    
    def _is_complete(self, thought: str) -> bool:
        """判断是否完成"""
        complete_keywords = ["完成", "结束", "done", "finish", "通过"]
        return any(kw in thought.lower() for kw in complete_keywords)


# 兼容旧接口
class OrchestratorAdapter:
    """适配器，让 ReActAgent 兼容旧 Orchestrator 接口"""
    
    def __init__(self):
        self.agent = ReActAgent()
    
    def run(self, raw_notes: str, platforms: List[str], **kwargs) -> dict:
        """兼容旧接口"""
        result = self.agent.run(raw_notes, platforms)
        return {
            "success": True,
            "content": result.content,
            "steps": [s.dict() for s in result.steps],
            "reasoning": result.reasoning,
        }
