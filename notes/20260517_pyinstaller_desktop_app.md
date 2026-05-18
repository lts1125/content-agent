# PyInstaller 打包桌面应用

## 背景/需求

纯小白用户不会用命令行 `python web_ui.py` 启动，希望做成双击就能打开的 macOS 桌面应用（.app）。

## 设计思路

- 使用 **PyInstaller** 将 Gradio Web UI 打包为 macOS `.app`
- 解决打包后的路径问题（`__file__` 指向只读 app bundle 内部）
- 配置文件放在用户可写目录 `~/Library/Application Support/ContentAgent/.env`
- 首次启动自动创建默认 .env 模板
- 保留 Web UI 页面内的模型配置功能，小白无需手动改文件

## 核心实现

### 1. 打包脚本 `scripts/build_app.py`

```python
PyInstaller 参数要点：
--windowed      # GUI 应用，无终端窗口
--onedir        # 单目录模式，启动更快
--collect-all gradio      # 收集 Gradio 前端资源
--collect-all pydantic_ai # 收集 pydantic_ai 数据文件
--collect-all ddgs        # 收集 DuckDuckGo 搜索数据
```

### 2. 打包后 .env 路径处理

```python
_IS_FROZEN = getattr(sys, "frozen", False)

if _IS_FROZEN:
    _APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "ContentAgent"
    _APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    ENV_PATH = _APP_SUPPORT_DIR / ".env"
else:
    ENV_PATH = Path(__file__).parent / ".env"
```

### 3. 首次启动自动创建默认配置

```python
def _ensure_default_env():
    if not ENV_PATH.exists():
        default_content = """# Content Agent - 环境变量配置
MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=
# TAVILY_API_KEY=
"""
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(default_content)
```

## 踩坑记录

1. **Gradio 静态文件必须显式收集** — `--collect-all gradio` 必不可少，否则前端页面白屏
2. **PyInstaller `--windowed` 模式下无终端** — 之前 `sys.exit(1)` 会导致应用直接退出且无提示，已改为页面内提示
3. **pydantic_ai 动态导入多** — 需要用 `--collect-all pydantic_ai` 收集所有子模块，否则会漏掉部分 provider 实现
4. **.env 路径** — 打包后 `__file__` 在 app bundle 内部只读，配置文件必须改到用户目录
5. **应用体积** — Gradio + 各种依赖导致 257MB，属于正常范围，后续可考虑 UPX 压缩
6. **新增依赖需要更新打包脚本** — 后续加入 python-docx 后，需在 `build_app.py` 中补充 `--collect-all docx` 和 `--hidden-import docx`、`docx.shared`、`docx.enum.text`，否则打包后无法导出 Word

## 使用方法

```bash
cd ~/content-agent
source .venv/bin/activate
python scripts/build_app.py
```

输出：`dist/ContentAgent.app`（双击即可启动）

## 验证结果

- ✅ 打包成功，大小 256.9 MB
- ✅ 双击启动后服务监听 localhost:7860
- ✅ Gradio 前端页面正常加载（HTTP 200）
- ✅ 首次启动自动创建 `~/Library/Application Support/ContentAgent/.env`
- ✅ 页面内「模型配置」可正常保存配置到上述路径

## 下一步

- [ ] 添加应用图标（`--icon` 参数 + Info.plist）
- [ ] 考虑签名（避免 macOS 安全警告）
- [ ] 测试 Windows 打包（`.exe`）
