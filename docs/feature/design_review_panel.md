# 审核面板设计文档

> 目标：把后台自动跑的质量检查搬到前台 UI，让用户能看到每条规则检查结果，并一键采纳修改或忽略某项。解决当前“评分不合格就直接报错”的痛点。

---

## 一、现状分析

### 1.1 当前流程

```
用户输入需求 → Agent 搜索→生成文案 → LLMScorer 评分
                                      ↓
                              分数 ≥ 阈值：通过，返回结果
                              分数 < 阈值：硬重试 3 次 → 还是不行 → 告诉用户"生成失败"
```

问题：
- 用户看不到到底哪条规则不合格
- 重试 3 次就放弃，不给用户任何干预机会
- 如果只是某一项微调（比如口语化评分低了 5 分），用户完全没机会说"忽略这项，直接发"

### 1.2 LLMScorer 现状

从 `agents/eval.py` 或类似文件中，LLMScorer 会从多个维度评分：
- 相关性（relevance）
- 可读性（readability）
- 原创性（originality）
- 实用性（practicality）
- 平台适配度（platform_fit）
- 热点匹配度（trend_match）

返回结果包含：
- `overall`: 整体得分
- `scores`: 各维度分数
- `passed`: 是否通过
- `weakest`: 最弱的维度
- `suggestions`: 改进建议
- `verdict`: 评语文本

这些数据目前只在后台使用，用户看不到。

---

## 二、设计方案

### 2.1 新的流程

```
用户输入需求 → Agent 搜索→生成文案 → LLMScorer 评分
                                      ↓
                              分数 ≥ 阈值：通过，返回结果
                              分数 < 阈值：进入审核面板
                                      ↓
                              展示各维度得分、建议、修改方案
                              用户可以：
                                - 点"采纳修改" → Agent 重新生成
                                - 点"忽略此项" → 从评分中删除该维度，重新计算总分
                                - 点"强行发布" → 不管评分直接返回结果
```

### 2.2 核心概念

**审核面板（ReviewPanel）**

审核面板是一个数据结构，包含：
- `verdict`: 原始评分结果
- `items`: 各条规则的展示状态（包含用户是否忽略）
- `user_decision`: 用户最终决策（revise / ignore / force_publish）
- `revision_prompt`: 如果用户选择修改，生成的修改指令

### 2.3 UI 交互流程

在 Gradio 中，审核面板会在生成完成后以特殊的消息形式展示：

```
🔍 质量检查报告

整体得分: 78/100 ❌ 未达标

| 维度 | 得分 | 状态 | 建议 |
|-------|------|------|--------|
| 相关性 | 90 | ✅ | - |
| 可读性 | 85 | ✅ | - |
| 原创性 | 70 | ✅ | - |
| 口语化 | 55 | ❌ | 添加更多口语化表达 |
| 热点匹配 | 60 | ❌ | 结合当前热点再开展 |

[采纳修改] [忽略未通过项] [强行发布]
```

Gradio 不支持消息内嵌交互按钮。所以实际实现会用以下方式：

**方案 A：文本指令式**

审核面板以 Markdown 形式展示，用户输入特定命令来响应：
- 输入 `revise` → 采纳修改，重新生成
- 输入 `ignore` → 忽略未通过项，重新计算总分
- 输入 `publish` → 强行发布

**方案 B：快捷按钮式**

在审核面板消息下方添加三个快捷按钮（通过 Gradio 的 `gr.Button`）：
- "采纳修改" → 触发重新生成
- "忽略并继续" → 触发重新评分（忽略未通过项）
- "强行发布" → 直接返回结果

推荐方案 B，交互更直观。

---

## 三、数据模型

### 3.1 ReviewPanel 数据类

新建 `agents/review.py`：

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ReviewItem:
    """单条规则检查项"""
    dimension: str           # 维度名称
    score: int               # 得分
    threshold: int           # 阈值
    passed: bool             # 是否通过
    suggestion: str          # 改进建议
    ignored: bool = False    # 用户是否忽略此项

@dataclass
class ReviewPanel:
    """审核面板"""
    overall: int
    threshold: int
    passed: bool
    items: List[ReviewItem]
    verdict_text: str
    user_decision: Optional[str] = None  # "revise" | "ignore" | "force_publish"
    revision_prompt: str = ""

    @property
    def effective_score(self) -> int:
        """计算有效得分（忽略未通过项后重新计算）"""
        if self.passed:
            return self.overall
        active_items = [i for i in self.items if not i.ignored]
        if not active_items:
            return self.overall
        return int(sum(i.score for i in active_items) / len(active_items))

    @property
    def effective_passed(self) -> bool:
        """忽略后是否通过"""
        return self.effective_score >= self.threshold

    def get_revision_prompt(self) -> str:
        """生成修改指令"""
        failed_items = [i for i in self.items if not i.passed and not i.ignored]
        if not failed_items:
            return "请根据整体评分修改文案"
        lines = ["请重点修改以下方面："]
        for item in failed_items:
            lines.append(f"- {item.dimension}: {item.suggestion}")
        return "\n".join(lines)
