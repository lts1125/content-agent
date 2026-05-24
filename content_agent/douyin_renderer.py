"""
抖音图文渲染器

将热点新闻/科技资讯渲染为 9:16 竖屏图文，适合抖音图文发布。
"""

import re
from pathlib import Path
from typing import List, Tuple


DOUYIN_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0a;
            font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 20px;
        }
        .card {
            width: 1080px;
            height: 1920px;
            background: #141414;
            border-radius: 24px;
            padding: 80px 60px;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
        }

        /* 封面 */
        .cover {
            background: #141414;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        .cover-tag {
            display: inline-block;
            background: #fe2c55;
            color: #fff;
            padding: 12px 32px;
            border-radius: 8px;
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 40px;
            letter-spacing: 2px;
        }
        .cover h1 {
            font-size: 72px;
            font-weight: 900;
            color: #fff;
            line-height: 1.2;
            margin-bottom: 40px;
        }
        .cover h1 span { color: #fe2c55; }
        .cover-sub {
            font-size: 32px;
            color: #888;
            line-height: 1.5;
        }
        .cover-footer {
            position: absolute;
            bottom: 60px;
            left: 0; right: 0;
            text-align: center;
            font-size: 24px;
            color: #444;
        }

        /* 要点卡片 */
        .point-card {
            background: #1a1a1a;
        }
        .point-card-header {
            display: flex;
            align-items: center;
            margin-bottom: 50px;
        }
        .point-num {
            width: 56px;
            height: 56px;
            background: #fe2c55;
            color: #fff;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            font-weight: 800;
            margin-right: 24px;
            flex-shrink: 0;
        }
        .point-title {
            font-size: 44px;
            font-weight: 800;
            color: #fff;
        }
        .point-items {
            display: flex;
            flex-direction: column;
            gap: 28px;
        }
        .point-item {
            display: flex;
            align-items: flex-start;
            gap: 20px;
        }
        .point-bullet {
            width: 10px;
            height: 10px;
            background: #fe2c55;
            border-radius: 50%;
            margin-top: 16px;
            flex-shrink: 0;
        }
        .point-text {
            font-size: 32px;
            line-height: 1.6;
            color: #ccc;
        }
        .point-text strong {
            color: #fe2c55;
            font-weight: 600;
        }

        /* 强调卡片 */
        .highlight-card {
            background: #fe2c55;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        .highlight-text {
            font-size: 52px;
            font-weight: 900;
            color: #fff;
            line-height: 1.4;
        }
        .highlight-sub {
            font-size: 28px;
            color: rgba(255,255,255,0.7);
            margin-top: 30px;
        }

        /* 金句卡片 */
        .quote-card {
            background: #141414;
            justify-content: center;
            align-items: center;
            text-align: center;
            border: 3px solid #333;
        }
        .quote-mark {
            font-size: 100px;
            color: #fe2c55;
            line-height: 1;
            margin-bottom: 20px;
            font-family: Georgia, serif;
        }
        .quote-text {
            font-size: 44px;
            font-weight: 700;
            color: #fff;
            line-height: 1.5;
            padding: 0 30px;
        }

        /* 互动卡片 */
        .cta-card {
            background: #1a1a1a;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        .cta-title {
            font-size: 44px;
            font-weight: 800;
            color: #fff;
            margin-bottom: 30px;
        }
        .cta-text {
            font-size: 28px;
            color: #888;
            line-height: 1.6;
            margin-bottom: 50px;
        }
        .cta-btn {
            background: #fe2c55;
            color: #fff;
            padding: 20px 60px;
            border-radius: 50px;
            font-size: 28px;
            font-weight: 700;
        }
    </style>
</head>
<body>
{CARDS}
</body>
</html>"""


def _smart_parse_news(content: str) -> Tuple[str, str, List[Tuple[str, List[str]]], str]:
    """
    解析热点新闻内容，返回 (标签, 标题, [(小节标题, 要点列表), ...], 金句)
    """
    lines = content.strip().split("\n")

    # 1. 找标签（第一行如果很短且带#或[]）
    tag = "科技前沿"
    title = "AI 行业最新动态"
    title_idx = 0

    for i, line in enumerate(lines[:5]):
        clean = line.strip()
        if clean.startswith("#") or clean.startswith("["):
            tag = clean.replace("#", "").replace("[", "").replace("]", "").strip()
            title_idx = i + 1
            break

    # 2. 找标题
    for i in range(title_idx, min(title_idx + 5, len(lines))):
        clean = lines[i].strip().replace("#", "").strip()
        if clean and len(clean) > 8 and len(clean) < 80:
            title = clean
            title_idx = i
            break

    # 3. 解析段落
    sections = []
    current_title = ""
    current_points = []

    i = title_idx + 1
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # 检测小节标题（严格：必须是 "数字. 文字" 格式，不能是列表项）
        is_header = False
        header_text = ""

        # 跳过列表项（以 - * • 开头）
        if line.startswith('-') or line.startswith('*') or line.startswith('•'):
            pass  # 不是标题，是列表项

        # 纯数字序号 + 文字，如 "1. 核心升级"
        elif (m := re.match(r'^(\d+)[\.\、\.]\s*(.+)', line)):
            is_header = True
            header_text = m.group(2).strip()

        # emoji 开头的短句
        elif re.match(r'^[\U0001F300-\U0001F9FF]\s*\S', line) and len(line) < 50:
            is_header = True
            header_text = re.sub(r'^[\U0001F300-\U0001F9FF]\s*', '', line).strip()

        # 纯文字短句，下一行是列表
        elif len(line) < 25 and i + 1 < len(lines) and re.match(r'^[-*•·]', lines[i + 1]):
            is_header = True
            header_text = line

        if is_header:
            if current_title and current_points:
                sections.append((current_title, current_points))
            current_title = header_text
            current_points = []
        else:
            clean = re.sub(r'^[-*•·\u2705\u274c]?\s*', '', line)
            clean = re.sub(r'^\d+[\.\、\.]\s*', '', clean).strip()
            if clean and len(clean) > 3:
                if len(clean) > 100:
                    clean = clean[:98] + "..."
                if current_title:
                    current_points.append(clean)

        i += 1

    if current_title and current_points:
        sections.append((current_title, current_points))

    # 限制最多 3 个 section
    if len(sections) > 3:
        merged = []
        for sec_title, sec_points in sections[2:]:
            merged.extend(sec_points)
        sections = sections[:2] + [("更多看点", merged)]

    # 兜底
    if not sections:
        all_points = []
        for line in lines[title_idx + 1:]:
            clean = re.sub(r'^[-*•·\u2705\u274c]\s*', '', line.strip()).strip()
            if clean and len(clean) > 5 and len(clean) < 100:
                all_points.append(clean)
        if all_points:
            sections = [("核心看点", all_points)]

    # 4. 提取金句
    quote = "科技改变生活，关注前沿动态。"
    candidates = []
    for line in lines:
        clean = line.strip()
        clean = re.sub(r'^[-*•·\u2705\u274c]\s*', '', clean)
        if 15 <= len(clean) <= 60:
            if any(w in clean for w in ["本质", "核心", "关键", "意味着", "标志着", "未来"]):
                candidates.append(clean)
    if candidates:
        quote = max(candidates, key=len)

    return tag, title, sections, quote


def _build_cover_card(tag: str, title: str) -> str:
    # 给标题里的关键词加红色
    title_colored = title
    for kw in ["AI", "GPT", "ChatGPT", "大模型", "科技", "突破", "发布", "开源"]:
        if kw in title and f'<span>{kw}</span>' not in title_colored:
            title_colored = title_colored.replace(kw, f'<span>{kw}</span>', 1)
            break

    return f"""
    <div class="card cover">
        <div class="cover-tag">{tag}</div>
        <h1>{title_colored}</h1>
        <div class="cover-sub">每日科技资讯 · 3分钟了解行业动态</div>
        <div class="cover-footer">@栖光实验室</div>
    </div>"""


def _build_point_card(index: int, title: str, points: List[str]) -> str:
    display_points = points[:4]
    items_html = "\n".join(
        f'<div class="point-item"><div class="point-bullet"></div><div class="point-text">{p}</div></div>'
        for p in display_points
    )
    return f"""
    <div class="card point-card">
        <div class="point-card-header">
            <div class="point-num">{index}</div>
            <div class="point-title">{title}</div>
        </div>
        <div class="point-items">
            {items_html}
        </div>
    </div>"""


def _build_highlight_card(text: str, sub: str = "") -> str:
    sub_html = f'<div class="highlight-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="card highlight-card">
        <div class="highlight-text">{text}</div>
        {sub_html}
    </div>"""


def _build_quote_card(quote: str) -> str:
    return f"""
    <div class="card quote-card">
        <div class="quote-mark">"</div>
        <div class="quote-text">{quote}</div>
    </div>"""


def _build_cta_card() -> str:
    return f"""
    <div class="card cta-card">
        <div class="cta-title">关注获取更多科技资讯</div>
        <div class="cta-text">每天3分钟<br>了解AI与科技行业最新动态</div>
        <div class="cta-btn">点赞 + 关注 ↓</div>
    </div>"""


class DouyinRenderer:
    """抖音图文渲染器：9:16 竖屏深色风格"""

    def render(self, content: str, output_dir: Path) -> str:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        tag, title, sections, quote = _smart_parse_news(content)

        cards = []

        # 1. 封面
        cards.append(_build_cover_card(tag, title))

        # 2. 内容卡片
        for idx, (sec_title, sec_points) in enumerate(sections[:3], 1):
            if sec_points:
                cards.append(_build_point_card(idx, sec_title, sec_points))

        # 3. 强调卡片（找一句重点）
        emphasis = None
        for line in content.split("\n"):
            line = line.strip()
            if 10 < len(line) < 40 and any(w in line for w in ["意味着", "标志着", "未来", "突破"]):
                emphasis = line
                break
        if emphasis:
            cards.append(_build_highlight_card(emphasis))

        # 4. 金句卡片
        cards.append(_build_quote_card(quote))

        # 5. 互动卡片
        cards.append(_build_cta_card())

        html = DOUYIN_TEMPLATE.replace("{CARDS}", "\n".join(cards))

        filepath = output_dir / "douyin_cards.html"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        return str(filepath)


def demo():
    """运行 demo"""
    sample = """#AI资讯

OpenAI 发布 GPT-5 预览版：多模态能力大幅提升

1. 核心升级
- 支持文本、图像、音频、视频统一处理
- 推理速度比 GPT-4 快 3 倍
- 代码生成准确率提升至 92%

2. 应用场景
- 可以直接分析视频内容并生成摘要
- 实时语音对话延迟降至 200ms
- 支持 200 万字长上下文

3. 开放策略
- 面向 Plus 用户逐步开放
- API 价格降低 50%
- 企业版支持私有化部署

这意味着 AI 正在从工具向助手进化，未来每个人都会有自己的 AI 助理。"""

    renderer = DouyinRenderer()
    path = renderer.render(sample, Path("output/douyin_demo"))
    print(f"已生成: {path}")


if __name__ == "__main__":
    demo()
