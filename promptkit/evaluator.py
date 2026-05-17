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

# Per-token pricing: (input, output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.00000025, 0.00000125),
    "claude-haiku": (0.00000025, 0.00000125),
    "claude-sonnet-4-6": (0.000003, 0.000015),
    "claude-sonnet": (0.000003, 0.000015),
    "claude-opus-4-7": (0.000015, 0.000075),
    "claude-opus": (0.000015, 0.000075),
}

def _render_template(template: str, variables: dict) -> str:
    """Replace {var_name} placeholders while leaving other {…} untouched.

    Only substitutes tokens that match a key in `variables`, so JSON
    examples like {"category": "…"} in the template are preserved.
    Raises KeyError if a placeholder has no matching variable.
    """
    required: set[str] = set(re.findall(r"\{(\w+)\}", template))
    missing = required - variables.keys()
    if missing:
        raise KeyError(next(iter(missing)))

    def replacer(m: re.Match) -> str:
        key = m.group(1)
        if key in variables:
            return str(variables[key])
        return m.group(0)  # leave unknown {…} alone

    return re.sub(r"\{(\w+)\}", replacer, template)


# Fallback bucket matching
_PRICING_BUCKETS = [
    ("haiku", (0.00000025, 0.00000125)),
    ("sonnet", (0.000003, 0.000015)),
    ("opus", (0.000015, 0.000075)),
]


@dataclass
class PromptResult:
    version: str
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    quality_score: float  # 0.0 – 1.0 from LLM-as-judge
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


