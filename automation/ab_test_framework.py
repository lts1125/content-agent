"""
A/B Test Framework — 变体生成 + 结果记录 + 最优推荐

为同一文案生成多个变体（标题/钩子/风格），记录各变体表现，分析最优版本。
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel
from pydantic_ai import Agent

from agents.store import _get_conn
from content_agent.agent_core import ModelConfig


@dataclass
class ABTestVariant:
    id: str
    task_id: str
    platform: str
    variant_type: Literal["title", "hook", "style"]
    variant_content: str
    status: Literal["pending", "published", "result_imported"]
    metrics_id: Optional[str]
    created_at: str


class TitleVariantsOutput(BaseModel):
    titles: List[str]


class HookVariantsOutput(BaseModel):
    hooks: List[str]


class StyleVariantsOutput(BaseModel):
    styles: List[str]


class ABTestFramework:
    def __init__(self, model=None):
        if model is None:
            model, _ = ModelConfig.from_env()
        self.model = model

    def generate_variants(
        self,
        queue_item_id: str,
        variant_types: List[str],
        count: int = 3,
    ) -> List[ABTestVariant]:
        """为指定队列项生成 A/B 测试变体"""
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM publish_queue WHERE id = ?", (queue_item_id,)
        ).fetchone()
        conn.close()
        if row is None:
            raise ValueError(f"队列项不存在: {queue_item_id}")
        if row["status"] not in ("pending", "approved"):
            raise ValueError(f"队列项状态为 {row['status']}，仅支持 pending 或 approved")

        content = row["content"] or ""
        platform = row["platform"] or ""
        task_id = row["task_id"] or ""
        title = row["title"] or ""

        variants = []
        now = datetime.now().isoformat()
        conn = _get_conn()

        for vtype in variant_types:
            vtype = vtype.strip().lower()
            if vtype not in ("title", "hook", "style"):
                continue
            generated = self._generate(vtype, content, title, platform, count)
            for g in generated:
                vid = f"ab_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO ab_test_variants
                    (id, task_id, platform, variant_type, variant_content, status, metrics_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (vid, task_id, platform, vtype, g, "pending", None, now),
                )
                variants.append(
                    ABTestVariant(
                        id=vid,
                        task_id=task_id,
                        platform=platform,
                        variant_type=vtype,
                        variant_content=g,
                        status="pending",
                        metrics_id=None,
                        created_at=now,
                    )
                )
        conn.commit()
        conn.close()
        return variants

    def _generate(self, vtype: str, content: str, title: str, platform: str, count: int) -> List[str]:
        if vtype == "title":
            prompt = f"""为以下内容生成 {count} 个不同的标题。

平台: {platform}
原标题: {title}
内容前 500 字:
{content[:500]}

要求：每个标题都要有吸引力，适合 {platform} 平台风格。输出 JSON 格式：{{"titles": ["标题1", "标题2", ...]}}
"""
            try:
                agent = Agent(
                    self.model,
                    system_prompt="你是一位标题专家，擅长为不同平台写出高点击率的标题。",
                    output_type=TitleVariantsOutput,
                )
                result = agent.run_sync(prompt)
                return result.output.titles[:count]
            except Exception as e:
                print(f"[ABTest] 生成标题变体失败: {e}")
                return []

        elif vtype == "hook":
            prompt = f"""为以下内容生成 {count} 个不同的开头钩子（前 2 句话）。

平台: {platform}
内容前 500 字:
{content[:500]}

要求：每个钩子都要在前 2 句话内抓住读者注意力。输出 JSON 格式：{{"hooks": ["钩子1", "钩子2", ...]}}
"""
            try:
                agent = Agent(
                    self.model,
                    system_prompt="你是一位文案高手，擅长写出让人忍不住继续读下去的开头。",
                    output_type=HookVariantsOutput,
                )
                result = agent.run_sync(prompt)
                return result.output.hooks[:count]
            except Exception as e:
                print(f"[ABTest] 生成钩子变体失败: {e}")
                return []

        elif vtype == "style":
            prompt = f"""为以下内容生成 {count} 个不同风格的改写版本（每版 100-200 字）。

平台: {platform}
内容前 500 字:
{content[:500]}

要求：风格差异要明显（如专业严谨 vs 轻松口语 vs 情绪共鸣）。输出 JSON 格式：{{"styles": ["风格版本1", "风格版本2", ...]}}
"""
            try:
                agent = Agent(
                    self.model,
                    system_prompt="你是一位多风格文案专家，能同一内容写出截然不同的风格。",
                    output_type=StyleVariantsOutput,
                )
                result = agent.run_sync(prompt)
                return result.output.styles[:count]
            except Exception as e:
                print(f"[ABTest] 生成风格变体失败: {e}")
                return []

        return []

    def list_variants(self, task_id: str) -> List[ABTestVariant]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM ab_test_variants WHERE task_id = ? ORDER BY created_at DESC",
            (task_id,),
        ).fetchall()
        conn.close()
        return [_row_to_variant(r) for r in rows]

    def record_result(self, variant_id: str, metrics_id: str) -> bool:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE ab_test_variants SET metrics_id = ?, status = ? WHERE id = ?",
            (metrics_id, "result_imported", variant_id),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    def analyze_results(self, task_id: str) -> dict:
        """分析某个 task 下的所有变体表现，返回最优版本"""
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT av.id, av.variant_type, av.variant_content, av.metrics_id,
                   cm.reads, cm.likes, cm.shares, cm.comments, cm.collects
            FROM ab_test_variants av
            LEFT JOIN content_metrics cm ON cm.id = av.metrics_id
            WHERE av.task_id = ?
            """,
            (task_id,),
        ).fetchall()
        conn.close()

        if not rows:
            return {"best_variant_id": None, "best_score": 0, "all_scores": {}}

        scores = {}
        best_id = None
        best_score = -1
        for row in rows:
            score = (
                (row["reads"] or 0)
                + (row["likes"] or 0) * 2
                + (row["shares"] or 0) * 3
                + (row["comments"] or 0) * 2
                + (row["collects"] or 0) * 2
            )
            scores[row["id"]] = {
                "variant_type": row["variant_type"],
                "variant_content": row["variant_content"],
                "score": score,
            }
            if score > best_score:
                best_score = score
                best_id = row["id"]

        return {
            "best_variant_id": best_id,
            "best_score": best_score,
            "all_scores": scores,
        }


def _row_to_variant(row) -> ABTestVariant:
    return ABTestVariant(
        id=row["id"],
        task_id=row["task_id"],
        platform=row["platform"],
        variant_type=row["variant_type"],
        variant_content=row["variant_content"] or "",
        status=row["status"],
        metrics_id=row["metrics_id"],
        created_at=row["created_at"],
    )
