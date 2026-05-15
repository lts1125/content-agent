"""
内容质量检查 - 混合模式：规则校验 + LLM 评分

流程：
  1. 规则校验（快速过滤硬性指标）
  2. LLM 精细评分（0-100）
  3. 综合分数 < 70 则带建议重试（最多 3 次）
"""

import re
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel


class ScoreResult(BaseModel):
    """LLM 结构化评分结果"""
    xiaohongshu: int = Field(..., ge=0, le=100, description="小红书文案得分")
    gongzhonghao: int = Field(..., ge=0, le=100, description="公众号文案得分")
    douyin: int = Field(..., ge=0, le=100, description="抖音文案得分")
    overall: int = Field(..., ge=0, le=100, description="综合得分（三平台平均）")
    weakest: str = Field(..., description="最弱的平台名称")
    suggestion: str = Field(..., description="具体改进建议，用于重试 prompt")


class CheckResult(BaseModel):
    """完整检查结果"""
    passed: bool
    overall_score: int
    rule_passed: bool
    rule_details: dict
    llm_score: Optional[ScoreResult] = None
    retry_suggestion: str = ""
    attempt: int = 1


# ============ 规则校验器 ============

class RuleChecker:
    """纯代码层面的硬性指标校验，零 API 成本"""

    @staticmethod
    def check_xiaohongshu(text: str) -> dict:
        """小红书规则校验"""
        checks = {
            "字数达标(200-800)": 200 <= len(text) <= 800,
            "含有emoji": bool(re.search(r'[\U0001F600-\U0001F9FF\u2600-\u26FF]', text)),
            "含有标签(#)": bool(re.search(r'#\S+', text)),
            "含有互动问句": bool(re.search(r'[?？]', text)),
            "分段清晰(≥3段)": text.count("\n\n") >= 2,
            "有数字或步骤": bool(re.search(r'\d[一-九]|第\d+步|步骤\d|①-⑳', text)),
            "标题吸睛(数字/表情/悬念)": bool(re.search(r'\d|[❓❗！]|[\U0001F600-\U0001F9FF]', text.split("\n")[0] if text else "")),
        }
        score = sum(checks.values()) / len(checks) * 100
        return {"score": round(score, 1), "checks": checks, "total": len(checks)}

    @staticmethod
    def check_gongzhonghao(text: str) -> dict:
        """公众号规则校验"""
        checks = {
            "字数达标(1000-3000)": 1000 <= len(text) <= 3000,
            "有标题层级(##)": bool(re.search(r'#{2,3}\s+', text)),
            "含代码块": "```" in text,
            "有总结部分": bool(re.search(r'[总结|小结|结论|最后]', text)),
            "有下一步/行动号召": bool(re.search(r'[下一步|行动|关注|开始|赶紧]', text)),
            "段落数量充足(≥5段)": text.count("\n\n") >= 4,
            "含有实例/场景": bool(re.search(r'[例如|比如|举个例子|场景]', text)),
        }
        score = sum(checks.values()) / len(checks) * 100
        return {"score": round(score, 1), "checks": checks, "total": len(checks)}

    @staticmethod
    def check_douyin(text: str) -> dict:
        """抖音规则校验"""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        short_lines = sum(1 for l in lines if len(l) <= 20)
        checks = {
            "字数达标(150-500)": 150 <= len(text) <= 500,
            "开头有钩子(停/别/你知道/别再)": bool(re.search(r'^[停!！别你知道还是|十个|别再]', text)),
            "短句比例高(≥50%)": len(lines) > 0 and short_lines / len(lines) >= 0.5,
            "有画面提示": bool(re.search(r'[【.*?[】]', text)),
            "有行动号召": bool(re.search(r'[关注|点赞|收藏|跟我|赶紧|试试]', text)),
            "口语化(我/你/大家)": bool(re.search(r'[我|你|大家|我们]', text)),
            "有转折/悬念": bool(re.search(r'[但是|然而|结果|没想到|反而|其实]', text)),
        }
        score = sum(checks.values()) / len(checks) * 100
        return {"score": round(score, 1), "checks": checks, "total": len(checks)}

    def check_all(self, xiaohongshu: str, gongzhonghao: str, douyin: str) -> dict:
        """三平台一起校验，返回合格状态和各项细节"""
        xhs_result = self.check_xiaohongshu(xiaohongshu)
        gzh_result = self.check_gongzhonghao(gongzhonghao)
        dy_result = self.check_douyin(douyin)

        all_checks = (
            list(xhs_result["checks"].values()) +
            list(gzh_result["checks"].values()) +
            list(dy_result["checks"].values())
        )
        total_pass = sum(all_checks)
        total_count = len(all_checks)
        overall_score = round(total_pass / total_count * 100, 1)

        # 找出失败的具体项
        failed = []
        for platform, result in [("小红书", xhs_result), ("公众号", gzh_result), ("抖音", dy_result)]:
            for check_name, passed in result["checks"].items():
                if not passed:
                    failed.append(f"{platform}: {check_name}")

        return {
            "overall_score": overall_score,
            "passed": overall_score >= 70,
            "xiaohongshu": xhs_result,
            "gongzhonghao": gzh_result,
            "douyin": dy_result,
            "failed_items": failed,
            "total_checks": total_count,
            "passed_checks": total_pass,
        }


