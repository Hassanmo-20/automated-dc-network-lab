"""JSON report generator for netauto validation results."""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Union
from netauto.validation.engine import ValidationReportData


class JsonReportGenerator:
    """Exports structured validation results into JSON."""

    def __init__(self, reports_dir: Union[str, Path] = "reports"):
        self.reports_dir = Path(reports_dir)
        self.history_dir = self.reports_dir / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, data: ValidationReportData) -> Path:
        """Write latest.json and a timestamped archive.

        Args:
            data: Complete ValidationReportData model.

        Returns:
            Path to the written latest.json file.
        """
        dict_data = asdict(data)

        # 1. Write latest.json
        latest_file = self.reports_dir / "latest.json"
        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(dict_data, f, indent=2)

        # 2. Write history archive
        ts_clean = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        history_file = self.history_dir / f"report-{ts_clean}.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(dict_data, f, indent=2)

        return latest_file
