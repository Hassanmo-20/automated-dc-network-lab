"""Markdown report generator conforming to Data Center Health Report specifications."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Union
from netauto.validation.engine import ValidationReportData


class MarkdownReportGenerator:
    """Generates comprehensive human-readable Markdown validation reports."""

    def __init__(self, reports_dir: Union[str, Path] = "reports"):
        self.reports_dir = Path(reports_dir)
        self.history_dir = self.reports_dir / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, data: ValidationReportData) -> Path:
        """Render the Markdown health report.

        Args:
            data: Complete ValidationReportData model.

        Returns:
            Path to the written latest.md file.
        """
        lines = []

        # Header & Overall Status
        lines.append("# Data Center Network Health Report\n")
        lines.append("## Overall Status\n")
        badge = (
            "🟢 **PASS**"
            if data.overall_status == "PASS"
            else "🟡 **DEGRADED**"
            if data.overall_status == "DEGRADED"
            else "🔴 **FAIL**"
        )
        lines.append(f"Status: {badge}\n")

        # Infrastructure Summary Table
        lines.append("## Infrastructure\n")
        lines.append("| Component | Expected | Actual | Status |")
        lines.append("|---|---:|---:|---|")

        # Containers
        c_exp = data.container_health.total_expected
        c_act = data.container_health.running_count
        c_st = "PASS" if c_exp == c_act else "FAIL"
        lines.append(f"| Containers | {c_exp} | {c_act} | {c_st} |")

        # OSPF
        total_ospf_exp = sum(h.expected_neighbor_count for h in data.ospf_health.values())
        total_ospf_act = sum(len([n for n in h.neighbors if n.is_full]) for h in data.ospf_health.values())
        ospf_st = "PASS" if total_ospf_exp == total_ospf_act else "FAIL"
        lines.append(f"| OSPF neighbors | {total_ospf_exp} | {total_ospf_act} | {ospf_st} |")

        # BGP
        total_bgp_exp = sum(h.expected_peer_count for h in data.bgp_health.values())
        total_bgp_act = sum(len([p for p in h.peers if p.is_established]) for h in data.bgp_health.values())
        bgp_st = "PASS" if total_bgp_exp == total_bgp_act else "FAIL"
        lines.append(f"| BGP sessions | {total_bgp_exp} | {total_bgp_act} | {bgp_st} |")

        # ECMP
        total_ecmp_exp = sum(len(h.prefix_results) for h in data.ecmp_health.values())
        total_ecmp_act = sum(
            len([p for p in h.prefix_results.values() if p.is_ecmp_active]) for h in data.ecmp_health.values()
        )
        ecmp_st = "PASS" if total_ecmp_exp == total_ecmp_act and total_ecmp_exp > 0 else "DEGRADED" if total_ecmp_act > 0 else "FAIL"
        lines.append(f"| ECMP paths | {total_ecmp_exp} | {total_ecmp_act} | {ecmp_st} |")
        lines.append("")

        # OSPF Details
        lines.append("## OSPF Details\n")
        lines.append("| Router | Role | Router ID | Full / Expected | Status | Details |")
        lines.append("|---|---|---|---:|---|---|")
        for r_name, h in data.ospf_health.items():
            full_cnt = len([n for n in h.neighbors if n.is_full])
            role = "Spine" if "spine" in r_name else "Leaf"
            lines.append(f"| {r_name} | {role} | {h.router_id or '-'} | {full_cnt}/{h.expected_neighbor_count} | {h.status} | {h.details} |")
        lines.append("")

        # BGP Details
        lines.append("## BGP Details\n")
        lines.append("| Router | Role | ASN | Established / Expected | Status | Details |")
        lines.append("|---|---|---|---:|---|---|")
        for r_name, b in data.bgp_health.items():
            est_cnt = len([p for p in b.peers if p.is_established])
            role = "Spine" if "spine" in r_name else "Leaf"
            lines.append(f"| {r_name} | {role} | {b.local_as} | {est_cnt}/{b.expected_peer_count} | {b.status} | {b.details} |")
        lines.append("")

        # Routing Table Details
        lines.append("## Routing Table Details\n")
        lines.append("| Router | Expected Prefixes | Installed | Status | Details |")
        lines.append("|---|---|---:|---|---|")
        for r_name, r in data.routing_health.items():
            lines.append(f"| {r_name} | {len(r.expected_prefixes)} | {len(r.routes)} | {r.status} | {r.details} |")
        lines.append("")

        # ECMP Details
        lines.append("## ECMP Details\n")
        lines.append("| Leaf Router | Destination Prefix | Expected Paths | Installed Next Hops | Status |")
        lines.append("|---|---|---:|---|---|")
        for leaf_name, e in data.ecmp_health.items():
            for pfx, res in e.prefix_results.items():
                nh_str = ", ".join(res.installed_next_hops) if res.installed_next_hops else "None"
                st = "PASS" if res.is_ecmp_active else "FAIL"
                lines.append(f"| {leaf_name} | {pfx} | {res.expected_paths} | {nh_str} | {st} |")
        lines.append("")

        # Connectivity Tests
        lines.append("## Connectivity Tests\n")
        lines.append(f"Status: {data.connectivity.status} ({data.connectivity.passed_tests}/{data.connectivity.total_tests} passed)\n")
        lines.append("| Source | Destination | Target IP | Packets (Tx/Rx) | Loss % | Avg RTT | Status |")
        lines.append("|---|---|---|---:|---:|---:|---|")
        for ping in data.connectivity.results:
            rtt_str = f"{ping.avg_rtt_ms:.2f} ms" if ping.avg_rtt_ms is not None else "N/A"
            st = "PASS" if ping.success else "FAIL"
            lines.append(
                f"| {ping.source_host} | {ping.destination_host} | {ping.destination_ip} | "
                f"{ping.packets_transmitted}/{ping.packets_received} | {ping.packet_loss_pct:.1f}% | {rtt_str} | {st} |"
            )
        lines.append("")

        # Failures & Diagnostics
        lines.append("## Failures\n")
        if not data.failures:
            lines.append("No failures detected. Fabric is operating at 100% health.\n")
        else:
            for idx, fail in enumerate(data.failures, 1):
                lines.append(f"### Failure {idx}: {fail.device} ({fail.protocol})\n")
                lines.append(f"- **Expected State:** {fail.expected_state}")
                lines.append(f"- **Actual State:** {fail.actual_state}")
                lines.append(f"- **Possible Explanation:** {fail.explanation}")
                lines.append("- **Suggested Troubleshooting Commands:**")
                for cmd in fail.suggested_commands:
                    lines.append(f"  ```bash\n  {cmd}\n  ```")
                lines.append("")

        # Timestamp
        lines.append("## Timestamp\n")
        lines.append(f"Report generated at: `{data.timestamp}` (UTC)\n")

        content = "\n".join(lines)

        # 1. Write latest.md
        latest_file = self.reports_dir / "latest.md"
        with open(latest_file, "w", encoding="utf-8") as f:
            f.write(content)

        # 2. Write history archive
        ts_clean = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        history_file = self.history_dir / f"report-{ts_clean}.md"
        with open(history_file, "w", encoding="utf-8") as f:
            f.write(content)

        return latest_file
