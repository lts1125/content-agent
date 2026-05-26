#!/usr/bin/env python3
"""
Content Agent - AI 内容改写工具

一键将技术学习笔记改写为小红书/公众号/抖音三平台文案，
并自动生成小红书配图。

用法:
    python main.py                              # 使用默认笔记演示
    python main.py -i notes.md                  # 从文件读取笔记
    python main.py -i notes.md -o ./dist        # 指定输出目录
    python main.py -i notes.md -p xiaohongshu   # 只生成小红书
"""

import argparse
import datetime
import os
import sys
import time
from pathlib import Path
from typing import List

from dotenv import load_dotenv

from content_agent.agent_core import ContentAgent
from content_agent.html_renderer import XiaohongshuRenderer
from content_agent.quality_checker import QualityChecker
from content_agent.research import research_notes, extract_keywords_with_llm

# Phase 0: 新架构（Orchestrator + Multi-Agent）
try:
    from agents import Orchestrator, TaskInput
    from agents.store import init_db, save_task
    HAS_NEW_ARCH = True
except Exception as e:
    HAS_NEW_ARCH = False
    _import_err = e

load_dotenv()


DEFAULT_NOTES = """背景：下班后决定学 AI Agent 开发，想做一个内容改写 Agent 做副业。

今天学习核心步骤：

步骤1 理解 Agent 本质
Agent 不是什么高深的东西，它就是 LLM + 工具调用 + 循环。
比如我让 Agent 写小红书文案，它需要先"思考"原文重点，然后"执行"改写，如果结果不满意还得"反思"再改。这就是 ReAct 模式（Reasoning + Acting）。

步骤2 选框架
不要一上来就碰 LangChain，太重了。我对比了几个：
- LangChain：功能全但隐性成本高，适合复杂企业项目
- PydanticAI：类型安全、轻量、对 Rust/后端开发者友好
- OpenAI Agents SDK：简单但捆绑 OpenAI
最后选了 PydanticAI，因为我喜欢它用 Pydantic Model 定义 result_type 的方式。

步骤3 搭环境
- 新建项目目录，用 python3 -m venv .venv 创建虚拟环境
- pip install pydantic-ai 安装
- 装 python-dotenv 管理 API Key
- 用 .env 文件存放 DEEPSEEK_API_KEY

步骤4 第一个 Agent 代码
核心就三行：
1. 定义 model（用 DeepSeekProvider + OpenAIChatModel）
2. 写 system_prompt
3. agent.run_sync(用户输入) 得结果
重点：system_prompt 是 Agent 的"灵魂"。

步骤5 踩坑记录
- 坑1：PydanticAI 0.8 API 和文档不一致，OpenAIModel 改名为 OpenAIChatModel
- 坑2：结果字段是 result.output 不是 result.data
- 坑3：Kimi Code API 有 User-Agent 白名单限制，最后切换到 DeepSeek

步骤6 下一步计划
- 加多平台输出
- 用 Pydantic Model 定义结构化输出
- 接入 MCP 工具协议
"""


def save_markdown(platform: str, content: str, output_dir: Path) -> str:
    """保存文案为 markdown 文件"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = output_dir / f"{timestamp}_{platform}.md"

    md_content = f"""---
title: {platform}文案
date: {datetime.datetime.now().isoformat()}
source: 学习笔记
platform: {platform}
---

{content}
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(md_content)
    return str(filename)


def _get_date_subdir(base_dir: Path) -> Path:
    """生成日期子目录，格式: output/YYYYMMDD/"""
    today = datetime.datetime.now().strftime("%Y%m%d")
    date_dir = base_dir / today
    date_dir.mkdir(parents=True, exist_ok=True)
    return date_dir


def _collect_notes(input_path: Path) -> List[Path]:
    """
    收集笔记文件。
    如果是文件，直接返回。
    如果是目录，遍历所有 .md 和 .txt 文件。
    """
    if input_path.is_file():
        return [input_path]

    notes = []
    for ext in ("*.md", "*.txt"):
        notes.extend(input_path.glob(ext))
        notes.extend(input_path.rglob(ext))  # 递归子目录

    # 去重并排序
    seen = set()
    unique = []
    for p in sorted(notes):
        if str(p) not in seen:
            seen.add(str(p))
            unique.append(p)
    return unique


