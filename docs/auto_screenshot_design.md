# 自动截图设计文档

> 用 Playwright 将 HTML 渲染为 PNG
> 时间：2026-05-25

---

## 1. 目标

- 抖音 HTML 卡片自动生成 PNG
- 支持自定义尺寸（1080×1920 竖屏）
- 接入 TopicExecutor，生成后自动截图

## 2. 技术选型

| 方案 | 选择 | 原因 |
|------|------|------|
| Playwright | 是 | 功能全，支持现代 CSS，截图质量高 |
| Selenium | 否 | 更慢更复杂 |
| wkhtmltoimage | 否 | 不支持现代 CSS |

## 3. 实现步骤

1. 安装依赖：`pip install playwright && playwright install chromium`
2. 截图模块：`content_agent/screenshot.py`
3. 接入 TopicExecutor：生成 HTML 后自动调用
4. CLI 命令：`python main.py --screenshot html_path`

## 4. 接口设计

```python
def html_to_png(
    html_path: str,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    full_page: bool = True,
) -> str:
    """HTML 转 PNG"""
```

## 5. 接入点

```
TopicExecutor._execute_douyin()
    -> DouyinRenderer.render()
    -> html_to_png()  # 新增
    -> 保存 PNG 到 output/douyin/
```
