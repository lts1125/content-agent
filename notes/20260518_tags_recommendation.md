# 标签/话题推荐功能实现笔记

## 背景/需求

Roadmap P1-9：用户生成三平台文案后，需要手动想标签和话题。对于小红书来说，没有合适的 #话题 标签等于白写。需要一个自动推荐功能，基于笔记内容生成各平台相关的标签/话题。

## 设计思路

利用 LLM 的内容理解能力，在生成三平台文案的同时，额外输出推荐标签。这样只需要一次 API 调用，不增加额外成本。

方案对比：
- **额外调用 Agent 专门提取标签**：准确但多花一次 API 调用，成本高
- **修改 Pydantic Model 增加 tags 字段**：一次调用完成所有内容，零额外成本 ✅ 选用

## 核心实现

### 1. 修改 Pydantic Model（agent_core.py）

```python
class MultiPlatformContent(BaseModel):
    xiaohongshu: str
    gongzhonghao: str
    douyin: str
    recommended_tags: str
    """基于笔记内容生成的各平台推荐标签/话题，按平台分类列出，用户可直接复制使用"""
```

### 2. 修改 System Prompt（agent_core.py）

在 system prompt 末尾增加「推荐标签/话题」章节：

```
【推荐标签/话题】
请基于笔记内容，额外输出各平台的推荐标签/话题，格式如下：

📱 小红书（5-8个）：
#标签1 #标签2 #标签3 ...

💬 公众号（3-5个关键词）：
关键词1、关键词2、关键词3 ...

🎥 抖音（3-5个）：
#话题1 #话题2 #话题3 ...

要求：标签必须与笔记内容高度相关，避免泛泛而谈的热门词。
```

### 3. Web UI 适配（web_ui.py）

- **新增 UI 组件**：在右侧输出区 Tabs 下方添加 `tags_output` Textbox
- **generate_content**：收集 `generation_result.recommended_tags`，合并后 yield
- **refine_content**：优化时也返回新的 `recommended_tags`
- **restore_history**：从历史记录恢复时也恢复标签
- **history_state**：entry 中增加 `recommended_tags` 字段
- **事件绑定**：所有 `gr.click()` 的 outputs 增加 `tags_output`

### 4. CLI 适配（main.py）

在 `process_single_note` 中保存文案后，打印推荐标签到终端：

```python
if generation_result and generation_result.recommended_tags:
    print(f"\n   🏷️ 推荐标签/话题:")
    for line in generation_result.recommended_tags.strip().split("\n"):
        if line.strip():
            print(f"      {line.strip()}")
```

## 踩坑记录

1. **Pydantic Model 变更的兼容性问题** — 修改 `MultiPlatformContent` 后，所有使用它的代码都需要适配。`history_state` 中之前存储的 entry 没有 `recommended_tags` 字段，恢复时用 `.get("recommended_tags", "")` 做兼容处理。

2. **批量模式的标签处理** — 批量生成多篇笔记时，每篇都有自己的标签。UI 上只显示第一篇的标签（因为标签通常和单篇内容强相关），但 history 中每篇都保存了自己的标签。

3. **Gradio 事件绑定的 outputs 数量必须匹配** — 修改 `generate_content` 的 yield 返回值后，所有调用它的 `gr.click()` 的 outputs 列表必须同步增加 `tags_output`，否则 Gradio 会报错。

## 使用方法

Web UI：
1. 输入笔记 → 生成文案
2. 在右侧输出区找到「🏷️ 推荐标签/话题」区域
3. 直接复制使用

CLI：
```bash
python main.py -i notes.md
# 终端输出中会打印推荐标签/话题
```

## 下一步

P1 最后一项：**敏感词预检**（P1-10）
