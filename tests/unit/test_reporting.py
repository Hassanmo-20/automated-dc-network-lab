"""Unit tests for JSON and Markdown report generation."""

import json
from pathlib import Path
from netauto.reporting.json_report import JsonReportGenerator
from netauto.reporting.markdown_report import MarkdownReportGenerator
from netauto.validation.connectivity import ConnectivityMatrixResult, PingResult
from netauto.validation.ecmp import EcmpPrefixResult, LeafEcmpHealth
from netauto.validation.engine import (
    ContainerHealthSummary,
    FailureDetail,
    ValidationReportData,
)
from netauto.protocols.ospf import RouterOspfHealth
from netauto.protocols.bgp import RouterBgpHealth
from netauto.validation.routing_table import RouterRoutingHealth


def create_dummy_report_data() -> ValidationReportData:
    return ValidationReportData(
        timestamp="2026-11-07T21:00:00Z",
        overall_status="PASS",
        container_health=ContainerHealthSummary(
            total_expected=10,
            running_count=10,
            running_nodes=["spine1", "spine2", "leaf1", "leaf2", "leaf3", "leaf4", "host1", "host2", "host3", "host4"],
            missing_nodes=[],
            status="PASS",
        ),
        ospf_health={
            "spine1": RouterOspfHealth("spine1", "10.255.0.1", [], 4, True, "PASS", "All 4 FULL"),
            "leaf1": RouterOspfHealth("leaf1", "10.255.1.1", [], 2, True, "PASS", "All 2 FULL"),
        },
        bgp_health={
            "spine1": RouterBgpHealth("spine1", 65000, [], 4, True, "PASS", "All 4 Established"),
            "leaf1": RouterBgpHealth("leaf1", 65101, [], 2, True, "PASS", "All 2 Established"),
        },
        routing_health={
            "leaf1": RouterRoutingHealth("leaf1", {}, ["172.16.12.0/24"], [], "PASS", "All routes installed")
        },
        ecmp_health={
            "leaf1": LeafEcmpHealth(
                "leaf1",
                {
                    "172.16.12.0/24": EcmpPrefixResult("172.16.12.0/24", ["10.0.0.0", "10.0.0.2"], 2, True, True, True, "Installed 2 paths")
                },
                True,
                "PASS",
                "All remote subnets multipath",
            )
        },
        connectivity=ConnectivityMatrixResult(
            results=[
                PingResult("host1", "host2", "172.16.12.10", 3, 3, 0.0, 0.45, True, "")
            ],
            total_tests=1,
            passed_tests=1,
            failed_tests=0,
            status="PASS",
            details="All tests passed",
        ),
        failures=[],
    )


def test_json_report_generation(tmp_path):
    """Verify JSON report generation and fields."""
    gen = JsonReportGenerator(reports_dir=tmp_path)
    data = create_dummy_report_data()
    file_path = gen.generate(data)

    assert file_path.is_file()
    loaded = json.loads(file_path.read_text(encoding="utf-8"))
    assert loaded["overall_status"] == "PASS"
    assert loaded["container_health"]["running_count"] == 10
    assert "spine1" in loaded["ospf_health"]


def test_markdown_report_generation(tmp_path):
    """Verify Markdown report generation contains required sections."""
    gen = MarkdownReportGenerator(reports_dir=tmp_path)
    data = create_dummy_report_data()
    file_path = gen.generate(data)

    assert file_path.is_file()
    md_content = file_path.read_text(encoding="utf-8")
    assert "# Data Center Network Health Report" in md_content
    assert "## Overall Status" in md_content
    assert "## Infrastructure" in md_content
    assert "## OSPF Details" in md_content
    assert "## BGP Details" in md_content
    assert "## ECMP Details" in md_content
    assert "## Connectivity Tests" in md_content
    assert "## Timestamp" in md_content
