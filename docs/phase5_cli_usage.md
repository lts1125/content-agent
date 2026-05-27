# CLI 使用手册

## 基础命令

### 默认演示
```bash
python main.py
```

### 从文件读取笔记
```bash
python main.py -i notes/my_note.md
```

### 指定平台和输出目录
```bash
python main.py -i notes/my_note.md -p xiaohongshu -o ./dist
```

## ReAct Agent 模式

ReAct 模式会让 Agent 按 “思考 -> 行动 -> 观察” 的流程调用工具，例如搜索、生成、评估和修改。

### 指定笔记文件生成
```bash
python main.py --react --note-file ~/notes/mcp.md --platforms gongzhonghao,xiaohongshu
```

### 直接输入笔记内容
```bash
python main.py --react --note-content "# 标题\n\n内容..." --platforms gongzhonghao
```

### 从 Vault 读取笔记
```bash
python main.py --react --vault-note "note_filename.md" --platforms gongzhonghao,xiaohongshu,douyin
```

### 生成后自动发布公众号
```bash
python main.py --react --note-file ~/notes/mcp.md --platforms gongzhonghao --publish --cover ~/images/cover.png
```

### 完整示例
```bash
# 生成公众号文章并自动发布
python main.py --react --note-file ~/notes/mcp.md --platforms gongzhonghao --publish

# 生成三平台内容，不自动发布
python main.py --react --vault-note "ai_agent_intro.md" --platforms gongzhonghao,xiaohongshu,douyin

# 快速测试
python main.py --react --note-content "# 测试\n这是一个测试笔记" --platforms gongzhonghao
```

## 发布命令

### 直接发布已生成的文件
```bash
python main.py --publish-file output/react/20260525_205105/gongzhonghao.md --cover ./images/cover.png
```

## 热点流水线

### 运行热点监控并生成选题
```bash
python main.py --trend-pipeline
```

### 自动模式（无需人工确认）
```bash
AGENT_TREND_MAX_EVAL=1 python main.py --trend-pipeline --trend-auto
```

## 队列管理

### 查看待发队列
```bash
python main.py --queue
```

### 审核通过
```bash
python main.py --approve queue_id
```

### 发布下一个 approved 项
```bash
python main.py --publish-next
```

### 发布所有 approved 项
```bash
python main.py --publish-all
```

## 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| --react | 启用 ReAct Agent 模式 | --react |
| --note-file | 指定笔记文件路径 | --note-file ~/notes/mcp.md |
| --note-content | 直接输入笔记内容 | --note-content "# 标题\n内容" |
| --vault-note | 从 Vault 读取笔记 | --vault-note "mcp_protocol.md" |
| --platforms | 目标平台（逗号分隔） | --platforms gongzhonghao,xiaohongshu,douyin |
| --publish | 生成后自动发布公众号 | --publish |
| --cover | 指定公众号封面图片 | --cover ~/images/cover.png |
| --publish-file | 直接发布已生成的 Markdown 文件 | --publish-file output/react/xxx/gongzhonghao.md |
| --trend-pipeline | 运行热点监控流水线 | --trend-pipeline |
| --trend-auto | 热点流水线自动模式 | --trend-auto |
| --queue | 查看待发队列 | --queue |
| --approve | 审核通过指定队列项 | --approve queue_id |
| --publish-next | 发布下一个 approved 项 | --publish-next |
| --publish-all | 发布所有 approved 项 | --publish-all |
