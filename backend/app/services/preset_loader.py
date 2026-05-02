import json
import os
from pathlib import Path
from typing import List, Optional
from app.models.scenario import Scenario

PRESETS_DIR = Path(__file__).parent.parent.parent / "presets"

def list_presets() -> List[str]:
    if not PRESETS_DIR.exists():
        return []
    return [f.stem for f in PRESETS_DIR.glob("*.json")]

def load_preset(preset_id: str) -> Optional[Scenario]:
    file_path = PRESETS_DIR / f"{preset_id}.json"
    if not file_path.exists():
        return None
    with open(file_path, "r") as f:
        data = json.load(f)
    return Scenario(**data)
