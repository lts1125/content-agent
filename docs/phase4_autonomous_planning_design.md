# 自主规划设计文档

## 背景

当前系统流程固定：
```
分析 → 搜索(可选) → 生成 → 评估 → 结束
```

问题：
1. 不能根据内容类型自动选择策略
2. 不能根据评估结果动态调整
3. 不能根据用户反馈学习

## 目标

实现自主规划：
```
Agent 根据输入自动选择最佳执行策略
```

## 设计

### 1. 内容类型识别

```python
class ContentType(Enum):
    DEEP_DIVE = "深度长文"      # 技术教程、源码分析
    HOT_NEWS = "热点快讯"       # 行业动态、产品发布
    TUTORIAL = "实战教程"       # 手把手教学
    REVIEW = "评测对比"         # 产品评测、方案对比
    OPINION = "观点评论"        # 个人见解、趋势判断
```

### 2. 策略定义

```python
@dataclass
class Strategy:
    name: str
    description: str
    steps: List[str]
    tools: List[str]
    max_attempts: int
    threshold: int
```

**预设策略**

| 策略 | 适用类型 | 步骤 | 工具 |
|------|---------|------|------|
| **深度研究** | DEEP_DIVE | 搜索→浏览→分析→生成→评估→修改 | search, browse, analyze, generate, evaluate |
| **热点快讯** | HOT_NEWS | 搜索→生成→评估 | search, generate, evaluate |
| **实战教程** | TUTORIAL | 读取→执行→生成→评估 | read, execute, generate, evaluate |
| **评测对比** | REVIEW | 搜索→浏览→分析→生成→评估 | search, browse, analyze, generate, evaluate |
| **观点评论** | OPINION | 搜索→生成→评估 | search, generate, evaluate |

### 3. 策略选择

```python
class StrategySelector:
    def select(self, raw_notes: str, topic: str) -> Strategy:
        """根据内容自动选择策略"""
        
        # 使用 LLM 判断内容类型
        prompt = f"""请判断以下内容属于哪种类型：

主题：{topic}
内容：{raw_notes[:500]}

选项：
- 深度长文（技术教程、源码分析）
- 热点快讯（行业动态、产品发布）
- 实战教程（手把手教学）
- 评测对比（产品评测、方案对比）
- 观点评论（个人见解、趋势判断）

请输出类型名称。"""
        
        result = self.llm_agent.run_sync(prompt)
        content_type = self._parse_type(result.output)
        
        return STRATEGIES[content_type]
```

### 4. 动态调整

```python
class AutonomousPlanner:
    def plan_and_execute(self, raw_notes: str, platforms: List[str]) -> ReActOutput:
        # 1. 选择策略
        strategy = self.strategy_selector.select(raw_notes, "")
        
        # 2. 执行策略
        context = AgentContext()
        for step in strategy.steps:
            if step == "search":
                result = self.tools["search"].execute(query=topic)
                context.research_report = result.data
            elif step == "browse":
                # 浏览搜索结果中的网页
                for url in extract_urls(context.research_report):
                    result = self.tools["browse"].execute(url=url)
                    context.research_report += f"\n\n{result.data}"
            elif step == "generate":
                result = self.tools["generate"].execute(
                    raw_notes=context.research_report or raw_notes,
                    platforms=platforms
                )
                context.draft_content = result.data
            elif step == "evaluate":
                result = self.tools["evaluate"].execute(**context.draft_content.to_dict())
                context.edit_verdict = result.data
                
                # 动态调整：如果评分低，增加修改步骤
                if result.data.overall < strategy.threshold:
                    strategy.steps.append("modify")
                    strategy.steps.append("evaluate")
            
            context.history.append(AgentMessage(
                from_agent="Planner",
                to_agent=step,
                message_type="result",
                content=str(result)
            ))
        
        return ReActOutput(
            content=context.draft_content,
            steps=context.history,
            reasoning=f"使用策略: {strategy.name}"
        )
```

### 5. 学习优化

```python
class StrategyLearner:
    def learn(self, execution_history: List[ExecutionRecord]):
        """从历史执行中学习最优策略"""
        
        for record in execution_history:
            content_type = record.content_type
            strategy = record.strategy
            score = record.final_score
            
            # 更新策略效果统计
            self.strategy_stats[content_type][strategy.name].append(score)
        
        # 为每种内容类型选择最优策略
        for content_type, stats in self.strategy_stats.items():
            best_strategy = max(stats, key=lambda s: sum(stats[s]) / len(stats[s]))
            self.strategy_recommendations[content_type] = best_strategy
```

## 实现计划

### Phase 1: 策略定义
- [ ] 定义 ContentType 枚举
- [ ] 定义预设策略
- [ ] 实现 StrategySelector

### Phase 2: 动态规划
- [ ] 实现 AutonomousPlanner
- [ ] 集成到 ReAct Agent
- [ ] 测试策略选择

### Phase 3: 学习优化
- [ ] 记录执行历史
- [ ] 实现 StrategyLearner
- [ ] 自动推荐最优策略

## 验收标准

1. 能自动识别内容类型
2. 能根据类型选择合适策略
3. 能根据评估结果动态调整
4. 能学习历史数据优化策略

## 风险

| 风险 | 缓解措施 |
|------|---------|
| 策略选择错误 | 允许用户手动覆盖 |
| 动态调整死循环 | 设置最大调整次数 |
| 学习数据不足 | 先使用预设策略，积累数据后再学习 |
