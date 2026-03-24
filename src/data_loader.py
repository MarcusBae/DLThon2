# data_loader.py
"""Utilities to load and validate JSON data from the `data/` directory.
Placeholder implementation – provide functions `load_schema()`, `load_theory()`, etc.
"""

import json
import os

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

def _load_json(filename: str):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_schema():
    return _load_json("schema.json")

def load_theory():
    return _load_json("theory.json")

def load_assets():
    return _load_json("assets.json")

def load_episodes():
    return _load_json("episodes.json")

# TODO: Add validation logic for each JSON structure
