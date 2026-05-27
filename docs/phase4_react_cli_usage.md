# ReAct Agent CLI 使用说明

## 快速开始

### 1. 指定笔记文件生成并发布

```bash
python main.py --react --note-file /path/to/note.md --platforms gongzhonghao,xiaohongshu
```

### 2. 直接输入笔记内容生成

```bash
python main.py --react --note-content "# 标题\n\n内容..." --platforms gongzhonghao
```

### 3. 从 Vault 笔记生成

```bash
python main.py --react --vault-note "note_filename.md" --platforms gongzhonghao,xiaohongshu,douyin
```

## 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| --react | 启用 ReAct 模式 | --react |
| --note-file | 指定笔记文件路径 | --note-file ~/notes/mcp.md |
| --note-content | 直接输入笔记内容 | --note-content "# 标题\n内容" |
| --vault-note | 从 Vault 读取笔记 | --vault-note "mcp_protocol.md" |
| --platforms | 目标平台（逗号分隔） | --platforms gongzhonghao,xiaohongshu |
| --publish | 生成后自动发布 | --publish |

## 完整示例

```bash
# 生成公众号文章并自动发布
python main.py --react --note-file ~/notes/mcp.md --platforms gongzhonghao --publish

# 生成三平台内容（不入队）
python main.py --react --vault-note "ai_agent_intro.md" --platforms gongzhonghao,xiaohongshu,douyin

# 快速测试
python main.py --react --note-content "# 测试\n这是一个测试笔记" --platforms gongzhonghao
```
