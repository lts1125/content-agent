"""
微博热搜源 — 抓取微博热搜榜

注意：微博页面结构可能变化，需要定期维护选择器。
如果抓取失败，会返回空列表并打印错误。
"""

import json
import urllib.parse
from typing import List

from content_agent.trend_watcher.base import TrendItem, TrendSource


try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


class WeiboHotSource(TrendSource):
    """微博热搜榜抓取器"""

    URL = "https://s.weibo.com/top/summary?cate=realtimehot"

    @property
    def name(self) -> str:
        return "weibo"

    def fetch(self) -> List[TrendItem]:
        """
        抓取微博热搜榜。
        使用微博公开 JSON API，避免反爬。
        """
        api_url = "https://weibo.com/ajax/side/hotSearch"
        try:
            import urllib.request
            req = urllib.request.Request(
                api_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                    "Referer": "https://weibo.com/",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[WeiboHot] API 请求失败: {e}")
            return []

        return self._parse_json(data)

    def _parse_json(self, data: dict) -> List[TrendItem]:
        """解析微博热搜 JSON"""
        trends = []
        realtime = data.get("data", {}).get("realtime", [])

        for item in realtime:
            title = item.get("word") or item.get("note", "")
            if not title:
                continue

            rank = item.get("rank", 0)
            heat = item.get("raw_hot") or item.get("num", "")
            # flag: 0=普通, 1=新, 2=热, 3=爆
            flag_map = {"0": "", "1": "新", "2": "热", "3": "爆"}
            tag = flag_map.get(str(item.get("flag", "0")), "")
            # 构建搜索链接
            word_scheme = item.get("word_scheme", "")
            url = f"https://s.weibo.com/weibo?q={urllib.parse.quote(word_scheme or title)}"

            trends.append(TrendItem(
                rank=rank,
                title=title,
                url=url,
                heat=str(heat),
                tag=tag,
                source=self.name,
            ))

        return trends


def demo():
    """运行 demo，抓取并展示热搜"""
    print("=" * 60)
    print("微博热搜抓取 Demo")
    print("=" * 60)

    source = WeiboHotSource()
    trends = source.fetch()

    if not trends:
        print("未获取到热搜数据，可能页面结构已变更或网络受限")
        return

    print(f"\n共获取 {len(trends)} 条热搜:\n")
    for item in trends[:20]:
        tag_str = f"[{item.tag}]" if item.tag else ""
        heat_str = f"({item.heat})" if item.heat else ""
        print(f"  {item.rank:2d}. {item.title} {tag_str} {heat_str}")

    # 关键词匹配示例
    keywords = ["AI", "人工智能", "大模型", "Agent", "ChatGPT", "OpenAI"]
    matched = source.filter_by_keywords(trends, keywords)

    print(f"\n关键词匹配 ({', '.join(keywords)}):")
    if matched:
        for item in matched:
            print(f"  ✓ {item.rank:2d}. {item.title}")
    else:
        print("  无匹配项")


if __name__ == "__main__":
    demo()
