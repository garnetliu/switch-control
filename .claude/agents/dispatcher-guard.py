#!/usr/bin/env python3
"""dispatcher 的两个钩子共用的脚本（挂在 dispatcher.md 开头的 hooks 里）。

交报告前（PreToolUse / SubagentHandback）：派出去的子代理还有没把结果交回来的，拒绝交报告。
结束回合时（Stop，子代理里实际是 SubagentStop）：报告已经交了、名下还有子代理在跑，拦住，让它先停掉。

谁被派出去、谁交回了结果，从 dispatcher 自己的会话记录里数；谁还在跑，看结束钩子带的 background_tasks。
"""

import json
import sys

HANDBACK = "[Subagent hand-back]"


def read_children(path):
    """返回 (每个子代理的 {started, returned, label}, 报告是否已交)。"""
    children = {}
    delivered = False

    def child(agent_id):
        return children.setdefault(agent_id, {"started": 0, "returned": 0, "label": agent_id})

    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") not in ("user", "assistant"):
                continue
            result = entry.get("toolUseResult")
            if isinstance(result, dict):
                if result.get("status") == "async_launched" and result.get("agentId"):
                    c = child(result["agentId"])
                    c["started"] += 1
                    c["label"] = result.get("description") or c["label"]
                elif result.get("resumedAgentId"):
                    child(result["resumedAgentId"])["started"] += 1
                elif result.get("success") is True and "Report delivered" in str(
                    result.get("message", "")
                ):
                    delivered = True
            origin = entry.get("origin")
            if (
                isinstance(origin, dict)
                and origin.get("kind") == "peer"
                and str(origin.get("body", "")).startswith(HANDBACK)
            ):
                sender = origin.get("senderTaskId") or origin.get("from")
                if sender in children:
                    children[sender]["returned"] += 1
            content = (entry.get("message") or {}).get("content")
            if entry.get("type") == "assistant" and isinstance(content, list):
                for block in content:
                    # 用 TaskStop 停掉的不会再交回结果，按已了结算。
                    if block.get("type") == "tool_use" and block.get("name") == "TaskStop":
                        stopped = (block.get("input") or {}).get("task_id")
                        if stopped in children:
                            children[stopped]["returned"] = children[stopped]["started"]
    return children, delivered


def names(children, ids):
    return "、".join(f"{children[i]['label']}（{i}）" for i in ids)


def main():
    data = json.load(sys.stdin)
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        path = (
            f"{data['transcript_path'][: -len('.jsonl')]}/subagents/agent-{data['agent_id']}.jsonl"
        )
        children, _ = read_children(path)
        pending = [i for i, c in children.items() if c["started"] > c["returned"]]
        if pending:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": (
                                f"还不能交报告：{names(children, pending)} 派出去后还没把结果交回给你。"
                                "现在直接结束这一回合等它的结果，不要轮询。"
                                "通知说它已经完成而你一直没收到结果，就用 SendMessage 向它要一次。"
                                "碰到必须马上交回主会话的事，先用 TaskStop 把还没交回的逐个停掉，再交报告。"
                            ),
                        }
                    },
                    ensure_ascii=False,
                )
            )
    elif event in ("Stop", "SubagentStop") and not data.get("stop_hook_active"):
        children, delivered = read_children(data["agent_transcript_path"])
        running = [
            t["id"]
            for t in data.get("background_tasks", [])
            if t.get("type") == "subagent"
            and t.get("status") == "running"
            and t.get("id") in children
        ]
        if delivered and running:
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": (
                            f"报告已经交了，但你派出去的 {names(children, running)} 还在跑。"
                            "用 TaskStop 把它们逐个停掉再结束；它们有没交回的结果要补报，就用 SendMessage 发给 main。"
                        ),
                    },
                    ensure_ascii=False,
                )
            )


main()