def process_single_note(
    note_path: Path,
    raw_notes: str,
    agent: ContentAgent,
    checker: QualityChecker,
    enabled_platforms: set,
    args,
    note_output_dir: Path,
) -> dict:
    """
    处理单个笔记，返回处理结果

    Returns:
        {"success": bool, "saved_files": list, "error": str|None}
    """
    note_name = note_path.stem
    result = {"success": False, "saved_files": [], "error": None}

    print(f"\n{'=' * 60}")
    print(f"📄 处理: {note_name} ({len(raw_notes)} 字)")
    print(f"{'=' * 60}")

    current_notes = raw_notes

    # 搜索增强（可选）
    if args.research:
        try:
            from pydantic_ai import Agent
            keyword_agent = Agent(
                agent.model,
                system_prompt="你是一个关键词提取助手，从技术笔记中提取精准的搜索关键词。"
            )
            keywords = extract_keywords_with_llm(raw_notes, keyword_agent)
            print(f"   💡 LLM 提取关键词: {keywords}")
        except Exception as e:
            print(f"   ⚠️ LLM 提取失败，使用启发式: {e}")
            keywords = None

        current_notes = research_notes(
            current_notes,
            search_engine=args.search_engine,
            max_results=3,
            verbose=True,
            keywords=keywords,
        )

    # 敏感词预检
    try:
        from content_agent.sensitive_checker import SensitiveChecker
        sc = SensitiveChecker()
        check_res = sc.check(raw_notes)
        if check_res["has_sensitive"]:
            hits = [h["word"] for h in check_res["hits"][:5]]
            print(f"   ⚠️ 敏感词预检: 检测到 {check_res['local_count']} 个敏感/违规词: {', '.join(hits)}")
            if len(check_res["hits"]) > 5:
                print(f"      等共 {len(check_res['hits'])} 个")
    except Exception:
        pass

    # 生成内容 + 质量检查 + 重试
    generation_result = None
    for attempt in range(1, 4):
        print(f"\n   🤖 第 {attempt} 次生成三平台文案...")

        try:
            generation_result = agent.run(current_notes)
        except Exception as e:
            result["error"] = f"Agent 调用失败: {e}"
            print(f"   ❌ {result['error']}")
            return result

        check = checker.check(
            generation_result.xiaohongshu,
            generation_result.gongzhonghao,
            generation_result.douyin,
            attempt=attempt,
        )

        print(f"   📊 质量检查: 综合 {check.overall_score}/100")

        if check.passed:
            print(f"   ✅ 通过，共 {attempt} 次")
            break

        if attempt < 3:
            print(f"   🔄 即将第 {attempt + 1} 次重试...")
            current_notes = (
                f"\u3010请根据以下改进要求重新输出三平台文案】\n"
                f"{check.retry_suggestion}\n\n"
                f"--- 原始笔记 ---\n{raw_notes}"
            )
        else:
            print(f"   ⚠️ 重试 3 次未达标，使用最后结果")

    if generation_result is None:
        result["error"] = "生成结果为空"
        return result

    # 保存文案
    saved = []
    if "xiaohongshu" in enabled_platforms:
        f = save_markdown("xiaohongshu", generation_result.xiaohongshu, note_output_dir)
        saved.append(f)
    if "gongzhonghao" in enabled_platforms:
        f = save_markdown("gongzhonghao", generation_result.gongzhonghao, note_output_dir)
        saved.append(f)
    if "douyin" in enabled_platforms:
        f = save_markdown("douyin", generation_result.douyin, note_output_dir)
        saved.append(f)

    print(f"   ✅ 已保存 {len(saved)} 个文件")

    # 打印推荐标签
    if generation_result and generation_result.recommended_tags:
        print(f"\n   🏷️ 推荐标签/\u8bdd\u9898:")
        for line in generation_result.recommended_tags.strip().split("\n"):
            if line.strip():
                print(f"      {line.strip()}")

    # 生成小红书配图
    if "xiaohongshu" in enabled_platforms:
        try:
            renderer = XiaohongshuRenderer()
            html_path = renderer.render(generation_result.xiaohongshu, note_output_dir / "配图")
            html_name = Path(html_path).name
            print(f"   🎨 配图已生成: {html_name}")
        except Exception as e:
            print(f"   ⚠️ 配图生成失败: {e}")

    result["success"] = True
    result["saved_files"] = saved
    return result


def process_single_note_v2(
    note_path: Path,
    raw_notes: str,
    enabled_platforms: set,
    args,
    note_output_dir: Path,
) -> dict:
    """
    Phase 0: 基于 Orchestrator 的新链路。
    功能与 process_single_note 等价，但内部走 agents/ 层。
    """
    from agents import Orchestrator, TaskInput
    from agents.store import save_task
    from content_agent.html_renderer import XiaohongshuRenderer
    from content_agent.sensitive_checker import SensitiveChecker

    result = {"success": False, "saved_files": [], "error": None}
    note_name = note_path.stem

    print(f"\n{'=' * 60}")
    print(f"📄 处理 (v2): {note_name} ({len(raw_notes)} 字)")
    print(f"{'=' * 60}")

    # 敏感词预检（保留现有行为）
    try:
        sc = SensitiveChecker()
        check_res = sc.check(raw_notes)
        if check_res["has_sensitive"]:
            hits = [h["word"] for h in check_res["hits"][:5]]
            print(f"   ⚠️ 敏感词预检: 检测到 {check_res['local_count']} 个敏感/违规词: {', '.join(hits)}")
    except Exception:
        pass

    # Orchestrator 调用
    try:
        orch = Orchestrator()
        task_input = TaskInput(
            note_text=raw_notes,
            note_source=str(note_path),
            platforms=list(enabled_platforms),
            enable_research=args.research,
            search_engine=args.search_engine,
        )
        state = orch.run(task_input)
    except Exception as e:
        result["error"] = f"Orchestrator 调用失败: {e}"
        print(f"   ❌ {result['error']}")
        return result

    # 保存结果
    saved = []
    final = state.final_output
    if not final:
        result["error"] = "生成结果为空"
        return result

    if "xiaohongshu" in enabled_platforms:
        f = save_markdown("xiaohongshu", final.xiaohongshu, note_output_dir)
        saved.append(f)
    if "gongzhonghao" in enabled_platforms:
        f = save_markdown("gongzhonghao", final.gongzhonghao, note_output_dir)
        saved.append(f)
    if "douyin" in enabled_platforms:
        f = save_markdown("douyin", final.douyin, note_output_dir)
        saved.append(f)

    print(f"   ✅ 已保存 {len(saved)} 个文件")

    if final.recommended_tags:
        print(f"\n   🏷️ 推荐标签/话题:")
        for line in final.recommended_tags.strip().split("\n"):
            if line.strip():
                print(f"      {line.strip()}")

    # 生成小红书配图
    if "xiaohongshu" in enabled_platforms:
        try:
            renderer = XiaohongshuRenderer()
            html_path = renderer.render(final.xiaohongshu, note_output_dir / "配图")
            print(f"   🎨 配图已生成: {Path(html_path).name}")
        except Exception as e:
            print(f"   ⚠️ 配图生成失败: {e}")

    # 持久化任务状态
    try:
        save_task(state)
    except Exception as e:
        print(f"   ⚠️ 任务状态保存失败: {e}")

    result["success"] = True
    result["saved_files"] = saved
    return result