```

### 3.2 数据库表

在 `agents/store.py` 中新增 `review_panels` 表：

```sql
CREATE TABLE IF NOT EXISTS review_panels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT    NOT NULL,
    overall     INTEGER,
    threshold   INTEGER,
    passed      INTEGER,
    verdict_text TEXT,
    user_decision TEXT,
    revision_prompt TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS review_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    panel_id    INTEGER NOT NULL,
    dimension   TEXT    NOT NULL,
    score       INTEGER,
    threshold   INTEGER,
    passed      INTEGER,
    suggestion  TEXT,
    ignored     INTEGER DEFAULT 0,
    FOREIGN KEY (panel_id) REFERENCES review_panels(id)
);
```

---

## 四、接口设计

### 4.1 ReviewManager 类

```python
class ReviewManager:
    """审核管理器：将 LLMScorer 结果转换为审核面板，处理用户决策。
    """

    def create_panel(self, verdict: EditVerdict, threshold: int = 75) -> ReviewPanel:
        """根据评分结果创建审核面板"""

    def apply_user_decision(self, panel: ReviewPanel, decision: str) -> dict:
        """
        应用用户决策。

        Returns:
            {
                "action": "revise" | "retry" | "publish",
                "prompt": str,           # 如果是 revise，这是修改指令
                "should_continue": bool, # 是否继续生成流程
            }
        """

    def save_panel(self, panel: ReviewPanel, task_id: str) -> None:
        """持久化审核面板"""

    def load_panel(self, task_id: str) -> Optional[ReviewPanel]:
        """加载审核面板"""
```

### 4.2 与 ChatAgent 集成

修改 `_handle_generate_stream`：

1. 生成完成后，调用 LLMScorer 评分
2. 如果未通过，创建 ReviewPanel
3. 不是直接重试，而是返回特殊的 "review" 类型结果
4. UI 展示审核面板，等待用户点击按钮
5. 根据用户选择：
   - 采纳修改 → 用 revision_prompt 重新生成
   - 忽略未通过项 → 重新计算得分，如果通过则返回结果
   - 强行发布 → 直接返回结果

---

## 五、Gradio UI 实现

### 5.1 审核面板消息格式

当生成完成但评分未通过时，返回的结果类型从 `"content"` 变为 `"review"`：

```python
{
    "type": "review",
    "panel": ReviewPanel,
    "content": "原始生成内容...",
    "platforms": [...],
    "files": [...],
}
```

### 5.2 UI 组件

在 `create_chat_ui()` 中添加三个审核按钮（默认隐藏）：

```python
with gr.Row(visible=False) as review_row:
    btn_revise = gr.Button("采纳修改", variant="primary")
    btn_ignore = gr.Button("忽略并继续")
    btn_force = gr.Button("强行发布")
```

当收到 `review` 类型结果时：
1. 显示审核按钮
2. 用户点击后触发相应处理

### 5.3 事件处理

每个按钮都绑定一个隐藏的 `gr.Textbox`来传递用户决策：

```python
decision_state = gr.State(None)

def on_review_decision(decision, panel_data, content, platforms, files):
    # 根据决策执行相应操作
    if decision == "revise":
        # 重新生成
        pass
    elif decision == "ignore":
        # 忽略未通过项，检查是否达标
        pass
    elif decision == "force_publish":
        # 直接返回结果
        pass

btn_revise.click(lambda: "revise", outputs=decision_state)
btn_ignore.click(lambda: "ignore", outputs=decision_state)
btn_force.click(lambda: "force_publish", outputs=decision_state)
```

---

## 六、关键边界条件

1. **审核流程只在 chat_ui 中实现**：CLI 模式保持现有的自动重试逻辑
2. **审核面板不阻断生成**：用户可以选择"强行发布"直接结束
3. **忽略项有上限**：最多忽略 2 项，避免用户全部忽略导致质量下降
4. **修改有次数限制**：采纳修改后最多再重试 2 次，避免无限循环
5. **审核结果持久化**：每次审核都保存到 review_panels 表，便于后续分析
