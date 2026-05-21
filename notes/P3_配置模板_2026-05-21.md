# P3: 配置模板（一键加载配置套餐）

## 需求
- 实现一个“配置模板”功能：用户可以快速加载预定义的平台/风格/搜索引擎组合，也可以保存/删除自定义模板

## 实现方案
- 新增 `content_agent/template_presets.py`：管理内置模板 + 用户自定义模板
- 在 `web_ui.py` 配置区域上方添加模板选择组件（Dropdown + 保存输入框 + 保存/删除按钮）
- 事件绑定：下拉框 change 批量更新配置组件，保存/删除按钮刷新 choices

## 模板存储
- 用户模板存储在 `~/.content_agent/templates.json`
- 格式：`{"user": {"user_<name>": {"name": "...", "platforms": [...], ...}}}`

## 内置模板
| ID | 名称 | 平台 | 搜索 | 风格 |
|---|---|---|---|---|
| xiaohongshu_hot | 小红书爆款 | 小红书 | 是 | 情绪共鸣 |
| all_platform_pro | 三平台全覆盖 | 全部 | 是 | 专业干货 |
| douyin_casual | 抖音口播 | 抖音 | 否 | 轻松口语 |
| gongzhonghao_deep | 公众号长文 | 公众号 | 是(Tavily) | 专业干货 |

## 用户自定义模板
- 保存时输入名称，程序自动前缀 `user_`
- 删除按钮只对用户模板可见/可用（内置模板隐藏）

## 相关文件
- `content_agent/template_presets.py` — 新建，模板存储与管理
- `web_ui.py` — 添加模板 UI 组件与事件绑定

## 验证
- `python3 -m py_compile web_ui.py content_agent/template_presets.py` — 通过
