#!/usr/bin/env python3
"""Export only task-scoped, secret-free evidence of completed Grok CLI calls."""
import argparse
import hashlib
import json
from pathlib import Path

import stockdb_offline_export as e


def audit(root):
    result = {"method": "independent_codex_exec_processes", "native_spawn_agent_used": False, "tasks": []}
    control = json.loads((root / "agents/process_control.json").read_text())
    usage_path = Path("/Users/simon/.opencodex/usage.jsonl")
    for task in ("coverage", "semantics"):
        directory = root / "agents" / task
        initial = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
        events = [json.loads(line) for line in (directory / "finish_events.jsonl").read_text().splitlines()]
        session = next(event["thread_id"] for event in initial if event["type"] == "thread.started")
        if control.get("finishing_processes", {}).get(task, {}).get("exit_code") != 0:
            raise ValueError(task + " final CLI exit code has not been independently recorded as zero")
        if not any(event["type"] == "turn.completed" for event in events):
            raise ValueError(task + " has not returned a completed turn")
        if any(event["type"] == "turn.failed" for event in events):
            raise ValueError(task + " contains failed turn")
        messages = [event["item"]["text"] for event in events if event.get("item", {}).get("type") == "agent_message"]
        final = (directory / "final_result.md").read_text().strip()
        if not final or not messages or final != messages[-1].strip():
            raise ValueError(task + " result is absent or does not match returned final message")
        rollouts = list(Path("/Users/simon/.codex/sessions/2026/09/05").glob("*" + session + ".jsonl"))
        if len(rollouts) != 1:
            raise ValueError("cannot resolve unique CLI session evidence")
        contexts = []
        for line in rollouts[0].open():
            row = json.loads(line)
            if row.get("type") == "turn_context":
                contexts.append({k: row["payload"].get(k) for k in ("cwd", "model", "turn_id")})
        if not contexts or any(ctx["model"] != "xai/grok-4.6" for ctx in contexts):
            raise ValueError("session used an unexpected configured model")
        conversation = hashlib.sha256(session.encode()).hexdigest()[:32]
        calls = []
        for line in usage_path.open():
            row = json.loads(line)
            if row.get("conversationId") != conversation:
                continue
            calls.append({**{k: row.get(k) for k in ("requestId", "timestamp", "conversationId", "requestedModel",
                             "resolvedModel", "provider", "model", "status", "usageStatus")},
                          "route_selected": row.get("routeDecision", {}).get("selected"),
                          "attempts": [{k: a.get(k) for k in ("provider", "model", "status", "sendCount")}
                                       for a in row.get("attempts", [])]})
        if not calls or not any(call["status"] == 200 for call in calls) or any(
                call["requestedModel"] != "xai/grok-4.6" or call["provider"] != "xai"
                or call["resolvedModel"] != "grok-4.6" for call in calls):
            raise ValueError("missing successful upstream Grok routing evidence")
        if any(a["provider"] != "xai" or a["model"] != "grok-4.6" for c in calls for a in c["attempts"]):
            raise ValueError("upstream fallback to a different model detected")
        stderr = (directory / "stderr.log").read_text()
        result["tasks"].append({"task": task, "session_id": session, "routing_conversation_id": conversation,
            "session_contexts": contexts, "upstream_call_count": len(calls), "upstream_calls": calls,
            "turn_completed": True, "final_cli_exit_code": 0,
            "initial_phase_interrupted": control["initial_processes"][task],
            "final_result": str(directory / "final_result.md"),
            "final_sha256": e.sha256_file(directory / "final_result.md"),
            "events_sha256": e.sha256_file(directory / "events.jsonl"),
            "finish_events_sha256": e.sha256_file(directory / "finish_events.jsonl"),
            "rollout_path": str(rollouts[0]),
            "cli_background_plugin_upgrade_timeout_observed": "failed to auto-upgrade configured marketplace" in stderr})
    target = root / "grok_cli_audit.json"
    if target.exists():
        raise FileExistsError("audit evidence already exists")
    result["status"] = "both_results_returned_and_actual_upstream_grok_4_6_verified"
    result["limitation"] = "CLI/session/router evidence; not independent attestation of vendor model weights"
    e.atomic_json(target, result)
    return {"status": result["status"], "tasks": [{k: t[k] for k in
               ("task", "session_id", "upstream_call_count", "turn_completed", "final_result")} for t in result["tasks"]]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), ensure_ascii=False, indent=2))
