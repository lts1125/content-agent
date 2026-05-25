# ReAct 改造设计文档

> 将当前生成-编辑循环升级为标准 ReAct Agent
> 时间：2026-05-25

---

## 1. 目标

- 增加推理步骤（Thought）
- 增加工具调用（Action）
- 增加环境观察（Observation）
- 形成完整的 ReAct 循环

## 2. 核心改造

### 2.1 增加工具系统

```python
class Tool:
    name: str
    description: str
    parameters: dict
    
    def execute(self, **kwargs) -> str:
        ...

# 工具列表
TOOLS = {
    "search": SearchTool(),           # 搜索热点/资料
    "browse": BrowseTool(),           # 浏览网页
    "analyze": AnalyzeTool(),         # 数据分析
    "generate": GenerateTool(),       # 生成内容
    "evaluate": EvaluateTool(),       # 评估内容
    "publish": PublishTool(),         # 发布内容
}
```

### 2.2 ReAct 循环

```python
class ReActAgent:
    def run(self, goal: str) -> str:
        context = []
        
        for step in range(max_steps):
            # 1. Thought
            thought = self.think(goal, context)
            context.append(f"Thought: {thought}")
            
            # 2. Action
            action = self.decide_action(thought)
            context.append(f"Action: {action}")
            
            # 3. Observation
            observation = self.execute_action(action)
            context.append(f"Observation: {observation}")
            
            # 检查是否完成
            if self.is_complete(goal, context):
                return self.generate_result(context)
        
        return self.generate_result(context)
```

### 2.3 Prompt 改造

```
你是一个内容创作 Agent。请按照 ReAct 格式思考和工作。

格式：
Thought: [你的思考过程]
Action: [工具名称]([参数])
Observation: [工具返回结果]

可用工具：
- search(query): 搜索网络资料
- browse(url): 浏览网页内容
- generate(content): 生成内容
- evaluate(content): 评估内容质量

目标：根据笔记生成三平台内容
```

## 3. 与现有系统集成

### 3.1 保留部分
- WriterAgent（作为 generate 工具）
- EditorAgent（作为 evaluate 工具）
- FeedbackAgent（作为 analyze 工具）
- RAG 检索（作为 search 工具的一种）

### 3.2 新增部分
- 网络搜索工具
- 网页浏览工具
- 推理步骤（Thought）
- 循环控制器

## 4. 实现步骤

1. **定义工具接口**（1 天）
2. **改造 Orchestrator**（2 天）
3. **增加推理 Prompt**（1 天）
4. **测试验证**（1 天）

## 5. 预期效果

```
用户：写一篇关于 MCP 的文章

Agent:
Thought: 用户想写 MCP 文章，我需要先了解 MCP 的最新动态
Action: search("MCP 协议 最新进展 2026")
Observation: 找到 5 篇相关文章，最新的是...

Thought: 根据搜索结果，MCP 最近有重要更新，我应该重点介绍
Action: generate(结合搜索结果生成内容)
Observation: 生成完成，Editor 评分 70，需要改进

Thought: 评分 70 说明内容不够深入，我需要增加代码示例
Action: refine(增加代码示例)
Observation: 修改完成，Editor 评分 85，通过

Thought: 内容已通过审核，可以发布
Action: publish(发布到三平台)
Observation: 发布成功
```

## 6. 工作量

预计 5 天完成改造。
