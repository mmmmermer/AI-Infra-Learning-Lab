from __future__ import annotations

import json

from .simulation import InferenceTask, simulate_fifo, summarize, summarize_by_kind


def build_workload() -> list[InferenceTask]:
    shapes = [
        ("short_chat", 300, 100),
        ("rag_answer", 2_000, 300),
        ("long_report", 6_000, 1_000),
    ]
    return [
        InferenceTask(
            task_id=f"task-{index:02d}",
            request_kind=kind,
            arrival_ms=index * 250.0,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
        )
        for index, (kind, prompt_tokens, output_tokens) in enumerate(shapes * 10)
    ]


def main() -> None:
    results = simulate_fifo(build_workload())
    report = {
        "overall": summarize(results),
        "by_request_kind": summarize_by_kind(results),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
