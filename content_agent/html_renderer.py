import os
import re
from pathlib import Path
from typing import List, Tuple


XIAOHONGSHU_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #e8e8e8;
            font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            padding: 30px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 30px;
        }
        .card {
            width: 900px;
            min-height: 1200px;
            background: #fff;
            border-radius: 32px;
            box-shadow: 0 12px 40px rgba(0,0,0,0.10);
            padding: 70px 60px;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
        }

        /* 封面 */
        .cover {
            background: #fff;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        .cover-emoji { font-size: 80px; margin-bottom: 30px; }
        .cover h1 {
            font-size: 64px;
            font-weight: 800;
            color: #1a1a1a;
            line-height: 1.25;
            margin-bottom: 30px;
        }
        .cover h1 span { color: #ff2442; }
        .cover-sub {
            font-size: 28px;
            color: #888;
            margin-bottom: 60px;
            line-height: 1.5;
        }
        .cover-tags {
            display: flex;
            gap: 14px;
            flex-wrap: wrap;
            justify-content: center;
        }
        .cover-tag {
            background: #fff3f5;
            color: #ff2442;
            padding: 10px 24px;
            border-radius: 30px;
            font-size: 22px;
            font-weight: 600;
        }
        .cover-footer {
            position: absolute;
            bottom: 50px;
            left: 0; right: 0;
            text-align: center;
            font-size: 22px;
            color: #ccc;
        }

        /* 要点卡片 */
        .point-card {
            background: #fafafa;
        }
        .point-card-header {
            display: flex;
            align-items: center;
            margin-bottom: 50px;
        }
        .point-num {
            width: 60px;
            height: 60px;
            background: #ff2442;
            color: #fff;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            font-weight: 700;
            margin-right: 24px;
            flex-shrink: 0;
        }
        .point-title {
            font-size: 40px;
            font-weight: 700;
            color: #1a1a1a;
        }
        .point-items {
            display: flex;
            flex-direction: column;
            gap: 28px;
        }
        .point-item {
            display: flex;
            align-items: flex-start;
            gap: 18px;
        }
        .point-bullet {
            width: 12px;
            height: 12px;
            background: #ff2442;
            border-radius: 50%;
            margin-top: 14px;
            flex-shrink: 0;
        }
        .point-text {
            font-size: 30px;
            line-height: 1.6;
            color: #333;
        }
        .point-text strong {
            color: #ff2442;
            font-weight: 600;
        }

        /* 单条强调卡片 */
        .highlight-card {
            background: #1a1a1a;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        .highlight-emoji { font-size: 72px; margin-bottom: 30px; }
        .highlight-text {
            font-size: 44px;
            font-weight: 700;
            color: #fff;
            line-height: 1.5;
        }
        .highlight-sub {
            font-size: 28px;
            color: #999;
            margin-top: 24px;
        }

        /* 金句卡片 */
        .quote-card {
            background: #fff;
            justify-content: center;
            align-items: center;
            text-align: center;
            border: 4px solid #ff2442;
        }
        .quote-mark {
            font-size: 100px;
            color: #ff2442;
            line-height: 1;
            margin-bottom: 10px;
            font-family: Georgia, serif;
        }
        .quote-text {
            font-size: 42px;
            font-weight: 700;
            color: #1a1a1a;
            line-height: 1.5;
            padding: 0 30px;
        }

        /* 互动卡片 */
        .cta-card {
            background: #fff3f5;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        .cta-emoji { font-size: 80px; margin-bottom: 24px; }
        .cta-title {
            font-size: 40px;
            font-weight: 700;
            color: #1a1a1a;
            margin-bottom: 20px;
        }
        .cta-text {
            font-size: 26px;
            color: #666;
            line-height: 1.6;
            margin-bottom: 40px;
        }
        .cta-btn {
            background: #ff2442;
            color: #fff;
            padding: 18px 50px;
            border-radius: 40px;
            font-size: 26px;
            font-weight: 600;
        }
    </style>
</head>
<body>
{CARDS}
</body>
</html>"""


# 每个主题配一个 emoji 和标签
_TOPIC_EMOJIS = {
    "agent": "🤖",
    "ai": "🤖",
    "编程": "💻",
    "代码": "💻",
    "学习": "📚",
    "副业": "💰",
    "赚钱": "💰",
    "踩坑": "⚠️",
    "总结": "📝",
    "框架": "🛠️",
    "教程": "📖",
    "笔记": "📝",
}


def _detect_topic_emoji(text: str) -> str:
    """根据内容检测合适的 emoji"""
    text_lower = text.lower()
    for keyword, emoji in _TOPIC_EMOJIS.items():
        if keyword in text_lower:
            return emoji
    return "💡"


def _detect_tags(text: str) -> List[str]:
    """从内容中提取标签"""
    tags = []
    keywords = [
        ("AI Agent", "AI Agent"), ("PydanticAI", "PydanticAI"),
        ("副业", "副业实战"), ("程序员", "程序员"),
        ("踩坑", "踩坑记录"), ("学习", "学习笔记"),
        ("LLM", "LLM"), ("大模型", "大模型"),
        ("Rust", "Rust"), ("Python", "Python"),
    ]
    for kw, tag in keywords:
        if kw in text:
            tags.append(tag)
    if not tags:
        tags = ["学习笔记", "技术分享"]
    return tags[:4]


def _smart_parse(content: str) -> Tuple[str, List[Tuple[str, List[str]]], str]:
    """
    智能解析小红书文案，返回 (标题, [(小节标题, 要点列表), ...], 金句)
    """
    lines = content.strip().split("\n")

    # 1. 找标题（第一个非空且不太短的行）
    title = "AI Agent 学习笔记"
    title_idx = 0
    for i, line in enumerate(lines[:8]):
        clean = line.strip().replace("#", "").strip()
        if clean and len(clean) > 8 and len(clean) < 60:
            title = clean
            title_idx = i
            break

    # 2. 解析段落结构（从标题行之后开始，避免重复）
    sections = []
    current_title = ""
    current_points = []
    buffer_lines = []

    i = title_idx + 1
    # 跳过标题后的空行和引言（直到遇到第一个明确的section标题）
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        # 检查是否是明确的section标题
        is_section_header = False
        
        # Markdown 标题（# ## ###）
        if re.match(r'^(#{1,3})\s+(.+)', line):
            is_section_header = True
        # Step/步骤 开头的行
        elif re.match(r'^(Step\s+\d+|步骤\d+|第\d+步)\s*[:：]', line, re.IGNORECASE):
            is_section_header = True
        # 带数字序号的行（如 "1. " 或 "1、"）
        elif re.match(r'^\d+[\.\、]\s+\S', line):
            is_section_header = True
        # emoji + 短句
        elif re.match(r'^[\U0001F300-\U0001F9FF]\s*\S', line) and len(line) < 50:
            is_section_header = True
        
        if is_section_header:
            break
        
        # 不是标题，跳过引言
        i += 1

    # 现在开始正式解析
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        is_header = False
        header_text = ""

        # Markdown 标题（# ## ###）
        m = re.match(r'^(#{1,3})\s+(.+)', line)
        if m:
            is_header = True
            header_text = m.group(2).strip()

        # Step/步骤 开头的行
        elif re.match(r'^(Step\s+\d+|步骤\d+|第\d+步)\s*[:：]', line, re.IGNORECASE):
            m = re.match(r'^(Step\s+\d+|步骤\d+|第\d+步)\s*[:：]\s*(.+)', line, re.IGNORECASE)
            if m:
                is_header = True
                header_text = m.group(2).strip()
            else:
                is_header = True
                header_text = line.strip()

        # 带数字序号的行（如 "1. 标题" 或 "1、标题"）
        elif re.match(r'^\d+[\.\、]\s+\S', line):
            m = re.match(r'^\d+[\.\、]\s+(.+)', line)
            if m:
                is_header = True
                header_text = m.group(1).strip()

        # emoji 开头的短句
        elif re.match(r'^[\U0001F300-\U0001F9FF]\s*\S', line) and len(line) < 50:
            is_header = True
            header_text = re.sub(r'^[\U0001F300-\U0001F9FF]\s*', '', line).strip()

        # **加粗** 包围的短句（且不太长）
        elif re.match(r'^\*\*(.+?)\*\*$', line.strip()) and len(line) < 50:
            is_header = True
            header_text = re.match(r'^\*\*(.+?)\*\*$', line.strip()).group(1).strip()

        if is_header:
            if current_title and current_points:
                sections.append((current_title, current_points))
            elif buffer_lines and not current_title:
                sections.append(("核心要点", buffer_lines))
                buffer_lines = []
            current_title = header_text
            current_points = []
        else:
            clean = line
            clean = re.sub(r'^[-*•·○●\u2705\u274c]+\s*', '', clean)
            clean = re.sub(r'^\d+[\.\、]\s*', '', clean)
            clean = clean.strip()

            if clean and len(clean) > 3:
                # 截断阈值从80提高到150字
                if len(clean) > 150:
                    clean = clean[:148] + "..."
                if current_title:
                    current_points.append(clean)
                else:
                    buffer_lines.append(clean)

        i += 1

    # 保存最后一个 section
    if current_title and current_points:
        sections.append((current_title, current_points))
    elif buffer_lines and not current_title:
        sections.append(("核心要点", buffer_lines))

        # 合并内容过少的 section（只合并非空section，避免过度合并）
        optimized = []
        for sec_title, sec_points in sections:
            if len(sec_points) >= 2 or not optimized:
                optimized.append((sec_title, sec_points))
            elif optimized:
                prev_title, prev_points = optimized[-1]
                # 只有上一个 section 已经有足够内容才合并
                if len(prev_points) >= 2:
                    optimized[-1] = (prev_title, prev_points + sec_points)
                else:
                    optimized.append((sec_title, sec_points))
        if optimized:
            sections = optimized

    # 过滤掉金句section（通常在最后，标题包含"金句"）
    quote_candidates = []
    filtered_sections = []
    for sec_title, sec_points in sections:
        if "金句" in sec_title and len(sec_points) <= 1:
            # 这是金句section，提取内容作为金句候选
            if sec_points:
                quote_candidates.extend(sec_points)
            continue
        filtered_sections.append((sec_title, sec_points))
    sections = filtered_sections

    # 重新平衡sections（确保每张卡片有足够内容）
    if len(sections) >= 2:
        # 如果最后一个section内容太少，合并到前一个
        if len(sections[-1][1]) <= 2 and len(sections) >= 2:
            merged_title = f"{sections[-2][0]} + {sections[-1][0]}"
            merged_points = sections[-2][1] + sections[-1][1]
            sections = sections[:-2] + [(merged_title, merged_points)]

    # 限制最多 3 个 section
    if len(sections) > 3:
        merged_points = []
        for sec_title, sec_points in sections[2:]:
            merged_points.extend(sec_points)
        sections = sections[:2] + [("更多要点", merged_points)]

    # 兜底处理
    if not sections:
        all_points = []
        for line in lines[title_idx + 1:]:
            clean = re.sub(r'^[-*•·○●\u2705\u274c]\s*', '', line.strip()).strip()
            if clean and len(clean) > 5 and len(clean) < 100:
                all_points.append(clean)
        if all_points:
            sections = [("核心要点", all_points)]

    # 3. 提取金句 - 改进逻辑
    quote = "学习不是为了成为谁，而是为了在机会来临时，你有能力抓住它。"
    candidates = []

    # 优先从 sections 中提取金句
    for sec_title, sec_points in sections:
        for point in sec_points:
            # 金句特征：15-80字，包含特定关键词，或带引号
            if 15 <= len(point) <= 80:
                if any(w in point for w in ["本质", "核心", "关键", "记住", "其实", "真正", "最重要"]):
                    candidates.append(point)
                elif '"' in point or "\u201c" in point or "\u2018" in point:
                    candidates.append(point)
                elif point.endswith(('！', '!')) and len(point) > 20:
                    candidates.append(point)
                elif '**' in point and len(point) > 15:
                    # 加粗的内容可能是重点
                    candidates.append(point)

    # 从原始内容中补充
    if not candidates:
        for line in lines:
            clean = line.strip()
            clean = re.sub(r'^[-*•·○●\u2705\u274c]\s*', '', clean)
            clean = re.sub(r'^\d+[\.\、]\s*', '', clean).strip()
            if not clean:
                continue
            if 15 <= len(clean) <= 80:
                if any(w in clean for w in ["本质", "核心", "关键", "记住", "其实", "真正", "最重要"]):
                    candidates.append(clean)
                elif clean.endswith(('！', '!')) and len(clean) > 20:
                    candidates.append(clean)

    if candidates:
        # 选择最长的作为金句（通常最完整）
        quote = max(candidates, key=len)
    else:
        # 兜底：找一句不太短的话
        for line in reversed(lines):
            clean = line.strip()
            if re.match(r'^[-*•·○●\u2705\u274c]', clean):
                continue
            if 15 < len(clean) < 80 and not clean.startswith(('\ud83d', '\ud83c')):
                quote = clean
                break

    return title, sections, quote


def _build_cover_card(title: str, emoji: str, tags: List[str]) -> str:
    tags_html = "\n".join(f'<div class="cover-tag">{t}</div>' for t in tags)
    # 给标题里的关键词加红色
    title_colored = title
    for kw in ["AI", "Agent", "副业", "赚钱", "踩坑", "核心", "本质"]:
        if kw in title and f'<span>{kw}</span>' not in title_colored:
            title_colored = title_colored.replace(kw, f'<span>{kw}</span>', 1)
            break  # 只加红一个

    return f"""
    <div class="card cover">
        <div class="cover-emoji">{emoji}</div>
        <h1>{title_colored}</h1>
        <div class="cover-sub">程序员副业实战 · 学习笔记分享</div>
        <div class="cover-tags">
            {tags_html}
        </div>
        <div class="cover-footer">@程序员Lee</div>
    </div>"""


def _build_point_card(index: int, title: str, points: List[str]) -> str:
    """一张要点卡片，最多放 6 条（扩充到6条），每条加 bullet"""
    # 限制每张卡片的点数：4→6
    display_points = points[:6]
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


def _build_highlight_card(emoji: str, text: str, sub: str = "") -> str:
    sub_html = f'<div class="highlight-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="card highlight-card">
        <div class="highlight-emoji">{emoji}</div>
        <div class="highlight-text">{text}</div>
        {sub_html}
    </div>"""


def _build_quote_card(quote: str) -> str:
    return f"""
    <div class="card quote-card">
        <div class="quote-mark">"</div>
        <div class="quote-text">{quote}</div>
    </div>"""


def _build_cta_card(question: str = "你也在搞副业学 AI 吗？") -> str:
    return f"""
    <div class="card cta-card">
        <div class="cta-emoji">💬</div>
        <div class="cta-title">{question}</div>
        <div class="cta-text">评论区聊聊你的学习进度<br>互相督促进步更快</div>
        <div class="cta-btn">点赞收藏 ↓ 关注不迷路</div>
    </div>"""


class XiaohongshuRenderer:
    def render(self, content: str, output_dir: Path) -> str:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        title, sections, quote = _smart_parse(content)
        emoji = _detect_topic_emoji(content)
        tags = _detect_tags(content)

        cards = []

        # 1. 封面
        cards.append(_build_cover_card(title, emoji, tags))

        # 2. 内容卡片：每个 section 一张卡片，最多 3 张
        # 优化：如果 section 内容少，合并到一张卡片
        content_cards = []
        for idx, (sec_title, sec_points) in enumerate(sections[:4], 1):
            if sec_points:
                content_cards.append((idx, sec_title, sec_points))
        
        # 如果只有1-2个section，每个section独立一张卡片
        # 如果有3-4个section，前2个独立，后2个合并
        if len(content_cards) >= 3:
            # 合并最后两个section到一张卡片
            merged_title = f"{content_cards[-2][1]} + {content_cards[-1][1]}"
            merged_points = content_cards[-2][2] + content_cards[-1][2]
            content_cards = content_cards[:-2] + [(len(content_cards)-1, merged_title, merged_points)]
        
        for idx, sec_title, sec_points in content_cards[:3]:
            cards.append(_build_point_card(idx, sec_title, sec_points))

        # 3. 如果内容有比较短的重点句，插一张强调卡片
        # 找一句 10-40 字的强调句
        emphasis = None
        for line in content.split("\n"):
            line = line.strip()
            if 10 < len(line) < 40 and ("就是" in line or "本质" in line or "核心" in line or "记住" in line):
                emphasis = line
                break
        if emphasis:
            cards.append(_build_highlight_card("🔥", emphasis))

        # 4. 金句卡片
        cards.append(_build_quote_card(quote))

        # 5. 互动卡片
        cards.append(_build_cta_card())

        html = XIAOHONGSHU_TEMPLATE.replace("{CARDS}", "\n".join(cards))

        filepath = output_dir / "xiaohongshu_cards.html"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        return str(filepath)