def _run_trend_pipeline(args):
    """P0: 热点监控完整流程"""
    from automation import TrendScheduler, TopicPicker
    
    vault_path = args.vault or os.getenv("VAULT_PATH", os.path.expanduser("~/.content_agent/vault"))
    
    print("=" * 60)
    print("🔥 热点监控流水线")
    print("=" * 60)
    
    # Step 1: 检查热点
    print("\n[1/4] 检查热点...")
    scheduler = TrendScheduler()
    result = scheduler.check_trends()
    
    if not result["matched"]:
        print("   未匹配到相关热点，流程结束")
        return
    
    print(f"   匹配到 {result['matched']} 条，评估通过 {result.get('passed', 0)} 条")
    
    # Step 2: 生成选题
    print("\n[2/4] 生成选题建议...")
    picker = TopicPicker()
    suggestions = picker.pick_topics(
        vault_path=vault_path,
        trending_hint=result.get("trending_text", ""),
        limit=args.trend_limit or 3
    )
    
    if not suggestions:
        print("   未生成选题建议")
        return
    
    print(f"   生成 {len(suggestions)} 条选题:")
    for s in suggestions:
        print(f"   • [{s.priority}] {s.title}")
        if s.trending_topic:
            print(f"     关联热点: {s.trending_topic}")
        print(f"     ID: {s.id}")
    
    # Step 3: 自动或半自动处理
    if args.trend_auto:
        print("\n[3/4] 自动接受所有选题...")
        for s in suggestions:
            picker.accept(s.id)
            print(f"   已接受: {s.title[:40]}...")
    else:
        print("\n[3/4] 等待人工确认（使用 --trend-auto 可跳过）")
        print("   请运行以下命令接受选题:")
        for s in suggestions:
            print(f"      python main.py --accept-topic {s.id}")
        return
    
    # Step 4: 执行生成
    print("\n[4/4] 执行选题生成内容...")
    from automation import TopicExecutor
    executor = TopicExecutor()
    results = executor.execute_batch(limit=len(suggestions))
    success = sum(1 for r in results if r["success"])
    print(f"   完成: {success}/{len(results)} 个选题执行成功")
    
    # 显示生成的队列项
    if success > 0:
        from automation import PublishQueue
        items = PublishQueue.list(status="pending")
        print(f"\n   待发队列新增 {len(items)} 项:")
        for item in items[:5]:
            print(f"   • [{item.platform}] {item.title[:40]}...")
    
    print("\n" + "=" * 60)
    print("✅ 热点流水线完成")
    print("=" * 60)


