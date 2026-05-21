"""
automation/ — Agent 化自动运行层

P0: Vault 监听 → 自动触发 → 待发队列 + 风格画像
"""

from automation.vault_watcher import VaultWatcher
from automation.agent_controller import AgentController
from automation.publish_queue import PublishQueue, QueueItem
from automation.style_profile import StyleProfile, StyleSample

__all__ = [
    "VaultWatcher",
    "AgentController",
    "PublishQueue",
    "QueueItem",
    "StyleProfile",
    "StyleSample",
]
