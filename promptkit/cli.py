from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.prompt import Prompt, Confirm

from .evaluator import PromptKit
from .storage import save_run, load_history, summary_table, history_table

# Load .env from project root if present
load_dotenv(Path(__file__).parent.parent / ".env")

console = Console()
kit = None  # lazy-initialised


def _get_kit(
    mock: bool = False,
    provider: str = "anthropic",
    ollama_url: str = "http://localhost:11434",
) -> PromptKit:
    global kit
    if mock:
        return PromptKit(mock=True)
    if provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY no está configurada.\n"
            "Agrégala al archivo [bold].env[/bold]:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )
        sys.exit(1)
    # Crea instancia fresca si cambió el provider/url
    if kit is None or getattr(kit, "_provider", None) != provider:
        kit = PromptKit(provider=provider, ollama_url=ollama_url)
    return kit


@click.group()
def cli():
    """PromptKit — Prompt Engineering CLI Toolkit"""


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

_MODEL_HELP = (
    "Modelo a usar (anula el del YAML). "
    "Anthropic: claude-haiku-4-5-20251001, claude-sonnet-4-6, claude-opus-4-7. "
    "Ollama: llama3.2, mistral, qwen2.5, phi3.5, etc."
)
_PROVIDER_HELP = "Provider de IA: 'anthropic' (default) u 'ollama' (local, gratis)."
_OLLAMA_URL_HELP = "URL de Ollama (default: http://localhost:11434)."


@cli.command("run")
@click.argument("prompt_yaml", type=click.Path(exists=True))
@click.option("--input", "-i", "input_json", default=None, help="JSON string de variables de entrada")
@click.option("--input-file", "input_file", default=None, type=click.Path(exists=True),
              help="Archivo JSON con un objeto de entrada")
@click.option("--model", "-m", default=None, help=_MODEL_HELP)
@click.option("--provider", "-p", default="anthropic", help=_PROVIDER_HELP)
@click.option("--ollama-url", default="http://localhost:11434", help=_OLLAMA_URL_HELP)
@click.option("--mock", is_flag=True, default=False, help="Respuestas simuladas (sin llamar a la API)")
@click.option("--save/--no-save", default=True, help="Guardar resultado en disco")
def run_cmd(prompt_yaml: str, input_json: str | None, input_file: str | None,
            model: str | None, provider: str, ollama_url: str, mock: bool, save: bool):
    """Run a prompt — asks for input interactively if no --input/--input-file given."""
    if input_file:
        with open(input_file, "r", encoding="utf-8") as fh:
            raw = fh.read()
        try:
            input_vars = json.loads(raw)
            if isinstance(input_vars, list):
                input_vars = input_vars[0]
        except json.JSONDecodeError as exc:
            console.print(f"[red]Invalid JSON in file:[/red] {exc}")
            sys.exit(1)
    elif input_json:
        try:
            input_vars = json.loads(input_json)
        except json.JSONDecodeError as exc:
            console.print(f"[red]Invalid JSON input:[/red] {exc}")
            sys.exit(1)
    else:
        # Interactive mode: read template variables one by one
        input_vars = _ask_input_vars(prompt_yaml)

    spec_name = Path(prompt_yaml).stem
    _print_run_header(spec_name, model, provider, mock)

    status_msg = "[bold green]Consultando Ollama…" if provider == "ollama" else "[bold green]Llamando a Claude API…"
    with console.status(status_msg):
        result = _get_kit(mock=mock, provider=provider, ollama_url=ollama_url).run(
            prompt_yaml, input_vars, model=model
        )

    _print_result(result)

    if save:
        path = save_run(result, spec_name)
        console.print(f"\n[dim]Guardado en:[/dim] {path}")


# ---------------------------------------------------------------------------
# chat  (loop interactivo continuo)
# ---------------------------------------------------------------------------

