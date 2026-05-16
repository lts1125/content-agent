# 批量处理多篇笔记实现记录

## 背景/需求

之前每次只能处理单篇笔记，用户积累多篇笔记后需要逐个跑，效率低。需要支持批量处理整个目录下的所有 `.md`/`.txt` 文件。

## 设计思路

**核心目标**：
- 输入可以是文件或目录
- 批量模式下每个笔记独立输出到子目录
- 共享同一个 Agent 实例（节省初始化开销）
- 显示处理进度和最终统计

**输出结构**：

单文件模式：
```
output/20260516/
  20260516_101000_xiaohongshu.md
  配图/xiaohongshu_cards.html
```

批量模式：
```
output/20260516/
  ai_invades_daily/
    20260516_101000_xiaohongshu.md
    配图/xiaohongshu_cards.html
  CLI工具化改造笔记/
    20260516_101001_gongzhonghao.md
    ...
```

## 核心实现

### 1. 提取 `process_single_note()` 函数

把原来的单文件处理逻辑（搜索增强 → 生成 → 质检 → 保存 → 配图）提取成独立函数：

```python
def process_single_note(
    note_path: Path,
    raw_notes: str,
    agent: ContentAgent,      # 共享实例
    checker: QualityChecker,  # 共享实例
    enabled_platforms: set,
    args,
    note_output_dir: Path,
) -> dict:
    ...
    return {"success": bool, "saved_files": list, "error": str|None}
```

### 2. 新增 `_collect_notes()` 函数

自动识别输入类型，收集所有笔记文件：

```python
def _collect_notes(input_path: Path) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    # 递归遍历 .md 和 .txt
    for ext in ("*.md", "*.txt"):
        notes.extend(input_path.glob(ext))
        notes.extend(input_path.rglob(ext))
```

### 3. 重写 `main()` 支持两种模式

```python
# 检测输入类型
note_files = _collect_notes(input_path)
is_batch = input_path.is_dir()

# 共享 Agent 和 Checker
agent = ContentAgent()
checker = QualityChecker(agent.model)

# 逐个处理
for idx, note_path in enumerate(note_files, 1):
    print(f"进度: {idx}/{len(note_files)}")
    result = process_single_note(...)

# 最终统计
print(f"{success_count}/{len(note_files)} 个笔记处理成功")
```

## 踩坑记录

1. **缩进错误**：`process_single_note` 里配图生成代码缩进多了一层，导致 `IndentationError`。修复后 lint 通过。

2. **API 调用超时**：批量处理 4 个笔记时，每个笔记要调多次 API（生成 + 质检），DeepSeek API 响应慢，总时间超过 600 秒。实际使用时建议：
   - 一次不要处理太多（2-3 篇为宜）
   - 或关闭质量检查加速
   - 或换更快的模型（如 GPT-4o-mini）

3. **`List` 类型注解未导入**：`_collect_notes` 返回 `List[Path]`，但 `main.py` 没导入 `typing.List`。已补 `from typing import List`。

4. **`html_path.name` 报错**：`renderer.render()` 返回字符串路径，但代码里调用了 `.name`（Path 属性）。修复：`html_name = Path(html_path).name`。

## 使用方法

```bash
# 单文件（原有功能不变）
python main.py -i notes/my_note.md

# 批量处理目录
python main.py -i notes/

# 批量 + 搜索增强
python main.py -i notes/ -r --search-engine tavily

# 批量 + 只生成小红书
python main.py -i notes/ -p xiaohongshu
```

## 下一步

- [ ] Web UI（Gradio/Streamlit）
- [ ] 批量处理时支持并发（需考虑 API 速率限制）
- [ ] 处理结果缓存，避免重复生成
