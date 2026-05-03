#!/usr/bin/env python3
"""
Generate preset JSON files for small, medium, large scenarios.
Run from project root: python scripts/generate_presets.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.data_generator import generate_preset

PRESETS_DIR = Path(__file__).parent.parent / "backend" / "presets"
PRESETS_DIR.mkdir(exist_ok=True)

for name in ["small", "medium", "large"]:
    scenario = generate_preset(name)
    out_path = PRESETS_DIR / f"{name}.json"
    out_path.write_text(scenario.model_dump_json(indent=2))
    print(f"✓ Generated {name}.json — "
          f"{len(scenario.delivery_points)} pkgs, "
          f"{len(scenario.no_fly_zones)} zones, "
          f"{scenario.drone_fleet.count} drones")
