from pydantic import BaseModel
from pydantic_ai import Agent

from content_agent.config.model_config import ModelConfig


class MultiPlatformContent(BaseModel):
    xiaohongshu: str
    """小红书笔记：emoji多、段落短、要点化、语气轻松，适合手机阅读"""

    gongzhonghao: str
    """公众号文章：深度长文、结构完整、有代码块和技术细节，适合桌面阅读"""

    douyin: str
    """抖音口播脚本：开头有钩子、短句、口语化、带画面提示，适合视频拍摄"""

    recommended_tags: str
    """基于笔记内容生成的各平台推荐标签/话题，按平台分类列出，用户可直接复制使用"""


SYSTEM_PROMPT = """你是一位全平台内容专家，擅长把技术学习笔记同时改写成三种风格的文案。

输入是程序员的学习笔记，输出必须包含三个平台的文案和推荐标签，分别符合以下要求：

【小红书笔记】
- 标题吸睛，带emoji和数字
- 开头一句话点出动机
- 正文分步骤，每步带emoji编号，每步简洁明了
- 保留核心概念和踩坑记录，但大白话解释
- 结尾金句总结 + 互动问句
- 添加3-5个话题标签（#xxx 格式）
- 全文300-600字

【公众号文章】
- 标题正式，可带副标题
- 开头用导言引入，讲背景和动机
- 正文分大章节，用## 标题分隔
- 每个步骤详细展开：有原理解释、代码示例、实际场景
- 包含具体的命令行代码块
- 有"总结"和"下一步"部分
- 全文1500-2500字，信息密度高

【抖音口播脚本】
- 开头前3秒必须有强钩子
- 每句话不超过15个字，短句排比
- 口语化，用"我""你""大家"等称呼
- 带画面提示（【镜头切到代码】【切换到页面】）
- 中间有转折或悬念，尾部有行动号召
- 全文200-400字，适合2-3分钟口播

【推荐标签/话题】
请基于笔记内容，额外输出各平台的推荐标签/话题，格式如下：

📱 小红书（5-8个）：
#标签1 #标签2 #标签3 ...

💬 公众号（3-5个关键词）：
关键词1、关键词2、关键词3 ...

🎥 抖音（3-5个）：
#话题1 #话题2 #话题3 ...

要求：标签必须与笔记内容高度相关，避免泛泛而谈的热门词。

核心原则：三个平台都必须基于同一份学习笔记，不编造内容，不流于表面，读者看完能复现学习路径。"""


class ContentAgent:
    def __init__(self):
        self.model, self.provider_name = ModelConfig.from_env()
        self.agent = Agent(
            self.model,
            system_prompt=SYSTEM_PROMPT,
            output_type=MultiPlatformContent,
        )

    def run(self, raw_notes: str) -> MultiPlatformContent:
        result = self.agent.run_sync(raw_notes)
        return result.output
