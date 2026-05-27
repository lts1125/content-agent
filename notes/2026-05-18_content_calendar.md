# 内容日历管理功能实现笔记

## 背景/需求

Roadmap P2-2：用户需要管理内容发布计划，跟踪每篇文案的状态（草稿 → 已排期 → 已生成 → 已发布）。之前用 Excel 或备忘录管理，容易遗漏，且和生成工具不联动。

## 设计思路

1. **数据模型** — 用 dataclass 定义发布计划条目，包含标题、主题、平台、排期日期、状态、关联笔记文件
2. **状态流转** — 草稿 → 已排期 → 已生成 → 已发布，单向流转
3. **数据持久化** — JSON 文件存储在 `~/.content_agent/calendar.json`，跨会话保留
4. **Web UI 集成** — 在 Gradio 中提供完整的增删改查界面

## 核心实现

### 1. 数据模型（calendar.py）

```python
@dataclass
class CalendarEntry:
    id: str
    title: str
    topic: str
    platforms: list[str]
    scheduled_date: str       # YYYY-MM-DD
    status: str               # draft, scheduled, generated, published
    note_file: str            # 关联笔记文件路径
    created_at: str
    updated_at: str
```

### 2. ContentCalendar 类

```python
class ContentCalendar:
    CONFIG_DIR = Path.home() / ".content_agent"
    DATA_FILE = CONFIG_DIR / "calendar.json"

    STATUS_MAP = {
        "草稿": "draft",
        "已排期": "scheduled",
        "已生成": "generated",
        "已发布": "published",
    }

    def add(self, title, topic, platforms, scheduled_date, note_file, status="draft"):
        entry_id = f"cal_{int(time.time() * 1000)}"
        # ... 创建并保存

    def update(self, entry_id, **kwargs):
        # ... 更新字段并重新保存

    def delete(self, entry_id):
        # ... 删除并重新保存

    def list_entries(self, filter_status=None, filter_date_from=None, filter_date_to=None):
        # ... 筛选、排序并返回
```

### 3. 自动持久化

每次 `add` / `update` / `delete` 内部都会自动调用 `_save()`：

```python
def _save(self):
    self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {"entries": [asdict(e) for e in self.entries.values()]}
    with open(self.DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

### 4. Web UI 集成

在 Web UI 新增「内容日历」Tab：

- **左侧**：添加计划表单（标题、主题、平台、排期日期、关联文件、状态）
- **右侧**：计划列表 + 筛选下拉框（全部/本周/本月/按状态）
- **操作**：选中后可编辑或删除

```python
with gr.TabItem("📅 内容日历"):
    # 左侧：添加/编辑表单
    # 右侧：计划列表 + 筛选
```

### 5. 筛选功能

```python
def refresh_calendar_entries(filter_type):
    if filter_type == "本周":
        entries = cal.get_upcoming(days=7)
    elif filter_type == "本月":
        entries = cal.get_upcoming(days=30)
    elif filter_type in cal.STATUS_MAP:
        entries = cal.list_entries(filter_status=filter_type)
    else:
        entries = cal.list_entries()
    return dropdown, markdown_list
```

## 踩坑记录

1. **日期格式统一** — 全部使用 `YYYY-MM-DD` 字符串，排序时直接用字符串比较，无需转换为 datetime 对象。

2. **状态中文与英文的映射** — UI 上显示中文（草稿/已排期/已生成/已发布），存储用英文（draft/scheduled/generated/published）。用 `STATUS_MAP` 和 `STATUS_MAP_REVERSE` 做双向转换。

3. **Gradio 事件绑定的返回值数量** — 编辑时需要同时更新表单多个字段 + 状态提示 + 下拉框选项，事件绑定的 outputs 列表必须与函数返回值数量完全一致，否则 Gradio 报错。

4. **下拉框的值类型** — Gradio Dropdown 的 value 可能是列表也可能是字符串，在处理时需要小心。特别是多选平台时，平台字段存为 `list[str]`，但表单传回的可能是单个字符串。

5. **定时任务与日历的联动** — 定时任务生成文案后，可以自动在日历中创建或更新条目状态。这部分目前需要手动关联，自动联动作为下一步优化。

## 使用方法

Web UI：
1. 打开「内容日历」Tab
2. 填写标题、主题、选择平台、设置排期日期
3. 点击「添加计划」
4. 在列表中选择条目，可以编辑或删除
5. 用筛选查看本周/本月/按状态的计划

数据保存在 `~/.content_agent/calendar.json`，跨次启动自动恢复。

## 下一步

- 定时任务生成文案后自动更新日历状态
- 支持导出日历为 Markdown / 表格
- 支持循环计划（每周一篇的固定栏目）