# ============ LLM 评分器 ============

SCORING_SYSTEM_PROMPT = """你是一位资深内容运营总监，担任三平台文案的质量检测官。

请严格按照以下标准对三份文案分别打分（0-100），并输出改进建议。

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

输出要求：
- overall 取三平台分数的平均数（四舍五入为整数）
- weakest 填写分数最低的平台名称（"小红书"/"公众号"/"抖音"）
- suggestion 填写具体改进建议，要简洁、可执行，用于重试 prompt
"""


class LLMScorer:
    """LLM 精细评分，复用同一个 model 换 prompt"""

    def __init__(self, model):
        self.agent = Agent(
            model,
            system_prompt=SCORING_SYSTEM_PROMPT,
            output_type=ScoreResult,
        )

    def score(self, xiaohongshu: str, gongzhonghao: str, douyin: str) -> ScoreResult:
        """对三平台文案进行 LLM 评分"""
        prompt = f"""请对以下三份文案进行评分：

=== 小红书 ===
{xiaohongshu[:1500]}

=== 公众号 ===
{gongzhonghao[:2000]}

=== 抖音 ===
{douyin[:1000]}
"""
        result = self.agent.run_sync(prompt)
        return result.output


# ============ 混合检查器 ============

class QualityChecker:
    """混合质量检查器：先走规则，再走 LLM"""

    RULE_THRESHOLD = 70      # 规则校验合格线
    LLM_THRESHOLD = 70       # LLM 评分合格线
    MAX_RETRIES = 3          # 最多重试次数

    def __init__(self, model):
        self.rule_checker = RuleChecker()
        self.llm_scorer = LLMScorer(model)

    def check(self, xiaohongshu: str, gongzhonghao: str, douyin: str, attempt: int = 1) -> CheckResult:
        """
        混合检查入口

        Returns:
            CheckResult: 包含是否通过、分数、重试建议
        """
        # ---- 阶段 1: 规则校验 ----
        rule_result = self.rule_checker.check_all(xiaohongshu, gongzhonghao, douyin)
        rule_passed = rule_result["passed"]

        if not rule_passed:
            # 规则不过，直接返回，不浪费 LLM token
            failed = "、".join(rule_result["failed_items"][:5])
            return CheckResult(
                passed=False,
                overall_score=int(rule_result["overall_score"]),
                rule_passed=False,
                rule_details=rule_result,
                retry_suggestion=f"规则校验未通过，请修复以下问题：{failed}",
                attempt=attempt,
            )

        # ---- 阶段 2: LLM 精细评分 ----
        try:
            llm_result = self.llm_scorer.score(xiaohongshu, gongzhonghao, douyin)
        except Exception as e:
            # LLM 评分失败时，以规则分数为准，不阻断正常输出
            return CheckResult(
                passed=True,  # 规则过了，先让它过
                overall_score=int(rule_result["overall_score"]),
                rule_passed=True,
                rule_details=rule_result,
                retry_suggestion=f"LLM评分失败: {e}，使用规则分数作为备份",
                attempt=attempt,
            )

        # 综合判断
        passed = llm_result.overall >= self.LLM_THRESHOLD

        return CheckResult(
            passed=passed,
            overall_score=llm_result.overall,
            rule_passed=True,
            rule_details=rule_result,
            llm_score=llm_result,
            retry_suggestion=llm_result.suggestion if not passed else "",
            attempt=attempt,
        )
