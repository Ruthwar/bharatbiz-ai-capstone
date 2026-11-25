"""Run one bounded, read-only agent review and print its audit trail.

Run: python scripts/agent_review.py --sku SKU-003 --supplier SUP-005 --delay-days 2 \
       --question "The cooking-oil supplier reports a two-day delay; what can we commit?"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("BHARATBIZ_TRACE_EXPORT", "none")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent_runtime import AgentRequest, run_review  # noqa: E402


def summary(result: dict) -> str:
    lines = [
        f"status: {result['status']}  intent: {result['intent']}  plan: {result['plan']['source']}",
        f"steps: {result['usage']['tool_calls']} calls, {result['retries']['rounds']} retry round(s), "
        f"{result['usage']['estimated_tokens']} estimated tokens, {result['usage']['elapsed_ms']} ms",
        f"failures: {', '.join(result['failure_labels']) or 'none'}",
        "plan:",
    ]
    for step in result["plan"]["steps"]:
        lines.append(f"  {step['step_id']}  {step['tool']}")
    lines.append("executed:")
    for step in result["steps"]:
        detail = step["code"] or step["status"]
        lines.append(f"  {step['step_id']}  {step['tool']:<20} {detail}")
    lines.append("citations:")
    for citation in result["citations"]:
        lines.append(
            f"  {citation['document_id']}  {citation['section']}  (in force {citation['effective_from']})"
        )
    if result["clarifications"]:
        lines.append("clarifications:")
        lines.extend(f"  - {item}" for item in result["clarifications"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default="The supplier reports a delay; what can we commit?")
    parser.add_argument("--intent")
    parser.add_argument("--sku-id")
    parser.add_argument("--supplier-id")
    parser.add_argument("--retailer-id")
    parser.add_argument("--delay-days", type=int)
    parser.add_argument("--required-units", type=int)
    parser.add_argument("--outflow-rupees")
    parser.add_argument("--conversation-id")
    parser.add_argument("--plan", type=Path, help="supplied plan JSON; malformed input falls back and is labelled")
    parser.add_argument("--json", action="store_true", help="print the full machine-readable run")
    parser.add_argument("--out", type=Path, help="write the full run to this JSON file")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8")) if args.plan else None
    request = AgentRequest(
        question=args.question,
        intent=args.intent,
        sku_id=args.sku_id,
        supplier_id=args.supplier_id,
        retailer_id=args.retailer_id,
        delay_days=args.delay_days,
        required_units=args.required_units,
        outflow_rupees=args.outflow_rupees,
        conversation_id=args.conversation_id,
        plan=plan,
    )
    result = run_review(request).to_dict()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(summary(result))
        if args.out:
            print(f"\nSaved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
