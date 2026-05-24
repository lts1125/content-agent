"""
稀土掘金热榜源 — 抓取掘金技术热榜

API: https://api.juejin.cn/content_api/v1/content/article_rank?category_id=1&type=hot
"""

import json
from typing import List

from content_agent.trend_watcher.base import TrendItem, TrendSource


class JuejinHotSource(TrendSource):
    """稀土掘金热榜抓取器"""

    API_URL = "https://api.juejin.cn/content_api/v1/content/article_rank"

    @property
    def name(self) -> str:
        return "juejin"

    def fetch(self) -> List[TrendItem]:
        """抓取掘金热榜"""
        try:
            import urllib.request
            # category_id=1 是后端，category_id=6809637769959178254 是 AI
            # 先抓综合热榜
            url = f"{self.API_URL}?category_id=1&type=hot"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                    "Referer": "https://juejin.cn/",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[JuejinHot] API 请求失败: {e}")
            return []

        return self._parse_json(data)

    def _parse_json(self, data: dict) -> List[TrendItem]:
        """解析掘金热榜 JSON"""
        trends = []
        items = data.get("data", [])

        for idx, item in enumerate(items):
            content = item.get("content", {})
            title = content.get("title", "")
            if not title:
                continue

            # 热度
            view_count = content.get("view_count", 0)
            like_count = content.get("like_count", 0)
            heat = f"{like_count}赞"

            # 链接
            content_id = content.get("content_id", "")
            url = f"https://juejin.cn/post/{content_id}" if content_id else ""

            trends.append(TrendItem(
                rank=idx + 1,
                title=title,
                url=url,
                heat=heat,
                source=self.name,
            ))

        return trends


def demo():
    """运行 demo"""
    print("=" * 60)
    print("稀土掘金热榜抓取 Demo")
    print("=" * 60)

    source = JuejinHotSource()
    trends = source.fetch()

    if not trends:
        print("未获取到热榜数据")
        return

    print(f"\n共获取 {len(trends)} 条热榜:\n")
    for item in trends[:15]:
        heat_str = f"({item.heat})" if item.heat else ""
        print(f"  {item.rank:2d}. {item.title} {heat_str}")

    # 关键词匹配示例
    keywords = ["AI", "人工智能", "大模型", "Agent", "ChatGPT", "LLM"]
    matched = source.filter_by_keywords(trends, keywords)

    print(f"\n关键词匹配 ({', '.join(keywords)}):")
    if matched:
        for item in matched:
            print(f"  * {item.rank:2d}. {item.title}")
    else:
        print("  无匹配项")


if __name__ == "__main__":
    demo()
