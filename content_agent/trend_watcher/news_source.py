"""
实时科技新闻源

抓取中英文科技新闻，返回结构化内容。
"""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional

import requests

from content_agent.trend_watcher.base import TrendItem, TrendSource


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    summary: str
    url: str
    source: str
    published: str
    language: str  # zh / en


class NewsSource(TrendSource):
    """实时科技新闻源"""

    @property
    def name(self) -> str:
        return "news"

    # RSS 源配置
    RSS_FEEDS = {
        # 中文
        "36kr": {
            "url": "https://36kr.com/feed",
            "language": "zh",
        },
        "机器之心": {
            "url": "https://www.jiqizhixin.com/rss",
            "language": "zh",
        },
        "量子位": {
            "url": "https://www.qbitai.com/feed",
            "language": "zh",
        },
        "IT之家": {
            "url": "https://www.ithome.com/rss/",
            "language": "zh",
        },
        # 英文
        "TechCrunch": {
            "url": "https://techcrunch.com/feed/",
            "language": "en",
        },
        "TheVerge": {
            "url": "https://www.theverge.com/rss/index.xml",
            "language": "en",
        },
        "ArsTechnica": {
            "url": "https://feeds.arstechnica.com/arstechnica/index",
            "language": "en",
        },
    }

    def fetch(self, limit: int = 20) -> List[TrendItem]:
        """抓取新闻"""
        all_items = []

        for source_name, config in self.RSS_FEEDS.items():
            try:
                items = self._fetch_rss(
                    config["url"],
                    source_name,
                    config["language"],
                    limit=limit,
                )
                all_items.extend(items)
            except Exception as e:
                print(f"[NewsSource] {source_name} 抓取失败: {e}")

        # 去重后返回
        seen = set()
        unique_items = []
        for item in all_items:
            if item.title not in seen:
                seen.add(item.title)
                unique_items.append(item)
        return unique_items[:limit]

    def _fetch_rss(self, url: str, source: str, language: str, limit: int) -> List[TrendItem]:
        """抓取单个 RSS 源"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        # 解析 RSS（处理编码问题）
        content = resp.content
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            # 尝试用 feedparser 风格解析
            return self._parse_rss_loose(content, source, language, limit)

        # 处理不同 RSS 格式
        items = []
        for item in root.findall(".//item")[:limit]:
            title = self._get_text(item, "title")
            link = self._get_text(item, "link")
            desc = self._get_text(item, "description")
            pub_date = self._get_text(item, "pubDate")

            # 清理 HTML 标签
            summary = self._strip_html(desc)
            if len(summary) > 300:
                summary = summary[:297] + "..."

            if title and link:
                items.append(TrendItem(
                    title=title,
                    url=link,
                    source=f"news_{source}",
                    summary=summary,
                    language=language,
                ))

        return items

    def _parse_rss_loose(self, content: bytes, source: str, language: str, limit: int) -> List[TrendItem]:
        """宽松解析 RSS（处理格式不规范的源）"""
        text = content.decode('utf-8', errors='ignore')
        items = []

        # 用正则提取 item
        import re
        item_pattern = r'<item>(.*?)</item>'
        title_pattern = r'<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>'
        link_pattern = r'<link>(.*?)</link>'
        desc_pattern = r'<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>'

        matches = list(re.finditer(item_pattern, text, re.DOTALL))
        for match in matches[:limit]:
            item_text = match.group(1)

            title_match = re.search(title_pattern, item_text)
            title = title_match.group(1) or title_match.group(2) if title_match else ""

            link_match = re.search(link_pattern, item_text)
            link = link_match.group(1) if link_match else ""

            desc_match = re.search(desc_pattern, item_text)
            desc = desc_match.group(1) or desc_match.group(2) if desc_match else ""

            if title and link:
                summary = self._strip_html(desc)
                if len(summary) > 300:
                    summary = summary[:297] + "..."
                items.append(TrendItem(
                    title=title.strip(),
                    url=link.strip(),
                    source=f"news_{source}",
                    summary=summary,
                    language=language,
                ))

        return items

    @staticmethod
    def _get_text(parent: ET.Element, tag: str) -> str:
        """获取子元素文本"""
        elem = parent.find(tag)
        return elem.text.strip() if elem is not None and elem.text else ""

    @staticmethod
    def _strip_html(text: str) -> str:
        """去除 HTML 标签"""
        if not text:
            return ""
        # 简单替换常见标签
        text = re.sub(r'<[^>]+>', '', text)
        # 解码 HTML 实体
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&amp;', '&').replace('&quot;', '"')
        return text.strip()

    def translate_to_chinese(self, items: List[TrendItem]) -> List[TrendItem]:
        """将英文新闻翻译成中文"""
        import os
        from pydantic_ai import Agent

        model = os.getenv("MODEL_PROVIDER", "deepseek")
        agent = Agent(
            model,
            system_prompt="""你是一位科技新闻翻译专家。

任务：将英文科技新闻翻译成中文摘要。

要求：
1. 标题翻译为中文，保留关键英文术语（如 GPT-5、OpenAI）
2. 摘要翻译为中文，简洁明了
3. 保持新闻的客观性和准确性
4. 输出格式：{"title": "中文标题", "summary": "中文摘要"}""",
        )

        translated = []
        for item in items:
            if item.language == "zh":
                translated.append(item)
                continue

            try:
                result = agent.run_sync(
                    f"标题: {item.title}\n摘要: {item.summary}\n\n请翻译成中文，返回 JSON 格式。"
                )
                data = json.loads(result.output)
                translated.append(TrendItem(
                    title=data.get("title", item.title),
                    url=item.url,
                    source=item.source,
                    summary=data.get("summary", item.summary),
                    language="zh",
                ))
            except Exception as e:
                print(f"[NewsSource] 翻译失败: {e}")
                # 翻译失败保留原文
                translated.append(item)

        return translated


def demo():
    """运行 demo"""
    source = NewsSource()
    print("=" * 60)
    print("实时科技新闻抓取")
    print("=" * 60)

    items = source.fetch(limit=10)
    print(f"\n抓取到 {len(items)} 条新闻")

    # 翻译英文
    items = source.translate_to_chinese(items)

    for item in items[:5]:
        print(f"\n[{item.source}] {item.title}")
        print(f"  摘要: {item.summary[:100]}...")
        print(f"  链接: {item.url}")


if __name__ == "__main__":
    demo()
