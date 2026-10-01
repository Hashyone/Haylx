from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quantum_economic_auditor.models.state import OptimizationResult


@dataclass
class ComparisonReport:
    results: list[OptimizationResult]

    def as_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([result.model_dump() for result in self.results])

    def save_csv(self, output_path: str | Path) -> Path:
        dataframe = self.as_dataframe()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        dataframe.to_csv(path, index=False)
        return path
