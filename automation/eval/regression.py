"""
回归测试 - 固定测试集 + 对比报告
"""

import json
import os
import time
from pathlib import Path
from typing import List, Optional

from automation.eval.evaluator import ContentEvaluator
from agents.orchestrator import Orchestrator
from agents.schemas import TaskInput


# 固定回归测试集
REGRESSION_CASES = [
    {
        "name": "MCP协议",
        "note_file": "20260515_mcp_search_enhancement.md",
        "topic": "MCP协议成为AI工具互联标准",
        "platforms": ["gongzhonghao"],
        "trending_hint": "MCP协议",
    },
    {
        "name": "CLI工具改造",
        "note_file": "CLI工具化改造笔记.md",
        "topic": "从脚本到CLI工具",
        "platforms": ["gongzhonghao"],
        "trending_hint": "",
    },
    {
        "name": "三平台输出",
        "note_file": "20260518_three_platform_output.md",
        "topic": "多平台内容输出",
        "platforms": ["xiaohongshu"],
        "trending_hint": "",
    },
]


class RegressionTester:
    """回归测试器"""

    def __init__(self, vault_path: Optional[str] = None):
        self.vault_path = Path(vault_path or os.getenv("VAULT_PATH", str(Path(__file__).resolve().parent.parent.parent / "notes")))
        self.evaluator = ContentEvaluator()
        self.orchestrator = Orchestrator()

    def run(self, cases: Optional[List[dict]] = None, quick: bool = False) -> dict:
        """
        运行回归测试

        Args:
            cases: 自定义测试用例
            quick: 快速模式（只跑1个用例）

        Returns:
            {
                "results": list,
                "summary": dict,
            }
        """
        if quick:
            cases = [REGRESSION_CASES[1]]  # CLI工具改造笔记
        else:
            cases = cases or REGRESSION_CASES

        results = []
        print(f"[Regression] 开始回归测试，共 {len(cases)} 个用例")

        for case in cases:
            print(f"\n[Regression] 测试用例: {case['name']}")
            case_result = self._run_case(case)
            results.append(case_result)

        summary = self._summarize(results)

        return {
            "results": results,
            "summary": summary,
        }

    def _run_case(self, case: dict) -> dict:
        """运行单个用例"""
        note_path = self.vault_path / case["note_file"]

        # 读取笔记
        if not note_path.exists():
            print(f"[Regression] 笔记不存在: {note_path}")
            return {
                "name": case["name"],
                "status": "skipped",
                "reason": "笔记不存在",
            }

        with open(note_path, "r") as f:
            note_text = f.read()

        # 生成内容
        task_input = TaskInput(
            note_text=note_text,
            note_source=str(note_path),
            platforms=case["platforms"],
            skip_edit=True,  # 快速模式，跳过编辑
        )

        start = time.time()
        state = self.orchestrator.run(task_input)
        gen_time = int((time.time() - start) * 1000)

        # 评估每个平台
        platform_results = []
        for platform in case["platforms"]:
            content = getattr(state.final_output, platform, "")
            if not content:
                continue

            eval_result = self.evaluator.evaluate(
                content=content,
                platform=platform,
                topic=case["topic"],
                task_id=state.task_id,
                trending_hint=case.get("trending_hint", ""),
            )

            platform_results.append({
                "platform": platform,
                "scores": eval_result["scores"],
                "rules": eval_result["rules"],
            })

        return {
            "name": case["name"],
            "status": "done",
            "task_id": state.task_id,
            "gen_time_ms": gen_time,
            "platforms": platform_results,
        }

    def _summarize(self, results: List[dict]) -> dict:
        """汇总统计"""
        total_cases = len(results)
        done_cases = [r for r in results if r.get("status") == "done"]

        if not done_cases:
            return {"total": total_cases, "done": 0, "avg_overall": 0}

        # 计算平均分
        all_scores = []
        for case in done_cases:
            for platform in case.get("platforms", []):
                all_scores.append(platform["scores"]["overall"])

        avg_overall = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0

        return {
            "total": total_cases,
            "done": len(done_cases),
            "skipped": total_cases - len(done_cases),
            "avg_overall": avg_overall,
        }

    def generate_report(self, current_results: dict, baseline_results: Optional[dict] = None) -> str:
        """生成对比报告"""
        lines = []
        lines.append("=" * 50)
        lines.append("回归测试报告")
        lines.append("=" * 50)
        lines.append(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"用例数: {current_results['summary']['total']}")
        lines.append(f"通过: {current_results['summary']['done']}")
        lines.append(f"跳过: {current_results['summary']['skipped']}")
        lines.append("")

        # 当前结果
        lines.append("当前结果:")
        lines.append(f"  综合评分: {current_results['summary']['avg_overall']}")
        lines.append("")

        # 各用例详情
        lines.append("各用例详情:")
        for case in current_results["results"]:
            if case["status"] == "skipped":
                lines.append(f"  [跳过] {case['name']}: {case['reason']}")
                continue

            for platform in case.get("platforms", []):
                score = platform["scores"]["overall"]
                lines.append(f"  [通过] {case['name']} ({platform['platform']}): {score}")

        # 与基线对比
        if baseline_results:
            lines.append("")
            lines.append("与基线对比:")
            baseline_avg = baseline_results["summary"]["avg_overall"]
            current_avg = current_results["summary"]["avg_overall"]
            diff = round(current_avg - baseline_avg, 2)

            if diff > 0:
                lines.append(f"  综合评分: {baseline_avg} -> {current_avg} (+{diff}) 上升")
            elif diff < 0:
                lines.append(f"  综合评分: {baseline_avg} -> {current_avg} ({diff}) 下降 ⚠️")
            else:
                lines.append(f"  综合评分: {baseline_avg} -> {current_avg} (无变化)")

        lines.append("")
        lines.append("=" * 50)

        return "\n".join(lines)


def demo():
    """测试回归"""
    tester = RegressionTester()

    # 只跑第一个用例（快速测试）
    results = tester.run(cases=[REGRESSION_CASES[0]])

    print("\n" + tester.generate_report(results))


if __name__ == "__main__":
    demo()
