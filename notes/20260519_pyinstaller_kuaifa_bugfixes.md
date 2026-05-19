# PyInstaller 打包后 kuaifa 调用兼容性修复

## 背景/需求

PyInstaller 打包为 macOS `.app` 后，用户双击启动应用，在「保存微信配置 → 验证配置 → 发布到草稿箱」三个环节连续报错，导致发布功能完全不可用。需要在打包环境下修复 kuaifa CLI 的调用兼容性。

## 设计思路

核心问题：**打包后的 macOS app 运行在一个精简的环境上下文中**，与终端 `python web_ui.py` 的运行环境存在多个差异：

1. Python 版本限制 — 系统 Python 3.9 不支持 `str | None` 类型注解
2. PATH 缺失 — app bundle 内没有用户 shell 的 PATH，找不到 `node`
3. kuaifa 的 shebang 依赖 — `#!/usr/bin/env node` 在 app 内失效
4. 配置文件字段格式 — 保存和验证使用了不同的 key 名

修复策略：
- 统一使用显式查找 `node` 和 `kuaifa` 可执行文件路径
- 所有 subprocess 调用改为 `[node_path, kuaifa_path, ...]`，绕过 shebang
- 统一 kuaifa 配置文件的字段名（与 kuaifa CLI 保持一致）

## 核心实现

### 1. 显式查找 node + kuaifa（publisher.py / web_ui.py）

```python
def _find_kuaifa() -> "str | None":
    kf = shutil.which("kuaifa")
    if kf:
        return kf
    for p in [Path.home() / ".hermes" / "node" / "bin" / "kuaifa", ...]:
        if p.exists():
            return str(p.resolve())
    return None

def _find_node() -> "str | None":
    node = shutil.which("node")
    if node:
        return node
    for p in [Path.home() / ".hermes" / "node" / "bin" / "node", ...]:
        if p.exists():
            return str(p.resolve())
    return None
```

### 2. 所有 kuaifa 调用都通过 node 执行

```python
# 发布草稿箱
env = os.environ.copy()
extra_paths = [str(Path(kuaifa_path).parent), str(Path(node_path).parent)]
env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])

subprocess.run(
    [node_path, kuaifa_path, "publish", markdown_path, "--draft", "--title", title],
    capture_output=True, text=True, timeout=60, env=env,
)
```

### 3. 统一配置字段名

kuaifa CLI 认的是扁平格式：
```json
{
  "appid": "wx...",
  "appsecret": "..."
}
```

`save_kuaifa_config()` 和 `verify_kuaifa_config()` 统一用这个格式读写。

### 4. 前置校验：未填配置不执行 CLI

```python
def verify_kuaifa_config() -> str:
    config_path = Path.home() / ".kuaifa" / "config.json"
    if not config_path.exists():
        return "❌ 请先填写并保存微信 AppID 和 AppSecret"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if not config.get("appid") or not config.get("appsecret"):
            return "❌ 请先填写并保存微信 AppID 和 AppSecret"
    except Exception:
        return "❌ 请先填写并保存微信 AppID 和 AppSecret"
    # ... 继续执行 kuaifa 验证
```

## 踩坑记录

1. **`str | None` 在 Python 3.9 报错** — 系统 Python 3.9 不支持 PEP 604 联合类型，改为 `"str | None"` 字符串注解绕过
2. **`env: node: No such file or directory`** — kuaifa 的 shebang `#!/usr/bin/env node` 在打包 app 内找不到 node，必须显式指定 node 路径执行
3. **`name 'json' is not defined`** — `web_ui.py` 顶部漏了 `import json`，打包后运行才暴露
4. **配置字段名不对齐** — 一开始存成 `wechat.app_id`，但 kuaifa CLI 读的是 `appid`，验证通过但发布失败
5. **空配置文件导致 JSONDecodeError** — 用户未保存时 `~/.kuaifa/config.json` 可能是 0 字节空文件，读取时抛异常，已用 try/except 兜底返回友好提示
6. **`publisher.py` 里的 `check_kuaifa()` 也受影响** — 不只 web_ui.py，发布入口 publisher.py 的三个函数（check / publish / list_templates）都要同步改造

## 使用方法

打包后测试流程：
1. 打开 `ContentAgent.app`
2. 在「发布配置」填写微信 AppID / AppSecret → 点击「保存配置」
3. 点击「验证微信配置」→ 应提示「✅ 微信配置验证通过」
4. 生成公众号文案 → 上传封面 → 点击「📤 一键发布到草稿箱」→ 应提示「✅ 已成功保存到微信公众号草稿箱」

## 验证结果

- ✅ 保存配置成功（不再 `name 'json' is not defined`）
- ✅ 验证配置通过（不再 `env: node: No such file or directory`）
- ✅ 发布到草稿箱成功（kuaifa CLI 在打包环境下正常调用）
- ✅ 未填配置时点验证，返回友好提示而非崩溃

## 下一步

- [ ] 考虑把 node/kuaifa 路径检测逻辑抽成公共模块，避免 web_ui.py 和 publisher.py 重复
- [ ] 后续如果在 CI 环境打包，需确认打包机的 node 路径是否一致