@cli.command("chat")
@click.argument("prompt_yaml", type=click.Path(exists=True))
@click.option("--model", "-m", default=None, help=_MODEL_HELP)
@click.option("--provider", "-p", default="anthropic", help=_PROVIDER_HELP)
@click.option("--ollama-url", default="http://localhost:11434", help=_OLLAMA_URL_HELP)
@click.option("--mock", is_flag=True, default=False, help="Respuestas simuladas")
@click.option("--save/--no-save", default=True, help="Guardar cada resultado en disco")
def chat_cmd(prompt_yaml: str, model: str | None, provider: str, ollama_url: str, mock: bool, save: bool):
    """Loop interactivo: escribe tus entradas, ve el resultado, repite. Ctrl+C para salir."""
    import yaml as _yaml
    with open(prompt_yaml, "r", encoding="utf-8") as fh:
        spec = _yaml.safe_load(fh)

    spec_name = Path(prompt_yaml).stem
    variables = _template_vars(spec.get("user_template", ""))
    eff_model = model or spec.get("model", "llama3.2" if provider == "ollama" else "haiku")
    provider_badge = "[green]ollama[/green]" if provider == "ollama" else "[cyan]anthropic[/cyan]"

    console.print(Panel(
        f"[bold cyan]Chat mode:[/bold cyan] [yellow]{spec_name}[/yellow] "
        f"[dim]({eff_model})[/dim] {provider_badge}\n"
        f"[dim]Variables: {', '.join(variables) if variables else 'ninguna'}[/dim]\n"
        f"[dim]Escribe tus respuestas. Presiona [bold]Ctrl+C[/bold] para salir.[/dim]",
        border_style="cyan",
        expand=False,
    ))

    kit_instance = _get_kit(mock=mock, provider=provider, ollama_url=ollama_url)
    run_count = 0

    try:
        while True:
            run_count += 1
            console.rule(f"[dim]Corrida #{run_count}[/dim]")

            # Collect inputs interactively
            if variables:
                input_vars: dict = {}
                for var in variables:
                    try:
                        if len(variables) == 1 and var == "text":
                            value = _read_multiline(f"[bold green]{var}[/bold green]")
                        else:
                            value = Prompt.ask(f"[bold green]{var}[/bold green]")
                    except EOFError:
                        console.print(f"\n[dim]Fin de entrada. {run_count - 1} corridas completadas.[/dim]")
                        return
                    input_vars[var] = value
            else:
                input_vars = {}

            with console.status("[bold green]Analizando…"):
                result = kit_instance.run(prompt_yaml, input_vars, model=model)

            _print_result(result)

            if save:
                save_run(result, spec_name)

            console.print()  # blank line before next iteration

    except (KeyboardInterrupt, click.exceptions.Abort):
        completed = run_count - 1
        console.print(f"\n\n[dim]Saliendo. {completed} corrida{'s' if completed != 1 else ''} completada{'s' if completed != 1 else ''}.[/dim]")


# ---------------------------------------------------------------------------
# batch
# ---------------------------------------------------------------------------

@cli.command("batch")
@click.argument("prompt_yaml", type=click.Path(exists=True))
@click.option("--file", "-f", "inputs_file", required=True, type=click.Path(exists=True),
              help="Archivo JSON con lista de entradas")
@click.option("--model", "-m", default=None, help=_MODEL_HELP)
@click.option("--provider", "-p", default="anthropic", help=_PROVIDER_HELP)
@click.option("--ollama-url", default="http://localhost:11434", help=_OLLAMA_URL_HELP)
@click.option("--mock", is_flag=True, default=False, help="Respuestas simuladas")
@click.option("--save/--no-save", default=True)
def batch_cmd(prompt_yaml: str, inputs_file: str, model: str | None,
              provider: str, ollama_url: str, mock: bool, save: bool):
    """Run a prompt against multiple inputs from a JSON file."""
    with open(inputs_file, "r", encoding="utf-8") as fh:
        inputs = json.load(fh)

    if not isinstance(inputs, list):
        console.print("[red]inputs file must contain a JSON array[/red]")
        sys.exit(1)

    spec_name = Path(prompt_yaml).stem
    provider_badge = "[green]ollama[/green]" if provider == "ollama" else "[cyan]anthropic[/cyan]"
    model_label = f" [dim]({model})[/dim]" if model else ""
    console.print(Panel(
        f"[bold cyan]Batch run:[/bold cyan] {spec_name}{model_label} {provider_badge}  ({len(inputs)} entradas)",
        expand=False,
    ))

    kit_b = _get_kit(mock=mock, provider=provider, ollama_url=ollama_url)
    results = []
    with console.status("[bold green]Procesando batch…") as status:
        for idx, iv in enumerate(inputs, 1):
            status.update(f"[bold green]Entrada {idx}/{len(inputs)}…")
            results.append(kit_b.run(prompt_yaml, iv, model=model))

    console.print(summary_table(results))
    _print_aggregate(results)

    if save:
        for r in results:
            save_run(r, spec_name)
        console.print(f"\n[dim]Results saved under results/ directory.[/dim]")


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

