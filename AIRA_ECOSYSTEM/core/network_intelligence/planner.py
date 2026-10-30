"""
core/network_intelligence/planner.py — Desired-State Configuration Planning.

Translates desired-state intent into version-aware RouterOS v6 and v7 candidate commands,
rollback definitions, and human-reviewable configuration diffs. Strictly read-only planning.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.canonical_network import get_canonical_registry, parse_routeros_major_version
from core.network_intelligence.models import (
    ConfigurationPlan,
    PlanStatus,
    ProposedCommand,
)
from core.network_intelligence.store import get_network_intelligence_store

logger = logging.getLogger("aira.network_intelligence.planner")


class ConfigurationPlanner:
    """Constructs version-aware configuration plans from structured desired state."""

    def __init__(self):
        self.store = get_network_intelligence_store()
        self.registry = get_canonical_registry()

    def normalize_desired_state(
        self,
        change_type: str,
        params: Dict[str, Any],
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validates mandatory parameters for supported change types.
        Returns (is_valid, missing_fields, normalized_params).
        Never invents missing IP addresses, VLAN IDs, gateways, or ASNs!
        """
        c_type = change_type.upper().strip()
        missing = []
        norm: Dict[str, Any] = dict(params)

        if c_type == "ADD_VLAN":
            if not params.get("vlan_id"):
                missing.append("vlan_id (e.g. 10, 20, 100)")
            if not params.get("interface") and not params.get("bridge"):
                missing.append("interface atau bridge pengikat (e.g. 'bridge', 'ether2')")

        elif c_type == "ADD_STATIC_ROUTE":
            if not params.get("dst_address"):
                missing.append("dst_address (e.g. '192.168.10.0/24' atau '0.0.0.0/0')")
            if not params.get("gateway"):
                missing.append("gateway (e.g. '192.168.1.1' atau 'ether1')")

        elif c_type == "CONFIGURE_NAT":
            if not params.get("action"):
                norm["action"] = "masquerade"
            if not params.get("out_interface") and not params.get("out_interface_list"):
                missing.append("out_interface atau out_interface_list (e.g. 'ether1' atau 'WAN')")

        elif c_type == "CONFIGURE_OSPF":
            if not params.get("network") and not params.get("interface"):
                missing.append("network (e.g. '10.0.0.0/24') atau interface OSPF")

        elif c_type == "CONFIGURE_BGP":
            if not params.get("remote_as"):
                missing.append("remote_as (e.g. 65001)")
            if not params.get("remote_ip"):
                missing.append("remote_ip (e.g. '192.168.100.1')")

        elif c_type == "ADD_FIREWALL_RULE":
            if not params.get("chain"):
                norm["chain"] = "forward"
            if not params.get("action"):
                missing.append("action (e.g. 'accept', 'drop')")

        is_valid = len(missing) == 0
        return is_valid, missing, norm

    def generate_plan(
        self,
        *,
        target_device: str,
        change_type: str,
        parameters: Dict[str, Any],
        incident_id: Optional[str] = None,
    ) -> ConfigurationPlan:
        """
        Generates a version-aware candidate configuration plan with dependencies and diff.
        Does NOT apply changes.
        """
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        op_id = f"op_{uuid.uuid4().hex[:8]}"

        # 1. Resolve target device and ROS version
        dev = self.registry.resolve_device(target_device)
        dev_id = dev.inventory_name if dev else target_device
        ros_major = (dev.ros_major_version or parse_routeros_major_version(dev.os_version) or 7) if dev else 7

        # 2. Validate completeness of desired state
        is_valid, missing_fields, norm_params = self.normalize_desired_state(change_type, parameters)

        desired_state_doc = {
            "target_device": dev_id,
            "change_type": change_type,
            "ros_major_version": ros_major,
            "parameters": norm_params,
        }

        if not is_valid:
            # Plan cannot proceed without mandatory values
            plan = ConfigurationPlan(
                plan_id=plan_id,
                operation_id=op_id,
                incident_id=incident_id,
                target_devices=[dev_id],
                desired_state=desired_state_doc,
                proposed_changes=[],
                configuration_diff="",
                dependencies=[],
                risk_level="UNKNOWN",
                blast_radius={},
                management_connectivity_risk=False,
                validation_results=[{
                    "severity": "ERROR",
                    "rule_id": "MISSING_MANDATORY_FIELDS",
                    "description": f"Parameter kritis belum diisi: {', '.join(missing_fields)}.",
                    "is_blocking": True,
                }],
                required_operator_inputs=missing_fields,
                limitations_disclosure="Input desired-state belum lengkap.",
                plan_status=PlanStatus.NEEDS_INPUT.value,
            )
            self.store.save_plan(plan)
            return plan

        # 3. Generate candidate commands based on ROS version
        c_type = change_type.upper().strip()
        commands: List[ProposedCommand] = []
        dependencies: List[Dict[str, Any]] = []

        if c_type == "ADD_VLAN":
            commands, dependencies = self._generate_vlan_commands(dev_id, norm_params, ros_major)
        elif c_type == "ADD_STATIC_ROUTE":
            commands, dependencies = self._generate_route_commands(dev_id, norm_params, ros_major)
        elif c_type == "CONFIGURE_NAT":
            commands, dependencies = self._generate_nat_commands(dev_id, norm_params, ros_major)
        elif c_type == "CONFIGURE_OSPF":
            commands, dependencies = self._generate_ospf_commands(dev_id, norm_params, ros_major)
        elif c_type == "CONFIGURE_BGP":
            commands, dependencies = self._generate_bgp_commands(dev_id, norm_params, ros_major)
        elif c_type == "ADD_FIREWALL_RULE":
            commands, dependencies = self._generate_firewall_commands(dev_id, norm_params, ros_major)
        else:
            # Generic fallback command
            cmd_str = norm_params.get("raw_command", "")
            if cmd_str:
                commands.append(ProposedCommand(
                    command_id=f"cmd_1",
                    target_device=dev_id,
                    command=cmd_str,
                    rollback_command=None,
                    intended_effect="Custom configuration command",
                    version_compatibility=f"v{ros_major}",
                ))

        # 4. Generate candidate diff
        diff_lines = [f"# Configuration Plan Diff for {dev_id} (RouterOS v{ros_major})"]
        diff_lines.append(f"# Change Type: {change_type}")
        diff_lines.append("# --- Current State (Baseline)")
        diff_lines.append("# +++ Proposed Changes")
        for cmd in commands:
            diff_lines.append(f"+ {cmd.command}")
            if cmd.rollback_command:
                diff_lines.append(f"  [Rollback]: - {cmd.rollback_command}")

        config_diff = "\n".join(diff_lines)

        plan = ConfigurationPlan(
            plan_id=plan_id,
            operation_id=op_id,
            incident_id=incident_id,
            target_devices=[dev_id],
            desired_state=desired_state_doc,
            proposed_changes=[c.to_dict() for c in commands],
            configuration_diff=config_diff,
            dependencies=dependencies,
            risk_level="LOW",
            blast_radius={"target_device": dev_id, "affected_objects_count": len(commands)},
            management_connectivity_risk=False,
            validation_results=[],
            expected_postconditions=[f"Penerapan perintah {change_type} berhasil terdaftar."],
            rollback_considerations=[c.rollback_command for c in commands if c.rollback_command],
            required_operator_inputs=[],
            approval_requirements=["Operator review and explicit confirmation required before application."],
            limitations_disclosure="Rencana ini dibuat secara statis. Tidak ada eksekusi konfigurasi ke router.",
            plan_status=PlanStatus.DRAFT.value,
        )

        self.store.save_plan(plan)
        return plan

    # -----------------------------------------------------------------------
    # Version-Aware Command Generators
    # -----------------------------------------------------------------------

    def _generate_vlan_commands(
        self, dev_id: str, params: Dict[str, Any], ros_major: int
    ) -> Tuple[List[ProposedCommand], List[Dict[str, Any]]]:
        vlan_id = str(params["vlan_id"])
        bridge = params.get("bridge", "bridge")
        vlan_name = params.get("name", f"vlan{vlan_id}")
        subnet = params.get("subnet")  # e.g. 192.168.10.1/24

        cmds = []
        deps = []

        # 1. Add VLAN interface
        cmd_if = f"/interface vlan add name={vlan_name} vlan-id={vlan_id} interface={bridge}"
        rb_if = f'/interface vlan remove [find name="{vlan_name}"]'
        cmds.append(ProposedCommand(
            command_id="cmd_vlan_if",
            target_device=dev_id,
            command=cmd_if,
            rollback_command=rb_if,
            intended_effect=f"Membuat SVI VLAN {vlan_id} pada bridge '{bridge}'.",
            dependencies=[],
            version_compatibility="v6,v7",
        ))

        # 2. Add bridge vlan entry
        cmd_bv = f"/interface bridge vlan add bridge={bridge} vlan-ids={vlan_id} tagged={bridge}"
        rb_bv = f'/interface bridge vlan remove [find vlan-ids="{vlan_id}"]'
        cmds.append(ProposedCommand(
            command_id="cmd_vlan_table",
            target_device=dev_id,
            command=cmd_bv,
            rollback_command=rb_bv,
            intended_effect=f"Mendaftarkan VLAN ID {vlan_id} pada tabel bridge VLAN.",
            dependencies=["cmd_vlan_if"],
            version_compatibility="v6,v7",
        ))
        deps.append({"parent": "cmd_vlan_if", "child": "cmd_vlan_table"})

        # 3. Optional IP address assignment
        if subnet:
            cmd_ip = f"/ip address add address={subnet} interface={vlan_name}"
            rb_ip = f'/ip address remove [find address="{subnet}"]'
            cmds.append(ProposedCommand(
                command_id="cmd_vlan_ip",
                target_device=dev_id,
                command=cmd_ip,
                rollback_command=rb_ip,
                intended_effect=f"Menetapkan alamat IP {subnet} pada interface {vlan_name}.",
                dependencies=["cmd_vlan_if"],
                version_compatibility="v6,v7",
            ))
            deps.append({"parent": "cmd_vlan_if", "child": "cmd_vlan_ip"})

        return cmds, deps

    def _generate_route_commands(
        self, dev_id: str, params: Dict[str, Any], ros_major: int
    ) -> Tuple[List[ProposedCommand], List[Dict[str, Any]]]:
        dst = params["dst_address"]
        gw = params["gateway"]
        dist = params.get("distance", 1)
        comment = params.get("comment", "AIRA-planned-route")

        if ros_major == 7:
            # RouterOS v7 syntax
            cmd = f"/ip route add dst-address={dst} gateway={gw} distance={dist} comment=\"{comment}\""
        else:
            # RouterOS v6 syntax
            cmd = f"/ip route add dst-address={dst} gateway={gw} distance={dist} comment=\"{comment}\""

        rb = f'/ip route remove [find dst-address="{dst}" and gateway="{gw}"]'

        p_cmd = ProposedCommand(
            command_id="cmd_route_add",
            target_device=dev_id,
            command=cmd,
            rollback_command=rb,
            intended_effect=f"Menambahkan rute ke {dst} via {gw}.",
            dependencies=[],
            version_compatibility=f"v{ros_major}",
        )
        return [p_cmd], []

    def _generate_nat_commands(
        self, dev_id: str, params: Dict[str, Any], ros_major: int
    ) -> Tuple[List[ProposedCommand], List[Dict[str, Any]]]:
        action = params.get("action", "masquerade")
        out_if = params.get("out_interface")
        out_list = params.get("out_interface_list")
        src_subnet = params.get("src_address")
        comment = params.get("comment", "AIRA-planned-NAT")

        cmd = f"/ip firewall nat add chain=srcnat action={action}"
        if out_list:
            cmd += f" out-interface-list={out_list}"
        elif out_if:
            cmd += f" out-interface={out_if}"
        if src_subnet:
            cmd += f" src-address={src_subnet}"
        cmd += f' comment="{comment}"'

        rb = f'/ip firewall nat remove [find comment="{comment}"]'

        p_cmd = ProposedCommand(
            command_id="cmd_nat_add",
            target_device=dev_id,
            command=cmd,
            rollback_command=rb,
            intended_effect="Menambahkan rule NAT masquerade / src-nat.",
            dependencies=[],
            version_compatibility="v6,v7",
        )
        return [p_cmd], []

    def _generate_ospf_commands(
        self, dev_id: str, params: Dict[str, Any], ros_major: int
    ) -> Tuple[List[ProposedCommand], List[Dict[str, Any]]]:
        net = params.get("network")
        iface = params.get("interface", "all")
        area = params.get("area", "backbone")

        if ros_major == 7:
            # RouterOS v7: uses interface templates
            cmd = f'/routing ospf interface-template add area={area} interfaces={iface}'
            if net:
                cmd += f' networks={net}'
            rb = f'/routing ospf interface-template remove [find area="{area}" and interfaces="{iface}"]'
        else:
            # RouterOS v6: uses networks and interfaces
            cmd = f'/routing ospf network add network={net or "0.0.0.0/0"} area={area}'
            rb = f'/routing ospf network remove [find network="{net or "0.0.0.0/0"}" and area="{area}"]'

        p_cmd = ProposedCommand(
            command_id="cmd_ospf_add",
            target_device=dev_id,
            command=cmd,
            rollback_command=rb,
            intended_effect=f"Mengaktifkan OSPF pada interface/network ({'v7 template' if ros_major == 7 else 'v6 network'}).",
            dependencies=[],
            version_compatibility=f"v{ros_major}",
        )
        return [p_cmd], []

    def _generate_bgp_commands(
        self, dev_id: str, params: Dict[str, Any], ros_major: int
    ) -> Tuple[List[ProposedCommand], List[Dict[str, Any]]]:
        r_as = params["remote_as"]
        r_ip = params["remote_ip"]
        p_name = params.get("name", f"bgp_peer_{r_as}")

        if ros_major == 7:
            # RouterOS v7: connection
            cmd = f'/routing bgp connection add name="{p_name}" remote.address={r_ip} remote.as={r_as} as={params.get("local_as", 65000)}'
            rb = f'/routing bgp connection remove [find name="{p_name}"]'
        else:
            # RouterOS v6: peer
            cmd = f'/routing bgp peer add name="{p_name}" remote-address={r_ip} remote-as={r_as}'
            rb = f'/routing bgp peer remove [find name="{p_name}"]'

        p_cmd = ProposedCommand(
            command_id="cmd_bgp_add",
            target_device=dev_id,
            command=cmd,
            rollback_command=rb,
            intended_effect=f"Menambahkan BGP peering ke AS{r_as} ({r_ip}).",
            dependencies=[],
            version_compatibility=f"v{ros_major}",
        )
        return [p_cmd], []

    def _generate_firewall_commands(
        self, dev_id: str, params: Dict[str, Any], ros_major: int
    ) -> Tuple[List[ProposedCommand], List[Dict[str, Any]]]:
        chain = params.get("chain", "forward")
        action = params.get("action", "accept")
        proto = params.get("protocol")
        port = params.get("dst_port")
        in_if = params.get("in_interface")
        comment = params.get("comment", "AIRA-planned-firewall")

        cmd = f"/ip firewall filter add chain={chain} action={action}"
        if proto:
            cmd += f" protocol={proto}"
        if port:
            cmd += f" dst-port={port}"
        if in_if:
            cmd += f" in-interface={in_if}"
        cmd += f' comment="{comment}"'

        rb = f'/ip firewall filter remove [find comment="{comment}"]'

        p_cmd = ProposedCommand(
            command_id="cmd_fw_add",
            target_device=dev_id,
            command=cmd,
            rollback_command=rb,
            intended_effect=f"Menambahkan filter rule {action} pada chain {chain}.",
            dependencies=[],
            version_compatibility="v6,v7",
        )
        return [p_cmd], []
