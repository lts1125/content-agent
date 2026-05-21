"""
小红书发布器 (半自动)

小红书无官方开放 API，P2 采用半自动方案：
格式化内容 → 打印发布指南 → 尝试打开浏览器。
"""

import webbrowser


class XiaohongshuPublisher:
    def publish(self, title: str, content: str, tags: str = "") -> dict:
        formatted = self._format_content(title, content, tags)
        print("\n📱 小红书发布指南")
        print("   请手动复制以下内容到小红书创作者平台: https://creator.xiaohongshu.com")
        print(f"\n{'='*40}")
        print(formatted)
        print(f"{'='*40}\n")

        try:
            webbrowser.open("https://creator.xiaohongshu.com")
        except Exception:
            pass

        return {
            "success": True,
            "message": "已生成发布指南",
            "manual": True,
            "details": formatted,
        }

    @staticmethod
    def _format_content(title: str, content: str, tags: str) -> str:
        lines = [f"标题: {title}", ""]
        lines.extend(content.splitlines())
        if tags:
            lines.extend(["", f"话题: {tags}"])
        return "\n".join(lines)
