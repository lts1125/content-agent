#!/usr/bin/env python3
"""
Content Agent - PyInstaller 打包脚本

将 Web UI 打包为 macOS 桌面应用 (.app)

使用方法:
    cd ~/content-agent
    source .venv/bin/activate
    python scripts/build_app.py

输出:
    dist/ContentAgent.app  (可双击运行的 macOS 应用)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"

# 清理旧的构建产物
print("🔧 清理旧的构建产物...")
for d in [BUILD_DIR, DIST_DIR]:
    if d.exists():
        shutil.rmtree(d)

# 确保输出目录存在
DIST_DIR.mkdir(exist_ok=True)

# PyInstaller 参数
# 注: --windowed 表示 GUI 应用（不显示终端窗口）
# --onefile 会打成单文件，但启动慢；这里用 --onedir 更适合 Gradio 应用
args = [
    sys.executable,
    "-m", "PyInstaller",
    "--name", "ContentAgent",
    "--windowed",  # GUI 应用，无终端窗口
    "--onedir",    # 单目录模式，启动更快
    "--clean",     # 每次重新构建
    "--noconfirm", # 不提示覆盖
    # 收集 Gradio 前端资源
    "--collect-all", "gradio",
    "--collect-all", "gradio_client",
    # 收集其他可能带数据文件的依赖
    "--collect-all", "pydantic_ai",
    "--collect-all", "ddgs",
    "--collect-all", "docx",  # python-docx 整体打包
    # 复制包 metadata（importlib.metadata 需要）
    "--copy-metadata", "genai_prices",
    "--copy-metadata", "pydantic_ai",
    # 隐藏导入（动态导入的模块）
    "--hidden-import", "content_agent.agent_core",
    "--hidden-import", "content_agent.quality_checker",
    "--hidden-import", "content_agent.research",
    "--hidden-import", "content_agent.html_renderer",
    "--hidden-import", "content_agent.docx_exporter",
    "--hidden-import", "requests",
    "--hidden-import", "dotenv",
    "--hidden-import", "docx",
    "--hidden-import", "docx.shared",
    "--hidden-import", "docx.enum.text",
    "--hidden-import", "docx.oxml.ns",
    "--hidden-import", "docx.oxml",
    "--hidden-import", "docx.styles",
    "--hidden-import", "docx.table",
    "--hidden-import", "docx.text",
    "--hidden-import", "docx.enum",
    "--hidden-import", "docx.oxml.table",
    "--hidden-import", "docx.oxml.text",
    # 添加 content_agent 包（确保模块被包含）
    "--add-data", f"{PROJECT_ROOT}/content_agent:content_agent",
    # 入口文件
    str(PROJECT_ROOT / "web_ui.py"),
]

print("🚀 开始打包 ContentAgent...")
print(f"   项目根目录: {PROJECT_ROOT}")
print(f"   输出目录: {DIST_DIR}")
print()

result = subprocess.run(args, cwd=PROJECT_ROOT)

if result.returncode != 0:
    print("❌ 打包失败")
    sys.exit(1)

# 打包后处理
APP_PATH = DIST_DIR / "ContentAgent.app"
CONTENTS = APP_PATH / "Contents"
MACOS = CONTENTS / "MacOS"
RESOURCES = CONTENTS / "Resources"

print(f"\n✅ 打包完成: {APP_PATH}")
print(f"   应用大小: {sum(f.stat().st_size for f in APP_PATH.rglob('*') if f.is_file()) / 1024 / 1024:.1f} MB")

# 创建启动脚本（可选：打开浏览器）
launcher_script = MACOS / "ContentAgent"
print(f"\n📋 启动脚本: {launcher_script}")

print("""
使用说明:
1. 双击 dist/ContentAgent.app 即可启动
2. 首次启动会在 ~/Library/Application Support/ContentAgent/ 创建 .env 配置文件
3. 在页面顶部「模型配置」中填写 API Key 即可使用

注意: 第一次启动可能稍慢（需要解压资源），后续启动会加快。
""")
