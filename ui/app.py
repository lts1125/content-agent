#!/usr/bin/env python3
"""
ui/app.py — Gradio Web UI 新入口

Phase 0：目录结构已创建，各 Tab 独立模块已占位。
当前仍委托给 web_ui.py 的完整 demo，后续逐步将各 Tab 迁移到 ui/tabs/ 下。
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Phase 0 fallback：直接导入 web_ui.py 的 demo 实例和 launch 逻辑
# 注意：web_ui.py 末尾应定义了 demo Blocks 并调用 demo.launch()
# 为避免重复 launch，这里只做模块级导入，由本文件的 __main__ 控制
from web_ui import demo  # noqa: F401

if __name__ == "__main__":
    # web_ui.py 如果已经在导入时调用了 demo.launch()，这里需要调整
    # 暂时保持与旧入口行为一致
    import web_ui  # noqa: F401
