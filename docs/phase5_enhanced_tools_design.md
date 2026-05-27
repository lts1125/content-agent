# 增强工具设计文档

## 背景

当前可用工具：
- search：DuckDuckGo 搜索
- generate：生成内容
- evaluate：评估内容
- publish：发布内容

缺少：网页浏览、数据分析、代码执行等

## 目标

增加工具，让 Agent 能：
1. 浏览网页获取实时信息
2. 分析数据生成图表
3. 执行代码验证想法
4. 读取文件获取资料

## 设计

### 1. 网页浏览工具

```python
class BrowseTool(BaseTool):
    """网页浏览工具"""
    
    def execute(self, url: str) -> ToolResult:
        """获取网页内容"""
        try:
            from web_extract import web_extract
            content = web_extract([url])
            return ToolResult(success=True, data=content)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

### 2. 数据分析工具

```python
class DataAnalysisTool(BaseTool):
    """数据分析工具"""
    
    def execute(self, data: str, analysis_type: str = "summary") -> ToolResult:
        """分析数据"""
        try:
            # 使用 LLM 分析数据
            prompt = f"请分析以下数据，输出{analysis_type}：\n\n{data}"
            result = self.llm_agent.run_sync(prompt)
            return ToolResult(success=True, data=result.output)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

### 3. 代码执行工具

```python
class CodeExecutionTool(BaseTool):
    """代码执行工具"""
    
    def execute(self, code: str, language: str = "python") -> ToolResult:
        """执行代码"""
        try:
            if language == "python":
                # 使用安全沙箱执行
                result = execute_code_sandbox(code)
                return ToolResult(success=True, data=result)
            else:
                return ToolResult(success=False, error=f"不支持的语言: {language}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

### 4. 文件读取工具

```python
class FileReadTool(BaseTool):
    """文件读取工具"""
    
    def execute(self, path: str) -> ToolResult:
        """读取文件内容"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return ToolResult(success=True, data=content)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

## 工具注册

```python
# agents/tools.py
TOOLS = {
    "search": SearchTool(),
    "browse": BrowseTool(),
    "generate": GenerateTool(),
    "evaluate": EvaluateTool(),
    "analyze": DataAnalysisTool(),
    "execute": CodeExecutionTool(),
    "read": FileReadTool(),
    "publish": PublishTool(),
}
```

## 使用场景

| 场景 | 工具组合 |
|------|---------|
| 热点分析 | search + browse + analyze |
| 技术验证 | search + execute + evaluate |
| 深度研究 | search + browse + read + analyze |
| 数据报告 | read + analyze + generate |

## 实现计划

### Phase 1: 基础工具
- [ ] BrowseTool
- [ ] FileReadTool

### Phase 2: 高级工具
- [ ] DataAnalysisTool
- [ ] CodeExecutionTool

### Phase 3: 集成测试
- [ ] 测试各工具
- [ ] 测试工具组合

## 安全考虑

| 工具 | 风险 | 缓解措施 |
|------|------|---------|
| browse | 访问恶意网站 | 限制域名白名单 |
| execute | 执行危险代码 | 沙箱执行，限制资源 |
| read | 读取敏感文件 | 限制文件路径 |

## 验收标准

1. 各工具能独立工作
2. 工具组合能完成复杂任务
3. 安全限制有效
