import os
import json
import sys

# Add the current directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.data_generator import generate_scenario

presets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")
os.makedirs(presets_dir, exist_ok=True)

configs = [
    {"id": "small", "n_packages": 8, "fleet_size": 3, "n_zones": 2, "seed": 42},
    {"id": "medium", "n_packages": 18, "fleet_size": 4, "n_zones": 4, "seed": 137},
    {"id": "large", "n_packages": 35, "fleet_size": 6, "n_zones": 6, "seed": 2024},
]

for conf in configs:
    scenario = generate_scenario(
        name=conf["id"],
        n_packages=conf["n_packages"],
        n_zones=conf["n_zones"],
        fleet_size=conf["fleet_size"],
        seed=conf["seed"]
    )
    # Overwrite the random ID with the preset ID for consistency
    scenario.id = conf["id"]
    
    file_path = os.path.join(presets_dir, f"{conf['id']}.json")
    with open(file_path, "w") as f:
        f.write(scenario.model_dump_json(indent=2))
        
print("Presets generated successfully.")