@cli.command("compare")
@click.argument("prompt_a", type=click.Path(exists=True))
@click.argument("prompt_b", type=click.Path(exists=True))
@click.option("--file", "-f", "inputs_file", required=True, type=click.Path(exists=True),
              help="JSON file with list of input objects")
@click.option("--model-a", default=None, help="Modelo para prompt A")
@click.option("--model-b", default=None, help="Modelo para prompt B")
@click.option("--model", "-m", default=None, help="Modelo para AMBOS prompts")
@click.option("--provider", "-p", default="anthropic", help=_PROVIDER_HELP)
@click.option("--provider-a", default=None, help="Provider solo para prompt A (anthropic/ollama)")
@click.option("--provider-b", default=None, help="Provider solo para prompt B (anthropic/ollama)")
@click.option("--ollama-url", default="http://localhost:11434", help=_OLLAMA_URL_HELP)
@click.option("--mock", is_flag=True, default=False, help="Respuestas simuladas")
@click.option("--save/--no-save", default=True)
def compare_cmd(prompt_a: str, prompt_b: str, inputs_file: str,
                model_a: str | None, model_b: str | None, model: str | None,
                provider: str, provider_a: str | None, provider_b: str | None,
                ollama_url: str, mock: bool, save: bool):
    """A/B test two prompts on the same inputs."""
    eff_model_a    = model_a or model
    eff_model_b    = model_b or model
    eff_provider_a = provider_a or provider
    eff_provider_b = provider_b or provider

    with open(inputs_file, "r", encoding="utf-8") as fh:
        inputs = json.load(fh)

    name_a = Path(prompt_a).stem
    name_b = Path(prompt_b).stem

    def _plabel(m, p):
        parts = []
        if m: parts.append(m)
        if p != "anthropic": parts.append(p)
        return f" ({', '.join(parts)})" if parts else ""

    console.print(Panel(
        f"[bold cyan]Comparando:[/bold cyan] "
        f"[yellow]{name_a}{_plabel(eff_model_a, eff_provider_a)}[/yellow] vs "
        f"[magenta]{name_b}{_plabel(eff_model_b, eff_provider_b)}[/magenta]  "
        f"({len(inputs)} entradas cada uno)",
        expand=False,
    ))

    with console.status("[bold green]Ejecutando comparación…"):
        kit_c = _get_kit(mock=mock, provider=eff_provider_a, ollama_url=ollama_url)
        comparison = kit_c.compare(
            prompt_a, prompt_b, inputs,
            model_a=eff_model_a, model_b=eff_model_b,
            provider_a=eff_provider_a, provider_b=eff_provider_b,
        )

    # Side-by-side stats table
    stats_a = comparison["prompt_a"]["stats"]
    stats_b = comparison["prompt_b"]["stats"]

    table = Table(title="Comparison Results", box=box.ROUNDED, show_lines=True)
    table.add_column("Metric", style="bold")
    table.add_column(name_a, justify="right", style="yellow")
    table.add_column(name_b, justify="right", style="magenta")

    metrics = [
        ("Avg Quality Score", "avg_quality_score"),
        ("Valid JSON Rate", "valid_json_rate"),
        ("Required Fields Rate", "required_fields_rate"),
        ("Avg Latency (ms)", "avg_latency_ms"),
        ("Total Cost ($)", "total_cost_usd"),
        ("Avg Input Tokens", "avg_input_tokens"),
        ("Avg Output Tokens", "avg_output_tokens"),
        ("Error Count", "error_count"),
    ]

    for label, key in metrics:
        val_a = stats_a.get(key, "N/A")
        val_b = stats_b.get(key, "N/A")
        # Highlight winner for quality metrics
        if isinstance(val_a, float) and isinstance(val_b, float):
            if key in ("avg_quality_score", "valid_json_rate", "required_fields_rate"):
                if val_a > val_b:
                    row_a, row_b = f"[bold green]{val_a}[/bold green]", str(val_b)
                elif val_b > val_a:
                    row_a, row_b = str(val_a), f"[bold green]{val_b}[/bold green]"
                else:
                    row_a, row_b = str(val_a), str(val_b)
            elif key == "avg_latency_ms":
                if val_a < val_b:
                    row_a, row_b = f"[bold green]{val_a}[/bold green]", str(val_b)
                elif val_b < val_a:
                    row_a, row_b = str(val_a), f"[bold green]{val_b}[/bold green]"
                else:
                    row_a, row_b = str(val_a), str(val_b)
            else:
                row_a, row_b = str(val_a), str(val_b)
        else:
            row_a, row_b = str(val_a), str(val_b)
        table.add_row(label, row_a, row_b)

    console.print(table)

    winner = comparison["winner"]
    reasoning = comparison["reasoning"]
    winner_style = "yellow" if winner == name_a else "magenta"

    console.print(Panel(
        f"[bold]Winner:[/bold] [{winner_style}]{winner}[/{winner_style}]\n\n{reasoning}",
        title="[bold green]Verdict[/bold green]",
        border_style="green",
        expand=False,
    ))

    if save:
        for r in comparison["prompt_a"]["results"]:
            save_run(r, name_a)
        for r in comparison["prompt_b"]["results"]:
            save_run(r, name_b)
        console.print("\n[dim]Results saved.[/dim]")


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

