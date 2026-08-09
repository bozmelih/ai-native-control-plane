#!/usr/bin/env python3
"""Validate AI-Native Control Plane V3 contracts and structured artifacts.

This validator uses only the Python standard library. A PASS proves local
structure and invariant coverage; it does not prove strategic correctness,
human approval, or authorization to act.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
REFERENCES = SKILL_ROOT / "references"
ASSETS = SKILL_ROOT / "assets"
ROOT = SKILL_ROOT.parents[1]
VERSION = "3.0.0"


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, code: str, message: str) -> None:
        self.errors.append(f"{code}: {message}")

    def warn(self, code: str, message: str) -> None:
        self.warnings.append(f"{code}: {message}")


def load_json(path: Path, result: Validation) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        result.error("ERR_FILE_MISSING", str(path))
    except json.JSONDecodeError as exc:
        result.error("ERR_JSON_INVALID", f"{path}: {exc}")
    return None


def require_keys(data: Any, keys: list[str], label: str, result: Validation) -> None:
    if not isinstance(data, dict):
        result.error("ERR_OBJECT_REQUIRED", label)
        return
    for key in keys:
        if key not in data:
            result.error("ERR_REQUIRED_FIELD", f"{label}.{key}")


def require_nonempty_string(value: Any, label: str, result: Validation) -> None:
    if not isinstance(value, str) or not value.strip():
        result.error("ERR_STRING_REQUIRED", label)


def require_list(value: Any, label: str, result: Validation, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        result.error("ERR_ARRAY_REQUIRED", label)
        return []
    if nonempty and not value:
        result.error("ERR_ARRAY_EMPTY", label)
    return value


def require_unique(items: list[Any], label: str, result: Validation) -> None:
    serialized = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in items]
    if len(serialized) != len(set(serialized)):
        result.error("ERR_DUPLICATE_VALUE", label)


def enum_contains(value: Any, options: list[str], label: str, result: Validation) -> None:
    if value not in options:
        result.error("ERR_ENUM", f"{label}={value!r}")


def validate_contract(contract: Any, result: Validation) -> dict[str, Any] | None:
    required = [
        "schema_version", "system", "architecture_layers", "invariants", "task_classes",
        "decision_types", "risk_tiers", "compute_routes", "evidence_classes",
        "method_packs", "domain_packs", "output_modes", "authority_gates",
        "risk_requirements"
    ]
    require_keys(contract, required, "control-plane-contract", result)
    if not isinstance(contract, dict):
        return None
    if contract.get("schema_version") != VERSION:
        result.error("ERR_CONTRACT_VERSION", str(contract.get("schema_version")))
    if contract.get("system") != "ai-native-control-plane":
        result.error("ERR_SYSTEM_ID", str(contract.get("system")))
    expected_layers = ["durable_state", "control_plane", "temporary_cognition_graph", "optional_execution_interface"]
    if contract.get("architecture_layers") != expected_layers:
        result.error("ERR_ARCHITECTURE_LAYERS", "durable state, control plane, temporary cognition, and interface must remain separate")
    invariants = contract.get("invariants")
    if not isinstance(invariants, dict):
        result.error("ERR_OBJECT_REQUIRED", "control-plane-contract.invariants")
    else:
        required_invariants = {
            "persona_is_required": False,
            "persona_grants_authority": False,
            "task_graph_is_ephemeral_by_default": True,
            "confidence_is_evidence": False,
            "implicit_state_write_allowed": False,
            "implicit_external_action_allowed": False,
            "validator_pass_is_human_approval": False,
            "compute_route_grants_authority": False,
            "earned_autonomy_is_scoped_expiring_and_revocable": True
        }
        for key, expected in required_invariants.items():
            if invariants.get(key) is not expected:
                result.error("ERR_INVARIANT", f"{key} must be {expected}")
    for key in ["task_classes", "decision_types", "risk_tiers", "compute_routes", "evidence_classes", "method_packs", "domain_packs", "output_modes", "authority_gates"]:
        items = require_list(contract.get(key), f"control-plane-contract.{key}", result, nonempty=True)
        require_unique(items, f"control-plane-contract.{key}", result)
    if contract.get("risk_tiers") != ["low", "medium", "high", "critical"]:
        result.error("ERR_RISK_TIERS", "risk tiers must be low, medium, high, critical")
    if contract.get("compute_routes") != ["light", "standard", "high", "maximum"]:
        result.error("ERR_COMPUTE_ROUTES", "compute routes must be light, standard, high, maximum")
    requirements = contract.get("risk_requirements")
    if not isinstance(requirements, dict) or set(requirements) != {"low", "medium", "high", "critical"}:
        result.error("ERR_RISK_REQUIREMENTS", "every risk tier needs a requirement")
    return contract


def contract_or_error(result: Validation) -> dict[str, Any] | None:
    return validate_contract(load_json(REFERENCES / "control-plane-contract.json", result), result)


def validate_context_sources(items: Any, result: Validation, label: str) -> None:
    sources = require_list(items, label, result, nonempty=True)
    ids: list[str] = []
    for index, source in enumerate(sources):
        item_label = f"{label}[{index}]"
        require_keys(source, ["source_id", "kind", "freshness", "permitted_use", "summary"], item_label, result)
        if isinstance(source, dict):
            for key in ["source_id", "kind", "freshness", "permitted_use", "summary"]:
                require_nonempty_string(source.get(key), f"{item_label}.{key}", result)
            ids.append(str(source.get("source_id", "")))
    require_unique(ids, f"{label}.source_id", result)


def valid_optional_personas(result: Validation) -> set[str]:
    personas = load_json(REFERENCES / "optional-personas.json", result)
    if not isinstance(personas, dict):
        return set()
    presets = require_list(personas.get("presets"), "optional-personas.presets", result, nonempty=True)
    ids: list[str] = []
    for index, preset in enumerate(presets):
        item_label = f"optional-personas.presets[{index}]"
        require_keys(preset, ["id", "use_for", "default_method_packs"], item_label, result)
        if isinstance(preset, dict):
            require_nonempty_string(preset.get("id"), f"{item_label}.id", result)
            require_nonempty_string(preset.get("use_for"), f"{item_label}.use_for", result)
            require_list(preset.get("default_method_packs"), f"{item_label}.default_method_packs", result, nonempty=True)
            ids.append(str(preset.get("id", "")))
    require_unique(ids, "optional-personas.presets.id", result)
    return set(ids)


def validate_epistemic_register(items: Any, contract: dict[str, Any], result: Validation, label: str) -> None:
    claims = require_list(items, label, result, nonempty=True)
    ids: list[str] = []
    for index, claim in enumerate(claims):
        item_label = f"{label}[{index}]"
        require_keys(claim, ["claim_id", "class", "statement", "source_ids"], item_label, result)
        if not isinstance(claim, dict):
            continue
        require_nonempty_string(claim.get("claim_id"), f"{item_label}.claim_id", result)
        require_nonempty_string(claim.get("statement"), f"{item_label}.statement", result)
        enum_contains(claim.get("class"), contract["evidence_classes"], f"{item_label}.class", result)
        source_ids = require_list(claim.get("source_ids"), f"{item_label}.source_ids", result)
        if claim.get("class") not in {"unknown", "assumption", "hypothesis"} and not source_ids:
            result.error("ERR_EVIDENCE_SOURCE_REQUIRED", item_label)
        ids.append(str(claim.get("claim_id", "")))
    require_unique(ids, f"{label}.claim_id", result)


def validate_authority_plan(plan: Any, contract: dict[str, Any], risk: Any, result: Validation, label: str) -> None:
    require_keys(plan, ["current_gate", "human_decision_required", "state_write", "external_action", "system_write", "next_gate"], label, result)
    if not isinstance(plan, dict):
        return
    enum_contains(plan.get("current_gate"), contract["authority_gates"], f"{label}.current_gate", result)
    enum_contains(plan.get("next_gate"), contract["authority_gates"], f"{label}.next_gate", result)
    if plan.get("state_write") not in {"propose_only", "explicit_authorization_required", "authorized_bounded_scope"}:
        result.error("ERR_STATE_WRITE_MODE", str(plan.get("state_write")))
    for field in ["external_action", "system_write"]:
        if plan.get(field) not in {"none", "explicit_authorization_required", "authorized_bounded_scope"}:
            result.error("ERR_ACTION_MODE", f"{field}={plan.get(field)!r}")
    if any(plan.get(field) == "authorized_bounded_scope" for field in ["state_write", "external_action", "system_write"]):
        require_nonempty_string(plan.get("authorization_reference"), f"{label}.authorization_reference", result)
    if risk in {"medium", "high", "critical"} and plan.get("human_decision_required") is not True:
        result.error("ERR_HUMAN_DECISION_REQUIRED", f"risk={risk}")


def validate_task(data: Any, result: Validation, label: str = "task") -> None:
    contract = contract_or_error(result)
    if contract is None:
        return
    required = [
        "schema_version", "task_id", "objective", "task_class", "decision_type", "risk_tier",
        "compute_route", "context_sources", "method_packs", "domain_packs", "cognition_graph",
        "epistemic_register", "uncertainty_register", "authority_plan", "output_mode"
    ]
    require_keys(data, required, label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") != VERSION:
        result.error("ERR_TASK_VERSION", str(data.get("schema_version")))
    for key in ["task_id", "objective"]:
        require_nonempty_string(data.get(key), f"{label}.{key}", result)
    enum_contains(data.get("task_class"), contract["task_classes"], f"{label}.task_class", result)
    enum_contains(data.get("decision_type"), contract["decision_types"], f"{label}.decision_type", result)
    risk = data.get("risk_tier")
    enum_contains(risk, contract["risk_tiers"], f"{label}.risk_tier", result)
    compute = data.get("compute_route")
    enum_contains(compute, contract["compute_routes"], f"{label}.compute_route", result)
    enum_contains(data.get("output_mode"), contract["output_modes"], f"{label}.output_mode", result)
    validate_context_sources(data.get("context_sources"), result, f"{label}.context_sources")
    selected_methods = require_list(data.get("method_packs"), f"{label}.method_packs", result, nonempty=True)
    require_unique(selected_methods, f"{label}.method_packs", result)
    for method in selected_methods:
        enum_contains(method, contract["method_packs"], f"{label}.method_packs", result)
    for domain in require_list(data.get("domain_packs"), f"{label}.domain_packs", result, nonempty=True):
        enum_contains(domain, contract["domain_packs"], f"{label}.domain_packs", result)
    presets = data.get("optional_persona_presets", [])
    if not isinstance(presets, list):
        result.error("ERR_ARRAY_REQUIRED", f"{label}.optional_persona_presets")
    else:
        require_unique(presets, f"{label}.optional_persona_presets", result)
        allowed_presets = valid_optional_personas(result)
        for preset in presets:
            if preset not in allowed_presets:
                result.error("ERR_OPTIONAL_PERSONA", str(preset))
    graph = require_list(data.get("cognition_graph"), f"{label}.cognition_graph", result, nonempty=True)
    graph_ids: list[str] = []
    for index, node in enumerate(graph):
        node_label = f"{label}.cognition_graph[{index}]"
        require_keys(node, ["node_id", "purpose", "method_packs"], node_label, result)
        if not isinstance(node, dict):
            continue
        require_nonempty_string(node.get("node_id"), f"{node_label}.node_id", result)
        require_nonempty_string(node.get("purpose"), f"{node_label}.purpose", result)
        node_methods = require_list(node.get("method_packs"), f"{node_label}.method_packs", result, nonempty=True)
        for method in node_methods:
            if method not in selected_methods:
                result.error("ERR_GRAPH_METHOD_NOT_SELECTED", f"{node_label}.{method}")
        graph_ids.append(str(node.get("node_id", "")))
    require_unique(graph_ids, f"{label}.cognition_graph.node_id", result)
    validate_epistemic_register(data.get("epistemic_register"), contract, result, f"{label}.epistemic_register")
    require_list(data.get("uncertainty_register"), f"{label}.uncertainty_register", result)
    validate_authority_plan(data.get("authority_plan"), contract, risk, result, f"{label}.authority_plan")
    requirements = contract.get("risk_requirements", {}).get(risk, {})
    rank = {route: index for index, route in enumerate(contract["compute_routes"])}
    if requirements and rank.get(compute, -1) < rank.get(requirements.get("minimum_compute"), 99):
        result.error("ERR_RISK_COMPUTE_TOO_LOW", f"risk={risk} compute={compute}")
    if requirements.get("red_team_required") and "red-team" not in selected_methods:
        result.error("ERR_RISK_RED_TEAM_REQUIRED", f"risk={risk}")
    if risk in {"high", "critical"} and not data.get("uncertainty_register"):
        result.error("ERR_UNCERTAINTY_REGISTER_REQUIRED", f"risk={risk}")
    if risk == "critical" and data.get("decision_type") != "irreversible_or_regulated":
        result.error("ERR_CRITICAL_DECISION_TYPE", str(data.get("decision_type")))


def validate_grant(data: Any, result: Validation, label: str = "grant") -> None:
    contract = contract_or_error(result)
    if contract is None:
        return
    required = [
        "schema_version", "grant_id", "status", "scope", "risk_ceiling", "allowed_actions",
        "prohibited_actions", "approval", "expires_on", "success_metric", "revocation_trigger", "review_cadence"
    ]
    require_keys(data, required, label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") != VERSION:
        result.error("ERR_GRANT_VERSION", str(data.get("schema_version")))
    for key in ["grant_id", "scope", "expires_on", "success_metric", "revocation_trigger", "review_cadence"]:
        require_nonempty_string(data.get(key), f"{label}.{key}", result)
    if data.get("status") not in {"proposed", "active", "suspended", "revoked", "expired"}:
        result.error("ERR_GRANT_STATUS", str(data.get("status")))
    enum_contains(data.get("risk_ceiling"), contract["risk_tiers"], f"{label}.risk_ceiling", result)
    if data.get("risk_ceiling") == "critical":
        result.error("ERR_CRITICAL_AUTONOMY_FORBIDDEN", label)
    require_list(data.get("allowed_actions"), f"{label}.allowed_actions", result, nonempty=True)
    require_list(data.get("prohibited_actions"), f"{label}.prohibited_actions", result, nonempty=True)
    try:
        date.fromisoformat(str(data.get("expires_on")))
    except ValueError:
        result.error("ERR_GRANT_EXPIRY_DATE", str(data.get("expires_on")))
    approval = data.get("approval")
    if data.get("status") == "active":
        require_keys(approval, ["approved_by", "approved_at", "evidence_reference"], f"{label}.approval", result)
        if isinstance(approval, dict):
            for key in ["approved_by", "approved_at", "evidence_reference"]:
                require_nonempty_string(approval.get(key), f"{label}.approval.{key}", result)


def validate_state(data: Any, result: Validation, label: str = "state") -> None:
    contract = contract_or_error(result)
    if contract is None:
        return
    required = [
        "schema_version", "project_id", "state_version", "accepted_decisions", "evidence_register",
        "open_questions", "risk_register", "authority_grants", "learning_events", "latest_task_ids",
        "state_write_authorization"
    ]
    require_keys(data, required, label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") != VERSION:
        result.error("ERR_STATE_VERSION", str(data.get("schema_version")))
    for key in ["project_id", "state_version"]:
        require_nonempty_string(data.get(key), f"{label}.{key}", result)
    for key in ["accepted_decisions", "evidence_register", "open_questions", "risk_register", "authority_grants", "learning_events", "latest_task_ids"]:
        require_list(data.get(key), f"{label}.{key}", result)
    if data.get("state_write_authorization") not in {"not_authorized", "explicitly_authorized"}:
        result.error("ERR_STATE_WRITE_AUTHORIZATION", str(data.get("state_write_authorization")))
    decision_ids: list[str] = []
    for index, decision in enumerate(data.get("accepted_decisions", [])):
        item_label = f"{label}.accepted_decisions[{index}]"
        require_keys(decision, ["decision_id", "decision", "accepted_by", "accepted_at", "evidence_reference"], item_label, result)
        if isinstance(decision, dict):
            for key in ["decision_id", "decision", "accepted_by", "accepted_at", "evidence_reference"]:
                require_nonempty_string(decision.get(key), f"{item_label}.{key}", result)
            decision_ids.append(str(decision.get("decision_id", "")))
    require_unique(decision_ids, f"{label}.accepted_decisions.decision_id", result)
    evidence_ids: list[str] = []
    for index, evidence in enumerate(data.get("evidence_register", [])):
        item_label = f"{label}.evidence_register[{index}]"
        require_keys(evidence, ["source_id", "class", "summary"], item_label, result)
        if isinstance(evidence, dict):
            require_nonempty_string(evidence.get("source_id"), f"{item_label}.source_id", result)
            enum_contains(evidence.get("class"), contract["evidence_classes"], f"{item_label}.class", result)
            require_nonempty_string(evidence.get("summary"), f"{item_label}.summary", result)
            evidence_ids.append(str(evidence.get("source_id", "")))
    require_unique(evidence_ids, f"{label}.evidence_register.source_id", result)
    for index, grant in enumerate(data.get("authority_grants", [])):
        validate_grant(grant, result, f"{label}.authority_grants[{index}]")


def validate_package(result: Validation) -> None:
    required_paths = [
        ROOT / "README.md",
        ROOT / ".gitignore",
        ROOT / "pyproject.toml",
        ROOT / ".github/workflows/validate.yml",
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "agents/openai.yaml",
        REFERENCES / "control-plane-contract.json",
        REFERENCES / "optional-personas.json",
        REFERENCES / "packs-and-routing.md",
        REFERENCES / "risk-and-authority.md",
        ASSETS / "task-packet.template.json",
        ASSETS / "project-state.template.json",
        ASSETS / "authority-grant.template.json",
        ASSETS / "decision-packet.template.md",
        SKILL_ROOT / "scripts/validate_artifacts.py"
    ]
    for path in required_paths:
        if not path.is_file():
            result.error("ERR_FILE_MISSING", str(path))
    skill = (SKILL_ROOT / "SKILL.md")
    if skill.is_file():
        content = skill.read_text(encoding="utf-8")
        if "[TODO" in content or not re.match(r"^---\nname: ai-native-control-plane\ndescription: .+\n---", content, re.DOTALL):
            result.error("ERR_SKILL_FRONTMATTER", "SKILL.md")
    interface = SKILL_ROOT / "agents/openai.yaml"
    if interface.is_file():
        interface_text = interface.read_text(encoding="utf-8")
        expected_interface_keys = ["interface:", "display_name:", "short_description:", "default_prompt:"]
        if not all(key in interface_text for key in expected_interface_keys):
            result.error("ERR_INTERFACE_METADATA", "agents/openai.yaml")
    contract = contract_or_error(result)
    personas = load_json(REFERENCES / "optional-personas.json", result)
    if isinstance(personas, dict):
        require_keys(personas, ["schema_version", "rule", "presets"], "optional-personas", result)
        if "cannot create authority" not in str(personas.get("rule", "")):
            result.error("ERR_PERSONA_BOUNDARY", "optional-personas.rule")
    elif personas is not None:
        result.error("ERR_OBJECT_REQUIRED", "optional-personas")
    if contract is not None:
        task = load_json(ASSETS / "task-packet.template.json", result)
        state = load_json(ASSETS / "project-state.template.json", result)
        grant = load_json(ASSETS / "authority-grant.template.json", result)
        if task is not None:
            validate_task(task, result, "task-packet.template")
        if state is not None:
            validate_state(state, result, "project-state.template")
        if grant is not None:
            validate_grant(grant, result, "authority-grant.template")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Validate package contracts and templates")
    parser.add_argument("--task", type=Path, help="Validate one task packet")
    parser.add_argument("--state", type=Path, help="Validate one persistent state record")
    parser.add_argument("--grant", type=Path, help="Validate one earned-autonomy grant")
    args = parser.parse_args()
    result = Validation()
    if args.all or not any((args.task, args.state, args.grant)):
        validate_package(result)
    if args.task:
        data = load_json(args.task, result)
        if data is not None:
            validate_task(data, result, str(args.task))
    if args.state:
        data = load_json(args.state, result)
        if data is not None:
            validate_state(data, result, str(args.state))
    if args.grant:
        data = load_json(args.grant, result)
        if data is not None:
            validate_grant(data, result, str(args.grant))
    for warning in result.warnings:
        print(f"WARNING {warning}")
    for error in result.errors:
        print(f"ERROR {error}")
    if result.errors:
        print(f"FAIL errors={len(result.errors)} warnings={len(result.warnings)}")
        return 1
    print(f"PASS errors=0 warnings={len(result.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
