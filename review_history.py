#!/usr/bin/env python3
"""
审核历史记录查询工具

用法:
    python review_history.py list          # 列出最近20条审核记录
    python review_history.py show <id>     # 查看某条记录的详细评分
    python review_history.py stats         # 统计概览
"""

import argparse
import sys
from pathlib import Path

# 确保能找到 agents 模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.store import list_review_panels, get_review_panel_detail


def cmd_list(args):
    """列出审核记录"""
    panels = list_review_panels(limit=args.limit)
    if not panels:
        print("暂无审核记录。")
        return

    print(f"## 审核记录列表（共 {len(panels)} 条）\n")
    print("| ID | task_id | 得分 | 阈值 | 状态 | 用户决策 | 时间 |")
    print("|----|---------|------|------|------|----------|------|")
    for p in panels:
        status = "✅" if p["passed"] else "❌"
        decision = p["user_decision"] or "-"
        print(
            f"| {p['id']} | {p['task_id']} | {p['overall']} | {p['threshold']} | {status} | {decision} | {p['created_at']} |"
        )


def cmd_show(args):
    """查看单条记录详情"""
    detail = get_review_panel_detail(args.id)
    if detail is None:
        print(f"❌ 找不到 ID 为 {args.id} 的审核记录。")
        return

    status = "✅ 已达标" if detail["passed"] else "❌ 未达标"
    decision_map = {
        "revise": "🔄 采纳修改",
        "ignore": "🤐 忽略未通过项",
        "force_publish": "🚩 强行发布",
    }
    decision = decision_map.get(detail["user_decision"], detail["user_decision"] or "未决策")

    print(f"## 审核记录 #{detail['id']}\n")
    print(f"- **task_id**: {detail['task_id']}")
    print(f"- **整体得分**: {detail['overall']}/{detail['threshold']} {status}")
    print(f"- **用户决策**: {decision}")
    print(f"- **时间**: {detail['created_at']}")
    if detail["revision_prompt"]:
        print(f"- **修改意见**: {detail['revision_prompt']}")
    print()

    items = detail.get("items", [])
    if items:
        print("### 各维度评分\n")
        print("| 维度 | 得分 | 阈值 | 状态 | 建议 | 忽略 |")
        print("|-------|------|------|------|--------|------|")
        for item in items:
            icon = "✅" if item["passed"] else "❌"
            ignored = "是" if item["ignored"] else "否"
            print(
                f"| {item['dimension']} | {item['score']} | {item['threshold']} | {icon} | {item['suggestion'] or '-'} | {ignored} |"
            )
    else:
        print("暂无详细评分项。")


def cmd_stats(args):
    """统计概览"""
    panels = list_review_panels(limit=1000)
    if not panels:
        print("暂无审核记录。")
        return

    total = len(panels)
    passed = sum(1 for p in panels if p["passed"])
    failed = total - passed
    avg_score = sum(p["overall"] for p in panels) / total

    decisions = {}
    for p in panels:
        d = p["user_decision"] or "未决策"
        decisions[d] = decisions.get(d, 0) + 1

    print("## 审核记录统计概览\n")
    print(f"- **总记录数**: {total}")
    print(f"- **通过数**: {passed} ({passed/total*100:.1f}%)")
    print(f"- **未通过数**: {failed} ({failed/total*100:.1f}%)")
    print(f"- **平均得分**: {avg_score:.1f}")
    print()
    print("### 用户决策分布")
    for d, count in sorted(decisions.items(), key=lambda x: -x[1]):
        print(f"- {d}: {count} 次")


def main():
    parser = argparse.ArgumentParser(description="审核历史记录查询工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出审核记录")
    p_list.add_argument("-n", "--limit", type=int, default=20, help="最多显示几条（默认20）")

    p_show = sub.add_parser("show", help="查看单条记录详情")
    p_show.add_argument("id", type=int, help="记录 ID")

    p_stats = sub.add_parser("stats", help="统计概览")

    args = parser.parse_args()

    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "show":
        cmd_show(args)
    elif args.cmd == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
