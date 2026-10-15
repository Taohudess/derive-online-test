"""LOAD_KB: read and validate kb.json from disk."""
import json
import os

DEFAULT_KB_PATH = "kb.json"


def resolve_path(path=None):
    return path or os.environ.get("KB_PATH") or DEFAULT_KB_PATH


def load_kb(path=None):
    path = resolve_path(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path}: expected a non-empty JSON list of documents")
    for i, doc in enumerate(data):
        if not isinstance(doc, dict):
            raise ValueError(f"{path}: record {i} is not an object")
        for key in ("id", "title", "text"):
            if not isinstance(doc.get(key), str) or not doc[key].strip():
                raise ValueError(f"{path}: record {i} missing string field '{key}'")
    ids = [d["id"] for d in data]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: duplicate document ids")
    return data
