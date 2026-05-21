"""
重试策略 (Retry Policy)

指数退避 + 关键词判断，用于发布失败后的自动重试。
"""

import random


class RetryPolicy:
    def __init__(self, max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def should_retry(self, error: str, attempt: int) -> bool:
        retryable_keywords = [
            "timeout", "connection", "network", "rate limit",
            "too many requests", "temporarily", "unavailable",
        ]
        non_retryable = [
            "blocked", "banned", "forbidden", "invalid",
            "rejected", "content violation",
        ]
        e_lower = error.lower()
        if any(k in e_lower for k in non_retryable):
            return False
        return attempt < self.max_retries and any(k in e_lower for k in retryable_keywords)

    def get_delay(self, attempt: int) -> float:
        delay = self.base_delay * (2 ** attempt)
        jitter = random.uniform(0, 1)
        return min(delay + jitter, self.max_delay)
