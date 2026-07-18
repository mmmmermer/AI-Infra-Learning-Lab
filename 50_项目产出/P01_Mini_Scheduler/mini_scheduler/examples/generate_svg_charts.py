from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from examples.export_results import ARTIFACT_DIR, main as export_results


ChartPoint = Tuple[str, float]


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def scaled_bar_width(value: float, max_value: float, max_width: int) -> float:
    if max_value <= 0:
        return 0.0
    return value / max_value * max_width


def write_bar_chart(path: Path, title: str, points: List[ChartPoint], unit: str = "") -> None:
    width = 920
    row_height = 42
    left = 230
    top = 72
    max_bar_width = 560
    height = top + len(points) * row_height + 50
    max_value = max(value for _, value in points) if points else 0.0

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="32" y="38" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#172026">{title}</text>',
    ]

    for index, (label, value) in enumerate(points):
        y = top + index * row_height
        bar_width = scaled_bar_width(value, max_value, max_bar_width)
        lines.extend(
            [
                f'<text x="32" y="{y + 22}" font-family="Arial, sans-serif" font-size="15" fill="#263238">{label}</text>',
                f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="24" rx="3" fill="#2f7d6d"/>',
                f'<text x="{left + bar_width + 10:.2f}" y="{y + 18}" font-family="Arial, sans-serif" font-size="14" fill="#172026">{value:.2f}{unit}</text>',
            ]
        )

    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_architecture_diagram(path: Path) -> None:
    width = 1120
    height = 620
    box_w = 165
    box_h = 76
    y_main = 110
    x_positions = [50, 255, 460, 665, 870]
    main_nodes = [
        ("Task", "id / type / priority\\nduration / token"),
        ("Queue", "pending tasks\\narrival order"),
        ("Scheduler", "FIFO / Priority\\nPredicted/Oracle SJF"),
        ("Worker Pool", "single worker\\nmulti worker"),
        ("Metrics", "avg / P95 / P99\\nutilization / queue"),
    ]

    def box(x: int, y: int, title: str, subtitle: str, fill: str = "#f7fbfa") -> List[str]:
        subtitle_lines = subtitle.split("\\n")
        lines = [
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="8" fill="{fill}" stroke="#2f7d6d" stroke-width="2"/>',
            f'<text x="{x + box_w / 2}" y="{y + 28}" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#172026">{title}</text>',
        ]
        for index, item in enumerate(subtitle_lines):
            lines.append(
                f'<text x="{x + box_w / 2}" y="{y + 50 + index * 17}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#46545c">{item}</text>'
            )
        return lines

    def arrow(x1: int, y1: int, x2: int, y2: int) -> str:
        return (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            'stroke="#53676f" stroke-width="2.5" marker-end="url(#arrow)"/>'
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#53676f"/>',
        "</marker>",
        "</defs>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="40" y="44" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#172026">Mini Scheduler Architecture</text>',
        '<text x="40" y="74" font-family="Arial, sans-serif" font-size="15" fill="#53676f">A minimal AI workload scheduling simulator: strategy, workload, metrics, and experiment outputs.</text>',
    ]

    for index, (title, subtitle) in enumerate(main_nodes):
        x = x_positions[index]
        lines.extend(box(x, y_main, title, subtitle))
        if index < len(main_nodes) - 1:
            lines.append(arrow(x + box_w + 12, y_main + box_h // 2, x_positions[index + 1] - 14, y_main + box_h // 2))

    support_nodes = [
        (80, 300, "Workloads", "demo / low load\\npeak / sensitivity", "#fffaf0"),
        (320, 300, "Strategies", "cost weights\\naging protection", "#fffaf0"),
        (560, 300, "Experiments", "high load\\nworker count", "#fffaf0"),
        (800, 300, "Artifacts", "CSV / Markdown\\nSVG charts", "#fffaf0"),
    ]

    for x, y, title, subtitle, fill in support_nodes:
        lines.extend(box(x, y, title, subtitle, fill))

    lines.extend(
        [
            arrow(162, 300, 505, y_main + box_h + 6),
            arrow(402, 300, 542, y_main + box_h + 6),
            arrow(642, 300, 952, y_main + box_h + 6),
            arrow(882, 300, 952, y_main + box_h + 6),
            '<rect x="80" y="450" width="860" height="92" rx="8" fill="#f4f6f8" stroke="#b7c4ca"/>',
            '<text x="110" y="486" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#172026">Key experiment questions</text>',
            '<text x="110" y="516" font-family="Arial, sans-serif" font-size="14" fill="#33434a">1. Does lower average wait always mean better P99?  2. Which task types are sacrificed by cost weights?</text>',
            '<text x="110" y="540" font-family="Arial, sans-serif" font-size="14" fill="#33434a">3. Can aging reduce starvation?  4. How does worker count trade P95 for utilization?</text>',
        ]
    )

    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_worker_p95_points(rows: List[dict], strategy: str) -> List[ChartPoint]:
    selected = [row for row in rows if row["strategy"] == strategy]
    return [(f'{strategy} workers={int(float(row["worker_count"]))}', float(row["p95_wait_time"])) for row in selected]


def build_worker_utilization_points(rows: List[dict], strategy: str) -> List[ChartPoint]:
    selected = [row for row in rows if row["strategy"] == strategy]
    return [(f'{strategy} workers={int(float(row["worker_count"]))}', float(row["worker_utilization"])) for row in selected]


def build_cost_p99_points(rows: List[dict]) -> List[ChartPoint]:
    return [(row["strategy"], float(row["p99_wait_time"])) for row in rows]


def main() -> None:
    export_results()

    worker_rows = read_csv(ARTIFACT_DIR / "worker_count_summary.csv")
    cost_rows = read_csv(ARTIFACT_DIR / "cost_weight_summary.csv")

    write_bar_chart(
        ARTIFACT_DIR / "worker_count_fifo_p95.svg",
        "FIFO: Worker Count vs P95 Wait Time",
        build_worker_p95_points(worker_rows, "fifo"),
    )
    write_bar_chart(
        ARTIFACT_DIR / "worker_count_fifo_utilization.svg",
        "FIFO: Worker Count vs Utilization",
        build_worker_utilization_points(worker_rows, "fifo"),
    )
    write_bar_chart(
        ARTIFACT_DIR / "cost_weight_p99.svg",
        "Cost-aware Weights vs P99 Wait Time",
        build_cost_p99_points(cost_rows),
    )
    write_architecture_diagram(ARTIFACT_DIR / "mini_scheduler_architecture.svg")

    print(f"generated_svg_charts={ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
