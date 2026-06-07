# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 文件 — 将 content-agent 打包为 Windows 独立 exe

使用方法（在 Windows 上执行）：
    pip install pyinstaller
    pyinstaller scripts/build-exe.spec --clean

输出：dist/ContentAgent/ContentAgent.exe
"""

import sys
from pathlib import Path

# 确保能找到项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ===== 配置 =====
ENTRY_POINT = str(PROJECT_ROOT / "chat_ui.py")
APP_NAME = "ContentAgent"
ICON_FILE = None  # 如有 .ico 图标可填写路径

# 分析并收集所有需要的模块
a = Analysis(
    [ENTRY_POINT],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # 将 bin/ 目录（node.exe + kuaifa 依赖）打包进去
        (str(PROJECT_ROOT / "bin"), "bin"),
        # 环境变量模板
        (str(PROJECT_ROOT / ".env.example"), "."),
        # Gradio 静态资源（必需，否则界面无法加载）
        (str(Path(sys.executable).parent / "Lib" / "site-packages" / "gradio" / "templates"), "gradio/templates"),
        (str(Path(sys.executable).parent / "Lib" / "site-packages" / "gradio" / "client" / "css"), "gradio/client/css"),
    ],
    hiddenimports=[
        # Gradio 相关
        "gradio",
        "gradio.components",
        "gradio.themes",
        "gradio.themes.utils",
        "gradio.themes.base",
        # FastEmbed / ONNX
        "fastembed",
        "fastembed.text",
        "onnxruntime",
        # 其他常见隐藏导入
        "dotenv",
        "pydantic",
        "pydantic.deprecated.decorator",
        "tiktoken",
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
        # 快速嵌入模型
        "fastembed.common.onnx_model",
        "fastembed.common.model_management",
        "fastembed.text.text_embedding",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除巨型依赖，减小体积
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "tensorboard",
        "matplotlib",
        "plotly",
        "scipy",
        "pandas",
        "sklearn",
        "pytest",
        "unittest",
        "pdb",
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,  # False = 将资源打包进 archive，启动更快
)

# 过滤掉 .pyc 缓存和无用的测试文件
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # 使用 UPX 压缩，减小体积
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # True = 显示控制台窗口，方便看日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE,
)