class PromptKit:
    def __init__(self, api_key: str | None = None, mock: bool = False) -> None:
        self._mock = mock
        if not mock:
            self._client = anthropic.Anthropic(
                api_key=api_key or os.environ["ANTHROPIC_API_KEY"]
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, prompt_path: str | Path, input_vars: dict, model: str | None = None) -> PromptResult:
        spec = self._load_spec(prompt_path)
        if model:
            spec["model"] = model
        if self._mock:
            return self._mock_execute(spec, input_vars)
        return self._execute(spec, input_vars)

    def batch_run(
        self, prompt_path: str | Path, inputs: list[dict], model: str | None = None
    ) -> list[PromptResult]:
        spec = self._load_spec(prompt_path)
        if model:
            spec["model"] = model
        execute = self._mock_execute if self._mock else self._execute
        return [execute(spec, iv) for iv in inputs]

    def compare(
        self,
        prompt_a: str | Path,
        prompt_b: str | Path,
        inputs: list[dict],
        model_a: str | None = None,
        model_b: str | None = None,
    ) -> dict:
        results_a = self.batch_run(prompt_a, inputs, model=model_a)
        results_b = self.batch_run(prompt_b, inputs, model=model_b)

        def avg(results: list[PromptResult], attr: str) -> float:
            vals = [getattr(r, attr) for r in results]
            return sum(vals) / len(vals) if vals else 0.0

        stats_a = self._aggregate_stats(results_a)
        stats_b = self._aggregate_stats(results_b)

        spec_a = self._load_spec(prompt_a)
        spec_b = self._load_spec(prompt_b)

        winner, reasoning = self._pick_winner(stats_a, stats_b, spec_a, spec_b)

        return {
            "prompt_a": {"name": spec_a["name"], "stats": stats_a, "results": results_a},
            "prompt_b": {"name": spec_b["name"], "stats": stats_b, "results": results_b},
            "winner": winner,
            "reasoning": reasoning,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_spec(self, path: str | Path) -> dict:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def _mock_execute(self, spec: dict, input_vars: dict) -> PromptResult:
        import random
        name = spec.get("name", "")
        parsed = _MOCK_RESPONSES.get(name, {"result": "mock response", "status": "ok"})
        raw = json.dumps(parsed, indent=2)
        expected_fields: list[str] = spec.get("expected_output_fields", [])
        in_tok = random.randint(150, 300)
        out_tok = random.randint(80, 180)
        return PromptResult(
            version=str(spec.get("version", "1.0")),
            model=spec.get("model", "claude-haiku-4-5-20251001") + " [mock]",
            latency_ms=round(random.uniform(200, 900), 2),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=round(self._cost(in_tok, out_tok, spec.get("model", "claude-haiku-4-5-20251001")), 8),
            quality_score=round(random.uniform(0.82, 0.97), 3),
            is_valid_json=True,
            has_required_fields=all(f in parsed for f in expected_fields),
            raw_output=raw,
            parsed_output=parsed,
            prompt_name=name,
            input_vars=input_vars,
        )

    def _execute(self, spec: dict, input_vars: dict) -> PromptResult:
        model: str = spec.get("model", "claude-haiku-4-5-20251001")
        max_tokens: int = spec.get("max_tokens", 1024)
        system_prompt: str = spec.get("system_prompt", "")
        user_template: str = spec.get("user_template", "{text}")
        expected_fields: list[str] = spec.get("expected_output_fields", [])
        version: str = str(spec.get("version", "1.0"))

        try:
            user_message = _render_template(user_template, input_vars)
        except KeyError as exc:
            return PromptResult(
                version=version,
                model=model,
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0,
                quality_score=0,
                is_valid_json=False,
                has_required_fields=False,
                raw_output="",
                prompt_name=spec.get("name", ""),
                input_vars=input_vars,
                error=f"Missing template variable: {exc}",
            )

        messages = [{"role": "user", "content": user_message}]

        t0 = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
            )
        except Exception as exc:
            return PromptResult(
                version=version,
                model=model,
                latency_ms=(time.perf_counter() - t0) * 1000,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0,
                quality_score=0,
                is_valid_json=False,
                has_required_fields=False,
                raw_output="",
                prompt_name=spec.get("name", ""),
                input_vars=input_vars,
                error=str(exc),
            )

        latency_ms = (time.perf_counter() - t0) * 1000
        raw = response.content[0].text
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        cost = self._cost(in_tok, out_tok, model)

        parsed, is_valid_json = self._parse_json(raw)
        has_fields = self._check_fields(parsed, expected_fields)

        quality = self._llm_judge(
            output=raw,
            task_description=spec.get("description", ""),
            criteria="accuracy, completeness, and adherence to the requested JSON format",
        )

        return PromptResult(
            version=version,
            model=model,
            latency_ms=round(latency_ms, 2),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=round(cost, 8),
            quality_score=round(quality, 3),
            is_valid_json=is_valid_json,
            has_required_fields=has_fields,
            raw_output=raw,
            parsed_output=parsed,
            prompt_name=spec.get("name", ""),
            input_vars=input_vars,
        )

    def _parse_json(self, text: str) -> tuple[dict, bool]:
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text), True
        except json.JSONDecodeError:
            return {}, False

    def _check_fields(self, parsed: dict, expected: list[str]) -> bool:
        if not expected:
            return True
        return all(f in parsed for f in expected)

    def _llm_judge(
        self, output: str, task_description: str, criteria: str
    ) -> float:
        judge_prompt = (
            f"You are an impartial AI evaluator.\n\n"
            f"Task description: {task_description}\n\n"
            f"Output to evaluate:\n{output}\n\n"
            f"Evaluation criteria: {criteria}\n\n"
            "Score this output from 0.0 to 1.0 where:\n"
            "  1.0 = perfect output, exactly meets all criteria\n"
            "  0.7 = good output, mostly meets criteria with minor issues\n"
            "  0.4 = mediocre output, partially meets criteria\n"
            "  0.0 = completely fails to meet criteria\n\n"
            "Respond with ONLY a JSON object: {\"score\": <float>, \"reason\": \"<one sentence>\"}"
        )

        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=128,
                messages=[{"role": "user", "content": judge_prompt}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            data = json.loads(raw)
            score = float(data.get("score", 0.5))
            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5

    def _cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        pricing = MODEL_PRICING.get(model)
        if pricing is None:
            model_lower = model.lower()
            for bucket, p in _PRICING_BUCKETS:
                if bucket in model_lower:
                    pricing = p
                    break
            else:
                pricing = (0.000003, 0.000015)  # default to sonnet
        in_price, out_price = pricing
        return input_tokens * in_price + output_tokens * out_price

    def _aggregate_stats(self, results: list[PromptResult]) -> dict:
        if not results:
            return {}
        n = len(results)
        return {
            "count": n,
            "avg_latency_ms": round(sum(r.latency_ms for r in results) / n, 2),
            "avg_quality_score": round(sum(r.quality_score for r in results) / n, 3),
            "valid_json_rate": round(sum(r.is_valid_json for r in results) / n, 3),
            "required_fields_rate": round(
                sum(r.has_required_fields for r in results) / n, 3
            ),
            "total_cost_usd": round(sum(r.cost_usd for r in results), 8),
            "avg_input_tokens": round(sum(r.input_tokens for r in results) / n, 1),
            "avg_output_tokens": round(sum(r.output_tokens for r in results) / n, 1),
            "error_count": sum(1 for r in results if r.error),
        }

    def _pick_winner(
        self,
        stats_a: dict,
        stats_b: dict,
        spec_a: dict,
        spec_b: dict,
    ) -> tuple[str, str]:
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
            # Tiebreaker: lower latency
            if stats_a.get("avg_latency_ms", 0) <= stats_b.get("avg_latency_ms", 0):
                winner = name_a
                reason = (
                    f"Tie on quality (A={score_a:.3f}, B={score_b:.3f}); "
                    f"{name_a} wins on latency ({stats_a['avg_latency_ms']}ms vs {stats_b['avg_latency_ms']}ms)."
                )
            else:
                winner = name_b
                reason = (
                    f"Tie on quality (A={score_a:.3f}, B={score_b:.3f}); "
                    f"{name_b} wins on latency ({stats_b['avg_latency_ms']}ms vs {stats_a['avg_latency_ms']}ms)."
                )
        elif score_a > score_b:
            winner = name_a
            reason = (
                f"{name_a} scores higher (composite {score_a:.3f} vs {score_b:.3f}). "
                f"Quality: {stats_a['avg_quality_score']} vs {stats_b['avg_quality_score']}, "
                f"Valid JSON: {stats_a['valid_json_rate']} vs {stats_b['valid_json_rate']}."
            )
        else:
            winner = name_b
            reason = (
                f"{name_b} scores higher (composite {score_b:.3f} vs {score_a:.3f}). "
                f"Quality: {stats_b['avg_quality_score']} vs {stats_a['avg_quality_score']}, "
                f"Valid JSON: {stats_b['valid_json_rate']} vs {stats_a['valid_json_rate']}."
            )

        return winner, reason
