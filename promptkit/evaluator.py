from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
import yaml

# ---------------------------------------------------------------------------
# Pricing — Anthropic models (local/Ollama = $0 always)
# ---------------------------------------------------------------------------

MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.00000025, 0.00000125),
    "claude-haiku":              (0.00000025, 0.00000125),
    "claude-sonnet-4-6":         (0.000003,   0.000015),
    "claude-sonnet":             (0.000003,   0.000015),
    "claude-opus-4-7":           (0.000015,   0.000075),
    "claude-opus":               (0.000015,   0.000075),
}

_PRICING_BUCKETS = [
    ("haiku",  (0.00000025, 0.00000125)),
    ("sonnet", (0.000003,   0.000015)),
    ("opus",   (0.000015,   0.000075)),
]

OLLAMA_DEFAULT_URL = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Template renderer
# ---------------------------------------------------------------------------

def _render_template(template: str, variables: dict) -> str:
    """Sustituye {var} en el template sin tocar los {…} de ejemplos JSON."""
    required: set[str] = set(re.findall(r"\{(\w+)\}", template))
    missing = required - variables.keys()
    if missing:
        raise KeyError(next(iter(missing)))

    def replacer(m: re.Match) -> str:
        key = m.group(1)
        return str(variables[key]) if key in variables else m.group(0)

    return re.sub(r"\{(\w+)\}", replacer, template)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PromptResult:
    version: str
    model: str
    provider: str           # "anthropic" | "ollama"
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    quality_score: float
    is_valid_json: bool
    has_required_fields: bool
    raw_output: str
    parsed_output: dict[str, Any] = field(default_factory=dict)
    prompt_name: str = ""
    input_vars: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "model": self.model,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "quality_score": self.quality_score,
            "is_valid_json": self.is_valid_json,
            "has_required_fields": self.has_required_fields,
            "raw_output": self.raw_output,
            "parsed_output": self.parsed_output,
            "prompt_name": self.prompt_name,
            "input_vars": self.input_vars,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------

