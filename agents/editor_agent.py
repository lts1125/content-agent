"""
EditorAgent — 审稿与质量检查 Agent

由 content_agent/quality_checker.py 升级而来：
- 保留底层 RuleChecker（零成本过滤）
- LLM 评分升级为结构化 EditVerdict
- suggestions 强制按格式输出：[平台] 第X段: 问题 → 期望
"""

from typing import Optional

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from agents.schemas import EditVerdict
from content_agent.quality_checker import RuleChecker, ScoreResult


# ---------------------------------------------------------------------------
# 改进版 LLM 评分 Prompt（强制结构化 suggestions）
# ---------------------------------------------------------------------------

SCORING_SYSTEM_PROMPT = """你是一位资深内容运营总监，担任三平台文案的质量检测官。

请严格按照以下标准对三份文案分别打分（0-100），并输出具体、可执行的修改建议。

【小红书评分标准】
- 标题是否有数字/emoji/悬念（20分）
- 开头3秒能否抓住注意力（20分）
- 信息密度是否适中、不流水账（20分）
- 结尾是否有互动钩子或金句（20分）
- 整体可读性、手机端阅读体验（20分）

【公众号评分标准】
- 结构是否完整（开头-正文-总结-下一步）（25分）
- 技术深度和可复现性（25分）
- 代码示例是否清晰有用（25分）
- 逻辑连贯、不跳跃（25分）

【抖音评分标准】
- 开头是否有强钩子（30分）
- 短句比例是否高（口语化）（20分）
- 是否有画面提示（20分）
- 结尾是否有行动号召（30分）

【suggestions 输出格式（强制）】
每条建议必须按以下格式：
[平台名称] 第X段: 具体问题描述 → 期望修改效果

示例：
[公众号] 第2段: 缺少具体的命令行示例 → 补充一个可复制的代码块
[小红书] 结尾: 没有互动问句 → 加一句"你们觉得哪个方法更好？评论区告诉我"
[抖音] 开头: 钩子不够强 → 前3秒直接抛出数字或反问句

要求：
- 必须定位到具体平台 + 具体段落/位置
- 问题描述要具体，不能写"加强口语化"这种空话
- 期望修改效果要可执行
- 最多输出 5 条建议，按优先级排序

【verdict 判定】
- overall >= 70 且 各平台 >= 60 → pass
- overall < 50 或 某平台 < 30 → human_review（用户介入）
- 其他情况 → retry（让 Writer 修改）

【weakest 判定】
填写分数最低的平台名称（"小红书"/"公众号"/"抖音"）。
"""


# ---------------------------------------------------------------------------
# EditorAgent
# ---------------------------------------------------------------------------

