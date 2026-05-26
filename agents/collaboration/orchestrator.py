"""
Orchestrator — 多 Agent 协作调度器

负责任务分解、Agent 调度、结果汇总
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from pydantic_ai import Agent

from agents.collaboration.context import AgentContext, AgentMessage
from agents.schemas import WriterOutput, EditVerdict, StyleProfile
from agents.writer_agent import WriterAgent
from agents.editor_agent import EditorAgent
from agents.researcher_agent import ResearcherAgent
from agents.writer_agent import _ModelConfig


class Orchestrator:
    """多 Agent 协作调度器"""

    def __init__(self):
        self.model, _ = _ModelConfig.from_env()
        self.agents = {}
        self._init_default_agents()

    def _init_default_agents(self):
        """初始化默认 Agent"""
        self.register_agent("Researcher", ResearcherAgent())
        self.register_agent("Writer", WriterAgent())
        self.register_agent("Editor", EditorAgent(self.model))

    def register_agent(self, name: str, agent):
        """注册 Agent"""
        self.agents[name] = agent

    def run(self, raw_notes: str, platforms: List[str], task_id: Optional[str] = None) -> dict:
        """
        执行完整的多 Agent 协作流程

        流程：
        1. Researcher 搜集资料（并行）
        2. Writer 生成初稿
        3. Editor 评估（并行）
        4. 如果评分低，迭代修改
        5. Designer 设计配图（并行）
        6. 汇总输出
        """
        task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        context = AgentContext(
            task_id=task_id,
            topic=raw_notes[:100],
            raw_notes=raw_notes
        )

        print(f"\n{'='*60}")
        print(f"🤖 多 Agent 协作模式 (Orchestrator)")
        print(f"{'='*60}")
        print(f"任务ID: {task_id}")
        print(f"平台: {', '.join(platforms)}")
        print(f"笔记长度: {len(raw_notes)} 字")

        # Phase 1: Researcher 搜集资料
        if "Researcher" in self.agents:
            print(f"\n📚 [Phase 1/4] Researcher 搜集资料...")
            research_result = self.agents["Researcher"].run(raw_notes)
            context.research_report = research_result
            context.add_message("Researcher", "Orchestrator", "result", research_result[:200])
            print(f"   ✅ 资料搜集完成 ({len(research_result)} 字)")

        # Phase 2: Writer 生成初稿
        if "Writer" in self.agents:
            print(f"\n✍️  [Phase 2/4] Writer 生成初稿...")
            writer_input = context.research_report or raw_notes
            draft = self.agents["Writer"].run(writer_input, platforms)
            context.draft_content = draft
            context.add_message("Writer", "Orchestrator", "result", "生成完成")
            print(f"   ✅ 初稿生成完成")

        # Phase 3: Editor 评估 + 迭代修改
        if "Editor" in self.agents and context.draft_content:
            print(f"\n🔍 [Phase 3/4] Editor 评估...")
            for attempt in range(3):
                verdict = self._evaluate(context, platforms)

                if verdict.overall >= 80:
                    print(f"   ✅ 评估通过 (评分: {verdict.overall}/100)")
                    break

                print(f"   ⚠️  评估未通过 (评分: {verdict.overall}/100)")
                if verdict.suggestions:
                    print(f"   💡 建议: {verdict.suggestions[0][:80]}...")

                if attempt < 2:
                    print(f"   🔄 第{attempt+1}次修改...")
                    context.add_message("Editor", "Writer", "feedback", str(verdict.suggestions[:3]))

                    # Writer 修改
                    if "Writer" in self.agents:
                        draft = self.agents["Writer"].run(
                            raw_notes,
                            platforms,
                            feedback=verdict.suggestions[0] if verdict.suggestions else ""
                        )
                        context.draft_content = draft
                else:
                    print(f"   ⚠️  已达最大修改次数，使用最后一次结果")

        # Phase 4: Designer 设计配图
        if "Designer" in self.agents and context.draft_content:
            print(f"\n🎨 [Phase 4/4] Designer 设计配图...")
            # 并行生成各平台配图
            with ThreadPoolExecutor() as executor:
                futures = {}
                for platform in platforms:
                    content = getattr(context.draft_content, platform, "")
                    if content:
                        future = executor.submit(
                            self.agents["Designer"].run,
                            content,
                            platform
                        )
                        futures[platform] = future

                for platform, future in futures.items():
                    try:
                        result = future.result(timeout=60)
                        print(f"   ✅ {platform} 配图完成")
                        context.add_message("Designer", "Orchestrator", "result", f"{platform}配图完成")
                    except Exception as e:
                        print(f"   ❌ {platform} 配图失败: {e}")
                        context.add_message("Designer", "Orchestrator", "error", str(e))

        print(f"\n{'='*60}")
        print(f"✅ 任务完成 (共 {len(context.history)} 次协作)")
        print(f"{'='*60}")

        return {
            "task_id": task_id,
            "content": context.draft_content,
            "verdict": context.edit_verdict,
            "history": context.history,
        }

    def _evaluate(self, context: AgentContext, platforms: List[str]) -> EditVerdict:
        """执行评估"""
        content = context.draft_content
        if not content:
            return EditVerdict(overall=0, passed=False)

        eval_content = {}
        for platform in platforms:
            text = getattr(content, platform, "")
            if text:
                eval_content[platform] = text

        # 只评估生成的平台
        if len(eval_content) == 1:
            platform, text = list(eval_content.items())[0]
            return self.agents["Editor"].run_single(platform, text)
        else:
            return self.agents["Editor"].run(
                eval_content.get("xiaohongshu", ""),
                eval_content.get("gongzhonghao", ""),
                eval_content.get("douyin", "")
            )
