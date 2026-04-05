from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from .datasets import load_example, load_natural_instructions
from .instructions import normalize_instruction_line, parse_instruction

PROMPT_RULES = """
You're in {city_name}. Please generate a road network for that city in your mind based on your knowledge.

Each of the next sets of navigation commands describes the walk from S to D. Describe going from D to S in the same style, following these rules.

1. The first step must give the absolute direction (e.g. East, West, North, South). It cannot be vague or merely semantic inversion.
2. You cannot simply invert each sentence. You have to understand the route itself.
3. Use the same navigation style as the input instruction. Prefer head, turn, continue, and arrive as movement verbs.
4. Report your confidence as a percentage at the end and briefly explain why.
5. The number of output instructions should match the input.
6. Include POIs or landmarks if they help explain the reverse route.
7. The first step being absolute direction is mandatory.
""".strip()

NAVIGATION_PREFIXES = ("head", "turn", "keep", "continue", "arrive", "walk")
STOP_PREFIXES = ("confidence:", "explanation:", "reasoning:", "notes:", "note:")


class ReverseRouteProvider(Protocol):
    def generate(self, city_name: str, instructions_text: str) -> str:
        ...


def build_reverse_route_prompt(city_name: str, instructions_text: str) -> str:
    return f"{PROMPT_RULES.format(city_name=city_name)}\n\n{instructions_text.strip()}\n"


def build_dataset_query(example_id: str | int, root: str = "data_set") -> str:
    example = load_example(example_id, root=root)
    natural = load_natural_instructions(example)
    if example.start is None or example.end is None:
        header = "start point: unknown\nend point: unknown"
    else:
        header = f"start point: {example.start}\nend point: {example.end}"
    return header + "\n" + "\n".join(natural)


def is_navigation_line(line: str) -> bool:
    normalized = normalize_instruction_line(line)
    lower = normalized.lower()
    if not any(lower.startswith(prefix) for prefix in NAVIGATION_PREFIXES):
        return False
    command = parse_instruction(normalized)
    if command.primary_action == "arrive":
        return True
    return command.primary_action is not None and command.primary_distance >= 0.0 and ("meter" in lower or "destination" in lower)


def extract_instruction_lines_from_response(response_text: str) -> list[str]:
    lines = [line.strip() for line in response_text.splitlines()]
    extracted: list[str] = []
    started = False
    for line in lines:
        if not line:
            if started:
                break
            continue
        lower = line.lower()
        if started and lower.startswith(STOP_PREFIXES):
            break
        if is_navigation_line(line):
            extracted.append(normalize_instruction_line(line))
            started = True
            continue
        if started:
            break
    return extracted


def clean_reverse_route_response(response_text: str) -> str:
    return "\n".join(extract_instruction_lines_from_response(response_text))


def write_reverse_route_outputs(
    response_text: str,
    *,
    raw_output_path: str | Path | None = None,
    clean_output_path: str | Path | None = None,
) -> tuple[str, str]:
    cleaned = clean_reverse_route_response(response_text)
    if raw_output_path is not None:
        Path(raw_output_path).write_text(response_text, encoding="utf-8")
    if clean_output_path is not None:
        Path(clean_output_path).write_text(cleaned + ("\n" if cleaned else ""), encoding="utf-8")
    return response_text, cleaned


class GeminiReverseRouteProvider:
    def __init__(self, api_key: str | None = None, model_name: str = "gemini-1.5-pro"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name

    def generate(self, city_name: str, instructions_text: str) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        import google.generativeai as genai

        genai.configure(api_key=self.api_key, transport="rest")
        model = genai.GenerativeModel(self.model_name)
        return model.generate_content(build_reverse_route_prompt(city_name, instructions_text)).text


class OpenAIReverseRouteProvider:
    def __init__(self, api_key: str | None = None, model_name: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name

    def generate(self, city_name: str, instructions_text: str) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        response = client.responses.create(
            model=self.model_name,
            input=build_reverse_route_prompt(city_name, instructions_text),
        )
        return response.output_text


def create_reverse_route_provider(provider_name: str, *, api_key: str | None = None, model_name: str | None = None) -> ReverseRouteProvider:
    normalized = provider_name.strip().lower()
    if normalized == "openai":
        return OpenAIReverseRouteProvider(api_key=api_key, model_name=model_name or "gpt-4o")
    if normalized == "gemini":
        return GeminiReverseRouteProvider(api_key=api_key, model_name=model_name or "gemini-1.5-pro")
    raise ValueError(f"Unsupported reverse-route provider: {provider_name}")
