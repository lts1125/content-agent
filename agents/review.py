"""
审核面板（ReviewPanel）

把后台自动跑的质量检查搬到前台 UI，
让用户能看到每条规则检查结果，并一键采纳修改或忽略某项。
"""

from dataclasses import dataclass, field
from typing import List, Optional

from agents.schemas import EditVerdict


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

PLATFORM_NAMES = {
    "xiaohongshu": "小红书",
    "gongzhonghao": "公众号",
    "douyin": "抖音",
}

MAX_IGNORE_ITEMS = 2       # 最多忽略 2 项
MAX_REVISION_ATTEMPTS = 2  # 采纳修改后最多再重试 2 次
DEFAULT_THRESHOLD = 75


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class ReviewItem:
    """单条规则检查项"""
    dimension: str           # 维度名称（平台名或其他维度）
    score: int               # 得分
    threshold: int           # 阈值
    passed: bool             # 是否通过
    suggestion: str          # 改进建议
    ignored: bool = False    # 用户是否忽略此项


@dataclass
class ReviewPanel:
    """审核面板"""
    overall: int
    threshold: int
    passed: bool
    items: List[ReviewItem]
    verdict_text: str
    user_decision: Optional[str] = None   # "revise" | "ignore" | "force_publish"
    revision_prompt: str = ""
    raw_content: Optional[object] = None  # 原始生成内容（WriterOutput）
    platforms: List[str] = field(default_factory=list)
    revision_count: int = 0               # 已采纳修改并重新生成的次数

    @property
    def effective_score(self) -> int:
        """计算有效得分（忽略未通过项后重新计算）"""
        if self.passed:
            return self.overall
        active_items = [i for i in self.items if not i.ignored]
        if not active_items:
            return self.overall
        return int(sum(i.score for i in active_items) / len(active_items))

    @property
    def effective_passed(self) -> bool:
        """忽略后是否通过"""
        return self.effective_score >= self.threshold

    @property
    def ignored_count(self) -> int:
        """已忽略项数量"""
        return sum(1 for i in self.items if i.ignored)

    def can_ignore_more(self) -> bool:
        """是否还能继续忽略"""
        return self.ignored_count < MAX_IGNORE_ITEMS

    def can_revise(self) -> bool:
        """是否还能采纳修改并重新生成"""
        return self.revision_count < MAX_REVISION_ATTEMPTS

    def get_revision_prompt(self) -> str:
        """生成修改指令"""
        failed_items = [i for i in self.items if not i.passed and not i.ignored]
        if not failed_items:
            return "请根据整体评分修改文案"
        lines = ["请重点修改以下方面："]
        for item in failed_items:
            lines.append(f"- {item.dimension}: {item.suggestion}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """将审核面板转换为 Markdown 显示"""
        status_icon = "✅" if self.passed else "❌"
        lines = [
            "## 🔍 质量检查报告",
            "",
            f"整体得分: **{self.overall}/100** {status_icon} {'已达标' if self.passed else '未达标'}",
        ]
        if self.revision_count > 0:
            remaining = MAX_REVISION_ATTEMPTS - self.revision_count
            lines.append(f"🔄 已重试 {self.revision_count}/{MAX_REVISION_ATTEMPTS} 次，剩余 {remaining} 次")
        lines.append("")
        lines.extend([
            "| 维度 | 得分 | 状态 | 建议 |",
            "|-------|------|------|--------|",
        ])
        for item in self.items:
            icon = "✅" if item.passed else "❌"
            note = "（已忽略）" if item.ignored else ""
            lines.append(
                f"| {item.dimension}{note} | {item.score} | {icon} | {item.suggestion or '-'} |"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ReviewManager
# ---------------------------------------------------------------------------

class ReviewManager:
    """审核管理器：将 EditorAgent 结果转换为审核面板，处理用户决策。"""

    @staticmethod
    def create_panel(verdict: EditVerdict, threshold: int = DEFAULT_THRESHOLD) -> ReviewPanel:
        """根据评分结果创建审核面板"""
        items = []
        scores = getattr(verdict, "scores", {}) or {}
        suggestions = getattr(verdict, "suggestions", []) or []

        # 将平台分数转换为 ReviewItem
        for platform, score in scores.items():
            name = PLATFORM_NAMES.get(platform, platform) or platform
            passed = score >= threshold
            # 尝试从 suggestions 中提取对应平台的建议
            suggestion = ""
            for s in suggestions:
                if platform in s or name in s:
                    suggestion = s
                    break
            if not suggestion and not passed:
                suggestion = f"{name}内容质量不达标，需改进"
            items.append(ReviewItem(
                dimension=name,
                score=int(score),
                threshold=threshold,
                passed=passed,
                suggestion=suggestion,
            ))

        # 如果没有平台分数，创建一个综合项
        if not items:
            items.append(ReviewItem(
                dimension="综合评分",
                score=verdict.overall,
                threshold=threshold,
                passed=verdict.passed,
                suggestion="; ".join(suggestions) if suggestions else "",
            ))

        verdict_text = getattr(verdict, "verdict", "")
        if verdict_text == "pass":
            verdict_text = "通过"
        elif verdict_text == "retry":
            verdict_text = "需修改"
        elif verdict_text == "human_review":
            verdict_text = "需人工复审"

        panel = ReviewPanel(
            overall=verdict.overall,
            threshold=threshold,
            passed=verdict.passed,
            items=items,
            verdict_text=verdict_text,
        )
        panel.revision_prompt = panel.get_revision_prompt()
        return panel

    @staticmethod
    def apply_user_decision(panel: ReviewPanel, decision: str) -> dict:
        """
        应用用户决策。

        Returns:
            {
                "action": "revise" | "retry" | "publish",
                "prompt": str,           # 如果是 revise，这是修改指令
                "should_continue": bool, # 是否继续生成流程
            }
        """
        panel.user_decision = decision

        if decision == "revise":
            return {
                "action": "revise",
                "prompt": panel.get_revision_prompt(),
                "should_continue": True,
            }

        if decision == "ignore":
            # 忽略未通过的项（从分数最低的开始忽略，不超过上限）
            failed = [i for i in panel.items if not i.passed and not i.ignored]
            failed.sort(key=lambda x: x.score)
            can_ignore = MAX_IGNORE_ITEMS - panel.ignored_count
            for item in failed[:can_ignore]:
                item.ignored = True

            if panel.effective_passed:
                return {
                    "action": "publish",
                    "prompt": "",
                    "should_continue": False,
                }
            return {
                "action": "retry",
                "prompt": panel.get_revision_prompt(),
                "should_continue": True,
            }

        if decision == "force_publish":
            return {
                "action": "publish",
                "prompt": "",
                "should_continue": False,
            }

        return {
            "action": "unknown",
            "prompt": "",
            "should_continue": False,
        }

    @staticmethod
    def save_panel(panel: ReviewPanel, task_id: str) -> None:
        """持久化审核面板"""
        from agents.store import save_review_panel
        save_review_panel(panel, task_id)

    @staticmethod
    def load_panel(task_id: str) -> Optional[ReviewPanel]:
        """加载审核面板"""
        from agents.store import load_review_panel
        return load_review_panel(task_id)