def _handle_agent_mode(args):
    """处理 Agent 模式 CLI 参数"""
    import shutil

    from automation import VaultWatcher, AgentController, PublishQueue

    vault_path = args.vault or os.getenv("VAULT_PATH", os.path.expanduser("~/.content_agent/vault"))
    inbox_dir = os.getenv("VAULT_INBOX", "inbox")

    if args.watch:
        if not os.path.isdir(vault_path):
            print(f"❌ Vault 路径不存在: {vault_path}")
            sys.exit(1)
        watcher = VaultWatcher(vault_path=vault_path, inbox_dir=inbox_dir)
        controller = AgentController(watcher=watcher)
        watcher.on_new_note = controller.on_new_note
        try:
            watcher.start()
        except KeyboardInterrupt:
            print("\n👋 停止监听")
            watcher.stop()
        return

    if args.process_inbox:
        watcher = VaultWatcher(vault_path=vault_path, inbox_dir=inbox_dir)
        controller = AgentController(watcher=watcher)
        inbox_path = Path(vault_path) / inbox_dir
        if not inbox_path.exists():
            print("⚠️ inbox 目录不存在，自动创建")
            inbox_path.mkdir(parents=True, exist_ok=True)
        files = [f for f in inbox_path.iterdir() if f.is_file() and f.suffix.lower() in (".md", ".txt")]
        if not files:
            print("📭 inbox 为空，没有文件需要处理")
            sys.exit(0)
        print(f"📁 发现 {len(files)} 个文件，开始批量处理...")
        results = controller.process_inbox(inbox_path)
        success = sum(1 for r in results if r["success"])
        print(f"\n✅ 成功: {success}/{len(results)}")
        for r in results:
            if not r["success"]:
                print(f"   ❌ {r.get('error', '未知错误')}")
        return

    # ---- B1: 自触发调度 ----
    if args.schedule_once:
        from automation import TaskScheduler, SchedulerConfig
        config = SchedulerConfig.from_yaml(args.config) if args.config else SchedulerConfig.from_env()
        scheduler = TaskScheduler(config)
        scheduler.run_once()
        return

    if args.daemon:
        from automation import TaskScheduler, SchedulerConfig
        config = SchedulerConfig.from_yaml(args.config) if args.config else SchedulerConfig.from_env()
        scheduler = TaskScheduler(config)
        scheduler.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 停止调度器")
            scheduler.shutdown()
        return

    if args.queue:
        items = PublishQueue.list(status=args.status)
        if not items:
            print(f"📭 队列中无 '{args.status}' 状态的项目")
            return
        print(f"\n{'ID':<20} {'Platform':<12} {'Status':<10} {'Title'}")
        print("-" * 70)
        for item in items:
            title = item.title[:30] + "..." if len(item.title) > 30 else item.title
            print(f"{item.id:<20} {item.platform:<12} {item.status:<10} {title}")
        print(f"\n共 {len(items)} 条")
        return

    if args.approve:
        ok = PublishQueue.approve(args.approve)
        if ok:
            print(f"✅ 已通过: {args.approve}")
        else:
            print(f"❌ 未找到: {args.approve}")
        return

    if args.reject:
        ok = PublishQueue.reject(args.reject)
        if ok:
            print(f"✅ 已拒绝: {args.reject}")
        else:
            print(f"❌ 未找到: {args.reject}")
        return

    # ---- P2: 审核门 + 自动发布 ----
    gate_mode = args.gate_mode
    if args.skip_gate:
        print("\n⚠️⚠️⚠️  WARNING: --skip-gate 已设置，审核门被强制禁用！⚠️⚠️⚠️\n")
        gate_mode = "disabled"

    if args.publish_next:
        from automation import PublishExecutor, PublishGate
        item = PublishQueue.get_oldest_approved()
        if item is None:
            print("📭 没有 approved 状态的队列项")
            return
        executor = PublishExecutor(gate=PublishGate(mode=gate_mode), max_retries=args.max_retries)
        result = executor.execute_one(item.id)
        if result.get("success"):
            print(f"✅ 发布成功: {item.id}")
        else:
            print(f"❌ 发布失败: {result.get('error', '未知错误')}")
        return

    if args.publish_all:
        from automation import PublishExecutor, PublishGate
        items = PublishQueue.list(status="approved")
        if not items:
            print("📭 没有 approved 状态的队列项")
            return
        gate = PublishGate(mode=gate_mode)
        decisions = gate.batch_review(items)
        executor = PublishExecutor(gate=gate, max_retries=args.max_retries)
        for item, decision in zip(items, decisions):
            if decision.decision != "approve":
                print(f"⏭️  跳过 {item.id}: {decision.decision}")
                continue
            print(f"🚀 发布 {item.id} ({item.platform})...")
            result = executor.execute_one(item.id, skip_gate=True)
            if result.get("success"):
                print(f"   ✅ 成功")
            else:
                print(f"   ❌ 失败: {result.get('error', '未知错误')}")
        return

    if args.publish_scheduled:
        from automation import PublishExecutor, PublishGate
        # publish_scheduled 强制使用 scheduled 模式，不允许 disabled 绕过审核
        executor = PublishExecutor(
            gate=PublishGate(mode="scheduled"),
            max_retries=args.max_retries,
        )
        results = executor.execute_scheduled()
        success = sum(1 for r in results if r.get("success"))
        print(f"\n✅ 成功: {success}/{len(results)}")
        return

    if args.schedule:
        if not args.schedule_at:
            print("❌ 请同时提供 --at 参数指定排期时间")
            return
        ok = PublishQueue.update_schedule(args.schedule, args.schedule_at)
        print(f"{'✅ 已排期' if ok else '❌ 未找到'}: {args.schedule} -> {args.schedule_at}")
        return

    if args.unschedule:
        ok = PublishQueue.unschedule(args.unschedule)
        print(f"{'✅ 已取消排期' if ok else '❌ 未找到'}: {args.unschedule}")
        return

    if args.retry_failed:
        from automation import PublishExecutor, PublishGate
        items = PublishQueue.get_failed_items(max_retries=args.max_retries)
        if not items:
            print("📭 没有需要重试的 failed 项")
            return
        executor = PublishExecutor(gate=PublishGate(mode=gate_mode), max_retries=args.max_retries)
        for item in items:
            print(f"🔄 重试 {item.id} ({item.platform})...")
            result = executor.execute_one(item.id)
            if result.get("success"):
                print(f"   ✅ 成功")
            else:
                print(f"   ❌ 失败: {result.get('error', '未知错误')}")
        return

    # ---- P1: 数据回流 + 风格画像 ----
    if args.import_metrics:
        from automation import FeedbackAgent
        agent = FeedbackAgent()
        result = agent.import_metrics(Path(args.import_metrics))
        print(f"📊 导入完成: {result['imported']} 条")
        if result["errors"]:
            print(f"⚠️ 错误: {len(result['errors'])} 条")
            for e in result["errors"][:5]:
                print(f"   {e}")
        return

    if args.analyze_feedback:
        from automation import FeedbackAgent
        agent = FeedbackAgent()
        profiles = agent.analyze(platform=args.platform)
        if profiles:
            for profile in profiles:
                print(f"\n🎨 风格画像 ({profile.platform})")
                print(f"   语气: {profile.preferred_tone}")
                print(f"   高分模式: {', '.join(profile.high_performing_patterns)}")
                print(f"   平均分: {profile.avg_score}")
                print(f"   样本数: {profile.sample_count}")
        else:
            print("⚠️ 无足够数据进行分析（需要已发布项 + metrics）")
        return

    if args.show_profile:
        from automation import FeedbackAgent
        agent = FeedbackAgent()
        target = args.platform or "xiaohongshu"
        profile = agent.get_profile(target)
        if profile:
            print(f"\n🎨 风格画像 ({profile.platform})")
            print(f"   语气: {profile.preferred_tone}")
            print(f"   高分模式: {', '.join(profile.high_performing_patterns)}")
            print(f"   平均分: {profile.avg_score}")
            print(f"   样本数: {profile.sample_count}")
        else:
            print(f"⚠️ 平台 '{target}' 暂无风格画像")
        return

    # ---- P1: 自动选题 ----
    if args.pick_topics:
        from automation import TopicPicker
        picker = TopicPicker()
        keywords = args.topic_keywords or os.getenv("AGENT_TOPIC_KEYWORDS")
        suggestions = picker.pick_topics(vault_path=vault_path, keywords=keywords)
        if suggestions:
            print(f"\n生成 {len(suggestions)} 条选题建议:")
            for s in suggestions:
                print(f"   • [{s.priority}] {s.title} ({s.trending_topic})")
        else:
            print("未生成选题建议")
        return

    if args.topics:
        from automation import TopicPicker
        picker = TopicPicker()
        items = picker.list_suggestions(status=args.topic_status)
        if not items:
            print(f"无 '{args.topic_status}' 状态的选题建议")
            return
        print(f"\n{'Title':<40} {'Status':<10} {'Priority'}")
        print("-" * 65)
        for item in items:
            title = item.title[:35] + "..." if len(item.title) > 35 else item.title
            print(f"{title:<40} {item.status:<10} {item.priority}")
        print(f"\n共 {len(items)} 条")
        return

    if args.accept_topic:
        from automation import TopicPicker
        ok = TopicPicker().accept(args.accept_topic)
        if ok:
            print(f"已接受: {args.accept_topic}")
        else:
            print(f"未找到: {args.accept_topic}")
        return

    if args.reject_topic:
        from automation import TopicPicker
        ok = TopicPicker().reject(args.reject_topic)
        if ok:
            print(f"已拒绝: {args.reject_topic}")
        else:
            print(f"未找到: {args.reject_topic}")
        return

    # ---- 批量执行 accepted 选题 ----
    if args.execute_topics:
        from automation import TopicExecutor
        executor = TopicExecutor()
        results = executor.execute_batch(limit=args.execute_limit)
        success = sum(1 for r in results if r["success"])
        print(f"\n完成: {success}/{len(results)} 个选题执行成功")
        for r in results:
            if not r["success"]:
                print(f"   失败: {r.get('error', '未知错误')}")
        return

    # ---- P0: 热点监控全流程 ----
    if args.trend_pipeline:
        _run_trend_pipeline(args)
        return

    # ---- P1: A/B 测试 ----
    if args.generate_ab:
        from automation import ABTestFramework, PublishQueue
        framework = ABTestFramework()
        types = [t.strip() for t in args.generate_ab.split(",")]
        queue_id = args.ab_queue_id
        if not queue_id:
            # 取最近的 pending/approved 项
            items = PublishQueue.list(status="pending")
            if not items:
                items = PublishQueue.list(status="approved")
            if not items:
                print("❌ 没有可用的队列项，请用 --ab-queue-id 指定")
                return
            queue_id = items[0].id
        try:
            variants = framework.generate_variants(queue_id, types, count=args.ab_count)
            print(f"✅ 为 {queue_id} 生成 {len(variants)} 个变体:")
            for v in variants:
                print(f"   [{v.variant_type}] {v.variant_content[:60]}...")
        except Exception as e:
            print(f"❌ 生成失败: {e}")
        return

    if args.ab_results:
        from automation import ABTestFramework
        result = ABTestFramework().analyze_results(args.ab_results)
        if result["best_variant_id"]:
            print(f"🏆 最优变体: {result['best_variant_id']}")
            print(f"   最佳得分: {result['best_score']}")
        else:
            print("⚠️ 无结果数据")
        return

    # ---- Eval 回归测试 ----
    if args.eval_regression:
        from automation.eval.regression import RegressionTester
        tester = RegressionTester()
        results = tester.run(quick=True)  # 快速模式
        report = tester.generate_report(results)
        print(report)
        return

    if args.eval_report:
        from automation.eval.regression import RegressionTester
        from agents.store import _get_conn
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM eval_results ORDER BY created_at DESC LIMIT 10").fetchall()
        conn.close()
        if not rows:
            print("📭 暂无评估数据")
            return
        print(f"\n最近 {len(rows)} 条评估记录:")
        print(f"{'Task':<20} {'Platform':<12} {'Overall':<8} {'Time'}")
        print("-" * 60)
        for r in rows:
            print(f"{r['task_id']:<20} {r['platform']:<12} {r['overall_score']:<8} {r['created_at']}")
        return

    # ---- ReAct Agent ----
    if args.react:
        _run_react_mode(args)
        return

    if args.publish_file:
        _publish_file_mode(args)
        return


