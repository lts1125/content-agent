# 本地笔记库联动（Obsidian / Markdown 目录）

## 背景/需求

用户希望能直接从本地 Markdown 笔记库（如 Obsidian Vault）中选择笔记，而不是每次手动粘贴或上传文件。这样可以让已有笔记工作流的用户无缝对接，提升生成效率。

## 设计思路

1. 用户配置一个本地目录路径作为“笔记库”
2. 程序递归扫描该目录下的所有 `.md` 文件
3. UI 上用 Dropdown 列出文件，用户选择后自动读取内容填充到输入框
4. 路径持久化到 `.env` 文件，下次启动自动恢复

## 核心实现

### 1. Vault 路径存取（web_ui.py）

```python
def _get_vault_path() -> str:
    env = _read_env_file()
    return env.get("VAULT_PATH", "").strip()

def _save_vault_path(path: str) -> str:
    if not Path(path.strip()).exists():
        return f"❌ 路径不存在: {path}"
    _write_env_file({"VAULT_PATH": path.strip()})
    return f"✅ 笔记库路径已保存"
```

### 2. 扫描与读取

```python
def scan_vault_files(vault_path: str) -> list[str]:
    vault = Path(vault_path)
    files = []
    for f in vault.rglob("*.md"):
        rel = f.relative_to(vault)
        files.append(str(rel))
    return sorted(files)

def read_vault_file(vault_path: str, rel_path: str) -> str:
    fpath = Path(vault_path) / rel_path
    return fpath.read_text(encoding="utf-8")
```

### 3. Gradio UI 组件

```python
vault_path_input = gr.Textbox(label="笔记库路径", placeholder="/Users/lee/Documents/ObsidianVault")
vault_save_btn = gr.Button("💾 保存路径")
vault_refresh_btn = gr.Button("🔄 刷新文件列表")
vault_file_select = gr.Dropdown(label="选择笔记文件", choices=[])
```

### 4. 事件绑定

```python
vault_save_btn.click(fn=on_vault_save, inputs=vault_path_input, outputs=[vault_status, vault_file_select])
vault_refresh_btn.click(fn=on_vault_refresh, inputs=vault_path_input, outputs=vault_file_select)
vault_file_select.change(fn=on_vault_select, inputs=[vault_path_input, vault_file_select], outputs=note_input)
```

## 踩坑记录

1. **Gradio Dropdown 更新 choices** — 在 Gradio 4.x 中，事件函数直接返回 `list[str]` 即可更新 Dropdown 的 choices，无需 `gr.Dropdown.update()`
2. **路径持久化选择** — Vault 路径和 API Key 不是一类配置，但都是用户级别的全局配置，放在 `.env` 里统一管理最简洁

## 使用方法

1. 在「输入」区域下方找到「📁 或从本地笔记库选择」
2. 填写 Markdown 目录路径（如 `/Users/lee/content-agent/notes` 或 Obsidian Vault 路径）
3. 点击「保存路径」
4. 点击「刷新文件列表」（保存时会自动刷新）
5. 从 Dropdown 选择文件，内容自动填充到上方的「笔记内容」输入框

## 验证结果

- ✅ 语法检查通过
- ✅ 保存路径后自动刷新文件列表
- ✅ 选择文件后自动填充到输入框
- ✅ 路径持久化到 .env，重启后自动恢复

## 下一步

- [ ] Notion 联动（通过 Notion API 读取 Database/Page）
- [ ] 支持子目录过滤（忽略 `attachments/` 等非笔记目录）
- [ ] 文件内容预览（Dropdown 旁边显示文件第一行标题）
