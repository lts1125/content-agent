"""
HTML 转 PNG - 用 Playwright 截图
"""

import os
from pathlib import Path
from typing import Optional


def html_to_png(
    html_path: str,
    output_path: Optional[str] = None,
    width: int = 1080,
    height: int = 1920,
    full_page: bool = True,
) -> str:
    """
    将 HTML 文件渲染为 PNG

    Args:
        html_path: HTML 文件路径
        output_path: 输出 PNG 路径（默认同名 .png）
        width: 视口宽度
        height: 视口高度
        full_page: 是否截取完整页面

    Returns:
        输出 PNG 路径
    """
    from playwright.sync_api import sync_playwright

    html_file = Path(html_path).resolve()
    if not html_file.exists():
        raise FileNotFoundError(f"HTML 文件不存在: {html_path}")

    if output_path is None:
        output_file = html_file.with_suffix(".png")
    else:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # 优先使用系统 Chrome，避免下载 Chromium
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(chrome_path):
            browser = p.chromium.launch(executable_path=chrome_path)
        else:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"file://{html_file}")

        # 等待字体和样式加载
        page.wait_for_timeout(1000)

        page.screenshot(path=str(output_file), full_page=full_page)
        browser.close()

    print(f"[Screenshot] 已保存: {output_file}")
    return str(output_file)


def demo():
    """测试截图"""
    # 找一个现有的 HTML 文件测试
    project_root = Path(__file__).resolve().parent.parent
    test_html = str(project_root / "output" / "douyin_demo" / "douyin_cards.html")
    if os.path.exists(test_html):
        result = html_to_png(test_html, width=1080, height=1920)
        print(f"截图完成: {result}")
    else:
        print(f"测试文件不存在: {test_html}")


if __name__ == "__main__":
    demo()
