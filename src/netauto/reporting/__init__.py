"""Reporting package for netauto."""

from netauto.reporting.json_report import JsonReportGenerator
from netauto.reporting.markdown_report import MarkdownReportGenerator

__all__ = ["JsonReportGenerator", "MarkdownReportGenerator"]
