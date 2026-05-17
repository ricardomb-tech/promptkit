from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.table import Table
from rich import box

if TYPE_CHECKING:
    from .evaluator import PromptResult

RESULTS_DIR = Path(__file__).parent.parent / "results"


def save_run(result: "PromptResult", run_name: str) -> Path:
    date_dir = RESULTS_DIR / datetime.now().strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    out_path = date_dir / f"{run_name}.json"

    # Append to existing list or create new
    existing: list[dict] = []
    if out_path.exists():
        with open(out_path, "r", encoding="utf-8") as fh:
            try:
                existing = json.load(fh)
            except json.JSONDecodeError:
                existing = []

    existing.append(result.to_dict())
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)

    return out_path


def load_history(prompt_name: str) -> list[dict]:
    if not RESULTS_DIR.exists():
        return []

    records: list[dict] = []
    for date_dir in sorted(RESULTS_DIR.iterdir()):
        if not date_dir.is_dir():
            continue
        run_file = date_dir / f"{prompt_name}.json"
        if run_file.exists():
            with open(run_file, "r", encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                    for item in data:
                        item["_date"] = date_dir.name
                    records.extend(data)
                except json.JSONDecodeError:
                    continue

    return records


def summary_table(results: list["PromptResult"]) -> Table:
    table = Table(
        title="Batch Run Results",
        box=box.ROUNDED,
        show_lines=True,
        highlight=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Input (truncated)", style="cyan", max_width=35)
    table.add_column("Latency (ms)", justify="right", style="yellow")
    table.add_column("Tokens In/Out", justify="right", style="blue")
    table.add_column("Cost ($)", justify="right", style="green")
    table.add_column("Quality", justify="right")
    table.add_column("JSON", justify="center")
    table.add_column("Fields", justify="center")

    for i, r in enumerate(results, 1):
        snippet = str(r.input_vars).strip()[:32] + ("…" if len(str(r.input_vars)) > 32 else "")
        quality_str = _score_color(r.quality_score)
        json_mark = "[green]✓[/green]" if r.is_valid_json else "[red]✗[/red]"
        fields_mark = "[green]✓[/green]" if r.has_required_fields else "[red]✗[/red]"

        table.add_row(
            str(i),
            snippet,
            f"{r.latency_ms:.0f}",
            f"{r.input_tokens}/{r.output_tokens}",
            f"{r.cost_usd:.6f}",
            quality_str,
            json_mark,
            fields_mark,
        )

    return table


def history_table(records: list[dict], prompt_name: str) -> Table:
    table = Table(
        title=f"History — {prompt_name}",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("Date", style="dim")
    table.add_column("Model", style="cyan")
    table.add_column("Quality", justify="right")
    table.add_column("JSON", justify="center")
    table.add_column("Latency (ms)", justify="right", style="yellow")
    table.add_column("Cost ($)", justify="right", style="green")

    for rec in records:
        quality_str = _score_color(rec.get("quality_score", 0))
        json_mark = "[green]✓[/green]" if rec.get("is_valid_json") else "[red]✗[/red]"
        table.add_row(
            rec.get("_date", "?"),
            rec.get("model", "?"),
            quality_str,
            json_mark,
            str(rec.get("latency_ms", "?")),
            f"{rec.get('cost_usd', 0):.6f}",
        )

    return table


def _score_color(score: float) -> str:
    if score >= 0.8:
        return f"[green]{score:.3f}[/green]"
    elif score >= 0.5:
        return f"[yellow]{score:.3f}[/yellow]"
    else:
        return f"[red]{score:.3f}[/red]"
