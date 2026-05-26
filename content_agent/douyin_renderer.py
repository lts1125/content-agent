"""
抖音图文渲染器

将热点新闻/科技资讯渲染为 9:16 竖屏图文，适合抖音图文发布。
保留全部内容，按顺序分配到多张卡片。
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
            min-height: 1920px;
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

        /* 内容卡片 */
        .content-card {
            background: #1a1a1a;
        }
        .content-card h2 {
            font-size: 40px;
            font-weight: 800;
            color: #fff;
            margin-bottom: 30px;
            padding-bottom: 15px;
            border-bottom: 3px solid #fe2c55;
        }
        .content-body {
            font-size: 30px;
            line-height: 1.8;
            color: #ccc;
        }
        .content-body p {
            margin-bottom: 16px;
        }
        .content-body strong {
            color: #fe2c55;
            font-weight: 600;
        }
        .content-body code {
            background: #2a2a2a;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 26px;
            color: #fe2c55;
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


def _parse_content(content: str) -> Tuple[str, str, List[str], str]:
    """
    解析抖音文案，返回 (标签, 标题, 段落列表, 金句)
    保留全部内容，不截断
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

    # 3. 提取所有段落（保留顺序，不截断）
    paragraphs = []
    current_para = []

    for line in lines[title_idx + 1:]:
        stripped = line.strip()

        # 跳过纯空行
        if not stripped:
            if current_para:
                paragraphs.append("\n".join(current_para))
                current_para = []
            continue

        current_para.append(stripped)

    # 保存最后一个段落
    if current_para:
        paragraphs.append("\n".join(current_para))

    # 4. 提取金句
    quote = ""
    for para in paragraphs:
        sentences = re.split(r'[。！?？]', para)
        for sent in sentences:
            sent = sent.strip()
            if 15 <= len(sent) <= 80:
                if any(w in sent for w in ["本质", "核心", "关键", "意味着", "标志着", "未来"]):
                    quote = sent
                    break
        if quote:
            break

    if not quote and paragraphs:
        for para in reversed(paragraphs):
            if len(para) > 15 and len(para) < 80:
                quote = para
                break

    if not quote:
        quote = "科技改变生活，关注前沿动态。"

    return tag, title, paragraphs, quote


def _build_cover_card(tag: str, title: str) -> str:
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


def _build_content_card(title: str, paragraphs: List[str]) -> str:
    """构建内容卡片，显示连续的段落"""
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
    quote = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', quote)
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

        tag, title, paragraphs, quote = _parse_content(content)

        cards = []

        # 1. 封面
        cards.append(_build_cover_card(tag, title))

        # 2. 内容卡片：按顺序分配段落到卡片
        # 每张卡片大约容纳 800-1000 字
        CARD_MAX_CHARS = 900
        current_card_paras = []
        current_card_chars = 0
        card_index = 1

        for para in paragraphs:
            para_chars = len(para)

            # 如果当前卡片已满，保存并开始新卡片
            if current_card_chars + para_chars > CARD_MAX_CHARS and current_card_paras:
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
