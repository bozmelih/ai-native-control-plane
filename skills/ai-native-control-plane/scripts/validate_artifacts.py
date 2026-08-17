#!/usr/bin/env python3
"""Validate AI-Native Control Plane V4 contracts and lifecycle artifacts.

A PASS proves deterministic structural conformance only. It does not prove
strategic correctness or authorize execution, memory writes, publication,
installation, or activation.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from compose_task import CompositionError, compose
from control_plane import LifecycleError, distill_outcome


SKILL_ROOT = Path(__file__).resolve().parents[1]
REFERENCES = SKILL_ROOT / "references"
ASSETS = SKILL_ROOT / "assets"
ROOT = SKILL_ROOT.parents[1]
VERSION = "4.0.0"
LEGACY_VERSIONS = {"3.0.0", "3.1.0"}
LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


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


def require_string(value: Any, label: str, result: Validation) -> None:
    if not isinstance(value, str) or not value.strip():
        result.error("ERR_STRING_REQUIRED", label)


def require_list(value: Any, label: str, result: Validation, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        result.error("ERR_ARRAY_REQUIRED", label)
        return []
    if nonempty and not value:
        result.error("ERR_ARRAY_EMPTY", label)
    return value


def enum_contains(value: Any, options: set[str] | list[str], label: str, result: Validation) -> None:
    if value not in options:
        result.error("ERR_ENUM", f"{label}={value!r}")


def require_unique(values: list[Any], label: str, result: Validation) -> None:
    rendered = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values]
    if len(rendered) != len(set(rendered)):
        result.error("ERR_DUPLICATE_VALUE", label)


def get_bundle(result: Validation) -> dict[str, Any] | None:
    names = {
        "contract": "control-plane-contract.json",
        "registry": "cognitive-primitive-registry.json",
        "lenses": "domain-lens-registry.json",
        "recipes": "seed-recipes.json",
        "personas": "optional-personas.json",
    }
    bundle = {key: load_json(REFERENCES / filename, result) for key, filename in names.items()}
    return bundle if all(isinstance(item, dict) for item in bundle.values()) else None


def validate_registry(data: Any, result: Validation) -> dict[str, dict[str, Any]]:
    require_keys(data, ["schema_version", "purpose", "selection_rule", "primitives"], "primitive-registry", result)
    if not isinstance(data, dict):
        return {}
    if data.get("schema_version") != VERSION:
        result.error("ERR_REGISTRY_VERSION", str(data.get("schema_version")))
    primitives = require_list(data.get("primitives"), "primitive-registry.primitives", result, nonempty=True)
    if not 15 <= len(primitives) <= 20:
        result.error("ERR_REGISTRY_SIZE", f"expected 15-20 primitives, got {len(primitives)}")
    required = [
        "id", "category", "purpose", "use_when", "avoid_when", "required_inputs",
        "evidence_needs", "reasoning_operation", "expected_outputs",
        "relative_compute_cost", "complements", "common_failure_modes",
    ]
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(primitives):
        label = f"primitive-registry.primitives[{index}]"
        require_keys(item, required, label, result)
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        require_string(item_id, f"{label}.id", result)
        enum_contains(item.get("category"), {"thinking_method", "quality_check", "synthesis"}, f"{label}.category", result)
        for key in ["purpose", "reasoning_operation"]:
            require_string(item.get(key), f"{label}.{key}", result)
        for key in ["use_when", "avoid_when", "required_inputs", "evidence_needs", "expected_outputs", "complements", "common_failure_modes"]:
            require_list(item.get(key), f"{label}.{key}", result, nonempty=key != "complements")
        enum_contains(item.get("relative_compute_cost"), {"light", "standard", "high"}, f"{label}.relative_compute_cost", result)
        if isinstance(item_id, str):
            if item_id in by_id:
                result.error("ERR_DUPLICATE_VALUE", f"primitive id {item_id}")
            by_id[item_id] = item
    for item_id, item in by_id.items():
        for complement in item.get("complements", []):
            if complement not in by_id:
                result.error("ERR_UNKNOWN_COMPLEMENT", f"{item_id}->{complement}")
    return by_id


def validate_lenses(data: Any, result: Validation) -> dict[str, dict[str, Any]]:
    require_keys(data, ["schema_version", "rule", "lenses"], "domain-lens-registry", result)
    if not isinstance(data, dict):
        return {}
    if data.get("schema_version") != VERSION:
        result.error("ERR_LENS_VERSION", str(data.get("schema_version")))
    if "not a department" not in str(data.get("rule", "")):
        result.error("ERR_LENS_DEPARTMENT_BOUNDARY", "domain-lens-registry.rule")
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(require_list(data.get("lenses"), "domain-lens-registry.lenses", result, nonempty=True)):
        label = f"domain-lens-registry.lenses[{index}]"
        require_keys(item, ["id", "scope_type", "purpose", "constraints", "evidence_standards"], label, result)
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        require_string(item_id, f"{label}.id", result)
        enum_contains(item.get("scope_type"), {"core_domain", "subdomain_lens", "cross_domain_lens"}, f"{label}.scope_type", result)
        require_list(item.get("constraints"), f"{label}.constraints", result, nonempty=True)
        require_list(item.get("evidence_standards"), f"{label}.evidence_standards", result, nonempty=True)
        if isinstance(item_id, str):
            if item_id in by_id:
                result.error("ERR_DUPLICATE_VALUE", f"lens id {item_id}")
            by_id[item_id] = item
    return by_id


def validate_contract(contract: Any, primitives: dict[str, dict[str, Any]], lenses: dict[str, dict[str, Any]], result: Validation) -> dict[str, Any] | None:
    required = [
        "schema_version", "system", "paradigm", "architecture_layers", "runtime_flow", "invariants",
        "lifecycle_statuses", "context_gate_statuses", "context_source_statuses",
        "context_requirement_priorities", "memory_classes", "durable_memory_classes",
        "memory_operations", "worker_selection_basis", "task_classes", "decision_types",
        "risk_tiers", "compute_routes", "evidence_classes", "cognitive_taxonomy",
        "thinking_methods", "quality_checks", "synthesis_steps", "domain_lenses",
        "compatibility_aliases", "output_modes", "output_mode_defaults", "authority_gates",
        "risk_requirements", "anti_bureaucracy", "observability_fields",
    ]
    require_keys(contract, required, "control-plane-contract", result)
    if not isinstance(contract, dict):
        return None
    if contract.get("schema_version") != VERSION:
        result.error("ERR_CONTRACT_VERSION", str(contract.get("schema_version")))
    if contract.get("system") != "ai-native-control-plane":
        result.error("ERR_SYSTEM_ID", str(contract.get("system")))
    if contract.get("paradigm") != "persistent_state_ephemeral_cognition":
        result.error("ERR_PARADIGM", str(contract.get("paradigm")))
    expected_layers = [
        "versioned_durable_memory", "context_lifecycle", "control_plane",
        "temporary_cognition_graph", "capability_based_worker_interface",
        "verification_and_distillation", "authorized_memory_adapter",
    ]
    if contract.get("architecture_layers") != expected_layers:
        result.error("ERR_ARCHITECTURE_LAYERS", "V4 layers must remain ordered and separate")
    flow = contract.get("runtime_flow", [])
    for stage in ["context_readiness_gate", "cognitive_composition", "capability_based_worker_planning", "verification", "distillation", "authorized_adapter_write"]:
        if stage not in flow:
            result.error("ERR_RUNTIME_FLOW", f"missing {stage}")
    expected_invariants = {
        "human_authority_is_explicit": True,
        "persona_is_required": False,
        "persona_grants_authority": False,
        "task_graph_is_ephemeral_by_default": True,
        "confidence_is_evidence": False,
        "implicit_state_write_allowed": False,
        "implicit_external_action_allowed": False,
        "validator_pass_is_human_approval": False,
        "acceptance_is_execution_authorization": False,
        "compute_route_grants_authority": False,
        "observations_auto_modify_routing_policy": False,
        "missing_required_context_allows_assumption": False,
        "blocked_context_allows_worker_selection": False,
        "distillation_grants_write_authority": False,
        "working_memory_auto_promotes": False,
        "worker_identity_grants_authority": False,
        "memory_adapter_invokes_git": False,
    }
    invariants = contract.get("invariants")
    if not isinstance(invariants, dict):
        result.error("ERR_OBJECT_REQUIRED", "control-plane-contract.invariants")
    else:
        for key, expected in expected_invariants.items():
            if invariants.get(key) is not expected:
                result.error("ERR_INVARIANT", f"{key} must be {expected}")
    if "confidence" in contract.get("evidence_classes", []):
        result.error("ERR_CONFIDENCE_AS_EVIDENCE", "confidence cannot be evidence")
    if contract.get("memory_classes") != ["context", "decision_log", "backlog", "working_memory"]:
        result.error("ERR_MEMORY_CLASSES", "memory classes changed")
    if contract.get("durable_memory_classes") != ["context", "decision_log", "backlog"]:
        result.error("ERR_DURABLE_MEMORY_CLASSES", "working memory cannot be durable")
    if contract.get("worker_selection_basis") != "capability_contract":
        result.error("ERR_WORKER_SELECTION_BASIS", "worker selection must be capability-based")
    taxonomy = contract.get("cognitive_taxonomy", {})
    if set(taxonomy) != {"thinking_method", "domain_lens", "quality_check", "synthesis"}:
        result.error("ERR_COGNITIVE_TAXONOMY", "typed cognition categories changed")
    methods = {item_id for item_id, item in primitives.items() if item.get("category") == "thinking_method"}
    checks = {item_id for item_id, item in primitives.items() if item.get("category") == "quality_check"}
    synthesis = {item_id for item_id, item in primitives.items() if item.get("category") == "synthesis"}
    if set(contract.get("thinking_methods", [])) != methods:
        result.error("ERR_METHOD_REGISTRY_MISMATCH", "contract and registry differ")
    if set(contract.get("quality_checks", [])) != checks:
        result.error("ERR_CHECK_REGISTRY_MISMATCH", "contract and registry differ")
    if set(contract.get("synthesis_steps", [])) != synthesis:
        result.error("ERR_SYNTHESIS_REGISTRY_MISMATCH", "contract and registry differ")
    if set(contract.get("domain_lenses", [])) != set(lenses):
        result.error("ERR_LENS_REGISTRY_MISMATCH", "contract and lens registry differ")
    requirements = contract.get("risk_requirements")
    if not isinstance(requirements, dict) or set(requirements) != set(LEVELS):
        result.error("ERR_RISK_REQUIREMENTS", "all risk tiers require policy")
    else:
        for risk, requirement in requirements.items():
            require_keys(requirement, ["minimum_compute", "human_decision_required", "required_quality_checks"], f"risk_requirements.{risk}", result)
            for check in require_list(requirement.get("required_quality_checks"), f"risk_requirements.{risk}.required_quality_checks", result):
                enum_contains(check, checks, f"risk_requirements.{risk}.required_quality_checks", result)
    return contract


def validate_supporting_references(bundle: dict[str, Any], contract: dict[str, Any], result: Validation) -> None:
    recipes = bundle["recipes"]
    require_keys(recipes, ["schema_version", "rule", "recipes"], "seed-recipes", result)
    if recipes.get("schema_version") != VERSION:
        result.error("ERR_RECIPE_VERSION", str(recipes.get("schema_version")))
    for index, recipe in enumerate(require_list(recipes.get("recipes"), "seed-recipes.recipes", result, nonempty=True)):
        label = f"seed-recipes.recipes[{index}]"
        require_keys(recipe, ["id", "use_as_prior_when", "thinking_methods", "domain_lenses", "quality_checks"], label, result)
        if isinstance(recipe, dict):
            for item in require_list(recipe.get("thinking_methods"), f"{label}.thinking_methods", result):
                enum_contains(item, contract["thinking_methods"], f"{label}.thinking_methods", result)
            for item in require_list(recipe.get("domain_lenses"), f"{label}.domain_lenses", result):
                enum_contains(item, contract["domain_lenses"], f"{label}.domain_lenses", result)
            for item in require_list(recipe.get("quality_checks"), f"{label}.quality_checks", result):
                enum_contains(item, contract["quality_checks"], f"{label}.quality_checks", result)
    personas = bundle["personas"]
    require_keys(personas, ["schema_version", "rule", "presets"], "optional-personas", result)
    if personas.get("schema_version") != VERSION:
        result.error("ERR_PERSONA_VERSION", str(personas.get("schema_version")))
    if "optional" not in str(personas.get("rule", "")) or "cannot create authority" not in str(personas.get("rule", "")):
        result.error("ERR_PERSONA_BOUNDARY", "optional-personas.rule")
    for index, preset in enumerate(require_list(personas.get("presets"), "optional-personas.presets", result, nonempty=True)):
        label = f"optional-personas.presets[{index}]"
        require_keys(preset, ["id", "suggested_thinking_methods", "suggested_domain_lenses", "suggested_quality_checks", "authority_effect"], label, result)
        if isinstance(preset, dict) and preset.get("authority_effect") != "none":
            result.error("ERR_PERSONA_AUTHORITY", str(preset.get("id")))


def validate_context_sources(items: Any, contract: dict[str, Any], result: Validation, label: str, legacy: bool = False) -> None:
    sources = require_list(items, label, result, nonempty=legacy)
    ids: list[str] = []
    required = ["source_id", "kind", "freshness", "permitted_use", "summary"]
    if not legacy:
        required += ["relevance_to_decision", "decision_change_potential", "status"]
    for index, source in enumerate(sources):
        item_label = f"{label}[{index}]"
        require_keys(source, required, item_label, result)
        if not isinstance(source, dict):
            continue
        for key in ["source_id", "kind", "freshness", "permitted_use", "summary"]:
            require_string(source.get(key), f"{item_label}.{key}", result)
        if not legacy:
            require_string(source.get("relevance_to_decision"), f"{item_label}.relevance_to_decision", result)
            enum_contains(source.get("status"), contract["context_source_statuses"], f"{item_label}.status", result)
        if isinstance(source.get("source_id"), str):
            ids.append(source["source_id"])
    require_unique(ids, f"{label}.source_id", result)


def validate_epistemic(items: Any, contract: dict[str, Any], result: Validation, label: str) -> None:
    for index, claim in enumerate(require_list(items, label, result)):
        item_label = f"{label}[{index}]"
        require_keys(claim, ["claim_id", "class", "statement", "source_ids"], item_label, result)
        if not isinstance(claim, dict):
            continue
        if claim.get("class") == "confidence":
            result.error("ERR_CONFIDENCE_AS_EVIDENCE", item_label)
        enum_contains(claim.get("class"), contract["evidence_classes"], f"{item_label}.class", result)
        require_list(claim.get("source_ids"), f"{item_label}.source_ids", result)


def validate_authority(data: Any, contract: dict[str, Any], risk: Any, result: Validation, label: str) -> None:
    require_keys(data, ["current_gate", "human_decision_required", "state_write", "external_action", "system_write", "next_gate"], label, result)
    if not isinstance(data, dict):
        return
    enum_contains(data.get("current_gate"), contract["authority_gates"], f"{label}.current_gate", result)
    enum_contains(data.get("next_gate"), contract["authority_gates"], f"{label}.next_gate", result)
    if data.get("state_write") != "propose_only" and not data.get("state_write_authorization_ref"):
        result.error("ERR_IMPLICIT_STATE_WRITE", label)
    if data.get("external_action") != "none" and not data.get("external_action_authorization_ref"):
        result.error("ERR_IMPLICIT_EXTERNAL_ACTION", label)
    if risk in {"high", "critical"} and data.get("human_decision_required") is not True:
        result.error("ERR_HIGH_RISK_HUMAN_GATE", label)
    if risk in {"high", "critical"} and data.get("next_gate") not in {"human_decision", "context_resolution"}:
        result.error("ERR_HIGH_RISK_HUMAN_GATE", label)


def _selected_ids(selection: Any, key: str, allowed: set[str], result: Validation, label: str) -> list[str]:
    if not isinstance(selection, dict):
        return []
    values = require_list(selection.get(key), f"{label}.{key}", result)
    ids: list[str] = []
    for index, item in enumerate(values):
        item_label = f"{label}.{key}[{index}]"
        require_keys(item, ["id", "why_selected", "uncertainty_reduced", "selected_by"], item_label, result)
        if isinstance(item, dict):
            enum_contains(item.get("id"), allowed, f"{item_label}.id", result)
            if isinstance(item.get("id"), str):
                ids.append(item["id"])
    require_unique(ids, f"{label}.{key}.id", result)
    return ids


def validate_composition(data: dict[str, Any], contract: dict[str, Any], result: Validation, label: str, blocked: bool) -> None:
    selection = data.get("selected_composition")
    require_keys(selection, ["thinking_methods", "domain_lenses", "quality_checks", "synthesis_steps", "primitive_count", "primitive_budget", "complex_graph_required"], f"{label}.selected_composition", result)
    methods = _selected_ids(selection, "thinking_methods", set(contract["thinking_methods"]), result, f"{label}.selected_composition")
    lenses = _selected_ids(selection, "domain_lenses", set(contract["domain_lenses"]), result, f"{label}.selected_composition")
    checks = _selected_ids(selection, "quality_checks", set(contract["quality_checks"]), result, f"{label}.selected_composition")
    synthesis = _selected_ids(selection, "synthesis_steps", set(contract["synthesis_steps"]), result, f"{label}.selected_composition")
    if not isinstance(selection, dict):
        return
    count = len(methods) + len(checks) + len(synthesis)
    if selection.get("primitive_count") != count:
        result.error("ERR_PRIMITIVE_COUNT", label)
    budget = selection.get("primitive_budget")
    if not isinstance(budget, int) or count > budget:
        result.error("ERR_PRIMITIVE_BUDGET", label)
    if blocked and (count or lenses or data.get("cognition_graph") or data.get("compute_route") is not None):
        result.error("ERR_BLOCKED_CONTEXT_SELECTED_WORKER", label)
    if data.get("task_class") in {"retrieval", "transform"} and selection.get("complex_graph_required") is False and count > contract["anti_bureaucracy"]["simple_task_max_cognitive_primitives"]:
        result.error("ERR_SIMPLE_TASK_OVERCOMPOSED", label)
    risk = data.get("risk_tier")
    required_checks = set(contract["risk_requirements"].get(risk, {}).get("required_quality_checks", []))
    if not blocked and not required_checks <= set(checks):
        result.error("ERR_RISK_REQUIRED_CHECK", f"{label}: {sorted(required_checks - set(checks))}")
    compute = data.get("compute_route")
    if not blocked:
        enum_contains(compute, contract["compute_routes"], f"{label}.compute_route", result)
        minimum = contract["risk_requirements"].get(risk, {}).get("minimum_compute")
        if minimum in contract["compute_routes"] and compute in contract["compute_routes"] and contract["compute_routes"].index(compute) < contract["compute_routes"].index(minimum):
            result.error("ERR_RISK_COMPUTE_TOO_LOW", f"risk={risk} compute={compute}")


def validate_v4_task(data: dict[str, Any], bundle: dict[str, Any], result: Validation, label: str) -> None:
    contract = bundle["contract"]
    required = [
        "schema_version", "task_id", "objective", "task_class", "decision_type", "risk_tier",
        "lifecycle_status", "context_plan", "context_sources", "compiled_context", "context_gate",
        "clarification_questions", "selected_composition", "cognition_graph", "compute_route",
        "epistemic_register", "uncertainty_register", "authority_plan", "worker_plan",
        "memory_update_status", "composition_observability", "output_mode",
    ]
    require_keys(data, required, label, result)
    if data.get("schema_version") != VERSION:
        result.error("ERR_TASK_VERSION", str(data.get("schema_version")))
    enum_contains(data.get("task_class"), contract["task_classes"], f"{label}.task_class", result)
    enum_contains(data.get("decision_type"), contract["decision_types"], f"{label}.decision_type", result)
    enum_contains(data.get("risk_tier"), contract["risk_tiers"], f"{label}.risk_tier", result)
    enum_contains(data.get("lifecycle_status"), contract["lifecycle_statuses"], f"{label}.lifecycle_status", result)
    validate_context_sources(data.get("context_sources"), contract, result, f"{label}.context_sources")
    plan = data.get("context_plan")
    require_keys(plan, ["requirements", "budget"], f"{label}.context_plan", result)
    if isinstance(plan, dict):
        requirements = require_list(plan.get("requirements"), f"{label}.context_plan.requirements", result)
        for index, requirement in enumerate(requirements):
            item_label = f"{label}.context_plan.requirements[{index}]"
            require_keys(requirement, ["requirement_id", "description", "priority", "why_needed", "preferred_source_ids", "accepted_statuses", "freshness_requirement", "blocking_if_unsatisfied", "question", "answer_needed", "owner"], item_label, result)
            if isinstance(requirement, dict):
                enum_contains(requirement.get("priority"), contract["context_requirement_priorities"], f"{item_label}.priority", result)
                if requirement.get("priority") == "required" and requirement.get("blocking_if_unsatisfied") is not True:
                    result.error("ERR_REQUIRED_CONTEXT_NOT_BLOCKING", item_label)
        budget = plan.get("budget")
        require_keys(budget, ["max_items", "max_characters"], f"{label}.context_plan.budget", result)
    compiled = data.get("compiled_context")
    require_keys(compiled, ["items", "source_refs", "selected_for", "excluded_sources", "budget", "used_items", "used_characters"], f"{label}.compiled_context", result)
    if isinstance(compiled, dict):
        for index, source in enumerate(require_list(compiled.get("items"), f"{label}.compiled_context.items", result)):
            if isinstance(source, dict) and source.get("decision_change_potential") is not True:
                result.error("ERR_CONTEXT_NOT_DECISION_RELEVANT", f"{label}.compiled_context.items[{index}]")
    gate = data.get("context_gate")
    require_keys(gate, ["status", "blockers", "warnings"], f"{label}.context_gate", result)
    gate_status = gate.get("status") if isinstance(gate, dict) else None
    enum_contains(gate_status, contract["context_gate_statuses"], f"{label}.context_gate.status", result)
    blocked = gate_status == "blocked"
    if blocked != (data.get("lifecycle_status") == "blocked_context"):
        result.error("ERR_CONTEXT_GATE_LIFECYCLE_MISMATCH", label)
    questions = require_list(data.get("clarification_questions"), f"{label}.clarification_questions", result)
    blockers = require_list(gate.get("blockers") if isinstance(gate, dict) else None, f"{label}.context_gate.blockers", result)
    if blocked and (not blockers or len(questions) != len(blockers)):
        result.error("ERR_TARGETED_CLARIFICATION_REQUIRED", label)
    if not blocked and (blockers or questions):
        result.error("ERR_READY_CONTEXT_HAS_BLOCKERS", label)
    validate_composition(data, contract, result, label, blocked)
    worker = data.get("worker_plan")
    if blocked:
        if worker is not None:
            result.error("ERR_BLOCKED_CONTEXT_SELECTED_WORKER", label)
    else:
        require_keys(worker, ["selection_basis", "required_capabilities", "allowed_tools", "compute_route", "context_refs", "output_contract", "authority_ceiling", "prohibited_actions"], f"{label}.worker_plan", result)
        if isinstance(worker, dict):
            if worker.get("selection_basis") != "capability_contract":
                result.error("ERR_WORKER_SELECTION_BASIS", label)
            if "model" in worker or "provider" in worker:
                result.error("ERR_MODEL_SPECIFIC_WORKER", label)
            require_list(worker.get("required_capabilities"), f"{label}.worker_plan.required_capabilities", result, nonempty=True)
            require_list(worker.get("prohibited_actions"), f"{label}.worker_plan.prohibited_actions", result, nonempty=True)
            refs = compiled.get("source_refs", []) if isinstance(compiled, dict) else []
            if worker.get("context_refs") != refs:
                result.error("ERR_WORKER_CONTEXT_MISMATCH", label)
    validate_epistemic(data.get("epistemic_register"), contract, result, f"{label}.epistemic_register")
    validate_authority(data.get("authority_plan"), contract, data.get("risk_tier"), result, f"{label}.authority_plan")
    enum_contains(data.get("memory_update_status"), {"not_started", "distillation_pending", "proposed", "applied"}, f"{label}.memory_update_status", result)
    enum_contains(data.get("output_mode"), contract["output_modes"], f"{label}.output_mode", result)
    require_keys(data.get("composition_observability"), contract["observability_fields"], f"{label}.composition_observability", result)


def validate_legacy_task(data: dict[str, Any], bundle: dict[str, Any], result: Validation, label: str) -> None:
    contract = bundle["contract"]
    base = ["schema_version", "task_id", "objective", "task_class", "decision_type", "risk_tier", "context_sources", "epistemic_register", "uncertainty_register", "authority_plan", "output_mode"]
    require_keys(data, base, label, result)
    validate_context_sources(data.get("context_sources"), contract, result, f"{label}.context_sources", legacy=True)
    if data.get("schema_version") == "3.0.0":
        require_keys(data, ["method_packs", "domain_packs", "cognition_graph", "compute_route"], label, result)
    else:
        require_keys(data, ["selected_composition", "cognition_graph", "compute_route"], label, result)
    validate_epistemic(data.get("epistemic_register"), contract, result, f"{label}.epistemic_register")
    validate_authority(data.get("authority_plan"), contract, data.get("risk_tier"), result, f"{label}.authority_plan")
    result.warn("WARN_LEGACY_TASK", f"{label} uses schema {data.get('schema_version')}")


def validate_task(data: Any, result: Validation, label: str = "task", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_bundle(result)
    if bundle is None or not isinstance(data, dict):
        if not isinstance(data, dict):
            result.error("ERR_OBJECT_REQUIRED", label)
        return
    if data.get("schema_version") in LEGACY_VERSIONS:
        validate_legacy_task(data, bundle, result, label)
    else:
        validate_v4_task(data, bundle, result, label)


def validate_grant(data: Any, result: Validation, label: str = "grant", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_bundle(result)
    if bundle is None:
        return
    required = ["schema_version", "grant_id", "status", "scope", "risk_ceiling", "allowed_actions", "prohibited_actions", "approval", "expires_on", "success_metric", "revocation_trigger", "review_cadence"]
    require_keys(data, required, label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") not in {VERSION, *LEGACY_VERSIONS}:
        result.error("ERR_GRANT_VERSION", str(data.get("schema_version")))
    enum_contains(data.get("status"), {"proposed", "active", "suspended", "revoked", "expired"}, f"{label}.status", result)
    enum_contains(data.get("risk_ceiling"), bundle["contract"]["risk_tiers"], f"{label}.risk_ceiling", result)
    if data.get("risk_ceiling") == "critical":
        result.error("ERR_CRITICAL_AUTONOMY_FORBIDDEN", label)
    try:
        date.fromisoformat(str(data.get("expires_on")))
    except ValueError:
        result.error("ERR_GRANT_EXPIRY_DATE", str(data.get("expires_on")))


def validate_state(data: Any, result: Validation, label: str = "state", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_bundle(result)
    if bundle is None:
        return
    if not isinstance(data, dict):
        result.error("ERR_OBJECT_REQUIRED", label)
        return
    if data.get("schema_version") in LEGACY_VERSIONS:
        require_keys(data, ["project_id", "state_version", "accepted_decisions", "evidence_register", "open_questions", "risk_register", "authority_grants", "learning_events", "latest_task_ids", "state_write_authorization"], label, result)
        result.warn("WARN_LEGACY_STATE", f"{label} uses schema {data.get('schema_version')}")
        return
    require_keys(data, ["schema_version", "project_id", "state_version", "corporate_memory", "working_memory", "governance", "state_write_authorization"], label, result)
    if data.get("schema_version") != VERSION:
        result.error("ERR_STATE_VERSION", str(data.get("schema_version")))
    memory = data.get("corporate_memory")
    require_keys(memory, ["context", "decision_log", "backlog"], f"{label}.corporate_memory", result)
    if isinstance(memory, dict):
        for key in ["context", "decision_log", "backlog"]:
            require_list(memory.get(key), f"{label}.corporate_memory.{key}", result)
    working = data.get("working_memory")
    require_keys(working, ["storage", "default_ttl_hours", "auto_promotion"], f"{label}.working_memory", result)
    if isinstance(working, dict):
        if working.get("storage") != ".control-plane/working":
            result.error("ERR_WORKING_MEMORY_STORAGE", label)
        if working.get("auto_promotion") is not False:
            result.error("ERR_WORKING_MEMORY_PROMOTION", label)
    governance = data.get("governance")
    require_keys(governance, ["risk_register", "authority_grants", "learning_events", "composition_observations", "routing_policy_version", "routing_policy_auto_update", "latest_task_ids"], f"{label}.governance", result)
    if isinstance(governance, dict) and governance.get("routing_policy_auto_update") is not False:
        result.error("ERR_SELF_MODIFYING_ROUTING", label)


def validate_composition_outcome(data: Any, result: Validation, label: str = "outcome", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_bundle(result)
    if bundle is None:
        return
    required = ["schema_version", "task_id"] + bundle["contract"]["observability_fields"] + ["routing_policy_changed_automatically"]
    require_keys(data, required, label, result)
    if isinstance(data, dict):
        if data.get("schema_version") != VERSION:
            result.error("ERR_OUTCOME_VERSION", str(data.get("schema_version")))
        if data.get("routing_policy_changed_automatically") is not False:
            result.error("ERR_SELF_MODIFYING_ROUTING", label)


def validate_execution_outcome(data: Any, result: Validation, label: str = "execution-outcome") -> None:
    require_keys(data, ["schema_version", "task_id", "completion_status", "memory_proposal_id", "base_revision", "verification", "learning_candidates"], label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") != VERSION:
        result.error("ERR_EXECUTION_OUTCOME_VERSION", str(data.get("schema_version")))
    enum_contains(data.get("completion_status"), {"completed", "partial", "blocked", "failed"}, f"{label}.completion_status", result)
    verification = data.get("verification")
    require_keys(verification, ["status", "evidence_refs"], f"{label}.verification", result)
    if isinstance(verification, dict):
        enum_contains(verification.get("status"), {"passed", "partial", "failed"}, f"{label}.verification.status", result)
        require_list(verification.get("evidence_refs"), f"{label}.verification.evidence_refs", result)
    ids = []
    for index, candidate in enumerate(require_list(data.get("learning_candidates"), f"{label}.learning_candidates", result)):
        item_label = f"{label}.learning_candidates[{index}]"
        require_keys(candidate, ["candidate_id", "record_id", "target_memory_class", "epistemic_class", "content", "source_refs", "rationale"], item_label, result)
        if isinstance(candidate, dict):
            ids.append(candidate.get("candidate_id"))
    require_unique(ids, f"{label}.learning_candidates.candidate_id", result)


def validate_memory_proposal(data: Any, result: Validation, label: str = "memory-proposal", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_bundle(result)
    if bundle is None:
        return
    require_keys(data, ["schema_version", "proposal_id", "task_id", "base_revision", "verified_evidence_refs", "write_status", "write_authorization_required", "write_authorization", "changes", "rejected_candidates", "routing_policy_changed_automatically"], label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") != VERSION:
        result.error("ERR_MEMORY_PROPOSAL_VERSION", str(data.get("schema_version")))
    if data.get("write_status") != "proposed" or data.get("write_authorization_required") is not True or data.get("write_authorization") != "not_authorized":
        result.error("ERR_MEMORY_PROPOSAL_GATE", label)
    if data.get("routing_policy_changed_automatically") is not False:
        result.error("ERR_SELF_MODIFYING_ROUTING", label)
    verified_refs = set(require_list(data.get("verified_evidence_refs"), f"{label}.verified_evidence_refs", result))
    ids = []
    for index, change in enumerate(require_list(data.get("changes"), f"{label}.changes", result)):
        item_label = f"{label}.changes[{index}]"
        require_keys(change, ["change_id", "operation", "record_id", "target_memory_class", "record"], item_label, result)
        if isinstance(change, dict):
            ids.append(change.get("change_id"))
            enum_contains(change.get("operation"), bundle["contract"]["memory_operations"], f"{item_label}.operation", result)
            enum_contains(change.get("target_memory_class"), bundle["contract"]["memory_classes"], f"{item_label}.target_memory_class", result)
            record = change.get("record")
            require_keys(record, ["record_id", "memory_class", "epistemic_class", "content", "source_refs", "rationale"], f"{item_label}.record", result)
            if isinstance(record, dict):
                source_refs = set(require_list(record.get("source_refs"), f"{item_label}.record.source_refs", result))
                if not source_refs <= verified_refs:
                    result.error("ERR_UNVERIFIED_PROVENANCE", item_label)
            if change.get("target_memory_class") == "working_memory" and isinstance(record, dict):
                if not record.get("expires_at"):
                    result.error("ERR_WORKING_MEMORY_TTL", item_label)
                if record.get("promotion_authorized") is not False:
                    result.error("ERR_WORKING_MEMORY_PROMOTION", item_label)
    require_unique(ids, f"{label}.changes.change_id", result)


def validate_authorization(data: Any, result: Validation, label: str = "authorization", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_bundle(result)
    if bundle is None:
        return
    require_keys(data, ["schema_version", "authorization_id", "status", "task_id", "scopes", "allowed_memory_classes", "approved_by", "evidence_reference", "expires_at"], label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") != VERSION:
        result.error("ERR_AUTHORIZATION_VERSION", str(data.get("schema_version")))
    enum_contains(data.get("status"), {"proposed", "active", "revoked", "expired"}, f"{label}.status", result)
    for memory_class in require_list(data.get("allowed_memory_classes"), f"{label}.allowed_memory_classes", result, nonempty=True):
        enum_contains(memory_class, bundle["contract"]["memory_classes"], f"{label}.allowed_memory_classes", result)
    try:
        parsed = datetime.fromisoformat(str(data.get("expires_at")).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except ValueError:
        result.error("ERR_AUTHORIZATION_EXPIRY", str(data.get("expires_at")))


def validate_package(result: Validation) -> None:
    required_paths = [
        ROOT / "README.md", ROOT / ".gitignore", ROOT / "pyproject.toml", ROOT / ".github/workflows/validate.yml",
        SKILL_ROOT / "SKILL.md", SKILL_ROOT / "agents/openai.yaml",
        REFERENCES / "control-plane-contract.json", REFERENCES / "cognitive-primitive-registry.json",
        REFERENCES / "domain-lens-registry.json", REFERENCES / "seed-recipes.json", REFERENCES / "optional-personas.json",
        REFERENCES / "packs-and-routing.md", REFERENCES / "risk-and-authority.md",
        REFERENCES / "context-and-memory-lifecycle.md", REFERENCES / "v3.1-to-v4-migration.md",
        REFERENCES / "v3-to-v3.1-migration.md",
        ASSETS / "composition-request.template.json", ASSETS / "task-packet.template.json",
        ASSETS / "project-state.template.json", ASSETS / "authority-grant.template.json",
        ASSETS / "composition-outcome.template.json", ASSETS / "execution-outcome.template.json",
        ASSETS / "memory-change-proposal.template.json", ASSETS / "memory-write-authorization.template.json",
        ASSETS / "decision-packet.template.md",
        SKILL_ROOT / "scripts/_composition_v31.py", SKILL_ROOT / "scripts/compose_task.py",
        SKILL_ROOT / "scripts/control_plane.py", SKILL_ROOT / "scripts/memory_adapter.py",
        SKILL_ROOT / "scripts/validate_artifacts.py",
    ]
    for path in required_paths:
        if not path.is_file():
            result.error("ERR_FILE_MISSING", str(path))
    skill = SKILL_ROOT / "SKILL.md"
    if skill.is_file():
        content = skill.read_text(encoding="utf-8")
        if "[TODO" in content or not re.match(r"^---\nname: ai-native-control-plane\ndescription: .+\n---", content, re.DOTALL):
            result.error("ERR_SKILL_FRONTMATTER", "SKILL.md")
    interface = SKILL_ROOT / "agents/openai.yaml"
    if interface.is_file():
        text = interface.read_text(encoding="utf-8")
        if not all(item in text for item in ["interface:", "display_name:", "short_description:", "default_prompt:", "$ai-native-control-plane"]):
            result.error("ERR_INTERFACE_METADATA", "agents/openai.yaml")
    if ".control-plane/working/" not in (ROOT / ".gitignore").read_text(encoding="utf-8"):
        result.error("ERR_WORKING_MEMORY_NOT_IGNORED", ".gitignore")

    bundle = get_bundle(result)
    if bundle is None:
        return
    primitives = validate_registry(bundle["registry"], result)
    lenses = validate_lenses(bundle["lenses"], result)
    contract = validate_contract(bundle["contract"], primitives, lenses, result)
    if contract is None:
        return
    validate_supporting_references(bundle, contract, result)

    request = load_json(ASSETS / "composition-request.template.json", result)
    task = load_json(ASSETS / "task-packet.template.json", result)
    state = load_json(ASSETS / "project-state.template.json", result)
    grant = load_json(ASSETS / "authority-grant.template.json", result)
    composition_outcome = load_json(ASSETS / "composition-outcome.template.json", result)
    execution_outcome = load_json(ASSETS / "execution-outcome.template.json", result)
    memory_proposal = load_json(ASSETS / "memory-change-proposal.template.json", result)
    authorization = load_json(ASSETS / "memory-write-authorization.template.json", result)
    if isinstance(request, dict):
        try:
            composed = compose(request)
        except CompositionError as exc:
            result.error("ERR_COMPOSITION_TEMPLATE", str(exc))
        else:
            validate_v4_task(composed, bundle, result, "composition-request.template.output")
            if isinstance(task, dict) and composed != task:
                result.error("ERR_TASK_TEMPLATE_DRIFT", "task-packet.template.json")
    if isinstance(task, dict):
        validate_v4_task(task, bundle, result, "task-packet.template")
    if isinstance(state, dict):
        validate_state(state, result, "project-state.template", bundle)
    if isinstance(grant, dict):
        validate_grant(grant, result, "authority-grant.template", bundle)
    if isinstance(composition_outcome, dict):
        validate_composition_outcome(composition_outcome, result, "composition-outcome.template", bundle)
    if isinstance(execution_outcome, dict):
        validate_execution_outcome(execution_outcome, result, "execution-outcome.template")
    if isinstance(memory_proposal, dict):
        validate_memory_proposal(memory_proposal, result, "memory-change-proposal.template", bundle)
    if isinstance(authorization, dict):
        validate_authorization(authorization, result, "memory-write-authorization.template", bundle)
    if isinstance(task, dict) and isinstance(execution_outcome, dict):
        try:
            distilled = distill_outcome(task, execution_outcome)
        except LifecycleError as exc:
            result.error("ERR_DISTILLATION_TEMPLATE", str(exc))
        else:
            validate_memory_proposal(distilled, result, "execution-outcome.template.proposal", bundle)
            if isinstance(memory_proposal, dict) and distilled != memory_proposal:
                result.error("ERR_MEMORY_PROPOSAL_TEMPLATE_DRIFT", "memory-change-proposal.template.json")

    fixtures = ROOT / "tests/fixtures/composition_requests"
    for path in sorted(fixtures.glob("*.json")):
        request_data = load_json(path, result)
        if not isinstance(request_data, dict):
            continue
        try:
            composed = compose(request_data)
        except CompositionError as exc:
            result.error("ERR_FIXTURE_COMPOSITION", f"{path.name}: {exc}")
        else:
            validate_v4_task(composed, bundle, result, f"fixture.{path.stem}")
    lifecycle_fixtures = ROOT / "tests/fixtures/lifecycle_requests"
    for path in sorted(lifecycle_fixtures.glob("*.json")):
        request_data = load_json(path, result)
        if not isinstance(request_data, dict):
            continue
        try:
            composed = compose(request_data)
        except CompositionError as exc:
            result.error("ERR_FIXTURE_COMPOSITION", f"{path.name}: {exc}")
        else:
            validate_v4_task(composed, bundle, result, f"fixture.{path.stem}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--task", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--grant", type=Path)
    parser.add_argument("--outcome", type=Path, help="Composition outcome")
    parser.add_argument("--execution-outcome", type=Path)
    parser.add_argument("--memory-proposal", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    result = Validation()
    bundle = get_bundle(result)
    provided = [args.task, args.request, args.state, args.grant, args.outcome, args.execution_outcome, args.memory_proposal, args.authorization]
    if args.all or not any(provided):
        validate_package(result)
    if args.task:
        data = load_json(args.task, result)
        if data is not None:
            validate_task(data, result, str(args.task), bundle)
    if args.request:
        data = load_json(args.request, result)
        if isinstance(data, dict):
            try:
                validate_task(compose(data), result, f"{args.request}.output", bundle)
            except CompositionError as exc:
                result.error("ERR_COMPOSITION", str(exc))
    if args.state:
        data = load_json(args.state, result)
        if data is not None:
            validate_state(data, result, str(args.state), bundle)
    if args.grant:
        data = load_json(args.grant, result)
        if data is not None:
            validate_grant(data, result, str(args.grant), bundle)
    if args.outcome:
        data = load_json(args.outcome, result)
        if data is not None:
            validate_composition_outcome(data, result, str(args.outcome), bundle)
    if args.execution_outcome:
        data = load_json(args.execution_outcome, result)
        if data is not None:
            validate_execution_outcome(data, result, str(args.execution_outcome))
    if args.memory_proposal:
        data = load_json(args.memory_proposal, result)
        if data is not None:
            validate_memory_proposal(data, result, str(args.memory_proposal), bundle)
    if args.authorization:
        data = load_json(args.authorization, result)
        if data is not None:
            validate_authorization(data, result, str(args.authorization), bundle)
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
