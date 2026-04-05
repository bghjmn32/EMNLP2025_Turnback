from __future__ import annotations

import json
import random
import time
from collections import deque
from pathlib import Path
from typing import Any

import requests

from .instructions import format_ors_steps_as_instruction_lines, format_ors_steps_as_natural_lines, parse_instruction_lines, write_parsed_instructions
from .io import save_geojson, write_json

NOMINAL_PER_MINUTE = 39
NOMINAL_PER_SECOND = 1
SAFETY_MARGIN = 0.95
ADAPTIVE_DOWN_FACTOR = 0.9
ADAPTIVE_UP_STEP = 1
STABILITY_WINDOW_SECONDS = 120
RETRIABLE_STATUSES = {502, 503, 504}
MAX_HTTP_RETRIES = 3
BASE_BACKOFF = 1.0


class RateLimiter:
    def __init__(self, per_minute: int = NOMINAL_PER_MINUTE, per_second: int = NOMINAL_PER_SECOND, safety_margin: float = SAFETY_MARGIN):
        self.nominal_per_minute = int(per_minute * safety_margin)
        self.nominal_per_second = int(per_second)
        self.per_minute = self.nominal_per_minute
        self.per_second = self.nominal_per_second
        self.last_minute: deque[float] = deque()
        self.last_second: deque[float] = deque()
        self._last_adjust_ts = time.monotonic()

    def _cleanup(self, now: float) -> None:
        while self.last_minute and now - self.last_minute[0] >= 60.0:
            self.last_minute.popleft()
        while self.last_second and now - self.last_second[0] >= 1.0:
            self.last_second.popleft()

    def wait_for_slot(self) -> None:
        while True:
            now = time.monotonic()
            self._cleanup(now)
            wait_time = 0.0
            if len(self.last_minute) >= self.per_minute:
                wait_time = max(wait_time, 60.0 - (now - self.last_minute[0]))
            if len(self.last_second) >= self.per_second:
                wait_time = max(wait_time, 1.0 - (now - self.last_second[0]))
            if wait_time <= 0:
                time.sleep(random.uniform(0.01, 0.05))
                now = time.monotonic()
                self.last_minute.append(now)
                self.last_second.append(now)
                return
            time.sleep(wait_time)

    def on_429(self, retry_after: float) -> None:
        time.sleep(float(retry_after))
        new_limit = max(int(self.per_minute * ADAPTIVE_DOWN_FACTOR), 10)
        if new_limit < self.per_minute:
            self.per_minute = new_limit
        self._last_adjust_ts = time.monotonic()

    def maybe_recover(self) -> None:
        now = time.monotonic()
        if now - self._last_adjust_ts >= STABILITY_WINDOW_SECONDS and self.per_minute < self.nominal_per_minute:
            self.per_minute = min(self.per_minute + ADAPTIVE_UP_STEP, self.nominal_per_minute)
            self._last_adjust_ts = now


class ORSClient:
    def __init__(self, api_key: str, limiter: RateLimiter | None = None, profile: str = "foot-walking"):
        self.api_key = api_key
        self.profile = profile
        self.limiter = limiter or RateLimiter()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8",
                "Authorization": api_key,
                "User-Agent": "path-builder/0.1",
            }
        )

    def directions(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> tuple[int, Any, dict[str, Any]]:
        url = f"https://api.openrouteservice.org/v2/directions/{self.profile}/geojson"
        body = {"coordinates": [[start_lon, start_lat], [end_lon, end_lat]]}
        self.limiter.wait_for_slot()
        for attempt in range(1, MAX_HTTP_RETRIES + 1):
            try:
                response = self.session.post(url, json=body, timeout=(5, 30))
                payload = response.json() if response.headers.get("Content-Type", "").startswith("application/json") else response.text
                return response.status_code, payload, dict(response.headers)
            except requests.RequestException as exc:
                if attempt == MAX_HTTP_RETRIES:
                    return 599, {"error": str(exc)}, {}
                time.sleep(BASE_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, 0.2))
        return 599, {"error": "unreachable"}, {}

    def batch_directions(self, routes: list[tuple[tuple[float, float], tuple[float, float], float]]) -> list[Any]:
        results: list[Any] = []
        for (start_lat, start_lon), (end_lat, end_lon), _ in routes:
            self.limiter.maybe_recover()
            status, payload, headers = self.directions(start_lat, start_lon, end_lat, end_lon)
            while status == 429:
                self.limiter.on_429(float(headers.get("Retry-After", 60)))
                status, payload, headers = self.directions(start_lat, start_lon, end_lat, end_lon)
            results.append(payload if status == 200 else {"error": payload, "status_code": status})
        return results


def save_geojsons_and_extract_instructions(api_results: list[Any], output_root: str | Path) -> None:
    base = Path(output_root)
    base.mkdir(parents=True, exist_ok=True)
    for index, payload in enumerate(api_results):
        folder = base / str(index)
        folder.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                (folder / "error.txt").write_text(payload, encoding="utf-8")
                continue
        if not isinstance(payload, dict) or "features" not in payload:
            write_json(folder / "error.json", payload if isinstance(payload, dict) else {"payload": payload})
            continue
        save_geojson(folder / "route.geojson", payload)
        instruction_lines = format_ors_steps_as_instruction_lines(payload)
        natural_lines = format_ors_steps_as_natural_lines(payload)
        (folder / "instructions.txt").write_text("\n".join(instruction_lines), encoding="utf-8")
        (folder / "natural_instructions.txt").write_text("\n".join(natural_lines), encoding="utf-8")
        commands = parse_instruction_lines(natural_lines)
        write_parsed_instructions(folder / "instructions_parse.txt", commands)

