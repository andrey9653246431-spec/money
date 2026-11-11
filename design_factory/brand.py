from __future__ import annotations

import json
from pathlib import Path


class Brand:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[1]
        tokens_path = self.root / "brand" / "tokens.json"
        self.tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
        self.width = int(self.tokens["width"])
        self.height = int(self.tokens["height"])
        self.font_path = self.root / self.tokens["font"]
        if not self.font_path.exists():
            raise FileNotFoundError(f"Фирменный шрифт не найден: {self.font_path}")

    def color(self, name: str) -> str:
        return self.tokens["colors"][name]

    @property
    def name(self) -> str:
        return self.tokens["brand_name"]