class EditorAgent:
    RULE_THRESHOLD = 70
    LLM_THRESHOLD = 70

    def __init__(self, model: OpenAIChatModel):
        self.rule_checker = RuleChecker()
        self.llm_agent = Agent(
            model,
            system_prompt=SCORING_SYSTEM_PROMPT,
            output_type=EditVerdict,
        )

    def run_single(self, platform: str, content: str) -> EditVerdict:
        """只评估单个平台"""
        # 根据平台选择检查方法
        if platform == "xiaohongshu":
            rule_result = self.rule_checker.check_xiaohongshu(content)
        elif platform == "gongzhonghao":
            rule_result = self.rule_checker.check_gongzhonghao(content)
        elif platform == "douyin":
            rule_result = self.rule_checker.check_douyin(content)
        else:
            return EditVerdict(
                overall=0, passed=False, verdict="retry",
                weakest=platform, suggestions=[f"未知平台: {platform}"],
                priority="high"
            )

        # 计算分数
        checks = list(rule_result["checks"].values())
        score = round(sum(checks) / len(checks) * 100, 1) if checks else 0

        if score < 70:
            failed = [k for k, v in rule_result["checks"].items() if not v][:5]
            return EditVerdict(
                scores={platform: score},
                overall=int(score),
                passed=False,
                verdict="retry",
                weakest=platform,
                suggestions=[f"{platform}: {', '.join(failed)}"],
                priority="high",
            )

        # LLM 评分（简化版）
        try:
            prompt = f"""请对以下{platform}文案进行评分（0-100）并给出修改建议：

{content}

请输出评分和建议。"""
            result = self.llm_agent.run_sync(prompt)
            if hasattr(result, 'output') and hasattr(result.output, 'overall'):
                return result.output
        except Exception:
            pass

        return EditVerdict(
            scores={platform: int(score)},
            overall=int(score),
            passed=True,
            verdict="pass",
            weakest=platform,
            suggestions=["规则检查通过"],
            priority="low",
        )

    def run(self, xiaohongshu: str, gongzhonghao: str, douyin: str, attempt: int = 1) -> EditVerdict:
        """混合检查入口"""
        # ---- 阶段 1: 规则校验 ----
        rule_result = self.rule_checker.check_all(xiaohongshu, gongzhonghao, douyin)

        if not rule_result["passed"]:
            failed = "、".join(rule_result["failed_items"][:5])
            return EditVerdict(
                scores={
                    "xiaohongshu": rule_result["xiaohongshu"]["score"],
                    "gongzhonghao": rule_result["gongzhonghao"]["score"],
                    "douyin": rule_result["douyin"]["score"],
                },
                overall=int(rule_result["overall_score"]),
                passed=False,
                verdict="retry",
                weakest=self._pick_weakest(rule_result),
                suggestions=[f"规则校验未通过: {failed}"],
                priority="high",
            )

        # ---- 阶段 2: LLM 精细评分 ----
        try:
            llm_verdict = self._llm_score(xiaohongshu, gongzhonghao, douyin)
        except Exception as e:
            # LLM 评分失败时，以规则分数为准，不阻断
            return EditVerdict(
                scores={
                    "xiaohongshu": rule_result["xiaohongshu"]["score"],
                    "gongzhonghao": rule_result["gongzhonghao"]["score"],
                    "douyin": rule_result["douyin"]["score"],
                },
                overall=int(rule_result["overall_score"]),
                passed=True,
                verdict="pass",
                weakest=self._pick_weakest(rule_result),
                suggestions=[f"LLM评分失败: {e}，使用规则分数作为备份"],
                priority="medium",
            )

        # 合并规则和 LLM 结果（LLM 为主，规则保底）
        llm_verdict.scores = {
            "xiaohongshu": max(int(rule_result["xiaohongshu"]["score"]), llm_verdict.scores.get("xiaohongshu", 0)),
            "gongzhonghao": max(int(rule_result["gongzhonghao"]["score"]), llm_verdict.scores.get("gongzhonghao", 0)),
            "douyin": max(int(rule_result["douyin"]["score"]), llm_verdict.scores.get("douyin", 0)),
        }
        llm_verdict.overall = max(int(rule_result["overall_score"]), llm_verdict.overall)
        return llm_verdict

    # --------------------- 内部 ---------------------
    def _llm_score(self, xiaohongshu: str, gongzhonghao: str, douyin: str) -> EditVerdict:
        prompt = f"""请对以下三份文案进行评分并给出修改建议：

=== 小红书 ===
{xiaohongshu[:1500]}

=== 公众号 ===
{gongzhonghao[:2000]}

=== 抖音 ===
{douyin[:1000]}
"""
        result = self.llm_agent.run_sync(prompt)
        return result.output

    @staticmethod
    def _pick_weakest(rule_result: dict) -> str:
        scores = {
            "xiaohongshu": rule_result["xiaohongshu"]["score"],
            "gongzhonghao": rule_result["gongzhonghao"]["score"],
            "douyin": rule_result["douyin"]["score"],
        }
        return min(scores, key=scores.get)
