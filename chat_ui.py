#!/usr/bin/env python3
"""
Content Agent - 聊天式 Web UI

基于 Gradio 的聊天界面，支持：
- 自然语言对话
- Agent 自动分析用户需求
- 自动选择平台、策略
- 生成内容并展示

运行: python chat_ui.py
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# 调试日志
_LOG_PATH = os.getenv(
    "CHAT_UI_LOG_PATH",
    os.path.join(os.path.expanduser("~"), ".content_agent", "chat_ui.log"),
)
try:
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
except OSError:
    _LOG_PATH = os.path.join(Path(__file__).resolve().parent, "data", "logs", "chat_ui.log")
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
try:
    logging.basicConfig(
        filename=_LOG_PATH,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
except OSError:
    _LOG_PATH = os.path.join(Path(__file__).resolve().parent, "data", "logs", "chat_ui.log")
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    logging.basicConfig(
        filename=_LOG_PATH,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
logger = logging.getLogger("chat_ui")
logger.info("=== chat_ui 初始化开始 ===")

from dotenv import load_dotenv
load_dotenv()

try:
    import gradio as gr
except ImportError as e:
    print(f"❌ Gradio 导入失败: {e}")
    print("提示: pip install gradio")
    sys.exit(1)

# 导入 Agent 组件
from agents.tools import execute_tool
from agents.planning import StrategySelector, AutonomousPlanner
from agents.schemas import WriterOutput


# ==================== 聊天核心逻辑 ====================

class ChatAgent:
    """聊天 Agent，处理用户消息并执行内容生成"""
    
    def __init__(self):
        self.selector = StrategySelector()
        self.planner = AutonomousPlanner()
        self.history = []
    
    def process_message(self, user_message: str) -> dict:
        """
        处理用户消息，分析意图并执行
        
        Returns:
            {
                "type": "text" | "content" | "error",
                "content": str,
                "platforms": list,
                "files": list,
            }
        """
        logger.info(f"用户消息: {user_message}")
        
        # 1. 分析用户意图
        intent = self._analyze_intent(user_message)
        logger.info(f"意图分析: {intent}")
        
        # 2. 根据意图执行
        if intent["type"] == "generate":
            return self._handle_generate(intent, user_message)
        elif intent["type"] == "help":
            return self._handle_help()
        elif intent["type"] == "status":
            return self._handle_status()
        else:
            return {
                "type": "text",
                "content": "我不太理解你的需求。你可以说：\n- '帮我写一篇关于XXX的公众号文章'\n- '生成小红书笔记：程序员健身指南'\n- '把这篇笔记改写成抖音文案'",
            }
    
    def _analyze_intent(self, message: str) -> dict:
        """分析用户意图"""
        message = message.lower()
        
        # 检查是否是生成请求
        generate_keywords = ["写", "生成", "创作", "来一篇", "帮我", "想要"]
        is_generate = any(kw in message for kw in generate_keywords)
        
        if is_generate:
            # 提取平台
            platforms = []
            if "公众号" in message or "微信" in message:
                platforms.append("gongzhonghao")
            if "小红书" in message:
                platforms.append("xiaohongshu")
            if "抖音" in message:
                platforms.append("douyin")
            
            # 如果没有指定平台，默认公众号
            if not platforms:
                platforms = ["gongzhonghao"]
            
            # 提取主题（简单实现：去掉常见词后的剩余内容）
            topic = message
            for kw in generate_keywords:
                topic = topic.replace(kw, "")
            topic = topic.strip("的关于之")
            
            return {
                "type": "generate",
                "platforms": platforms,
                "topic": topic,
            }
        
        # 检查是否是帮助请求
        if "帮助" in message or "help" in message or "怎么用" in message:
            return {"type": "help"}
        
        # 检查是否是状态请求
        if "状态" in message or "进度" in message:
            return {"type": "status"}
        
        return {"type": "unknown"}
    
    def _handle_generate(self, intent: dict, original_message: str) -> dict:
        """处理生成请求"""
        platforms = intent["platforms"]
        topic = intent["topic"]
        
        # 如果没有提取到主题，使用原始消息
        if not topic or len(topic) < 5:
            topic = original_message
        
        try:
            # 1. 搜索资料
            search_result = execute_tool("search", query=topic[:200])
            research_report = search_result.data if search_result.success else ""
            
            # 2. 构建笔记
            raw_notes = f"# {topic}\n\n## 搜索资料\n\n{research_report}\n\n## 主题\n\n{topic}"
            
            # 3. 选择策略
            strategy = self.selector.select(raw_notes)
            
            # 4. 执行生成
            result = self.planner.plan_and_execute(raw_notes, platforms, strategy)
            
            # 5. 构建响应
            content = result.get("content")
            if not content:
                return {
                    "type": "error",
                    "content": "生成失败，请重试",
                }
            
            # 构建输出文本
            output_text = f"✅ 已生成 {len(platforms)} 个平台的内容\n\n"
            output_text += f"📋 使用策略: {strategy.name}\n"
            output_text += f"📊 评分: {result.get('verdict', {}).overall if result.get('verdict') else 'N/A'}/100\n\n"
            
            files = []
            for platform in platforms:
                text = getattr(content, platform, "")
                if text:
                    output_text += f"---\n\n### {'公众号' if platform == 'gongzhonghao' else '小红书' if platform == 'xiaohongshu' else '抖音'}\n\n{text[:500]}...\n\n"
                    
                    # 保存文件
                    output_dir = Path("output/chat") / datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_dir.mkdir(parents=True, exist_ok=True)
                    file_path = output_dir / f"{platform}.md"
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    files.append(str(file_path))
            
            return {
                "type": "content",
                "content": output_text,
                "platforms": platforms,
                "files": files,
            }
            
        except Exception as e:
            logger.error(f"生成失败: {e}", exc_info=True)
            return {
                "type": "error",
                "content": f"生成失败: {str(e)}",
            }
    
    def _handle_help(self) -> dict:
        """处理帮助请求"""
        return {
            "type": "text",
            "content": """🤖 **Content Agent 使用指南**

