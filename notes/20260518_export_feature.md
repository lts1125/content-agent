# 一键导出功能实现笔记

## 背景/需求

Roadmap P1-7：用户生成三平台文案后，需要把结果保存到本地。纯文本复制不够，需要支持：
- Markdown 导出（带 frontmatter，方便导入 Obsidian/Notion）
- Word 导出（给客户/编辑看，或做排版微调）

## 设计思路

在每个平台输出 Tab 内添加导出按钮行，点击后生成临时文件并提供下载：
- Markdown：`.md` 文件，包含 YAML frontmatter（title / date / platform）
- Word：`.docx` 文件，保留段落结构，标题居中，1.5 倍行距

不依赖外部存储，全部用 `tempfile.mkstemp` 生成临时文件，Gradio `gr.File` 组件提供下载。

## 核心实现

### 1. 导出函数（web_ui.py）

```python
def export_markdown(platform: str, content: str):
    """导出指定平台文案为 Markdown 文件"""
    if not content or content.startswith("（未选择此平台）") or content.startswith("❌"):
        return gr.update(value=None, visible=False), f"⚠️ {platform} 无内容可导出"

    fd, path = tempfile.mkstemp(suffix=f"_{platform}.md", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {platform}文案\ndate: {datetime.now().isoformat()}\nplatform: {platform}\n---\n\n")
        f.write(content)
    return gr.update(value=path, visible=True), f"✅ {platform} Markdown 已就绪，点击下载"


def export_word(platform: str, content: str):
    """导出指定平台文案为 Word 文件"""
    if not content or content.startswith("（未选择此平台）") or content.startswith("❌"):
        return gr.update(value=None, visible=False), f"⚠️ {platform} 无内容可导出"

    try:
        from docx import Document
    except ImportError:
        return gr.update(value=None, visible=False), "⚠️ 未安装 python-docx，请运行: pip install python-docx"

    fd, path = tempfile.mkstemp(suffix=f"_{platform}.docx")
    os.close(fd)

    doc = Document()
    doc.add_heading(f"{platform}文案", level=1).alignment = 1
    for line in content.split("\n"):
## 核心实现

### 1. 导出函数（web_ui.py）

Markdown 导出：

```python
def export_markdown(platform: str, content: str):
    """导出指定平台文案为 Markdown 文件"""
    ...
```

Word 导出（新版，精美排版）：

```python
def export_word(platform: str, content: str):
    from content_agent.docx_exporter import render_markdown_to_docx
    path = render_markdown_to_docx(content, title=f"{platform}文案")
    ...
```

### 2. 精美 Word 排版引擎（content_agent/docx_exporter.py）

新增独立模块 `docx_exporter.py`，专门处理 Markdown → 精美 Word 转换：

- **标题识别**：`#` `、`##` `、`###` → Heading 1/2/3，字号递减，加粗
- **列表**：`-` `*` `+` → 无序列表；`1.` → 有序列表，带缩进
- **代码块**：` ``` ` → 表格容器+浅灰背景+等宽字体 Courier New
- **行内格式**：`**加粗**` `、`*斜体*` `、``代码`` `、`[链接]()` 全部支持
- **引用块**：`>` → 左缩进+灰色斜体
- **分隔线**：`---` → 居中虚线
- **首行缩进**：正文段落自动首行缩进 2 字符
- **页面边距**：A4 标准边距，1.5 倍行距
- **页脚**：自动添加"由 Content Agent 生成 · 时间"

样式详情：

| 元素 | 字体 | 字号 | 颜色 | 其他 |
|--------|------|------|------|------|
| 文档标题 | Arial | 20pt | 黑色 | 居中 |
| Heading 1 | Arial | 18pt | 黑色 | 加粗，段前 14pt |
| Heading 2 | Arial | 15pt | 黑色 | 加粗，段前 10pt |
| 正文 | Arial | 11pt | 黑色 | 1.5倍行距，首行缩进 |
| 代码块 | Courier New | 9pt | #333 | 浅灰背景 F8F8F8 |
| 行内代码 | Courier New | 9.5pt | 黑色 | 浅灰背景 F0F0F0 |
| 链接 | Arial | 11pt | #0066CC | 下划线 |
| 引用 | Arial | 11pt | #666666 | 斜体，左缩进 0.8cm |

### 3. UI 布局

每个平台 Tab 添加导出按钮行：

```python
with gr.Row():
    export_md_xhs_btn = gr.Button("📥 导出 Markdown", size="sm")
    export_docx_xhs_btn = gr.Button("📄 导出 Word", size="sm")
xiaohongshu_download = gr.File(label="下载文件", visible=False)
```

## 踩坑记录

1. **Gradio `gr.File` 的可见性控制** — 初始 `visible=False`，导出成功后 `gr.update(value=path, visible=True)`。如果直接返回字符串路径给一个隐藏的 File 组件，组件不会自动显示。

2. **Word 导出的临时文件句柄** — `tempfile.mkstemp` 返回的是文件描述符 + 路径，需要用 `os.close(fd)` 先关闭描述符，否则 `doc.save(path)` 可能报权限错误（Windows 上尤其明显）。

3. **python-docx 是可选依赖** — 不强制安装，未安装时给出友好提示，不影响其他功能。

4. **python-docx 中文字体回退** — 需要同时设置 `run.font.name` 和 `run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)`，否则中文会显示为异常字体。

5. **Markdown 解析的复杂度** — 不使用额外依赖，用正则逐行解析。支持常见元素（标题、列表、代码块、引用、行内格式），足够覆盖 content-agent 生成的三平台文案结构。

6. **PyInstaller 打包新模块** — 新增 `content_agent/docx_exporter.py` 后，需在 `build_app.py` 补充 `--hidden-import content_agent.docx_exporter`，以及更多 `docx.*` 的子模块 hidden-import，否则动态导入会在打包后失败。

7. **`Run` 对象没有 `get_or_add_rPr`** — python-docx 中 `Run` 对象本身没有 `get_or_add_rPr()` 方法，必须通过 `run._element.get_or_add_rPr()` 访问底层 XML 元素。同理，设置 `rFonts` 时也要用 `rPr.get_or_add_rFonts()` 避免 `rPr` 为 None 的情况。

## 使用方法

```bash
# 安装 Word 导出依赖（可选）
pip install python-docx

# 启动 Web UI
python web_ui.py
```

在页面中：
1. 生成三平台文案
2. 切换到对应平台 Tab
3. 点击「📥 导出 Markdown」或「📄 导出 Word」
4. 下方出现下载组件，点击即可保存到本地

## 下一步

P1 下一项：**标签/话题推荐**（P1-9）
