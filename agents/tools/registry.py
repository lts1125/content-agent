"""
工具注册表
"""

from typing import Dict, Optional, Tuple, Type

from .base import BaseTool, ToolResult
from .search import SearchTool
from .browse import BrowseTool
from .file_read import FileReadTool
from .generate import GenerateTool
from .evaluate import EvaluateTool
from .publish import PublishTool
from .analysis import DataAnalysisTool
from .code_execution import CodeExecutionTool


# 工具类注册表（懒加载，导入时不实例化）
# 格式: name -> (ToolClass, description)
_TOOL_SPECS: Dict[str, Tuple[Type[BaseTool], str]] = {
    "search": (SearchTool, "搜索网络资料，获取最新信息。参数: query(搜索关键词)"),
    "browse": (BrowseTool, "浏览网页内容，获取详细信息。参数: url(网页地址)"),
    "read": (FileReadTool, "读取本地文件内容。参数: path(文件路径)"),
    "generate": (GenerateTool, "生成内容。参数: raw_notes(原始笔记), platforms(平台列表), style(风格)"),
    "evaluate": (EvaluateTool, "评估内容质量。参数: xiaohongshu(小红书内容), gongzhonghao(公众号内容), douyin(抖音内容)"),
    "publish": (PublishTool, "发布内容到平台。参数: queue_id(队列项ID)"),
    "analyze": (DataAnalysisTool, "分析数据并生成洞察。参数: data(数据内容), analysis_type(分析类型: summary/trend/comparison)"),
    "execute": (CodeExecutionTool, "执行 Python 代码并返回结果。参数: code(代码字符串)"),
}

# 工具实例缓存
_tool_instances: Dict[str, BaseTool] = {}


def get_tool(name: str) -> Optional[BaseTool]:
    """获取工具实例（懒加载，第一次取用时实例化）"""
    if name not in _tool_instances and name in _TOOL_SPECS:
        cls, _ = _TOOL_SPECS[name]
        _tool_instances[name] = cls()
    return _tool_instances.get(name)


def list_tools() -> list:
    """列出所有可用工具（不触发实例化）"""
    return [f"- {name}: {desc}" for name, (_, desc) in _TOOL_SPECS.items()]


def execute_tool(name: str, **kwargs) -> ToolResult:
    """执行指定工具"""
    tool = get_tool(name)
    if tool is None:
        return ToolResult(success=False, data="", error=f"未知工具: {name}")
    return tool.execute(**kwargs)


# 保留向后兼容：TOOL_REGISTRY 属性指向实例缓存
TOOL_REGISTRY = _tool_instances
