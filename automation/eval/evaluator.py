"""
内容评估器 - 主入口

整合 LLM Judge + 规则检查，保存结果到数据库
"""

import hashlib
import time
from typing import Optional

from automation.eval.llm_judge import LLMJudge


class ContentEvaluator:
    """内容评估器"""

    def __init__(self, llm_judge: Optional[LLMJudge] = None):
        self.judge = llm_judge or LLMJudge()

    def evaluate(
        self,
        content: str,
        platform: str,
        topic: str = "",
        task_id: str = "",
        model: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: int = 0,
        trending_hint: str = "",
    ) -> dict:
        """
        评估内容并保存结果

        Returns:
            {
                "id": str,
                "scores": dict,  # LLM 打分
                "rules": dict,   # 规则检查
                "saved": bool,
            }
        """
        start = time.time()

        # 1. LLM 打分（多维度）
        print(f"[Evaluator] 开始评估 ({platform})...")
        scores = self.judge.evaluate(
            content=content,
            topic=topic,
            platform=platform,
            trending_hint=trending_hint,
        )

        # 2. 规则检查（完善版）
        rules = self._check_rules(content, platform)

        # 3. 保存到数据库
        eval_id = f"eval_{hashlib.md5(f'{task_id}:{platform}:{time.time()}'.encode()).hexdigest()[:12]}"

        result = {
            "id": eval_id,
            "task_id": task_id,
            "platform": platform,
            "content_hash": hashlib.md5(content.encode()).hexdigest()[:16],
            "relevance_score": scores["relevance"],
            "readability_score": scores["readability"],
            "originality_score": scores["originality"],
            "practicality_score": scores["practicality"],
            "platform_fit_score": scores.get("platform_fit", 0),
            "trend_match_score": scores.get("trend_match", 0),
            "overall_score": scores["overall"],
            "word_count": rules["word_count"],
            "char_count": rules["char_count"],
            "paragraph_count": rules["paragraph_count"],
            "emoji_count": rules["emoji_count"],
            "tag_count": rules["tag_count"],
            "has_sensitive_words": rules["has_sensitive_words"],
            "has_link": rules["has_link"],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
            "eval_latency_ms": 0,
            "model": model,
            "eval_model": self.judge.model,
        }

        saved = self._save(result)

        eval_time = int((time.time() - start) * 1000)
        print(f"[Evaluator] 评估完成: overall={scores['overall']}/10, 耗时={eval_time}ms")

        return {
            "id": eval_id,
            "scores": scores,
            "rules": rules,
            "saved": saved,
        }

    def _check_rules(self, content: str, platform: str = "") -> dict:
        """规则检查（完善版）"""
        import re

        # 基础统计
        char_count = len(content)
        word_count = len(content.replace(" ", "").replace("\n", ""))

        # 段落数（按空行分割）
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        paragraph_count = len(paragraphs)

        # emoji 数量
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # 表情符号
            "\U0001F300-\U0001F5FF"  # 符号和象形文字
            "\U0001F680-\U0001F6FF"  # 交通和地图符号
            "\U0001F1E0-\U0001F1FF"  # 国旗
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )
        emoji_count = len(emoji_pattern.findall(content))

        # 标签数量（#标签）
        tag_pattern = re.compile(r"#\w+")
        tag_count = len(tag_pattern.findall(content))

        # 敏感词检查
        sensitive_words = ["共产党", "法轮功", "色情", "赌博"]
        has_sensitive = any(w in content for w in sensitive_words)

        # 链接检查
        has_link = bool(re.search(r"https?://", content))

        # 平台特定规则
        platform_rules = {}
        if platform == "xiaohongshu":
            platform_rules = {
                "title_length_ok": 15 <= word_count <= 20,
                "emoji_ok": 5 <= emoji_count <= 10,
                "tag_ok": 5 <= tag_count <= 8,
            }
        elif platform == "gongzhonghao":
            platform_rules = {
                "title_length_ok": 20 <= word_count <= 30,
                "paragraph_ok": 5 <= paragraph_count <= 10,
                "tag_ok": 3 <= tag_count <= 5,
            }

        return {
            "word_count": word_count,
            "char_count": char_count,
            "paragraph_count": paragraph_count,
            "emoji_count": emoji_count,
            "tag_count": tag_count,
            "has_sensitive_words": has_sensitive,
            "has_link": has_link,
            **platform_rules,
        }

    def _save(self, result: dict) -> bool:
        """保存到数据库"""
        try:
            from agents.store import _get_conn, init_eval_results_table

            # 确保表存在
            init_eval_results_table()

            conn = _get_conn()
            conn.execute(
                """
                INSERT INTO eval_results (
                    id, task_id, platform, content_hash,
                    relevance_score, readability_score, originality_score, practicality_score, overall_score,
                    word_count, has_sensitive_words, has_link,
                    prompt_tokens, completion_tokens, latency_ms,
                    model, eval_model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    result["id"],
                    result["task_id"],
                    result["platform"],
                    result["content_hash"],
                    result["relevance_score"],
                    result["readability_score"],
                    result["originality_score"],
                    result["practicality_score"],
                    result["overall_score"],
                    result["word_count"],
                    result["has_sensitive_words"],
                    result["has_link"],
                    result["prompt_tokens"],
                    result["completion_tokens"],
                    result["latency_ms"],
                    result["model"],
                    result["eval_model"],
                ),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[Evaluator] 保存失败: {e}")
            return False


def demo():
    """测试评估"""
    evaluator = ContentEvaluator()

    content = """
# 从脚本到 CLI 工具

前几周我搭建了一个 Content Agent...
"""

    result = evaluator.evaluate(
        content=content,
        platform="gongzhonghao",
        topic="AI Agent CLI 改造",
        task_id="task_demo",
        model="deepseek-chat",
        prompt_tokens=1000,
        completion_tokens=2000,
        latency_ms=5000,
    )

    print(f"\n评估ID: {result['id']}")
    print(f"综合评分: {result['scores']['overall']}/10")
    print(f"字数: {result['rules']['word_count']}")
    print(f"已保存: {result['saved']}")


if __name__ == "__main__":
    demo()
