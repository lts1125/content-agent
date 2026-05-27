# 多 Agent 协作设计文档

## 背景

当前系统采用单 Agent 串行流程：
```
Writer → Editor → 结束
```

问题：
1. Writer 和 Editor 没有真正协作，只是先后执行
2. Researcher 只在 ReAct 中简单搜索，没有深度研究
3. 各 Agent 之间没有信息共享和反馈循环

## 目标

实现多 Agent 协作系统：
```
Orchestrator → 调度多个 Agent 并行/串行工作
```

## 设计

### 1. Agent 角色定义

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| **Orchestrator** | 任务分解、调度、汇总 | 用户请求 | 执行计划 |
| **Researcher** | 资料搜集、事实核查 | 主题/关键词 | 研究报告 |
| **Writer** | 内容生成 | 资料 + 风格要求 | 初稿 |
| **Editor** | 质量检查、修改建议 | 初稿 | 评估报告 |
| **Designer** | 配图设计 | 内容 | 配图方案 |

### 2. 协作流程

```
用户请求
    ↓
Orchestrator 分解任务
    ↓
Researcher 搜集资料（并行）
    ↓
Writer 生成初稿
    ↓
Editor 评估（并行）
    ↓
如果评分 < 80：
    Writer 修改（基于 Editor 反馈）
    Editor 再评估
    循环直到通过
    ↓
Designer 设计配图（并行）
    ↓
Orchestrator 汇总输出
```

### 3. 通信机制

**共享上下文（Shared Context）**
```python
@dataclass
class AgentContext:
    task_id: str
    topic: str
    raw_notes: str
    research_report: str = ""
    draft_content: WriterOutput = None
    edit_verdict: EditVerdict = None
    style_profile: StyleProfile = None
    history: List[AgentMessage] = field(default_factory=list)
```

**消息格式**
```python
@dataclass
class AgentMessage:
    from_agent: str
    to_agent: str
    message_type: str  # "request", "feedback", "result"
    content: str
    timestamp: str
```

### 4. 并行执行

```python
# Researcher 和 风格分析 并行
with ThreadPoolExecutor() as executor:
    future_research = executor.submit(researcher.run, topic)
    future_style = executor.submit(style_analyzer.run, history)
    
    research_report = future_research.result()
    style_profile = future_style.result()

# Writer 使用两者结果生成
writer.run(research_report, style_profile)
```

### 5. 迭代优化

```python
for attempt in range(max_attempts):
    draft = writer.generate(context)
    verdict = editor.evaluate(draft)
    
    if verdict.overall >= 80:
        break
    
    # 将 Editor 反馈加入上下文
    context.edit_verdict = verdict
    context.history.append(AgentMessage(
        from_agent="Editor",
        to_agent="Writer",
        message_type="feedback",
        content=verdict.suggestions[0]
    ))
```

## 实现计划

### Phase 1: 基础设施
- [ ] 创建 `agents/orchestrator.py`
- [ ] 创建 `agents/collaboration/` 目录
- [ ] 实现 `AgentContext` 和 `AgentMessage`
- [ ] 实现基础通信机制

### Phase 2: Agent 改造
- [ ] Researcher 增强：深度搜索、多源验证
- [ ] Writer 改造：接收风格画像和研究报告
- [ ] Editor 改造：输出结构化反馈
- [ ] Designer 改造：接收内容生成配图

### Phase 3: 协作流程
- [ ] 实现并行执行
- [ ] 实现迭代优化循环
- [ ] 实现 Orchestrator 调度

### Phase 4: 集成测试
- [ ] 测试多 Agent 协作流程
- [ ] 性能测试
- [ ] 稳定性测试

## 技术选型

- **并行执行**: `concurrent.futures.ThreadPoolExecutor`
- **通信**: 内存共享（同进程）
- **状态管理**: `AgentContext` 对象
- **日志**: 结构化日志记录协作过程

## 风险

| 风险 | 缓解措施 |
|------|---------|
| 并行执行复杂 | 先实现串行，再逐步并行化 |
| 上下文膨胀 | 限制历史消息数量，只保留关键信息 |
| 死循环 | 设置最大迭代次数 |
| 性能下降 | 监控各 Agent 执行时间，优化慢节点 |

## 验收标准

1. 多 Agent 能协作完成内容生成任务
2. 协作过程可追溯（日志记录）
3. 迭代优化能提升内容质量
4. 性能不劣于单 Agent 流程
