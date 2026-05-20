"""
ui/tabs/config_tab.py — ⚙️ 配置 Tab

包含：
- 模型配置（Provider、API Key）
- 发布配置（kuaifa 微信公众号）

定时任务和内容日历暂时保留在 web_ui.py，后续再迁移。
"""

import gradio as gr

from ui.state import (
    load_config_for_ui,
    save_config as _default_save_config,
    get_config_status,
    load_kuaifa_config,
    save_kuaifa_config,
    get_kuaifa_setup_status,
    verify_kuaifa_config,
)


def create_tab(save_config_fn=None):
    """
    创建配置 Tab。

    Args:
        save_config_fn: 可选的自定义 save_config 函数。
                        用于在保存配置后执行额外操作（如清除 Agent 缓存）。
                        签名必须与 ui.state.save_config 一致。
    """
    _save_config = save_config_fn or _default_save_config
    with gr.Row():
        with gr.Column(scale=1):
            # ── 模型配置 ──
            with gr.Accordion("⚙️ 模型配置（第一次使用请先填写）", open=False):
                config_status = gr.Textbox(
                    label="状态",
                    value=get_config_status()[1],
                    interactive=False,
                )

                provider_select = gr.Dropdown(
                    label="选择 Provider",
                    choices=[
                        ("DeepSeek (推荐，性价比最高)", "deepseek"),
                        ("Kimi (月之暗面)", "kimi"),
                        ("MiniMax", "minimax"),
                        ("OpenAI / Azure", "openai"),
                        ("自定义 OpenAI-compatible", "custom"),
                    ],
                    value=load_config_for_ui()["provider"],
                )

                deepseek_key_input = gr.Textbox(
                    label="DeepSeek API Key",
                    placeholder="sk-...",
                    type="password",
                    value=load_config_for_ui()["deepseek_key"],
                    visible=load_config_for_ui()["provider"] == "deepseek",
                )
                kimi_key_input = gr.Textbox(
                    label="Kimi API Key",
                    placeholder="sk-...",
                    type="password",
                    value=load_config_for_ui()["kimi_key"],
                    visible=load_config_for_ui()["provider"] == "kimi",
                )
                minimax_key_input = gr.Textbox(
                    label="MiniMax API Key",
                    placeholder="your-minimax-api-key",
                    type="password",
                    value=load_config_for_ui()["minimax_key"],
                    visible=load_config_for_ui()["provider"] == "minimax",
                )
                openai_key_input = gr.Textbox(
                    label="OpenAI API Key",
                    placeholder="sk-...",
                    type="password",
                    value=load_config_for_ui()["openai_key"],
                    visible=load_config_for_ui()["provider"] == "openai",
                )

                with gr.Column(visible=load_config_for_ui()["provider"] == "custom") as custom_fields:
                    custom_key_input = gr.Textbox(
                        label="API Key",
                        placeholder="sk-...",
                        type="password",
                        value=load_config_for_ui()["custom_key"],
                    )
                    custom_base_url_input = gr.Textbox(
                        label="Base URL",
                        placeholder="https://api.example.com/v1",
                        value=load_config_for_ui()["custom_base_url"],
                    )
                    custom_model_name_input = gr.Textbox(
                        label="Model Name",
                        placeholder="deepseek-ai/DeepSeek-V3",
                        value=load_config_for_ui()["custom_model_name"],
                    )
                    gr.Markdown("""
                    常见平台参考：
                    - 硅基流动: `https://api.siliconflow.cn/v1` + `deepseek-ai/DeepSeek-V3`
                    - 通义千问: `https://dashscope.aliyuncs.com/compatible-mode/v1` + `qwen-plus`
                    - 智谱: `https://open.bigmodel.cn/api/paas/v4` + `glm-4-flash`
                    - Ollama: `http://localhost:11434/v1` + `qwen2.5:7b`
                    """)

                gr.Markdown("---")
                tavily_key_input = gr.Textbox(
                    label="Tavily API Key（搜索增强用，可选）",
                    placeholder="tvly-... （选填，用 Tavily 搜索时需要）",
                    type="password",
                    value=load_config_for_ui()["tavily_key"],
                )
                gr.Markdown("注册: [https://app.tavily.com/home](https://app.tavily.com/home) 免费 1000 credits/月")

                save_config_btn = gr.Button("💾 保存配置", variant="primary", size="sm")

            # Provider 切换时显示/隐藏对应的 Key 输入框
            def _toggle_provider_inputs(provider):
                return {
                    deepseek_key_input: gr.update(visible=provider == "deepseek"),
                    kimi_key_input: gr.update(visible=provider == "kimi"),
                    minimax_key_input: gr.update(visible=provider == "minimax"),
                    openai_key_input: gr.update(visible=provider == "openai"),
                    custom_fields: gr.update(visible=provider == "custom"),
                }

            provider_select.change(
                fn=_toggle_provider_inputs,
                inputs=[provider_select],
                outputs=[deepseek_key_input, kimi_key_input, minimax_key_input, openai_key_input, custom_fields],
            )

            save_config_btn.click(
                fn=_save_config,
                inputs=[
                    provider_select,
                    deepseek_key_input,
                    kimi_key_input,
                    minimax_key_input,
                    openai_key_input,
                    custom_key_input,
                    custom_base_url_input,
                    custom_model_name_input,
                    tavily_key_input,
                ],
                outputs=[config_status],
            )

        with gr.Column(scale=1):
            # ── kuaifa 发布配置 ──
            with gr.Accordion("🔧 发布配置（kuaifa 微信公众号）", open=False):
                kf_cfg = load_kuaifa_config()
                kuaifa_status = gr.Textbox(
                    label="状态",
                    value=get_kuaifa_setup_status(),
                    interactive=False,
                )
                kuaifa_appid = gr.Textbox(
                    label="微信 AppID",
                    placeholder="wx...",
                    value=kf_cfg.get("appid", ""),
                )
                kuaifa_appsecret = gr.Textbox(
                    label="微信 AppSecret",
                    placeholder="微信公众号的 AppSecret",
                    type="password",
                    value=kf_cfg.get("appsecret", ""),
                )
                kuaifa_api_key = gr.Textbox(
                    label="kuaifa API Key",
                    placeholder="kuaifa_...",
                    type="password",
                    value=kf_cfg.get("api-key", ""),
                )
                kuaifa_author = gr.Textbox(
                    label="默认作者名",
                    placeholder="如：小爪",
                    value=kf_cfg.get("default-author", ""),
                )
                with gr.Row():
                    save_kuaifa_btn = gr.Button("💾 保存发布配置", variant="primary", size="sm")
                    verify_kuaifa_btn = gr.Button("🔐 验证微信配置", size="sm")

            save_kuaifa_btn.click(
                fn=save_kuaifa_config,
                inputs=[kuaifa_appid, kuaifa_appsecret, kuaifa_api_key, kuaifa_author],
                outputs=[kuaifa_status],
            )
            verify_kuaifa_btn.click(
                fn=verify_kuaifa_config,
                inputs=[],
                outputs=[kuaifa_status],
            )