你可以用自然语言和我对话：

**生成内容：**
- "帮我写一篇关于 Python 的公众号文章"
- "生成小红书笔记：程序员健身指南"
- "把这篇笔记改写成抖音文案"

**支持的平台：**
- 公众号（长文）
- 小红书（短笔记）
- 抖音（口播脚本）

**其他命令：**
- "帮助" - 显示使用指南
- "状态" - 查看系统状态

**提示：**
- 描述越详细，生成内容越精准
- 可以指定多个平台，用"和"连接
""",
        }
    
    def _handle_status(self) -> dict:
        """处理状态请求"""
        return {
            "type": "text",
            "content": """📊 **系统状态**

✅ Agent 核心: 运行中
✅ 工具系统: 正常
✅ 策略选择器: 正常
✅ 生成引擎: 正常

**可用工具：**
- 搜索 (search)
- 浏览 (browse)
- 文件读取 (read)
- 数据分析 (analyze)
- 代码执行 (execute)

**支持平台：**
- 公众号 (gongzhonghao)
- 小红书 (xiaohongshu)
- 抖音 (douyin)
""",
        }


# ==================== Gradio 界面 ====================

def create_chat_ui():
    """创建聊天界面"""
    agent = ChatAgent()

    def respond(message, chat_history):
        """处理用户消息"""
        # 添加用户消息
        chat_history.append({"role": "user", "content": message})
        
        # 处理消息
        result = agent.process_message(message)
        
        # 构建响应
        gzh_path = ""
        if result["type"] == "content":
            # 有生成内容
            response = result["content"]
            if result.get("files"):
                response += "\n\n📁 **生成文件：**\n"
                for f in result["files"]:
                    response += f"- {f}\n"
                # 提取公众号文件路径
                for f in result["files"]:
                    if "gongzhonghao" in f:
                        gzh_path = f
                        break
        else:
            response = result["content"]
        
        # 添加助手消息
        chat_history.append({"role": "assistant", "content": response})
        
        return "", chat_history, gzh_path
    
    def clear_history():
        """清空历史"""
        agent.history = []
        return [], ""
    
    def publish_gzh(cover_image, gzh_file_path):
        """发布到微信公众号草稿箱"""
        if not gzh_file_path:
            return "❌ 请先生成公众号内容"
        if not cover_image:
            return "❌ 请上传封面图片"
        
        try:
            from content_agent.publisher import publish_wechat_draft
            # 读取文件内容提取标题（第一行 # 标题）
            content = Path(gzh_file_path).read_text(encoding="utf-8")
            title = content.splitlines()[0].lstrip("# ").strip() if content else "Generated Article"
            if not title:
                title = "Generated Article"
            
            result = publish_wechat_draft(
                markdown_path=gzh_file_path,
                title=title,
                cover_path=cover_image,
            )
            if result.get("success"):
                return f"✅ {result.get('message', '发布成功')}"
            else:
                return f"❌ {result.get('message', '发布失败')}\n详情: {result.get('details', '')}"
        except Exception as e:
            return f"❌ 发布异常: {str(e)}"
    
    # 构建界面 - 使用系统字体避免加载 Google Fonts（国内网络阻塞问题）
    theme = gr.themes.Soft(
        font=["system-ui", "SF Pro Display", "Segoe UI", "PingFang SC", "Microsoft YaHei", "sans-serif"],
        font_mono=["SF Mono", "SFMono-Regular", "Consolas", "Liberation Mono", "Menlo", "monospace"],
    )
    
    with gr.Blocks(
        title="Content Agent - 聊天模式",
        theme=theme,
        css="""
        .chat-container { height: 600px; }
        .input-box { margin-top: 20px; }
        .publish-box { margin-top: 16px; padding: 16px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fafafa; }
        """
    ) as demo:
        # 存储最后一次生成的公众号文件路径。State 必须创建在 Blocks 内，
        # 否则事件输出会引用未注册组件，导致 Gradio 前端/API 报错。
        last_gzh_file = gr.State("")

        gr.Markdown("""
        # 🤖 Content Agent - AI 内容创作助手
        
        用自然语言告诉我你想创作什么内容，我会自动分析、搜索资料、生成文案。
        
        **示例：**
        - "帮我写一篇关于 MCP 协议的公众号文章"
        - "生成小红书笔记：程序员颈椎拯救计划"
        - "把 Python 异步编程改写成抖音口播脚本"
        """)
        
        # 聊天区域
        chatbot = gr.Chatbot(
            label="对话",
            height=500,
            type="messages",
        )
        
        # 输入区域
        with gr.Row():
            msg_input = gr.Textbox(
                label="输入消息",
                placeholder="告诉我你想创作什么内容...",
                scale=8,
                show_label=False,
            )
            send_btn = gr.Button("发送", scale=1, variant="primary")
        
        # 快捷按钮
        with gr.Row():
            btn_gzh = gr.Button("📱 公众号文章", size="sm")
            btn_xhs = gr.Button("📕 小红书笔记", size="sm")
            btn_dy = gr.Button("🎵 抖音文案", size="sm")
            clear_btn = gr.Button("🗑️ 清空对话", size="sm", variant="secondary")
        
        # 公众号发布区域
        with gr.Row(variant="panel"):
            with gr.Column(scale=1):
                cover_upload = gr.Image(
                    label="📷 公众号封面",
                    type="filepath",
                    height=150,
                    show_label=True,
                )
            with gr.Column(scale=2):
                pub_status = gr.Textbox(
                    label="发布状态",
                    value="等待生成内容...",
                    interactive=False,
                    show_label=True,
                )
                publish_btn = gr.Button("📤 发布到公众号草稿箱", variant="primary", size="sm")
        
        # 事件绑定
        send_btn.click(
            respond,
            inputs=[msg_input, chatbot],
            outputs=[msg_input, chatbot, last_gzh_file]
        )
        
        msg_input.submit(
            respond,
            inputs=[msg_input, chatbot],
            outputs=[msg_input, chatbot, last_gzh_file]
        )
        
        clear_btn.click(
            clear_history,
            outputs=[chatbot, last_gzh_file]
        )
        
        # 快捷按钮事件
        def quick_gzh():
            return respond("帮我写一篇技术文章的公众号版本", [])
        
        def quick_xhs():
            return respond("生成小红书笔记", [])
        
        def quick_dy():
            return respond("生成抖音口播脚本", [])
        
        btn_gzh.click(
            quick_gzh,
            outputs=[msg_input, chatbot, last_gzh_file]
        )
        btn_xhs.click(
            quick_xhs,
            outputs=[msg_input, chatbot, last_gzh_file]
        )
        btn_dy.click(
            quick_dy,
            outputs=[msg_input, chatbot, last_gzh_file]
        )
        
        # 发布按钮事件
        publish_btn.click(
            publish_gzh,
            inputs=[cover_upload, last_gzh_file],
            outputs=[pub_status]
        )
        
        # 使用说明
        with gr.Accordion("📖 使用说明", open=False):
            gr.Markdown("""
            ### 如何使用
            
            1. **直接输入需求**：用自然语言描述你想创作的内容
            2. **指定平台**：可以指定公众号、小红书、抖音中的一个或多个
            3. **等待生成**：Agent 会自动搜索资料、选择策略、生成内容
            4. **发布公众号**：生成公众号文章后，上传封面图片，点击发布按钮
            
            ### 支持的指令
            
            - **生成内容**："帮我写一篇关于XXX的文章"
            - **指定平台**："生成小红书笔记：XXX"
            - **多平台**："生成公众号和小红书的内容：XXX"
            - **查看状态**："状态"
            - **帮助**："帮助"
            
            ### 提示
            
            - 描述越详细，生成内容越精准
            - 可以要求特定风格或格式
            - 生成后可以要求修改或调整
            - 发布到公众号需要：
              - 先生成公众号内容
              - 上传封面图片（必填）
              - 安装 kuaifa CLI (`npm install -g kuaifa`)
            """)
    
    return demo


# ==================== 启动 ====================

if __name__ == "__main__":
    print("🚀 启动 Content Agent 聊天界面...")
    print("📖 使用说明：")
    print("   - 输入需求，Agent 会自动生成内容")
    print("   - 支持平台：公众号、小红书、抖音")
    print("   - 输入'帮助'查看详细指南")
    print()
    
    demo = create_chat_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False,
        show_error=True,
    )
