# HTML 配图卡片渲染功能实现笔记

## 背景/需求

Roadmap P1-2：小红书需要配图才能发布。手动做图耗时，希望 Agent 能自动生成美观的配图卡片，用户只需截图即可直接发布。

## 设计思路

用纯 HTML + CSS 生成小红书风格的图文卡片，支持封面页 + 多页要点卡片。用户用浏览器打开后截图即可。

方案对比：
- **Pillow/PIL 绘图**：可控但代码冗长，排版复杂
- **HTML + CSS**：开发快、效果精美、可实时调整 ✅ 选用
- **调用外部设计 API**：成本高、有网络依赖

## 核心实现

### 1. XiaohongshuRenderer 类（html_renderer.py）

```python
class XiaohongshuRenderer:
    def render(self, title: str, content: str, tags: str = "") -> Tuple[str, List[str]]:
        """
        渲染小红书配图卡片
        返回: (完整 HTML 字符串, [封面页 HTML, 要点页1 HTML, ...])
        """
        points = self._extract_points(content)
        cover_html = self._render_cover(title, tags)
        point_pages = [self._render_point_card(i, p) for i, p in enumerate(points)]
        full_html = XIAOHONGSHU_TEMPLATE.format(
            cover=cover_html,
            point_cards="\n".join(point_pages),
        )
        return full_html, [cover_html] + point_pages
```

### 2. 封面页设计

- 尺寸：900x1200px（小红书 3:4 比例）
- 大标题 + emoji + 副标题
- 底部话题标签（粉色 pill 样式）
- 白色圆角卡片 + 阴影

### 3. 要点卡片设计

- 同样的 900x1200px 尺寸
- 顶部：编号圆圈 + 标题
- 中部：正文（保留换行和 emoji）
- 底部：页码指示器

### 4. CSS 关键样式

```css
.card {
    width: 900px;
    min-height: 1200px;
    background: #fff;
    border-radius: 32px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.10);
    padding: 70px 60px;
}
.cover-tag {
    background: #fff3f5;
    color: #ff2442;
    padding: 10px 24px;
    border-radius: 30px;
    font-size: 22px;
    font-weight: 600;
}
```

### 5. 与 Web UI 集成

Web UI 中新增 `xiaohongshu_preview` HTML 组件：
- 生成文案后自动渲染 HTML 预览
- 使用 `_scale_html()` 函数将 900px 宽度的卡片按比例缩放到容器宽度
- 用户可以直接在浏览器中截图

```python
def _scale_html(html: str, scale: float = 0.48) -> str:
    """将 HTML 中所有 px 值按比例缩放"""
    def replace_px(match):
        val = int(match.group(1))
        if val <= 3:
            return match.group(0)
        return f"{max(1, int(val * scale))}px"
    return re.sub(r'(\d+)px', replace_px, html)
```

### 6. 保存逻辑

生成的 HTML 文件保存到 `output/2026xxxxx/配图/` 目录下，与文案 Markdown 同目录。

## 踩坑记录

1. **浏览器截图的清晰度问题** — HTML 预览在浏览器中打开是 900px 宽度，但在 Web UI 的 Gradio HTML 组件中需要缩放。`_scale_html` 函数用正则替换所有 px 值，但要避免过度缩放小数值（如 border-radius: 3px）。

2. **emoji 在 HTML 中的渲染** — 大部分现代浏览器支持 emoji，但字体回退需要设置好。CSS 中指定了 `-apple-system` 等字体栈确保跨平台一致。

3. **内容过长时的分页** — 如果笔记内容很长，单张卡片放不下。目前方案是提取 3-5 个核心要点，每张卡片一个要点。如果内容太多，可能需要自动分页。

4. **Gradio 的 HTML 组件限制** — Gradio 的 `gr.HTML` 组件对复杂 CSS 支持有限，某些高级特性（如 backdrop-filter）可能不生效。因此样式尽量使用基础 CSS。

5. **中文排版细节** — 行高、字间距、段落间距需要反复微调，才能在手机上看起来舒服。

## 使用方法

CLI：
```bash
python main.py -i notes.md -p xiaohongshu
# 输出目录下会生成 配图/xiaohongshu_card.html
```

Web UI：
1. 生成文案后，在「小红书」Tab 下方直接看到 HTML 预览
2. 用浏览器打开 `output/日期/配图/xiaohongshu_card.html`
3. 逐页截图（Command+Shift+4 选区截图）
4. 直接上传到小红书发布

## 下一步

- 支持自动生成封面背景图（接入 AI 绘画 API）
- 支持更多配色主题
- 考虑导出为 PNG/PDF（用 headless browser 截图）
