"""
Orchestrator — 纯 Python 调度器，非 LLM。

职责：
- 接收 TaskInput，制定纯规则 ExecutionPlan
- 按序调用 ResearchAgent → WriterAgent → EditorAgent
- 控制 Writer → Editor 循环（最多 3 次含初稿）
- 熔断：3 次不过则推给用户（human_review）
"""

import time
import uuid
from typing import Optional

from agents.schemas import TaskInput, TaskState, ExecutionPlan, WriterOutput, EditVerdict
from agents.research_agent import ResearchAgent
from agents.writer_agent import WriterAgent
from agents.editor_agent import EditorAgent


MAX_EDIT_LOOPS = 3          # 含初稿最多 3 次
MAX_LLM_CALLS = 5           # 单次任务 LLM 调用上限（Orchestrator 本身不占用）


class Orchestrator:
    def __init__(
        self,
        research_agent: Optional[ResearchAgent] = None,
        writer_agent: Optional[WriterAgent] = None,
        editor_agent: Optional[EditorAgent] = None,
    ):
        self.research_agent = research_agent or ResearchAgent()
        self.writer_agent = writer_agent or WriterAgent()
        self.editor_agent = editor_agent or EditorAgent(self.writer_agent.model)

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------
    def run(self, task_input: TaskInput) -> TaskState:
        plan = self._make_plan(task_input)
        state = TaskState(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            note_source=task_input.note_source,
            metadata={"plan": plan.steps, "started_at": time.time()},
        )

        # 1. 搜索增强（可选，1 次）
        # 先把原始笔记塞进 metadata，供 ResearchAgent 读取
        state.metadata["_raw_note_text"] = task_input.note_text
        if plan.needs_search:
            state.status = "researching"
            state = self.research_agent.run(state, engine=task_input.search_engine)

        # 2. 生成 + 编辑循环
        state.status = "writing"
        state = self._write_edit_loop(state, task_input)

        # 3. 收尾
        if state.status not in ("done", "failed"):
            state.status = "done"
        state.metadata["finished_at"] = time.time()
        state.metadata["duration_sec"] = round(
            state.metadata["finished_at"] - state.metadata["started_at"], 2
        )

        # 记录执行轨迹
        state.trace = {
            "plan": plan.steps,
            "drafts_count": len(state.drafts),
            "edit_loops": len(state.edit_history),
            "final_score": state.edit_history[-1].overall if state.edit_history else None,
            "duration_sec": state.metadata["duration_sec"],
            "llm_calls": state.metadata.get("llm_calls", 0),
        }

        # 4. Eval 评估
        self._run_eval(state, task_input)

        return state

    def _run_eval(self, state: TaskState, inp: TaskInput):
        """运行 Eval 评估"""
        try:
            from automation.eval.evaluator import ContentEvaluator

            evaluator = ContentEvaluator()
            output = state.final_output
            if not output:
                return

            for platform in inp.platforms:
                content = getattr(output, platform, "")
                if not content:
                    continue

                evaluator.evaluate(
                    content=content,
                    platform=platform,
                    topic=inp.note_source or "",
                    task_id=state.task_id,
                    model=state.metadata.get("model", ""),
                    prompt_tokens=state.metadata.get("prompt_tokens", 0),
                    completion_tokens=state.metadata.get("completion_tokens", 0),
                    latency_ms=int(state.metadata.get("duration_sec", 0) * 1000),
                )
        except Exception as e:
            print(f"[Orchestrator] Eval 评估失败: {e}")

    # ------------------------------------------------------------------
    # 纯规则计划
    # ------------------------------------------------------------------
    @staticmethod
    def _make_plan(inp: TaskInput) -> ExecutionPlan:
        steps = []
        if inp.enable_research:
            steps.append("research")
        steps.extend(["write", "edit"])
        return ExecutionPlan(
            steps=steps,
            reasoning="纯规则调度：按用户勾选的选项执行",
            needs_search=inp.enable_research,
            target_platforms=inp.platforms,
        )

    # ------------------------------------------------------------------
    # 受控生成-编辑循环
    # ------------------------------------------------------------------
    def _write_edit_loop(self, state: TaskState, inp: TaskInput) -> TaskState:
        """Writer → Editor 循环，最多 3 轮；如果 skip_edit 为 True，只生成初稿不审稿"""
        llm_calls = 0
        raw_notes = self._build_writer_input(state, inp)

        # ---- 快速模式：只出初稿，跳过 Editor ----
        if inp.skip_edit:
            draft = self.writer_agent.run(
                raw_notes,
                platforms=inp.platforms,
                style=inp.style,
                concurrent=inp.concurrent_mode,
            )
            state.drafts.append(draft)
            state.final_output = draft
            state.status = "done"
            state.metadata["llm_calls"] = 1
            return state

        for attempt in range(1, MAX_EDIT_LOOPS + 1):
            # ---- Writer ----
            if attempt == 1:
                draft = self.writer_agent.run(
                    raw_notes,
                    platforms=inp.platforms,
                    style=inp.style,
                    concurrent=inp.concurrent_mode,
                )
            else:
                last_verdict = state.edit_history[-1]
                draft = self.writer_agent.refine(
                    prev_draft=state.drafts[-1],
                    verdict=last_verdict,
                    raw_notes=raw_notes,
                    platforms=inp.platforms,
                    concurrent=inp.concurrent_mode,
                )
            state.drafts.append(draft)
            llm_calls += 1

            # ---- Editor ----
            state.status = "editing"
            verdict = self.editor_agent.run(
                draft.xiaohongshu,
                draft.gongzhonghao,
                draft.douyin,
                attempt=attempt,
            )
            state.edit_history.append(verdict)
            llm_calls += 1

            # ---- 通过 or 终止 ----
            if verdict.passed:
                state.final_output = draft
                state.status = "done"
                state.metadata["llm_calls"] = llm_calls
                return state

            if attempt >= MAX_EDIT_LOOPS:
                # 3 次不过，取最佳稿（overall 最高的一次）
                best_idx = self._pick_best_draft(state)
                state.final_output = state.drafts[best_idx]
                state.status = "done"
                state.metadata["llm_calls"] = llm_calls
                state.metadata["human_review_needed"] = True
                return state

            # Token 预算熔断
            if llm_calls >= MAX_LLM_CALLS:
                best_idx = self._pick_best_draft(state)
                state.final_output = state.drafts[best_idx]
                state.status = "done"
                state.metadata["llm_calls"] = llm_calls
                state.metadata["token_budget_exceeded"] = True
                return state

        return state

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _build_writer_input(state: TaskState, inp: TaskInput) -> str:
        """拼接原始笔记 + 研究资料，供 Writer 使用"""
        if state.research_data and state.research_data.key_insights:
            return (
                f"【搜索补充资料】\n{state.research_data.key_insights}\n\n"
                f"--- 原始笔记 ---\n{inp.note_text}"
            )
        return inp.note_text

    @staticmethod
    def _pick_best_draft(state: TaskState) -> int:
        """从 edit_history 中找出 overall 最高的一次"""
        if not state.edit_history:
            return 0
        scores = [v.overall for v in state.edit_history]
        return scores.index(max(scores))