_MOCK_RESPONSES: dict[str, dict] = {
    "example_classifier": {
        "category": "technical_issue",
        "confidence": 0.97,
        "reasoning": "Text describes a server crash event with timestamp and impact on user sessions.",
        "keywords": ["server crashed", "3am", "user sessions", "on-call"],
    },
    "example_extractor": {
        "subject": "Server outage incident",
        "sentiment": "negative",
        "entities": {
            "people": ["on-call engineer"],
            "organizations": [],
            "locations": [],
            "dates": ["3am"],
        },
        "key_facts": [
            "Server crashed at 3am",
            "All user sessions lost",
            "45-minute service restoration time",
        ],
        "action_required": True,
    },
}


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class PromptKit:
    def __init__(
        self,
        provider: str = "anthropic",
        api_key: str | None = None,
        ollama_url: str = OLLAMA_DEFAULT_URL,
        mock: bool = False,
    ) -> None:
        self._mock = mock
        self._provider = provider.lower()
        self._ollama_url = ollama_url.rstrip("/")

        if mock:
            return

        if self._provider == "anthropic":
            self._anthropic = anthropic.Anthropic(
                api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            )
            self._openai_client = None
        elif self._provider == "ollama":
            from openai import OpenAI
            self._openai_client = OpenAI(
                base_url=f"{self._ollama_url}/v1",
                api_key="ollama",          # Ollama no valida la key
            )
            self._anthropic = None
        else:
            raise ValueError(f"Provider desconocido: '{provider}'. Usa 'anthropic' u 'ollama'.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        prompt_path: str | Path,
        input_vars: dict,
        model: str | None = None,
        provider: str | None = None,
    ) -> PromptResult:
        spec = self._load_spec(prompt_path)
        if model:
            spec["model"] = model
        if provider:
            spec["provider"] = provider
        if self._mock:
            return self._mock_execute(spec, input_vars)
        return self._execute(spec, input_vars)

    def batch_run(
        self,
        prompt_path: str | Path,
        inputs: list[dict],
        model: str | None = None,
        provider: str | None = None,
    ) -> list[PromptResult]:
        spec = self._load_spec(prompt_path)
        if model:
            spec["model"] = model
        if provider:
            spec["provider"] = provider
        execute = self._mock_execute if self._mock else self._execute
        return [execute(spec, iv) for iv in inputs]

    def compare(
        self,
        prompt_a: str | Path,
        prompt_b: str | Path,
        inputs: list[dict],
        model_a: str | None = None,
        model_b: str | None = None,
        provider_a: str | None = None,
        provider_b: str | None = None,
    ) -> dict:
        results_a = self.batch_run(prompt_a, inputs, model=model_a, provider=provider_a)
        results_b = self.batch_run(prompt_b, inputs, model=model_b, provider=provider_b)

        stats_a = self._aggregate_stats(results_a)
        stats_b = self._aggregate_stats(results_b)
        spec_a  = self._load_spec(prompt_a)
        spec_b  = self._load_spec(prompt_b)
        winner, reasoning = self._pick_winner(stats_a, stats_b, spec_a, spec_b)

        return {
            "prompt_a": {"name": spec_a["name"], "stats": stats_a, "results": results_a},
            "prompt_b": {"name": spec_b["name"], "stats": stats_b, "results": results_b},
            "winner": winner,
            "reasoning": reasoning,
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute(self, spec: dict, input_vars: dict) -> PromptResult:
        # El provider del spec anula el del constructor (permite mezclar en compare)
        effective_provider = spec.get("provider", self._provider).lower()

        if effective_provider == "ollama":
            return self._execute_ollama(spec, input_vars)
        return self._execute_anthropic(spec, input_vars)

    def _execute_anthropic(self, spec: dict, input_vars: dict) -> PromptResult:
        model         = spec.get("model", "claude-haiku-4-5-20251001")
        max_tokens    = spec.get("max_tokens", 1024)
        system_prompt = spec.get("system_prompt", "")
        user_template = spec.get("user_template", "{text}")
        expected      = spec.get("expected_output_fields", [])
        version       = str(spec.get("version", "1.0"))

        try:
            user_message = _render_template(user_template, input_vars)
        except KeyError as exc:
            return self._error_result(spec, input_vars, f"Variable faltante: {exc}", "anthropic")

        t0 = time.perf_counter()
        try:
            response = self._anthropic.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            return self._error_result(spec, input_vars, str(exc), "anthropic",
                                      latency_ms=(time.perf_counter() - t0) * 1000)

        latency_ms = (time.perf_counter() - t0) * 1000
        raw     = response.content[0].text
        in_tok  = response.usage.input_tokens
        out_tok = response.usage.output_tokens

        parsed, is_valid_json = self._parse_json(raw)
        has_fields = self._check_fields(parsed, expected)
        quality    = self._llm_judge_anthropic(raw, spec.get("description", ""))

        return PromptResult(
            version=version, model=model, provider="anthropic",
            latency_ms=round(latency_ms, 2),
            input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=round(self._cost(in_tok, out_tok, model), 8),
            quality_score=round(quality, 3),
            is_valid_json=is_valid_json, has_required_fields=has_fields,
            raw_output=raw, parsed_output=parsed,
            prompt_name=spec.get("name", ""), input_vars=input_vars,
        )

    def _execute_ollama(self, spec: dict, input_vars: dict) -> PromptResult:
        model         = spec.get("model", "llama3.2")
        max_tokens    = spec.get("max_tokens", 1024)
        system_prompt = spec.get("system_prompt", "")
        user_template = spec.get("user_template", "{text}")
        expected      = spec.get("expected_output_fields", [])
        version       = str(spec.get("version", "1.0"))

        try:
            user_message = _render_template(user_template, input_vars)
        except KeyError as exc:
            return self._error_result(spec, input_vars, f"Variable faltante: {exc}", "ollama")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        t0 = time.perf_counter()
        try:
            response = self._openai_client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            )
        except Exception as exc:
            return self._error_result(spec, input_vars, str(exc), "ollama",
                                      latency_ms=(time.perf_counter() - t0) * 1000)

        latency_ms = (time.perf_counter() - t0) * 1000
        raw     = response.choices[0].message.content or ""
        in_tok  = response.usage.prompt_tokens if response.usage else 0
        out_tok = response.usage.completion_tokens if response.usage else 0

        parsed, is_valid_json = self._parse_json(raw)
        has_fields = self._check_fields(parsed, expected)
        quality    = self._llm_judge_ollama(raw, spec.get("description", ""), model)

        return PromptResult(
            version=version, model=model, provider="ollama",
            latency_ms=round(latency_ms, 2),
            input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=0.0,          # modelos locales = gratis
            quality_score=round(quality, 3),
            is_valid_json=is_valid_json, has_required_fields=has_fields,
            raw_output=raw, parsed_output=parsed,
            prompt_name=spec.get("name", ""), input_vars=input_vars,
        )

    def _mock_execute(self, spec: dict, input_vars: dict) -> PromptResult:
        import random
        name   = spec.get("name", "")
        prov   = spec.get("provider", self._provider)
        parsed = _MOCK_RESPONSES.get(name, {"result": "mock response", "status": "ok"})
        raw    = json.dumps(parsed, indent=2)
        expected = spec.get("expected_output_fields", [])
        in_tok   = random.randint(150, 300)
        out_tok  = random.randint(80, 180)
        model    = spec.get("model", "llama3.2" if prov == "ollama" else "claude-haiku-4-5-20251001")
        return PromptResult(
            version=str(spec.get("version", "1.0")),
            model=model + " [mock]", provider=prov,
            latency_ms=round(random.uniform(200, 900), 2),
            input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=0.0 if prov == "ollama" else round(self._cost(in_tok, out_tok, model), 8),
            quality_score=round(random.uniform(0.82, 0.97), 3),
            is_valid_json=True,
            has_required_fields=all(f in parsed for f in expected),
            raw_output=raw, parsed_output=parsed,
            prompt_name=name, input_vars=input_vars,
        )

    # ------------------------------------------------------------------
    # LLM Judge (uno por provider)
    # ------------------------------------------------------------------

    def _llm_judge_anthropic(self, output: str, task_description: str) -> float:
        prompt = self._judge_prompt(output, task_description)
        try:
            resp = self._anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_judge_score(resp.content[0].text)
        except Exception:
            return 0.5

    def _llm_judge_ollama(self, output: str, task_description: str, model: str) -> float:
        prompt = self._judge_prompt(output, task_description)
        try:
            resp = self._openai_client.chat.completions.create(
                model=model,
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_judge_score(resp.choices[0].message.content or "")
        except Exception:
            return 0.5

    def _judge_prompt(self, output: str, task_description: str) -> str:
        return (
            f"You are an impartial AI evaluator.\n\n"
            f"Task description: {task_description}\n\n"
            f"Output to evaluate:\n{output}\n\n"
            "Score this output from 0.0 to 1.0:\n"
            "  1.0 = perfect  |  0.7 = good  |  0.4 = mediocre  |  0.0 = fails\n\n"
            'Respond ONLY with JSON: {"score": <float>, "reason": "<one sentence>"}'
        )

    def _parse_judge_score(self, raw: str) -> float:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            data = json.loads(raw)
            return max(0.0, min(1.0, float(data.get("score", 0.5))))
        except Exception:
            return 0.5

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _error_result(
        self, spec: dict, input_vars: dict, error: str,
        provider: str, latency_ms: float = 0
    ) -> PromptResult:
        return PromptResult(
            version=str(spec.get("version", "1.0")),
            model=spec.get("model", ""), provider=provider,
            latency_ms=round(latency_ms, 2),
            input_tokens=0, output_tokens=0, cost_usd=0,
            quality_score=0, is_valid_json=False, has_required_fields=False,
            raw_output="", prompt_name=spec.get("name", ""),
            input_vars=input_vars, error=error,
        )

    def _load_spec(self, path: str | Path) -> dict:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def _parse_json(self, text: str) -> tuple[dict, bool]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text), True
        except json.JSONDecodeError:
            return {}, False

    def _check_fields(self, parsed: dict, expected: list[str]) -> bool:
        return all(f in parsed for f in expected) if expected else True

    def _cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        pricing = MODEL_PRICING.get(model)
        if pricing is None:
            for bucket, p in _PRICING_BUCKETS:
                if bucket in model.lower():
                    pricing = p
                    break
            else:
                pricing = (0.000003, 0.000015)
        return input_tokens * pricing[0] + output_tokens * pricing[1]

    def _aggregate_stats(self, results: list[PromptResult]) -> dict:
        if not results:
            return {}
        n = len(results)
        return {
            "count": n,
            "avg_latency_ms":       round(sum(r.latency_ms for r in results) / n, 2),
            "avg_quality_score":    round(sum(r.quality_score for r in results) / n, 3),
            "valid_json_rate":      round(sum(r.is_valid_json for r in results) / n, 3),
            "required_fields_rate": round(sum(r.has_required_fields for r in results) / n, 3),
            "total_cost_usd":       round(sum(r.cost_usd for r in results), 8),
            "avg_input_tokens":     round(sum(r.input_tokens for r in results) / n, 1),
            "avg_output_tokens":    round(sum(r.output_tokens for r in results) / n, 1),
            "error_count":          sum(1 for r in results if r.error),
        }

    def _pick_winner(self, stats_a, stats_b, spec_a, spec_b) -> tuple[str, str]:
        score_a = (
            stats_a.get("avg_quality_score", 0) * 0.5
            + stats_a.get("valid_json_rate", 0) * 0.25
            + stats_a.get("required_fields_rate", 0) * 0.25
        )
        score_b = (
            stats_b.get("avg_quality_score", 0) * 0.5
            + stats_b.get("valid_json_rate", 0) * 0.25
            + stats_b.get("required_fields_rate", 0) * 0.25
        )
        name_a = spec_a.get("name", "Prompt A")
        name_b = spec_b.get("name", "Prompt B")

        if abs(score_a - score_b) < 0.02:
            if stats_a.get("avg_latency_ms", 0) <= stats_b.get("avg_latency_ms", 0):
                return name_a, (
                    f"Empate en calidad (A={score_a:.3f}, B={score_b:.3f}); "
                    f"{name_a} gana por latencia ({stats_a['avg_latency_ms']}ms vs {stats_b['avg_latency_ms']}ms)."
                )
            return name_b, (
                f"Empate en calidad (A={score_a:.3f}, B={score_b:.3f}); "
                f"{name_b} gana por latencia ({stats_b['avg_latency_ms']}ms vs {stats_a['avg_latency_ms']}ms)."
            )
        if score_a > score_b:
            return name_a, (
                f"{name_a} puntaje mayor (compuesto {score_a:.3f} vs {score_b:.3f}). "
                f"Calidad: {stats_a['avg_quality_score']} vs {stats_b['avg_quality_score']}."
            )
        return name_b, (
            f"{name_b} puntaje mayor (compuesto {score_b:.3f} vs {score_a:.3f}). "
            f"Calidad: {stats_b['avg_quality_score']} vs {stats_a['avg_quality_score']}."
        )
