# 审核面板（ReviewPanel）功能实现

## 背景/需求

当前流程问题：生成文案后如果评分不合格，后台会自动重试3次，然后直接报错告诉用户"生成失败"。用户看不到哪条规则不合格，也没有任何干预机会。

目标：把后台质量检查搬到 Gradio 前台 UI，让用户能看到各维度得分和建议，并一键采纳修改或忽略未通过项。

## 设计思路

核心方案：在 `planner.py` 中添加 `enable_review_panel` 参数，评估未通过时不自动重试，而是返回 `review` 类型结果。`chat_ui.py` 收到后展示审核面板，等待用户点击操作按钮。

## 核心实现

### 1. 审核面板数据结构（agents/review.py）

```python
@dataclass
class ReviewItem:
    dimension: str
    score: int
    threshold: int
    passed: bool
    suggestion: str
    ignored: bool = False

@dataclass
class ReviewPanel:
    overall: int
    threshold: int
    passed: bool
    items: List[ReviewItem]
    verdict_text: str
    user_decision: Optional[str] = None
    revision_prompt: str = ""
    revision_count: int = 0  # 采纳修改并重新生成的次数
```

`ReviewManager` 提供 `create_panel`、`apply_user_decision`、`save_panel`、`load_panel` 等方法。

### 2. 数据库表（agents/store.py）

新增 `review_panels` 和 `review_items` 两张表，通过 `panel_id` 关联。提供 `save_review_panel`、`load_review_panel`、`list_review_panels` 三个函数。

### 3. 与编排器集成（agents/planning/planner.py）

```python
def plan_and_execute(..., enable_review_panel: bool = False):
    # ... 生成和评估 ...
    if enable_review_panel and not verdict.passed:
        panel = ReviewManager.create_panel(verdict)
        return {"type": "review", "panel": panel, ...}
    # ... 原有的自动重试逻辑 ...
```

### 4. Gradio UI（chat_ui.py）

- 添加 `review_row` 按钮组（采纳修改 / 忽略未通过项 / 强行发布），默认隐藏
- 添加 `review_state = gr.State(None)` 保存当前审核面板数据
- `_result_to_response` 识别 `review` 类型，显示按钮
- `on_revise_generate` 自动携带修改意见重新生成

### 5. 修改次数限制

设计文档要求：采纳修改后最多再重试 2 次，避免无限循环。

- `ReviewPanel.revision_count` 记录已重试次数
- `ReviewPanel.can_revise()` 检查是否超过 `MAX_REVISION_ATTEMPTS = 2`
- `on_revise_generate` 中超限时提示用户选择忽略或强行发布
- `to_markdown()` 显示当前重试次数和剩余次数

## 踩坑记录

1. **测试环境不完整** — chat_ui 导入链走到 agents/writer_agent.py 时缺 pydantic_ai，再走到 agents/memory.py 时缺 chromadb。解决方案：用 `.venv/bin/python` 运行测试，虚拟环境里依赖已齐。

2. **gradiomock 不完善** — 测试文件中 `sys.modules["gradio"] = _mock_gr`，但 `_mock_gr.Blocks` 是 `MagicMock` 类而不是实例，导致 chat_ui 导入时 `gr.Blocks.get_api_info` 报 `AttributeError`。解决方案：改为 `_mock_gr.Blocks = unittest.mock.MagicMock()` 并添加 `get_api_info` 属性。

3. **系统环境被污染** — 运行 pip install 时忘了 `source .venv/bin/activate`，把大量包装到了 `/Users/lee/Library/Python/3.9/。解决方案：`pip uninstall -y` 清理后，以后先激活虚拟环境再操作。

## 使用方法

```bash
source .venv/bin/activate
python tests/test_review_panel.py -v
```

当前测试状态：18 个测试全部通过，0 跳过。

## 历史记录查询

### 实现

新增 `review_history.py` CLI 工具，支持三个子命令：

```bash
source .venv/bin/activate
python review_history.py list          # 列出最近20条
python review_history.py show <id>     # 查看详情
python review_history.py stats         # 统计概览
```

输出格式为 Markdown 表格，可直接复制到笔记。

### 数据库扩展

`agents/store.py` 新增 `get_review_panel_detail(panel_id)` 函数，返回包含所有评分项的完整记录。

## 下一步

- [ ] 考虑是否把历史记录查询集成到 chat_ui 的某个 Tab 或 Accordion 中
