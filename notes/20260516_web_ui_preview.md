# Web UI 实时预览 HTML 卡片

## 背景/需求

Roadmap P0-1：在 Web UI 中嵌入 HTML 卡片预览，让用户看到生成后的视觉效果，而不仅仅是文本。

## 设计思路

- 利用现有的 `html_renderer.py` 中的 `XiaohongshuRenderer`，在生成文案后同步生成 HTML 卡片
- 在小红书 Tab 中上下布局：上部 Textbox（可编辑复制）+ 下部 `gr.HTML`（视觉预览）
- 使用 `tempfile.TemporaryDirectory()` 作为临时输出目录，避免污染正式输出目录
- 其他平台（公众号/抖音）的 HTML 卡片渲染器暂未实现，后续补充

## 核心代码

### web_ui.py 修改

```python
# 导入
from content_agent.html_renderer import XiaohongshuRenderer

# generate_content() 中生成 HTML 预览
xiaohongshu_html = ""
if "xiaohongshu" in enabled and xiaohongshu_text:
    try:
        renderer = XiaohongshuRenderer()
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = renderer.render(xiaohongshu_text, tmpdir)
            with open(html_path, "r", encoding="utf-8") as f:
                xiaohongshu_html = f.read()
    except Exception as e:
        print(f"HTML 预览生成失败: {e}")

# 返回值增加 xiaohongshu_html
return xiaohongshu_text, gongzhonghao_text, douyin_text, xiaohongshu_html, status

# 界面布局
with gr.TabItem("📱 小红书"):
    xiaohongshu_output = gr.Textbox(...)
    xiaohongshu_preview = gr.HTML()  # 卡片预览区域
```

## 踩坑记录

1. **gr.HTML 不支持 label 参数** — Gradio 4.44.1 的 `gr.HTML` 组件没有 `label` 参数，传入后被忽略，后去掉
2. **返回值必须一一对应** — `generate_btn.click(outputs=[...])` 的 outputs 列表必须与 `generate_content()` 返回值数量一致，否则绑定失败

## 使用方法

生成文案后，小红书 Tab 下方自动显示 HTML 卡片预览。

## 下一步

- [ ] 公众号/抖音 的 HTML 卡片渲染器
- [ ] 其他平台的预览区域
