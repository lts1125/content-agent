"""
知乎热榜源 — 抓取知乎热榜

API: https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total
"""

import json
from typing import List

from content_agent.trend_watcher.base import TrendItem, TrendSource


class ZhihuHotSource(TrendSource):
    """知乎热榜抓取器"""

    API_URL = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"

    @property
    def name(self) -> str:
        return "zhihu"

    def fetch(self) -> List[TrendItem]:
        """
        抓取知乎热榜。
        
        注意：知乎 API 需要登录态 Cookie，默认返回空列表。
        如需启用，请设置 ZHIHU_COOKIE 环境变量。
        """
        import os
        cookie = os.getenv("ZHIHU_COOKIE", "")
        if not cookie:
            print("[ZhihuHot] 未设置 ZHIHU_COOKIE，跳过知乎热榜")
            return []

        try:
            import urllib.request
            req = urllib.request.Request(
                self.API_URL,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                    "Referer": "https://www.zhihu.com/",
                    "Cookie": cookie,
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[ZhihuHot] API 请求失败: {e}")
            return []

        return self._parse_json(data)

    def _parse_json(self, data: dict) -> List[TrendItem]:
        """解析知乎热榜 JSON"""
        trends = []
        items = data.get("data", [])

        for idx, item in enumerate(items):
            card = item.get("target", {})
            title = card.get("title", "")
            if not title:
                continue

            # 热度指标：answer_count + follower_count 综合
            answer_count = card.get("answer_count", 0)
            follower_count = card.get("follower_count", 0)
            heat = f"{answer_count}回答"

            # 链接
            question_id = card.get("id", "")
            url = f"https://www.zhihu.com/question/{question_id}" if question_id else ""

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
    print("知乎热榜抓取 Demo")
    print("=" * 60)

    source = ZhihuHotSource()
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
