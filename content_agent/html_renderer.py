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
            padding: 60px 50px;
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
            font-size: 56px;
            font-weight: 800;
            color: #1a1a1a;
            line-height: 1.3;
            margin-bottom: 30px;
        }
        .cover h1 span { color: #ff2442; }
        .cover-sub {
            font-size: 26px;
            color: #888;
            margin-bottom: 50px;
            line-height: 1.5;
        }
        .cover-tags {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            justify-content: center;
        }
        .cover-tag {
            background: #fff3f5;
            color: #ff2442;
            padding: 8px 20px;
            border-radius: 30px;
            font-size: 20px;
            font-weight: 600;
        }
        .cover-footer {
            position: absolute;
            bottom: 50px;
            left: 0; right: 0;
            text-align: center;
            font-size: 20px;
            color: #ccc;
        }

        /* 内容卡片 */
        .content-card {
            background: #fafafa;
        }
        .content-card h2 {
            font-size: 36px;
            font-weight: 700;
            color: #1a1a1a;
            margin-bottom: 30px;
            padding-bottom: 15px;
            border-bottom: 3px solid #ff2442;
        }
        .content-body {
            font-size: 26px;
            line-height: 1.8;
            color: #333;
        }
        .content-body p {
            margin-bottom: 16px;
        }
        .content-body strong {
            color: #ff2442;
            font-weight: 600;
        }
        .content-body code {
            background: #f0f0f0;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 22px;
            color: #ff2442;
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
            font-size: 38px;
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
    text_lower = text.lower()
    for keyword, emoji in _TOPIC_EMOJIS.items():
        if keyword in text_lower:
            return emoji
    return "💡"


def _detect_tags(text: str) -> List[str]:
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


def _parse_content(content: str) -> Tuple[str, List[str], str]:
    """
    解析小红书文案，返回 (标题, 内容段落列表, 金句)
    保留所有内容，不截断
    """
    lines = content.strip().split("\n")
    
    # 1. 找标题
    title = "AI Agent 学习笔记"
    title_idx = 0
    for i, line in enumerate(lines[:8]):
        clean = line.strip().replace("#", "").strip()
        if clean and len(clean) > 8 and len(clean) < 60:
            title = clean
            title_idx = i
            break
    
    # 2. 提取所有内容段落（保留顺序，不截断）
    # 小红书文案常用 1️⃣/2️⃣/⚠️/💡/#话题 作为结构边界；如果只按空行切分，
    # 很容易把整篇正文塞进一张卡片里。
    paragraphs = []
    current_para = []

    def flush_current():
        nonlocal current_para
        if current_para:
            paragraphs.append("\n".join(current_para))
            current_para = []

    def is_section_start(text: str) -> bool:
        return bool(
            re.match(r'^\d+[\.、]\s+', text)
            or re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩]\s*', text)
            or re.match(r'^[0-9]?[️⃣]\s*', text)
            or re.match(r'^[一二三四五六七八九十][、.]\s+', text)
            or re.match(r'^第[一二三四五六七八九十0-9]+[步部分章节]\s*', text)
            or text.startswith(("📌", "✅", "❌", "⚠️", "💡", "👉", "👇", "#"))
        )
    
    for line in lines[title_idx + 1:]:
        stripped = line.strip()
        
        # 跳过纯空行
        if not stripped:
            flush_current()
            continue
        
        # 处理列表项
        if re.match(r'^[-*•·○●\u2705\u274c]\s+', stripped) or is_section_start(stripped):
            flush_current()
            # 保留列表标记
            current_para.append(stripped)
        else:
            current_para.append(stripped)
    
    # 保存最后一个段落
    flush_current()
    
    # 3. 提取金句（从段落中找）
    quote = ""
    for para in paragraphs:
        # 找包含关键词的短句
        sentences = re.split(r'[。！?？]', para)
        for sent in sentences:
            sent = sent.strip()
            if 15 <= len(sent) <= 80:
                if any(w in sent for w in ["本质", "核心", "关键", "记住", "其实", "真正", "最重要"]):
                    quote = sent
                    break
                elif '"' in sent or "\u201c" in sent:
                    quote = sent
                    break
        if quote:
            break
    
    # 兜底金句
    if not quote and paragraphs:
        for para in reversed(paragraphs):
            if len(para) > 15 and len(para) < 80:
                quote = para
                break
    
    if not quote:
        quote = "学习不是为了成为谁，而是为了在机会来临时，你有能力抓住它。"
    
    return title, paragraphs, quote


def _split_long_para(para: str, max_chars: int = 360) -> List[str]:
    """把过长段落按句子拆开，避免单张卡片内容过载。"""
    if len(para) <= max_chars:
        return [para]

    parts = re.split(r'(?<=[。！？!?])', para)
    chunks = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current and len(current) + len(part) > max_chars:
            chunks.append(current)
            current = part
        else:
            current = f"{current}{part}" if current else part

    if current:
        chunks.append(current)

    return chunks or [para]


def _build_cover_card(title: str, emoji: str, tags: List[str]) -> str:
    tags_html = "\n".join(f'<div class="cover-tag">{t}</div>' for t in tags)
    title_colored = title
    for kw in ["AI", "Agent", "副业", "赚钱", "踩坑", "核心", "本质"]:
        if kw in title and f'<span>{kw}</span>' not in title_colored:
            title_colored = title_colored.replace(kw, f'<span>{kw}</span>', 1)
            break

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


def _build_content_card(title: str, paragraphs: List[str]) -> str:
    """构建内容卡片，显示连续的段落"""
    # 将段落转换为HTML
    para_html = []
    for para in paragraphs:
        # 处理加粗
        para = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', para)
        # 处理代码
        para = re.sub(r'`([^`]+)`', r'<code>\1</code>', para)
        # 处理换行
        para = para.replace("\n", "<br>")
        para_html.append(f'<p>{para}</p>')
    
    body_html = "\n".join(para_html)
    
    return f"""
    <div class="card content-card">
        <h2>{title}</h2>
        <div class="content-body">
            {body_html}
        </div>
    </div>"""


def _build_quote_card(quote: str) -> str:
    # 处理加粗
    quote = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', quote)
    return f"""
    <div class="card quote-card">
        <div class="quote-mark">"</div>
        <div class="quote-text">{quote}</div>
    </div>"""


def _build_cta_card() -> str:
    return f"""
    <div class="card cta-card">
        <div class="cta-emoji">💬</div>
        <div class="cta-title">你也在搞副业学 AI 吗？</div>
        <div class="cta-text">评论区聊聊你的学习进度<br>互相督促进步更快</div>
        <div class="cta-btn">点赞收藏 ↓ 关注不迷路</div>
    </div>"""


class XiaohongshuRenderer:
    def render(self, content: str, output_dir: Path) -> str:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        title, paragraphs, quote = _parse_content(content)
        emoji = _detect_topic_emoji(content)
        tags = _detect_tags(content)

        cards = []

        # 1. 封面
        cards.append(_build_cover_card(title, emoji, tags))

        # 2. 内容卡片：按顺序分配段落到卡片
        # 小红书配图更适合一张卡讲 1-2 个要点，避免一张过满、后面过空。
        CARD_TARGET_CHARS = 280
        CARD_MAX_CHARS = 420
        expanded_paragraphs = []
        for para in paragraphs:
            expanded_paragraphs.extend(_split_long_para(para))

        current_card_paras = []
        current_card_chars = 0
        card_index = 1
        
        for para in expanded_paragraphs:
            para_chars = len(para)
            
            # 如果当前卡片已满，保存并开始新卡片
            if (
                current_card_paras
                and (
                    current_card_chars + para_chars > CARD_TARGET_CHARS
                    or current_card_chars + para_chars > CARD_MAX_CHARS
                    or current_card_chars >= CARD_TARGET_CHARS
                )
            ):
                cards.append(_build_content_card(f"Part {card_index}", current_card_paras))
                current_card_paras = [para]
                current_card_chars = para_chars
                card_index += 1
            else:
                current_card_paras.append(para)
                current_card_chars += para_chars
        
        # 保存最后一个内容卡片
        if current_card_paras:
            cards.append(_build_content_card(f"Part {card_index}", current_card_paras))

        # 3. 金句卡片
        if quote:
            cards.append(_build_quote_card(quote))

        # 4. 互动卡片
        cards.append(_build_cta_card())

        html = XIAOHONGSHU_TEMPLATE.replace("{CARDS}", "\n".join(cards))

        filepath = output_dir / "xiaohongshu_cards.html"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        return str(filepath)
