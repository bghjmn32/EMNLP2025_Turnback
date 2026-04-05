from pathlib import Path

from path_builder.directions import RateLimiter, save_geojsons_and_extract_instructions


def test_rate_limiter_backoff_reduces_minute_budget(monkeypatch):
    monkeypatch.setattr("path_builder.directions.time.sleep", lambda *_args, **_kwargs: None)
    limiter = RateLimiter(per_minute=40, per_second=1)
    before = limiter.per_minute
    limiter.on_429(0)
    assert limiter.per_minute < before


def test_save_geojsons_and_extract_instructions_creates_reproduction_files(tmp_path: Path):
    payload = [
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "segments": [
                            {
                                "steps": [
                                    {
                                        "name": "Main Street",
                                        "instruction": "Turn right onto Main Street",
                                        "distance": 12.5,
                                        "duration": 9.0,
                                    }
                                ]
                            }
                        ]
                    },
                    "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [0.001, 0.0]]},
                }
            ],
        }
    ]
    save_geojsons_and_extract_instructions(payload, tmp_path)
    example_dir = tmp_path / "0"
    assert (example_dir / "route.geojson").exists()
    assert "Main Street" in (example_dir / "natural_instructions.txt").read_text(encoding="utf-8")
    assert (example_dir / "instructions_parse.txt").exists()
