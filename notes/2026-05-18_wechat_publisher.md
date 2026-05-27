# 微信公众号草稿箱发布功能实现笔记

## 背景/需求

Roadmap P2-3：文案生成后，用户还需要手动复制粘贴到微信公众号后台，填标题、上传封面、调排版。流程繁琐，希望能一键发布到草稿箱，确认后即可发送。

## 设计思路

由于微信公众号没有开放给个人的发布 API，借助第三方工具 [kuaifa CLI](https://github.com/shirenchuang/kuaifa) 实现草稿箱自动保存。

1. **封装 kuaifa CLI** — 用 subprocess 调用 `kuaifa publish` 命令
2. **Markdown 中转** — 将公众号文案保存为临时 Markdown 文件，作为 kuaifa 的输入
3. **封面支持** — 支持本地图片上传或 URL（微信草稿必须有封面）
4. **Web UI 集成** — 在「公众号」Tab 下添加发布面板
5. **配置面板** — Web UI 内直接配置 AppID / AppSecret / API Key

## 核心实现

### 1. Publisher 模块（publisher.py）

```python
class PublisherError(Exception):
    pass

def check_kuaifa() -> tuple[bool, str]:
    """检查 kuaifa CLI 是否可用"""
    kuaifa_path = shutil.which("kuaifa")
    if not kuaifa_path:
        return False, "kuaifa CLI 未安装或未在 PATH 中"
    # ...

def publish_wechat_draft(
    markdown_path: str,
    title: str,
    cover_path: str = "",
    author: str = "",
    digest: str = "",
    template_id: str = "",
) -> dict:
    """发布文章到微信公众号草稿箱"""
    cmd = [
        "kuaifa", "publish", markdown_path,
        "--draft", "--title", title,
    ]
    if cover_path:
        cmd.extend(["--cover", cover_path])
    if author:
        cmd.extend(["--author", author])
    if digest:
        cmd.extend(["--digest", digest])
    # ... subprocess.run
    return {"success": ..., "message": ..., "details": ...}

def save_content_as_markdown(title: str, content: str) -> str:
    """将文案保存为 Markdown 文件"""
    out_path = Path(tempfile.gettempdir()) / f"{title[:50]}.md"
    out_path.write_text(content, encoding="utf-8")
    return str(out_path)
```

### 2. Web UI 发布面板

在「公众号」Tab 下新增折叠面板：

```python
with gr.Accordion("📤 发布到公众号草稿箱（需安装 kuaifa CLI）", open=False):
    publish_title = gr.Textbox(label="文章标题")
    publish_author = gr.Textbox(label="作者名（可选）")
    publish_digest = gr.Textbox(label="文章摘要（可选）")
    cover_upload = gr.File(label="上传封面图片", file_types=["image"], type="filepath")
    cover_url = gr.Textbox(label="或填入图片 URL")
    publish_wechat_btn = gr.Button("📤 一键发布到草稿箱", variant="primary")
    publish_result = gr.Textbox(label="发布结果", interactive=False)
```

### 3. 发布回调函数

```python
def publish_to_wechat(gongzhonghao_text, title, author, digest, cover_file, cover_url):
    if not gongzhonghao_text.strip():
        return "❌ 公众号文案为空"

    cover_path = ""
    if cover_file:
        cover_path = cover_file if isinstance(cover_file, str) else cover_file.name
    elif cover_url.strip():
        cover_path = cover_url.strip()

    if not cover_path:
        return "❌ 微信草稿要求必须有封面图片"

    md_path = save_content_as_markdown(title or "未命名", gongzhonghao_text)
    result = publish_wechat_draft(md_path, title, cover_path, author, digest)
    return result["message"] + ("\n\n详情:\n" + result["details"] if result["details"] else "")
```

### 4. kuaifa 配置面板

在「模型配置」旁边新增折叠面板，让用户可以在 Web UI 内直接配置：

```python
with gr.Accordion("🔧 发布配置（kuaifa 微信公众号）", open=False):
    kuaifa_appid = gr.Textbox(label="微信 AppID")
    kuaifa_appsecret = gr.Textbox(label="微信 AppSecret", type="password")
    kuaifa_api_key = gr.Textbox(label="kuaifa API Key", type="password")
    kuaifa_author = gr.Textbox(label="默认作者名")
    save_kuaifa_btn = gr.Button("💾 保存发布配置")
    verify_kuaifa_btn = gr.Button("🔐 验证微信配置")
```

配置保存到 `~/.kuaifa/config.json`，和 kuaifa CLI 的配置文件共用。

### 5. 安装检测

启动时自动检测 kuaifa 安装状态：

```python
def get_kuaifa_setup_status() -> str:
    if not shutil.which("kuaifa"):
        return "❌ kuaifa 未安装\n请先在终端运行：npm install -g kuaifa"
    cfg = load_kuaifa_config()
    missing = [k for k in ["appid", "appsecret", "api-key"] if not cfg.get(k)]
    if missing:
        return f"⚠️ 已安装，但缺少配置：{', '.join(missing)}"
    return "✅ kuaifa 已安装且配置完整"
```

## 踩坑记录

1. **kuaifa 是 npm 工具，不能打包** — PyInstaller 只能打包 Python 依赖，kuaifa CLI 需要目标机器单独安装 Node.js + kuaifa。这是目前最大的限制。

2. **微信草稿必须有封面** — kuaifa 的 `--cover` 参数必填，否则会报错。UI 中加了强制检查，没有封面时阻止发布并提示用户。

3. **Gradio File 组件的返回值类型** — 在不同版本的 Gradio 中，File 组件上传后返回的可能是字符串路径或 FileData 对象。代码中做了兼容处理：`isinstance(cover_file, str)` 和 `hasattr(cover_file, "name")`。

4. **kuaifa 配置文件格式** — 配置存在 `~/.kuaifa/config.json`，不是常规的 INI 或 YAML。存储时用 `json.dump` 保存即可。

5. **发布超时问题** — 微信 API 调用可能较慢，subprocess 设置了 60 秒超时。如果网络不好可能失败，需要告诉用户重试。

6. **封面图自动生成** — 本来计划用 FAL API 自动生成封面，但账户余额耗尽。暂时由用户手动上传封面或提供 URL，后续有效 API Key 后再接入自动生成。

## 使用方法

**首次配置（每台机器只需一次）：**

1. 安装 kuaifa CLI：
   ```bash
   npm install -g kuaifa
   ```

2. 在 Web UI 的「发布配置」面板中填写：
   - 微信 AppID
   - 微信 AppSecret
   - kuaifa API Key（在 https://www.kuaifa.art 注册获取）
   - 默认作者名

3. 点击「验证微信配置」确认通过

**发布文案：**

1. 生成公众号文案
2. 在「公众号」Tab 下打开「发布到公众号草稿箱」
3. 填写标题、作者、摘要（可选）
4. 上传封面图片或填入图片 URL
5. 点击「一键发布」
6. 打开微信公众号后台 → 内容与创作 → 草稿箱 → 检查并发送

## 下一步

- 支持小红书自动发布（需要研究小红书的发布机制，可能需要浏览器自动化）
- 支持抖音自动发布
- 封面图自动生成（待 FAL 或其他图像 API 有效 Key 后接入）
- 发布成功后自动更新内容日历状态为「已发布」
