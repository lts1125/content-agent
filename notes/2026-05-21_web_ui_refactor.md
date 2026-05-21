# web_ui.py 拆分重构

## 背景
web_ui.py 已达到 1894 行，单文件维护困难。决定拆分为 web_ui.py + ui/handlers.py。

## 拆分后结构

| 文件 | 行数 | 职责 |
|---|---|---|
| web_ui.py | ~1009 | UI 组件定义 + 事件绑定 + 启动入口 |
| ui/handlers.py | ~994 | 所有业务处理函数（生成、导出、发布、配置、Vault、快发 CLI 等） |

## 拆分边界

**web_ui.py 保留：**
- 顶部导入（gradio、handlers、其他模块）
- Gradio UI 组件定义（with gr.Blocks 主体）
- 事件绑定中内联定义的辅助函数（如 refresh_history_list、add_scheduled_task 等）
- `if __name__ == "__main__"` 启动逻辑

**ui/handlers.py 移入：**
- 配置管理（.env 读写、get_config_status、load/save config）
- 配置模板管理（内置模板 + 用户自定义模板）
- Obsidian Vault 扫描/读取
- 文件上传处理
- kuaifa CLI 配置管理
- 生成核心逻辑（generate_content、refine_content、generate_titles、generate_cover_prompt）
- 历史记录恢复
- 导出功能（Markdown/Word）
- 发布到微信公众号
- Agent/Checker/Orchestrator 缓存实例

## 注意事项
- handlers.py 依赖 gradio，因为多个函数返回 gr.update()/gr.Progress()
- 为避免循环导入，handlers.py 不导入 web_ui.py 中的任何内容
- 内联辅助函数（如 _save_template_and_refresh）仍留在 web_ui.py 中，因为它们直接操作 Gradio 组件更新

## 验证
- `python3 -m py_compile web_ui.py ui/handlers.py` — 通过
