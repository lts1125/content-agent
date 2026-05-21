"""
automation/ — Agent 化自动运行层

P0: Vault 监听 → 自动触发 → 待发队列 + 风格画像
P1: 数据回流分析 + 自动选题 + A/B 测试框架
"""

from automation.vault_watcher import VaultWatcher
from automation.agent_controller import AgentController
from automation.publish_queue import PublishQueue, QueueItem
from automation.style_profile import StyleProfile, StyleSample
from automation.feedback_agent import FeedbackAgent, ContentMetrics, StyleProfileRecord
from automation.topic_picker import TopicPicker
from automation.ab_test_framework import ABTestFramework, ABTestVariant

__all__ = [
    "VaultWatcher",
    "AgentController",
    "PublishQueue",
    "QueueItem",
    "StyleProfile",
    "StyleSample",
    "FeedbackAgent",
    "ContentMetrics",
    "StyleProfileRecord",
    "TopicPicker",
    "ABTestFramework",
    "ABTestVariant",
]