def _publish_file_mode(args):
    """直接发布已生成的 Markdown 文件"""
    from content_agent.publisher import publish_wechat_draft
    from pathlib import Path

    file_path = Path(args.publish_file)
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        sys.exit(1)

    print(f"📄 读取文件: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取标题
    lines = content.split("\n")
    title = lines[0].replace("#", "").strip() if lines else "发布内容"

    print(f"📝 标题: {title}")
    print(f"📊 内容长度: {len(content)} 字")

    # 发布
    cover = args.cover or os.getenv("WECHAT_DEFAULT_COVER", "")
    if not cover:
        print("⚠️ 未设置封面图片（--cover 或 WECHAT_DEFAULT_COVER）")
        response = input("是否继续发布? [y/N]: ")
        if response.lower() != "y":
            print("已取消")
            return

    print("\n📤 发布到公众号...")
    try:
        result = publish_wechat_draft(str(file_path), title=title, cover_path=cover)
        if result.get("success"):
            print(f"✅ 发布成功！")
            print(f"   media_id: {result.get('details', '')[-50:]}")
        else:
            print(f"❌ 发布失败: {result.get('error', '未知错误')}")
            print(f"   详情: {result.get('details', '')}")
    except Exception as e:
        print(f"❌ 发布异常: {e}")


def _run_react_mode(args):
    """运行 ReAct Agent 模式"""
    from agents.react_agent import ReActAgent
    from agents.store import _get_conn
    import datetime

    # 获取笔记内容
    raw_notes = ""
    if args.note_file:
        with open(args.note_file, "r", encoding="utf-8") as f:
            raw_notes = f.read()
        print(f"📄 从文件读取笔记: {args.note_file}")
    elif args.note_content:
        raw_notes = args.note_content
        print("📝 使用直接输入的笔记内容")
    elif args.vault_note:
        vault_path = os.getenv("VAULT_PATH", ".")
        note_path = Path(vault_path) / args.vault_note
        if note_path.exists():
            with open(note_path, "r", encoding="utf-8") as f:
                raw_notes = f.read()
            print(f"📄 从 Vault 读取笔记: {note_path}")
        else:
            print(f"❌ Vault 笔记不存在: {note_path}")
            sys.exit(1)
    else:
        print("❌ 请提供笔记内容（--note-file / --note-content / --vault-note）")
        sys.exit(1)

    # 解析平台
    platforms = [p.strip() for p in args.platforms.split(",")] if args.platforms else ["gongzhonghao"]
    print(f"🎯 目标平台: {', '.join(platforms)}")

    # 运行 Agent
    if args.v2:
        # 使用新架构（Orchestrator + 多 Agent 协作）
        print("\n🚀 启动多 Agent 协作模式 (Orchestrator)...")
        from agents.collaboration.orchestrator import Orchestrator
        orch = Orchestrator()
        result = orch.run(raw_notes, platforms)

        # 显示结果
        print(f"\n✅ 生成完成！")
        if result.get("content"):
            for platform in platforms:
                content = getattr(result["content"], platform, "")
                if content:
                    print(f"  {platform}: {len(content)} 字")

        # 保存到文件
        output_dir = Path("output/react") / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir.mkdir(parents=True, exist_ok=True)

        if result.get("content"):
            for platform in platforms:
                content = getattr(result["content"], platform, "")
                if content:
                    file_path = output_dir / f"{platform}.md"
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"  💾 已保存: {file_path}")
    else:
        # 使用旧架构（ReAct Agent）
        print("\n🚀 启动 ReAct Agent...")
        agent = ReActAgent(max_steps=3)
        result = agent.run(raw_notes, platforms)

        print(f"\n✅ 生成完成！")
        print(f"步骤数: {len(result.steps)}")
        for i, step in enumerate(result.steps):
            print(f"  Step {i+1}: {step.thought[:60]}...")

        # 显示内容预览
        print(f"\n📊 生成结果:")
        for platform in platforms:
            content = getattr(result.content, platform, "")
            print(f"  {platform}: {len(content)} 字")

        # 保存到文件
        output_dir = Path("output/react") / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir.mkdir(parents=True, exist_ok=True)

        for platform in platforms:
            content = getattr(result.content, platform, "")
            if content:
                file_path = output_dir / f"{platform}.md"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  💾 已保存: {file_path}")

    # 生成小红书配图
    if "xiaohongshu" in platforms:
        try:
            from content_agent.html_renderer import XiaohongshuRenderer
            renderer = XiaohongshuRenderer()
            html_path = renderer.render(result.content.xiaohongshu, output_dir / "配图")
            print(f"  🎨 小红书配图已生成: {Path(html_path).name}")
        except Exception as e:
            print(f"  ⚠️ 小红书配图生成失败: {e}")

    # 生成抖音配图
    if "douyin" in platforms:
        try:
            from content_agent.douyin_renderer import DouyinRenderer
            renderer = DouyinRenderer()
            html_path = renderer.render(result.content.douyin, output_dir / "配图")
            print(f"  🎨 抖音配图已生成: {Path(html_path).name}")
        except Exception as e:
            print(f"  ⚠️ 抖音配图生成失败: {e}")

    # 自动发布（公众号）
    if args.publish and "gongzhonghao" in platforms:
        print("\n📤 自动发布公众号...")
        from content_agent.publisher import publish_wechat_draft
        import tempfile

        content = result.content.gongzhonghao
        if not content:
            print("❌ 公众号内容为空，无法发布")
            return

        lines = content.split("\n")
        title = lines[0].replace("#", "").strip() if lines else "ReAct 生成内容"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            temp_path = f.name

        cover = args.cover or os.getenv("WECHAT_DEFAULT_COVER", "")
        if not cover:
            print("⚠️ 未设置封面图片（--cover 或 WECHAT_DEFAULT_COVER），发布可能失败")
        
        try:
            pub_result = publish_wechat_draft(temp_path, title=title, cover_path=cover)
            
            import os as os2
            os2.unlink(temp_path)

            if pub_result.get("success"):
                print(f"✅ 发布成功！media_id: {pub_result.get('details', '')[-50:]}")
            else:
                print(f"❌ 发布失败: {pub_result.get('error', '未知错误')}")
                print(f"详情: {pub_result.get('details', '')}")
        except Exception as e:
            print(f"❌ 发布异常: {e}")
            import os as os2
            if os2.path.exists(temp_path):
                os2.unlink(temp_path)

    print(f"\n📂 输出目录: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Content Agent - AI 内容改写工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                              使用默认笔记演示
  python main.py -i notes.md                  从文件读取笔记
  python main.py -i notes/                    批量处理目录下所有笔记
  python main.py -i notes.md -o ./dist        指定输出目录
  python main.py -i notes.md -p xiaohongshu   只生成小红书
  python main.py -i notes.md -r               启用搜索增强
  python main.py -i notes/ -r --search-engine tavily  批量+搜索增强
        """,
    )
    parser.add_argument(
        "--input", "-i",
        help="输入的笔记文件或目录 (.md / .txt)"
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="输出目录 (默认: output)"
    )
    parser.add_argument(
        "--platforms", "-p",
        default="all",
        help="平台选择，逗号分隔，默认 all (选项: xiaohongshu,gongzhonghao,douyin)"
    )
    parser.add_argument(
        "--clean", "-c",
        action="store_true",
        help="清理同一天的旧文件后再生成（默认保留历史文件）"
    )
    parser.add_argument(
        "--research", "-r",
        action="store_true",
        help="启用搜索增强，在生成前自动搜索相关背景资料"
    )
    parser.add_argument(
        "--search-engine",
        default="duckduckgo",
        choices=["duckduckgo", "tavily"],
        help="搜索引擎选择（默认: duckduckgo，无需 API key）"
    )
    parser.add_argument(
        "--v2",
        action="store_true",
        help="使用新架构（Orchestrator + Multi-Agent）运行"
    )

    agent_group = parser.add_mutually_exclusive_group()
    agent_group.add_argument("--watch", action="store_true", help="启动 Vault 监听模式")
    agent_group.add_argument("--process-inbox", action="store_true", help="批量处理 inbox 后退出")
    agent_group.add_argument("--schedule-once", action="store_true", help="单次执行调度任务（扫描+生成+发布）")
    agent_group.add_argument("--daemon", action="store_true", help="常驻后台运行调度器")
    parser.add_argument("--config", type=str, help="调度配置文件路径（YAML）")
    parser.add_argument("--queue", action="store_true", help="查看待发队列")
    parser.add_argument("--status", default="pending", help="队列筛选状态")
    parser.add_argument("--approve", metavar="ID", help="审核通过指定队列项")
    parser.add_argument("--reject", metavar="ID", help="拒绝指定队列项")
    parser.add_argument("--publish-next", action="store_true", help="交互式审核并发布下一个 approved 项")
    parser.add_argument("--publish-all", action="store_true", help="批量审核并发布所有 approved 项")
    parser.add_argument("--publish-scheduled", action="store_true", help="执行到期的排期发布")
    parser.add_argument("--schedule", metavar="ID", help="为队列项设置排期时间")
    parser.add_argument("--at", metavar="TIME", dest="schedule_at", help="排期时间，如 '2026-05-25 09:00'")
    parser.add_argument("--unschedule", metavar="ID", help="取消排期")
    parser.add_argument("--gate-mode", default="interactive", choices=["interactive", "scheduled", "disabled"], help="审核门模式")
    parser.add_argument("--skip-gate", action="store_true", help="开发调试：跳过审核门（打印警告）")
    parser.add_argument("--retry-failed", action="store_true", help="重试所有 failed 状态的项")
    parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数")

    # P1: Agent 智能优化
    parser.add_argument("--import-metrics", metavar="PATH", help="导入平台数据 CSV/JSON")
    parser.add_argument("--analyze-feedback", action="store_true", help="分析反馈并更新风格画像")
    parser.add_argument("--show-profile", action="store_true", help="查看当前风格画像")
    parser.add_argument("--platform", help="指定平台（用于 --analyze-feedback / --show-profile）")
    parser.add_argument("--vault", help="Vault 路径（默认读取 VAULT_PATH 环境变量）")
    parser.add_argument("--pick-topics", action="store_true", help="从 Vault 自动生成选题建议")
    parser.add_argument("--topic-keywords", help="选题热点关键词（默认读取 AGENT_TOPIC_KEYWORDS）")
    parser.add_argument("--topics", action="store_true", help="查看选题建议")
    parser.add_argument("--topic-status", default="pending", help="选题建议筛选状态")
    parser.add_argument("--accept-topic", metavar="ID", help="接受选题建议并自动生成为内容")
    parser.add_argument("--reject-topic", metavar="ID", help="拒绝选题建议")
    parser.add_argument("--execute-topics", action="store_true", help="批量执行所有 accepted 选题")
    parser.add_argument("--execute-limit", type=int, default=10, help="批量执行数量上限")
    parser.add_argument("--trend-pipeline", action="store_true", help="[P0] 运行热点监控完整流程")
    parser.add_argument("--trend-auto", action="store_true", help="[P0] 热点流程自动接受选题（无需人工确认）")
    parser.add_argument("--trend-limit", type=int, default=3, help="[P0] 热点流程生成选题数量上限")
    parser.add_argument("--generate-ab", metavar="TYPES", help="生成 A/B 变体，如 title,hook")
    parser.add_argument("--ab-count", type=int, default=3, help="每种变体类型生成数量")
    parser.add_argument("--ab-queue-id", help="指定队列项 ID 生成 A/B 变体")
    parser.add_argument("--ab-results", metavar="TASK_ID", help="查看 A/B 测试结果")

    # Eval 回归测试
    parser.add_argument("--eval-regression", action="store_true", help="运行回归测试")
    parser.add_argument("--eval-report", action="store_true", help="查看最近的回归测试报告")

    # ReAct Agent
    parser.add_argument("--react", action="store_true", help="使用 ReAct Agent 生成内容")
    parser.add_argument("--note-file", help="指定笔记文件路径")
    parser.add_argument("--note-content", help="直接输入笔记内容")
    parser.add_argument("--vault-note", help="从 Vault 读取笔记文件名")
    parser.add_argument("--publish", action="store_true", help="生成后自动发布（公众号）")
    parser.add_argument("--cover", help="指定公众号封面图片路径")
    parser.add_argument("--publish-file", help="直接发布已生成的 Markdown 文件（不重新生成）")

    args = parser.parse_args()

    # Phase 0: 初始化 SQLite
    if HAS_NEW_ARCH:
        try:
            from agents.store import init_db
            init_db()
        except Exception as e:
            print(f"⚠️ 数据库初始化失败: {e}")

    # ---- Agent Mode 处理 ----
    agent_args = [
        args.watch, args.process_inbox, args.schedule_once, args.daemon,
        args.queue, args.approve, args.reject,
        args.publish_next, args.publish_all, args.publish_scheduled,
        args.schedule, args.unschedule, args.retry_failed,
        args.import_metrics, args.analyze_feedback,
        args.show_profile, args.pick_topics, args.topics, args.accept_topic,
        args.reject_topic, args.execute_topics, args.trend_pipeline,
        args.generate_ab, args.ab_results,
        args.eval_regression, args.eval_report,
        args.react, args.publish_file,
    ]
    if any(agent_args):
        if not HAS_NEW_ARCH:
            print(f"❌ Agent 模式不可用: {_import_err}")
            sys.exit(1)
        _handle_agent_mode(args)
        return

    # 1. 确定输入
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"❌ 错误: 输入路径不存在: {args.input}")
            sys.exit(1)
        note_files = _collect_notes(input_path)
        if not note_files:
            print(f"⚠️ 未找到任何 .md 或 .txt 笔记文件")
            sys.exit(0)
        is_batch = input_path.is_dir()
    else:
        # 默认模式：使用内置笔记
        note_files = [None]
        is_batch = False

    print(f"📁 共发现 {len(note_files)} 个笔记文件" if is_batch else "📄 单文件模式")

    # 2. 解析平台选项
    platform_arg = args.platforms.lower().strip()
    if platform_arg == "all":
        enabled_platforms = {"xiaohongshu", "gongzhonghao", "douyin"}
    else:
        enabled_platforms = {p.strip() for p in platform_arg.split(",")}
        valid = {"xiaohongshu", "gongzhonghao", "douyin"}
        invalid = enabled_platforms - valid
        if invalid:
            print(f"❌ 错误: 无效平台: {', '.join(invalid)}")
            print(f"   有效选项: {', '.join(valid)}")
            sys.exit(1)

    # 3. 初始化共享的 Agent 和 Checker
    try:
        agent = ContentAgent()
    except ValueError as e:
        print(f"❌ 配置错误: {e}")
        sys.exit(1)

    checker = QualityChecker(agent.model)

    # 4. 处理笔记
    base_output_dir = Path(args.output)
    date_dir = _get_date_subdir(base_output_dir)

    # 如果是单文件模式且传了 --clean，清理日期目录
    if not is_batch and args.clean and date_dir.exists():
        import shutil
        cleaned = 0
        for item in date_dir.iterdir():
            if item.is_file():
                item.unlink()
                cleaned += 1
            elif item.is_dir():
                shutil.rmtree(item)
                cleaned += 1
        if cleaned > 0:
            print(f"🚿 已清理 {cleaned} 个旧文件/目录")

    results = []
    for idx, note_path in enumerate(note_files, 1):
        if note_path is None:
            # 默认笔记模式
            raw_notes = DEFAULT_NOTES
            note_name = "default"
            note_output_dir = date_dir
        else:
            with open(note_path, "r", encoding="utf-8") as f:
                raw_notes = f.read()
            note_name = note_path.stem
            if is_batch:
                # 批量模式：每个笔记单独子目录
                note_output_dir = date_dir / note_name
                note_output_dir.mkdir(parents=True, exist_ok=True)
            else:
                # 单文件模式：也创建笔记名子目录，保持结构统一
                note_output_dir = date_dir / note_name
                note_output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n📊 进度: {idx}/{len(note_files)}")

        if args.v2 and HAS_NEW_ARCH:
            result = process_single_note_v2(
                note_path=note_path or Path("default"),
                raw_notes=raw_notes,
                enabled_platforms=enabled_platforms,
                args=args,
                note_output_dir=note_output_dir,
            )
        else:
            result = process_single_note(
                note_path=note_path or Path("default"),
                raw_notes=raw_notes,
                agent=agent,
                checker=checker,
                enabled_platforms=enabled_platforms,
                args=args,
                note_output_dir=note_output_dir,
            )
        results.append(result)

    # 5. 总结
    success_count = sum(1 for r in results if r["success"])
    total_files = sum(len(r["saved_files"]) for r in results)

    print(f"\n{'=' * 60}")
    print(f"🎉 全部完成！{success_count}/{len(note_files)} 个笔记处理成功")
    print(f"📁 共生成 {total_files} 个文件")
    print(f"📂 输出目录: {date_dir.absolute()}")
    print(f"{'=' * 60}")

    # 失败的笔记打印错误
    failed = [(note_files[i].name if note_files[i] else "default", r["error"])
              for i, r in enumerate(results) if not r["success"]]
    if failed:
        print(f"\n❌ 失败的笔记:")
        for name, err in failed:
            print(f"   • {name}: {err}")


if __name__ == "__main__":
    main()
