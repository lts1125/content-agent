"""
Feedback Agent — 数据回流分析 + 风格画像更新

接收用户导入的平台数据，关联已发布队列项，调用 LLM 分析高/低表现差异，
更新 style_profiles 表。
"""

import csv
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel
from pydantic_ai import Agent

from agents.store import _get_conn
from content_agent.agent_core import ModelConfig


@dataclass
class ContentMetrics:
    id: str
    queue_item_id: str
    platform: str
    reads: int = 0
    likes: int = 0
    shares: int = 0
    comments: int = 0
    collects: int = 0
    import_date: str = ""
    publish_date: str = ""


@dataclass
class StyleProfileRecord:
    id: str
    platform: str
    preferred_tone: str
    high_performing_patterns: List[str]
    avg_score: int
    sample_count: int
    created_at: str
    updated_at: str


class FeedbackAnalysisOutput(BaseModel):
    preferred_tone: str
    high_performing_patterns: List[str]


def _composite_score(m: ContentMetrics) -> int:
    return (
        m.reads + m.likes * 2 + m.shares * 3 + m.comments * 2 + m.collects * 2
    )


class FeedbackAgent:
    def __init__(self, model=None):
        if model is None:
            model, _ = ModelConfig.from_env()
        self.model = model

    def import_metrics(self, file_path: Path, platform: Optional[str] = None) -> dict:
        """导入平台数据（CSV 或 JSON），返回统计信息，并自动判断是否触发分析"""
        imported = 0
        errors = []

        if not file_path.exists():
            return {"imported": 0, "errors": [f"文件不存在: {file_path}"], "should_analyze": False}

        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            rows = self._parse_csv(file_path)
        elif suffix in (".json", ".jsonl"):
            rows = self._parse_json(file_path)
        else:
            return {"imported": 0, "errors": [f"不支持的文件格式: {suffix}"], "should_analyze": False}

        import_date = datetime.now().isoformat()
        conn = _get_conn()
        for row in rows:
            try:
                mid = f"metric_{uuid.uuid4().hex[:12]}"
                
                # 自动识别平台（如果未指定）
                pf = platform or row.get("platform", "")
                if not pf:
                    if "read_count" in row or "reads" in row:
                        pf = "gongzhonghao"
                    elif "collect_count" in row or "collects" in row:
                        pf = "xiaohongshu"
                    else:
                        pf = "unknown"
                
                reads = int(row.get("read_count") or row.get("reads") or 0)
                likes = int(row.get("like_count") or row.get("likes") or 0)
                shares = int(row.get("share_count") or row.get("shares") or 0)
                comments = int(row.get("comment_count") or row.get("comments") or 0)
                collects = int(row.get("collect_count") or row.get("collects") or 0)
                
                conn.execute(
                    """
                    INSERT INTO content_metrics
                    (id, queue_item_id, platform, reads, likes, shares, comments, collects, import_date, publish_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mid,
                        row.get("queue_item_id", ""),
                        pf,
                        reads,
                        likes,
                        shares,
                        comments,
                        collects,
                        import_date,
                        row.get("publish_date", ""),
                    ),
                )
                imported += 1
            except Exception as e:
                errors.append(str(e))
        conn.commit()
        conn.close()
        
        # 判断是否触发分析
        should_analyze = False
        if imported > 0 and platform:
            should_analyze = self._should_analyze(platform)
        
        return {"imported": imported, "errors": errors, "should_analyze": should_analyze}
    
    def _should_analyze(self, platform: str) -> bool:
        """判断是否应该触发分析"""
        conn = _get_conn()
        
        # 1. 检查样本数量
        count_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM content_metrics WHERE platform = ?",
            (platform,),
        ).fetchone()
        total_samples = count_row["cnt"] if count_row else 0
        
        if total_samples < 5:
            conn.close()
            print(f"[FeedbackAgent] 平台 '{platform}' 样本不足 ({total_samples} 条)，继续积累")
            return False
        
        # 2. 检查上次分析时间
        profile_row = conn.execute(
            "SELECT updated_at FROM style_profiles WHERE platform = ?",
            (platform,),
        ).fetchone()
        
        if profile_row and profile_row["updated_at"]:
            last_update = datetime.fromisoformat(profile_row["updated_at"])
            days_since = (datetime.now() - last_update).days
            if days_since < 7:
                # 3. 检查新数据占比
                new_count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM content_metrics WHERE platform = ? AND import_date > ?",
                    (platform, profile_row["updated_at"]),
                ).fetchone()["cnt"]
                new_ratio = new_count / total_samples if total_samples > 0 else 0
                
                if new_ratio < 0.3:
                    conn.close()
                    print(f"[FeedbackAgent] 平台 '{platform}' 新数据占比 {new_ratio:.1%}，不足 30%，跳过分析")
                    return False
        
        # 4. 检查表现差异
        if profile_row:
            avg_row = conn.execute(
                "SELECT AVG(reads + likes * 2 + shares * 3 + comments * 2 + collects * 2) as avg_score FROM content_metrics WHERE platform = ?",
                (platform,),
            ).fetchone()
            current_avg = avg_row["avg_score"] if avg_row and avg_row["avg_score"] else 0
            
            profile_avg = conn.execute(
                "SELECT avg_score FROM style_profiles WHERE platform = ?",
                (platform,),
            ).fetchone()["avg_score"]
            
            if profile_avg and profile_avg > 0:
                diff = abs(current_avg - profile_avg) / profile_avg
                if diff < 0.2:
                    conn.close()
                    print(f"[FeedbackAgent] 平台 '{platform}' 表现差异 {diff:.1%}，不足 20%，跳过分析")
                    return False
        
        conn.close()
        print(f"[FeedbackAgent] 平台 '{platform}' 满足分析条件，触发分析")
        return True

    @staticmethod
    def _parse_csv(file_path: Path) -> List[dict]:
        rows = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return rows

    @staticmethod
    def _parse_json(file_path: Path) -> List[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            if file_path.suffix.lower() == ".jsonl":
                rows = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rows.append(json.loads(line))
                return rows
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def analyze(self, platform: Optional[str] = None) -> List[StyleProfileRecord]:
        """分析反馈并更新风格画像。若 platform 为 None，分析所有平台。"""
        conn = _get_conn()
        if platform:
            rows = conn.execute(
                """
                SELECT pq.id as queue_id, pq.platform, pq.content,
                       cm.reads, cm.likes, cm.shares, cm.comments, cm.collects
                FROM publish_queue pq
                LEFT JOIN content_metrics cm ON cm.queue_item_id = pq.id
                WHERE pq.status = 'published' AND pq.platform = ?
                """,
                (platform,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT pq.id as queue_id, pq.platform, pq.content,
                       cm.reads, cm.likes, cm.shares, cm.comments, cm.collects
                FROM publish_queue pq
                LEFT JOIN content_metrics cm ON cm.queue_item_id = pq.id
                WHERE pq.status = 'published'
                """
            ).fetchall()
        conn.close()

        if not rows:
            return []

        # 构建 metrics 列表并计算综合分
        scored = []
        for row in rows:
            m = ContentMetrics(
                id="",
                queue_item_id=row["queue_id"],
                platform=row["platform"],
                reads=row["reads"] or 0,
                likes=row["likes"] or 0,
                shares=row["shares"] or 0,
                comments=row["comments"] or 0,
                collects=row["collects"] or 0,
            )
            scored.append((row["content"] or "", m, _composite_score(m)))

        if not scored:
            return []

        platforms = sorted(set(p.platform for _, p, _ in scored))
        target_platforms = [platform] if platform else platforms
        results = []
        now = datetime.now().isoformat()
        conn = _get_conn()

        for pf in target_platforms:
            pf_rows = [s for s in scored if s[1].platform == pf]
            if len(pf_rows) < 3:
                print(f"[FeedbackAgent] 平台 '{pf}' 样本不足 ({len(pf_rows)} 条)，跳过分析")
                continue
            pf_rows.sort(key=lambda x: x[2], reverse=True)
            top_n = max(1, len(pf_rows) // 3)
            bottom_n = max(1, len(pf_rows) // 3)
            pf_high = pf_rows[:top_n]
            pf_low = pf_rows[-bottom_n:]
            high_threshold = pf_high[-1][2] if pf_high else 0
            low_threshold = pf_low[0][2] if pf_low else 0

            pf_prompt = self._build_analysis_prompt(pf_high, pf_low, high_threshold, low_threshold)
            try:
                pf_analysis = self._call_llm(pf_prompt)
            except Exception as e:
                print(f"[FeedbackAgent] LLM 分析失败 [{pf}]: {e}")
                continue

            pf_avg = sum(s[2] for s in pf_rows) // len(pf_rows)
            sid = f"profile_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO style_profiles (id, platform, preferred_tone, high_performing_patterns, avg_score, sample_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform) DO UPDATE SET
                    preferred_tone=excluded.preferred_tone,
                    high_performing_patterns=excluded.high_performing_patterns,
                    avg_score=excluded.avg_score,
                    sample_count=excluded.sample_count,
                    updated_at=excluded.updated_at
                """,
                (
                    sid,
                    pf,
                    pf_analysis.preferred_tone,
                    json.dumps(pf_analysis.high_performing_patterns, ensure_ascii=False),
                    pf_avg,
                    len(pf_rows),
                    now,
                    now,
                ),
            )
            results.append(self.get_profile(pf))

        conn.commit()
        conn.close()
        return results

    @staticmethod
    def _build_analysis_prompt(
        high_performers: List[tuple], low_performers: List[tuple], high_threshold: int, low_threshold: int
    ) -> str:
        high_text = "\n\n".join(
            [f"【文案 {i+1}】（综合分: {s}）\n{content[:500]}" for i, (content, _, s) in enumerate(high_performers)]
        )
        low_text = "\n\n".join(
            [f"【文案 {i+1}】（综合分: {s}）\n{content[:500]}" for i, (content, _, s) in enumerate(low_performers)]
        )
        return f"""你是一位内容分析专家。请分析以下高表现和低表现文案的差异，输出风格画像。

【高表现文案】（综合分 >= {high_threshold}）
{high_text}

【低表现文案】（综合分 <= {low_threshold}）
{low_text}

请输出 JSON 格式：
{{"preferred_tone": "该平台高表现文案的共同语气特征（一句话描述）", "high_performing_patterns": ["模式1", "模式2", "模式3"]}}
"""

    def _call_llm(self, prompt: str) -> FeedbackAnalysisOutput:
        agent = Agent(
            self.model,
            system_prompt="你是一位专业的内容分析师，擅长从数据中发现内容规律。",
            output_type=FeedbackAnalysisOutput,
        )
        result = agent.run_sync(prompt)
        return result.output

    def get_profile(self, platform: str) -> Optional[StyleProfileRecord]:
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM style_profiles WHERE platform = ?", (platform,)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return StyleProfileRecord(
            id=row["id"],
            platform=row["platform"],
            preferred_tone=row["preferred_tone"] or "",
            high_performing_patterns=json.loads(row["high_performing_patterns"]) if row["high_performing_patterns"] else [],
            avg_score=row["avg_score"] or 0,
            sample_count=row["sample_count"] or 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