@cli.command("history")
@click.argument("prompt_name")
def history_cmd(prompt_name: str):
    """Show quality score trend for a prompt over time."""
    records = load_history(prompt_name)

    if not records:
        console.print(f"[yellow]No history found for:[/yellow] {prompt_name}")
        return

    console.print(history_table(records, prompt_name))

    scores = [r.get("quality_score", 0) for r in records]
    if len(scores) > 1:
        trend = scores[-1] - scores[0]
        direction = "[green]↑ improving[/green]" if trend > 0 else "[red]↓ declining[/red]" if trend < 0 else "[dim]→ stable[/dim]"
        console.print(f"\nTrend over {len(scores)} runs: {direction} ({trend:+.3f})")


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

@cli.command("new")
@click.argument("name")
def new_cmd(name: str):
    """Scaffold a new prompt YAML interactively."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    out_path = prompts_dir / f"{name}.yaml"

    if out_path.exists():
        if not Confirm.ask(f"[yellow]{out_path.name}[/yellow] already exists. Overwrite?"):
            return

    console.print(Panel(f"[bold cyan]New prompt:[/bold cyan] {name}", expand=False))

    description = Prompt.ask("Description")
    model = Prompt.ask(
        "Model",
        choices=["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-7"],
        default="claude-haiku-4-5-20251001",
    )
    max_tokens = int(Prompt.ask("Max tokens", default="512"))
    system_prompt = Prompt.ask("System prompt (one line; use \\n for newlines)")
    system_prompt = system_prompt.replace("\\n", "\n")
    user_template = Prompt.ask(
        "User template (use {var} placeholders)",
        default="Process the following: {text}",
    )
    fields_raw = Prompt.ask("Expected output JSON fields (comma-separated)", default="")
    expected_fields = [f.strip() for f in fields_raw.split(",") if f.strip()]

    spec = {
        "version": "1.0",
        "name": name,
        "description": description,
        "model": model,
        "max_tokens": max_tokens,
        "system_prompt": system_prompt,
        "user_template": user_template,
        "expected_output_fields": expected_fields,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.dump(spec, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    console.print(f"\n[green]Created:[/green] {out_path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_run_header(spec_name: str, model: str | None, provider: str, mock: bool) -> None:
    provider_badge = "[green]ollama[/green]" if provider == "ollama" else "[cyan]anthropic[/cyan]"
    mock_badge = " [dim][MOCK][/dim]" if mock else ""
    model_label = f" [dim]({model})[/dim]" if model else ""
    console.print(Panel(
        f"[bold cyan]Ejecutando:[/bold cyan] {spec_name}{model_label} {provider_badge}{mock_badge}",
        expand=False,
    ))


def _template_vars(template: str) -> list[str]:
    """Return unique placeholder names found in a template, in order of appearance."""
    import re
    seen: set[str] = set()
    result: list[str] = []
    for name in re.findall(r"\{(\w+)\}", template):
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _ask_input_vars(prompt_yaml: str) -> dict:
    """Read template variables from YAML and ask for each one interactively."""
    import yaml as _yaml
    with open(prompt_yaml, "r", encoding="utf-8") as fh:
        spec = _yaml.safe_load(fh)

    template: str = spec.get("user_template", "")
    variables = _template_vars(template)

    if not variables:
        return {}

    console.print(f"[dim]Este prompt necesita {len(variables)} variable(s). Escribe cada una:[/dim]\n")

    input_vars: dict = {}
    for var in variables:
        if len(variables) == 1 and var == "text":
            value = _read_multiline(f"[bold green]{var}[/bold green]")
        else:
            value = Prompt.ask(f"  [bold green]{var}[/bold green]")
        input_vars[var] = value

    return input_vars


def _read_multiline(label: str) -> str:
    """Ask for multiline text input. Empty line + Enter to finish. Raises EOFError on EOF."""
    console.print(
        f"  {label}  [dim](escribe tu texto; línea vacía para terminar)[/dim]"
    )
    lines: list[str] = []
    while True:
        try:
            line = input("  > ")
        except EOFError:
            if not lines:
                raise  # propagate so callers can exit
            break
        if line == "" and lines:
            break
        lines.append(line)
    return "\n".join(lines)


def _print_result(result) -> None:
    status = "[green]✓[/green]" if result.is_valid_json else "[red]✗[/red]"
    fields_status = "[green]✓[/green]" if result.has_required_fields else "[red]✗[/red]"

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim")
    meta.add_column()
    meta.add_row("Model:", result.model)
    meta.add_row("Latency:", f"{result.latency_ms:.0f} ms")
    meta.add_row("Tokens:", f"{result.input_tokens} in / {result.output_tokens} out")
    meta.add_row("Cost:", f"${result.cost_usd:.6f}")
    meta.add_row("Quality score:", f"{result.quality_score:.3f}")
    meta.add_row("Valid JSON:", status)
    meta.add_row("Required fields:", fields_status)
    console.print(meta)

    if result.error:
        console.print(Panel(f"[red]{result.error}[/red]", title="Error", border_style="red"))
        return

    if result.parsed_output:
        console.print(Panel(
            json.dumps(result.parsed_output, indent=2),
            title="[bold]Parsed Output[/bold]",
            border_style="blue",
        ))
    else:
        console.print(Panel(result.raw_output, title="[bold]Raw Output[/bold]", border_style="dim"))


def _print_aggregate(results) -> None:
    if not results:
        return
    n = len(results)
    avg_q = sum(r.quality_score for r in results) / n
    avg_lat = sum(r.latency_ms for r in results) / n
    total_cost = sum(r.cost_usd for r in results)
    valid_json_pct = sum(r.is_valid_json for r in results) / n * 100

    console.print(f"\n[bold]Aggregate:[/bold] {n} runs | "
                  f"avg quality [cyan]{avg_q:.3f}[/cyan] | "
                  f"avg latency [yellow]{avg_lat:.0f}ms[/yellow] | "
                  f"valid JSON [green]{valid_json_pct:.0f}%[/green] | "
                  f"total cost [green]${total_cost:.5f}[/green]")


if __name__ == "__main__":
    cli()
