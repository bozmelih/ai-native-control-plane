#!/usr/bin/env python3
"""Validate AI-Native Control Plane V3.1 contracts and artifacts.

This standard-library validator checks structure, taxonomy, composition,
epistemic, compute, context, persona, and authority invariants. A PASS does not
prove strategic correctness or authorize state writes or external action.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from compose_task import CompositionError, compose


SKILL_ROOT = Path(__file__).resolve().parents[1]
REFERENCES = SKILL_ROOT / "references"
ASSETS = SKILL_ROOT / "assets"
ROOT = SKILL_ROOT.parents[1]
VERSION = "3.1.0"
LEGACY_VERSION = "3.0.0"
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


def enum_contains(value: Any, options: list[str] | set[str], label: str, result: Validation) -> None:
    if value not in options:
        result.error("ERR_ENUM", f"{label}={value!r}")


def get_reference_bundle(result: Validation) -> dict[str, Any] | None:
    contract = load_json(REFERENCES / "control-plane-contract.json", result)
    registry = load_json(REFERENCES / "cognitive-primitive-registry.json", result)
    lenses = load_json(REFERENCES / "domain-lens-registry.json", result)
    recipes = load_json(REFERENCES / "seed-recipes.json", result)
    personas = load_json(REFERENCES / "optional-personas.json", result)
    if not all(isinstance(item, dict) for item in [contract, registry, lenses, recipes, personas]):
        return None
    return {
        "contract": contract,
        "registry": registry,
        "lenses": lenses,
        "recipes": recipes,
        "personas": personas,
    }


def validate_registry(registry: Any, result: Validation) -> dict[str, dict[str, Any]]:
    require_keys(registry, ["schema_version", "purpose", "selection_rule", "primitives"], "primitive-registry", result)
    if not isinstance(registry, dict):
        return {}
    if registry.get("schema_version") != VERSION:
        result.error("ERR_REGISTRY_VERSION", str(registry.get("schema_version")))
    primitives = require_list(registry.get("primitives"), "primitive-registry.primitives", result, nonempty=True)
    if not 15 <= len(primitives) <= 20:
        result.error("ERR_REGISTRY_SIZE", f"expected 15-20 primitives, got {len(primitives)}")
    required = [
        "id", "category", "purpose", "use_when", "avoid_when", "required_inputs",
        "evidence_needs", "reasoning_operation", "expected_outputs",
        "relative_compute_cost", "complements", "common_failure_modes",
    ]
    by_id: dict[str, dict[str, Any]] = {}
    for index, primitive in enumerate(primitives):
        label = f"primitive-registry.primitives[{index}]"
        require_keys(primitive, required, label, result)
        if not isinstance(primitive, dict):
            continue
        item_id = primitive.get("id")
        require_nonempty_string(item_id, f"{label}.id", result)
        enum_contains(primitive.get("category"), {"thinking_method", "quality_check", "synthesis"}, f"{label}.category", result)
        for key in ["purpose", "reasoning_operation"]:
            require_nonempty_string(primitive.get(key), f"{label}.{key}", result)
        for key in ["use_when", "avoid_when", "required_inputs", "evidence_needs", "expected_outputs", "complements", "common_failure_modes"]:
            require_list(primitive.get(key), f"{label}.{key}", result, nonempty=key != "complements")
        enum_contains(primitive.get("relative_compute_cost"), {"light", "standard", "high"}, f"{label}.relative_compute_cost", result)
        if isinstance(item_id, str):
            if item_id in by_id:
                result.error("ERR_DUPLICATE_VALUE", f"primitive id {item_id}")
            by_id[item_id] = primitive
    for item_id, primitive in by_id.items():
        for complement in primitive.get("complements", []):
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
    for index, lens in enumerate(require_list(data.get("lenses"), "domain-lens-registry.lenses", result, nonempty=True)):
        label = f"domain-lens-registry.lenses[{index}]"
        require_keys(lens, ["id", "scope_type", "purpose", "constraints", "evidence_standards"], label, result)
        if not isinstance(lens, dict):
            continue
        item_id = lens.get("id")
        require_nonempty_string(item_id, f"{label}.id", result)
        enum_contains(lens.get("scope_type"), {"core_domain", "subdomain_lens", "cross_domain_lens"}, f"{label}.scope_type", result)
        require_nonempty_string(lens.get("purpose"), f"{label}.purpose", result)
        require_list(lens.get("constraints"), f"{label}.constraints", result, nonempty=True)
        require_list(lens.get("evidence_standards"), f"{label}.evidence_standards", result, nonempty=True)
        if isinstance(item_id, str):
            if item_id in by_id:
                result.error("ERR_DUPLICATE_VALUE", f"domain lens id {item_id}")
            by_id[item_id] = lens
    return by_id


def validate_contract(contract: Any, primitives: dict[str, dict[str, Any]], lenses: dict[str, dict[str, Any]], result: Validation) -> dict[str, Any] | None:
    required = [
        "schema_version", "system", "paradigm", "architecture_layers", "runtime_flow",
        "invariants", "task_classes", "decision_types", "risk_tiers", "compute_routes",
        "compute_selection_signals", "composition_selection_signals", "evidence_classes",
        "cognitive_taxonomy", "thinking_methods", "quality_checks", "synthesis_steps",
        "domain_lenses", "deprecated_fields", "compatibility_aliases", "output_modes",
        "authority_gates", "risk_requirements", "anti_bureaucracy", "observability_fields",
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
    expected_layers = ["durable_state", "control_plane", "temporary_cognition_graph", "optional_execution_interface"]
    if contract.get("architecture_layers") != expected_layers:
        result.error("ERR_ARCHITECTURE_LAYERS", "V3 architecture layers changed")
    required_flow = ["cognitive_need_diagnosis", "cognitive_composition", "authority_gate"]
    if any(item not in contract.get("runtime_flow", []) for item in required_flow):
        result.error("ERR_RUNTIME_FLOW", "diagnosis, composition, and authority gate are required")

    invariants = contract.get("invariants")
    expected_invariants = {
        "human_authority_is_explicit": True,
        "persona_is_required": False,
        "persona_grants_authority": False,
        "domain_lens_is_department": False,
        "task_graph_is_ephemeral_by_default": True,
        "confidence_is_evidence": False,
        "implicit_state_write_allowed": False,
        "implicit_external_action_allowed": False,
        "validator_pass_is_human_approval": False,
        "acceptance_is_execution_authorization": False,
        "compute_route_grants_authority": False,
        "earned_autonomy_is_scoped_expiring_and_revocable": True,
        "observations_auto_modify_routing_policy": False,
    }
    if not isinstance(invariants, dict):
        result.error("ERR_OBJECT_REQUIRED", "control-plane-contract.invariants")
    else:
        for key, expected in expected_invariants.items():
            if invariants.get(key) is not expected:
                result.error("ERR_INVARIANT", f"{key} must be {expected}")

    if "confidence" in contract.get("evidence_classes", []):
        result.error("ERR_CONFIDENCE_AS_EVIDENCE", "confidence cannot be an evidence class")
    if contract.get("risk_tiers") != ["low", "medium", "high", "critical"]:
        result.error("ERR_RISK_TIERS", "risk tiers must be low, medium, high, critical")
    if contract.get("compute_routes") != ["light", "standard", "high", "maximum"]:
        result.error("ERR_COMPUTE_ROUTES", "compute routes must remain light, standard, high, maximum")

    taxonomy = contract.get("cognitive_taxonomy", {})
    if set(taxonomy) != {"thinking_method", "domain_lens", "quality_check", "synthesis"}:
        result.error("ERR_COGNITIVE_TAXONOMY", "typed categories must remain separate")
    registry_methods = {item_id for item_id, item in primitives.items() if item.get("category") == "thinking_method"}
    registry_checks = {item_id for item_id, item in primitives.items() if item.get("category") == "quality_check"}
    registry_synthesis = {item_id for item_id, item in primitives.items() if item.get("category") == "synthesis"}
    if set(contract.get("thinking_methods", [])) != registry_methods:
        result.error("ERR_METHOD_REGISTRY_MISMATCH", "contract and primitive registry differ")
    if set(contract.get("quality_checks", [])) != registry_checks:
        result.error("ERR_CHECK_REGISTRY_MISMATCH", "contract and primitive registry differ")
    if set(contract.get("synthesis_steps", [])) != registry_synthesis:
        result.error("ERR_SYNTHESIS_REGISTRY_MISMATCH", "contract and primitive registry differ")
    if set(contract.get("domain_lenses", [])) != set(lenses):
        result.error("ERR_LENS_REGISTRY_MISMATCH", "contract and domain lens registry differ")

    aliases = contract.get("compatibility_aliases", {})
    method_aliases = aliases.get("method_packs", {}) if isinstance(aliases, dict) else {}
    for legacy_id, mappings in method_aliases.items():
        for mapping in require_list(mappings, f"compatibility_aliases.method_packs.{legacy_id}", result, nonempty=True):
            if not isinstance(mapping, dict):
                continue
            category = mapping.get("category")
            item_id = mapping.get("id")
            if category == "domain_lens":
                enum_contains(item_id, set(lenses), f"compatibility alias {legacy_id}", result)
            elif item_id not in primitives or primitives[item_id].get("category") != category:
                result.error("ERR_COMPATIBILITY_ALIAS", f"{legacy_id}->{category}:{item_id}")
    requirements = contract.get("risk_requirements")
    if not isinstance(requirements, dict) or set(requirements) != {"low", "medium", "high", "critical"}:
        result.error("ERR_RISK_REQUIREMENTS", "every risk tier needs a requirement")
    else:
        for risk, requirement in requirements.items():
            require_keys(requirement, ["minimum_compute", "human_decision_required", "required_quality_checks"], f"risk_requirements.{risk}", result)
            if isinstance(requirement, dict):
                enum_contains(requirement.get("minimum_compute"), contract["compute_routes"], f"risk_requirements.{risk}.minimum_compute", result)
                for check in require_list(requirement.get("required_quality_checks"), f"risk_requirements.{risk}.required_quality_checks", result):
                    enum_contains(check, contract["quality_checks"], f"risk_requirements.{risk}.required_quality_checks", result)
    return contract


def validate_recipes(data: Any, contract: dict[str, Any], result: Validation) -> set[str]:
    require_keys(data, ["schema_version", "rule", "recipes"], "seed-recipes", result)
    if not isinstance(data, dict):
        return set()
    if data.get("schema_version") != VERSION:
        result.error("ERR_RECIPE_VERSION", str(data.get("schema_version")))
    if "non-mandatory" not in str(data.get("rule", "")):
        result.error("ERR_RECIPE_MANDATORY", "seed-recipes.rule")
    ids: list[str] = []
    for index, recipe in enumerate(require_list(data.get("recipes"), "seed-recipes.recipes", result, nonempty=True)):
        label = f"seed-recipes.recipes[{index}]"
        require_keys(recipe, ["id", "use_as_prior_when", "thinking_methods", "domain_lenses", "quality_checks"], label, result)
        if not isinstance(recipe, dict):
            continue
        item_id = recipe.get("id")
        require_nonempty_string(item_id, f"{label}.id", result)
        require_nonempty_string(recipe.get("use_as_prior_when"), f"{label}.use_as_prior_when", result)
        for method in require_list(recipe.get("thinking_methods"), f"{label}.thinking_methods", result):
            enum_contains(method, contract["thinking_methods"], f"{label}.thinking_methods", result)
        for lens in require_list(recipe.get("domain_lenses"), f"{label}.domain_lenses", result):
            enum_contains(lens, contract["domain_lenses"], f"{label}.domain_lenses", result)
        for check in require_list(recipe.get("quality_checks"), f"{label}.quality_checks", result):
            enum_contains(check, contract["quality_checks"], f"{label}.quality_checks", result)
        if isinstance(item_id, str):
            ids.append(item_id)
    require_unique(ids, "seed-recipes.recipes.id", result)
    return set(ids)


def validate_personas(data: Any, contract: dict[str, Any], result: Validation) -> set[str]:
    require_keys(data, ["schema_version", "rule", "presets"], "optional-personas", result)
    if not isinstance(data, dict):
        return set()
    if data.get("schema_version") != VERSION:
        result.error("ERR_PERSONA_VERSION", str(data.get("schema_version")))
    rule = str(data.get("rule", ""))
    if "cannot create authority" not in rule or "optional" not in rule:
        result.error("ERR_PERSONA_BOUNDARY", "optional-personas.rule")
    ids: list[str] = []
    for index, preset in enumerate(require_list(data.get("presets"), "optional-personas.presets", result, nonempty=True)):
        label = f"optional-personas.presets[{index}]"
        required = [
            "id", "use_for", "communication_lens", "suggested_thinking_methods",
            "suggested_domain_lenses", "suggested_quality_checks", "authority_effect",
        ]
        require_keys(preset, required, label, result)
        if not isinstance(preset, dict):
            continue
        item_id = preset.get("id")
        require_nonempty_string(item_id, f"{label}.id", result)
        if preset.get("authority_effect") != "none":
            result.error("ERR_PERSONA_AUTHORITY", str(item_id))
        for method in require_list(preset.get("suggested_thinking_methods"), f"{label}.suggested_thinking_methods", result):
            enum_contains(method, contract["thinking_methods"], f"{label}.suggested_thinking_methods", result)
        for lens in require_list(preset.get("suggested_domain_lenses"), f"{label}.suggested_domain_lenses", result):
            enum_contains(lens, contract["domain_lenses"], f"{label}.suggested_domain_lenses", result)
        for check in require_list(preset.get("suggested_quality_checks"), f"{label}.suggested_quality_checks", result):
            enum_contains(check, contract["quality_checks"], f"{label}.suggested_quality_checks", result)
        if isinstance(item_id, str):
            ids.append(item_id)
    require_unique(ids, "optional-personas.presets.id", result)
    return set(ids)


def validate_context_sources(items: Any, result: Validation, label: str, legacy: bool = False) -> None:
    sources = require_list(items, label, result, nonempty=True)
    ids: list[str] = []
    base = ["source_id", "kind", "freshness", "permitted_use", "summary"]
    required = base if legacy else base + ["relevance_to_decision", "decision_change_potential", "status"]
    for index, source in enumerate(sources):
        item_label = f"{label}[{index}]"
        require_keys(source, required, item_label, result)
        if not isinstance(source, dict):
            continue
        for key in base:
            require_nonempty_string(source.get(key), f"{item_label}.{key}", result)
        if not legacy:
            require_nonempty_string(source.get("relevance_to_decision"), f"{item_label}.relevance_to_decision", result)
            if source.get("decision_change_potential") is not True:
                result.error("ERR_CONTEXT_NOT_DECISION_RELEVANT", item_label)
            enum_contains(source.get("status"), {"available", "stale", "conflicting", "untrusted", "inaccessible"}, f"{item_label}.status", result)
        ids.append(str(source.get("source_id", "")))
    require_unique(ids, f"{label}.source_id", result)


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
        if claim.get("class") == "confidence":
            result.error("ERR_CONFIDENCE_AS_EVIDENCE", item_label)
        enum_contains(claim.get("class"), contract["evidence_classes"], f"{item_label}.class", result)
        source_ids = require_list(claim.get("source_ids"), f"{item_label}.source_ids", result)
        if claim.get("class") not in {"unknown", "assumption", "hypothesis"} and not source_ids:
            result.error("ERR_EVIDENCE_SOURCE_REQUIRED", item_label)
        ids.append(str(claim.get("claim_id", "")))
    require_unique(ids, f"{label}.claim_id", result)


def validate_authority_plan(plan: Any, contract: dict[str, Any], risk: Any, result: Validation, label: str) -> None:
    required = ["current_gate", "human_decision_required", "state_write", "external_action", "system_write", "next_gate"]
    require_keys(plan, required, label, result)
    if not isinstance(plan, dict):
        return
    enum_contains(plan.get("current_gate"), contract["authority_gates"], f"{label}.current_gate", result)
    enum_contains(plan.get("next_gate"), contract["authority_gates"], f"{label}.next_gate", result)
    if plan.get("state_write") not in {"propose_only", "explicit_authorization_required", "authorized_bounded_scope"}:
        result.error("ERR_STATE_WRITE_MODE", str(plan.get("state_write")))
    for field in ["external_action", "system_write"]:
        if plan.get(field) not in {"none", "explicit_authorization_required", "authorized_bounded_scope"}:
            result.error("ERR_ACTION_MODE", f"{field}={plan.get(field)!r}")
    authorized = any(plan.get(field) == "authorized_bounded_scope" for field in ["state_write", "external_action", "system_write"])
    if authorized:
        require_nonempty_string(plan.get("authorization_reference"), f"{label}.authorization_reference", result)
    if plan.get("state_write") == "authorized_bounded_scope" and not plan.get("authorization_reference"):
        result.error("ERR_IMPLICIT_STATE_WRITE", label)
    if risk in {"medium", "high", "critical"} and plan.get("human_decision_required") is not True:
        result.error("ERR_HUMAN_DECISION_REQUIRED", f"risk={risk}")
    if risk in {"high", "critical"} and "human_decision" not in {plan.get("current_gate"), plan.get("next_gate")}:
        result.error("ERR_HIGH_RISK_HUMAN_GATE", label)


def validate_selection_entries(items: Any, category: str, allowed: set[str], result: Validation, label: str) -> list[str]:
    entries = require_list(items, label, result)
    ids: list[str] = []
    for index, entry in enumerate(entries):
        item_label = f"{label}[{index}]"
        require_keys(entry, ["id", "why_selected", "uncertainty_reduced", "selected_by"], item_label, result)
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("id")
        enum_contains(item_id, allowed, f"{item_label}.id", result)
        require_nonempty_string(entry.get("why_selected"), f"{item_label}.why_selected", result)
        require_nonempty_string(entry.get("uncertainty_reduced"), f"{item_label}.uncertainty_reduced", result)
        require_nonempty_string(entry.get("selected_by"), f"{item_label}.selected_by", result)
        ids.append(str(item_id))
    require_unique(ids, f"{label}.id", result)
    return ids


def validate_signals(signals: Any, contract: dict[str, Any], result: Validation, label: str) -> None:
    required = list(dict.fromkeys(contract["composition_selection_signals"] + contract["compute_selection_signals"]))
    require_keys(signals, required, label, result)
    if not isinstance(signals, dict):
        return
    level_fields = [
        "ambiguity", "uncertainty", "decision_consequence", "expected_error_cost",
        "cross_domain_complexity", "context_complexity", "context_staleness",
        "complexity", "validation_requirement",
    ]
    for key in level_fields:
        enum_contains(signals.get(key), set(LEVELS), f"{label}.{key}", result)
    enum_contains(signals.get("reversibility"), {"low", "medium", "high"}, f"{label}.reversibility", result)
    for key in ["evidence_gaps", "conflicting_context", "need_for_independent_challenge"]:
        if not isinstance(signals.get(key), bool):
            result.error("ERR_BOOLEAN_REQUIRED", f"{label}.{key}")
    alternatives = signals.get("materially_plausible_alternatives")
    if not isinstance(alternatives, int) or alternatives < 0:
        result.error("ERR_ALTERNATIVE_COUNT", f"{label}.materially_plausible_alternatives")


def expected_minimum_compute(task: dict[str, Any], contract: dict[str, Any]) -> str:
    risk_minimum = contract["risk_requirements"][task["risk_tier"]]["minimum_compute"]
    index = contract["compute_routes"].index(risk_minimum)
    signals = task.get("composition_signals", {})
    compute_fields = ["complexity", "uncertainty", "decision_consequence", "expected_error_cost", "context_complexity", "cross_domain_complexity", "validation_requirement"]
    levels = [LEVELS.get(signals.get(field), 0) for field in compute_fields]
    if max(levels, default=0) >= 3:
        index = max(index, 3)
    elif max(levels, default=0) >= 2:
        index = max(index, 2)
    elif max(levels, default=0) >= 1 or task.get("task_class") in {"decision", "design", "incident"}:
        index = max(index, 1)
    count = task.get("selected_composition", {}).get("primitive_count", 0)
    if isinstance(count, int) and count >= 7:
        index = max(index, 2)
    return contract["compute_routes"][index]


def validate_v31_task(data: dict[str, Any], bundle: dict[str, Any], result: Validation, label: str) -> None:
    contract = bundle["contract"]
    required = [
        "schema_version", "task_id", "objective", "task_class", "decision_type", "risk_tier",
        "composition_signals", "context_sources", "selected_composition", "composition_deviations",
        "cognition_graph", "compute_route", "compute_rationale", "epistemic_register",
        "uncertainty_register", "authority_plan", "optional_persona_presets", "output_mode",
        "composition_observability",
    ]
    require_keys(data, required, label, result)
    if data.get("schema_version") != VERSION:
        result.error("ERR_TASK_VERSION", str(data.get("schema_version")))
    for key in ["task_id", "objective"]:
        require_nonempty_string(data.get(key), f"{label}.{key}", result)
    enum_contains(data.get("task_class"), contract["task_classes"], f"{label}.task_class", result)
    enum_contains(data.get("decision_type"), contract["decision_types"], f"{label}.decision_type", result)
    risk = data.get("risk_tier")
    enum_contains(risk, contract["risk_tiers"], f"{label}.risk_tier", result)
    validate_signals(data.get("composition_signals"), contract, result, f"{label}.composition_signals")
    validate_context_sources(data.get("context_sources"), result, f"{label}.context_sources")

    composition = data.get("selected_composition")
    require_keys(composition, ["thinking_methods", "domain_lenses", "quality_checks", "synthesis_steps", "primitive_count", "primitive_budget", "complex_graph_required"], f"{label}.selected_composition", result)
    if not isinstance(composition, dict):
        return
    method_ids = validate_selection_entries(composition.get("thinking_methods"), "thinking_method", set(contract["thinking_methods"]), result, f"{label}.selected_composition.thinking_methods")
    lens_ids = validate_selection_entries(composition.get("domain_lenses"), "domain_lens", set(contract["domain_lenses"]), result, f"{label}.selected_composition.domain_lenses")
    check_ids = validate_selection_entries(composition.get("quality_checks"), "quality_check", set(contract["quality_checks"]), result, f"{label}.selected_composition.quality_checks")
    synthesis_ids = validate_selection_entries(composition.get("synthesis_steps"), "synthesis", set(contract["synthesis_steps"]), result, f"{label}.selected_composition.synthesis_steps")
    actual_count = len(method_ids) + len(check_ids) + len(synthesis_ids)
    if composition.get("primitive_count") != actual_count:
        result.error("ERR_PRIMITIVE_COUNT", f"{label}: expected {actual_count}")
    budget = composition.get("primitive_budget")
    if not isinstance(budget, int) or budget < actual_count:
        result.error("ERR_PRIMITIVE_BUDGET", f"{label}: count={actual_count} budget={budget}")

    simple = data.get("task_class") in {"retrieval", "transform"}
    if simple:
        maximum = contract["anti_bureaucracy"]["simple_task_max_cognitive_primitives"]
        if actual_count > maximum:
            result.error("ERR_SIMPLE_TASK_OVERCOMPOSED", f"{label}: {actual_count}>{maximum}")
        if composition.get("complex_graph_required") is not False:
            result.error("ERR_SIMPLE_TASK_COMPLEX_GRAPH", label)
    elif actual_count and composition.get("complex_graph_required") is not True:
        result.error("ERR_COMPLEX_GRAPH_REQUIRED", label)

    required_checks = set(contract["risk_requirements"].get(risk, {}).get("required_quality_checks", []))
    for check in sorted(required_checks - set(check_ids)):
        result.error("ERR_RISK_CHECK_REQUIRED", f"risk={risk} check={check}")
    if risk in {"high", "critical"} and "red-team" not in check_ids:
        result.error("ERR_RISK_RED_TEAM_REQUIRED", f"risk={risk}")

    graph = require_list(data.get("cognition_graph"), f"{label}.cognition_graph", result, nonempty=bool(actual_count))
    if simple and graph:
        result.error("ERR_SIMPLE_TASK_GRAPH_NOT_EMPTY", label)
    graph_ids: list[str] = []
    referenced = {"thinking_method": [], "quality_check": [], "synthesis": []}
    selected_by_category = {"thinking_method": set(method_ids), "quality_check": set(check_ids), "synthesis": set(synthesis_ids)}
    seen_nodes: set[str] = set()
    for index, node in enumerate(graph):
        node_label = f"{label}.cognition_graph[{index}]"
        require_keys(node, ["node_id", "category", "primitive_id", "purpose", "why_selected", "applied_domain_lenses", "depends_on"], node_label, result)
        if not isinstance(node, dict):
            continue
        node_id = node.get("node_id")
        category = node.get("category")
        primitive_id = node.get("primitive_id")
        require_nonempty_string(node_id, f"{node_label}.node_id", result)
        enum_contains(category, {"thinking_method", "quality_check", "synthesis"}, f"{node_label}.category", result)
        if category in selected_by_category and primitive_id not in selected_by_category[category]:
            result.error("ERR_GRAPH_PRIMITIVE_NOT_SELECTED", f"{node_label}.{primitive_id}")
        for lens in require_list(node.get("applied_domain_lenses"), f"{node_label}.applied_domain_lenses", result):
            if lens not in lens_ids:
                result.error("ERR_GRAPH_LENS_NOT_SELECTED", f"{node_label}.{lens}")
        for dependency in require_list(node.get("depends_on"), f"{node_label}.depends_on", result):
            if dependency not in seen_nodes:
                result.error("ERR_GRAPH_DEPENDENCY", f"{node_label}->{dependency}")
        if isinstance(category, str) and isinstance(primitive_id, str) and category in referenced:
            referenced[category].append(primitive_id)
        graph_ids.append(str(node_id))
        seen_nodes.add(str(node_id))
    require_unique(graph_ids, f"{label}.cognition_graph.node_id", result)
    for category, selected_ids in selected_by_category.items():
        missing = selected_ids - set(referenced[category])
        if missing:
            result.error("ERR_SELECTED_PRIMITIVE_NOT_IN_GRAPH", f"{category}:{sorted(missing)}")
        duplicates = [item_id for item_id in referenced[category] if referenced[category].count(item_id) > 1]
        independent = bool(data.get("composition_signals", {}).get("need_for_independent_challenge"))
        if duplicates and not independent:
            result.error("ERR_DUPLICATE_COGNITION", f"{category}:{sorted(set(duplicates))}")

    compute = data.get("compute_route")
    enum_contains(compute, contract["compute_routes"], f"{label}.compute_route", result)
    rationale = require_list(data.get("compute_rationale"), f"{label}.compute_rationale", result, nonempty=True)
    for index, reason in enumerate(rationale):
        require_nonempty_string(reason, f"{label}.compute_rationale[{index}]", result)
    if compute in contract["compute_routes"]:
        minimum = expected_minimum_compute(data, contract)
        if contract["compute_routes"].index(compute) < contract["compute_routes"].index(minimum):
            result.error("ERR_COMPUTE_TOO_LOW", f"selected={compute} required={minimum}")
        if simple and compute != "light":
            result.error("ERR_SIMPLE_TASK_COMPUTE", f"selected={compute}")

    validate_epistemic_register(data.get("epistemic_register"), contract, result, f"{label}.epistemic_register")
    uncertainties = require_list(data.get("uncertainty_register"), f"{label}.uncertainty_register", result)
    if risk in {"high", "critical"} and not uncertainties:
        result.error("ERR_UNCERTAINTY_REGISTER_REQUIRED", f"risk={risk}")
    validate_authority_plan(data.get("authority_plan"), contract, risk, result, f"{label}.authority_plan")
    enum_contains(data.get("output_mode"), contract["output_modes"], f"{label}.output_mode", result)

    presets = require_list(data.get("optional_persona_presets"), f"{label}.optional_persona_presets", result)
    require_unique(presets, f"{label}.optional_persona_presets", result)
    allowed_presets = validate_personas(bundle["personas"], contract, result)
    for preset in presets:
        enum_contains(preset, allowed_presets, f"{label}.optional_persona_presets", result)

    deviations = require_list(data.get("composition_deviations"), f"{label}.composition_deviations", result)
    for index, deviation in enumerate(deviations):
        item_label = f"{label}.composition_deviations[{index}]"
        require_keys(deviation, ["action", "category", "id", "reason"], item_label, result)
        if isinstance(deviation, dict):
            enum_contains(deviation.get("action"), {"add", "remove"}, f"{item_label}.action", result)
            enum_contains(deviation.get("category"), {"thinking_method", "domain_lens", "quality_check"}, f"{item_label}.category", result)
            require_nonempty_string(deviation.get("reason"), f"{item_label}.reason", result)

    observability = data.get("composition_observability")
    require_keys(observability, contract["observability_fields"], f"{label}.composition_observability", result)


def validate_legacy_task(data: dict[str, Any], bundle: dict[str, Any], result: Validation, label: str) -> None:
    contract = bundle["contract"]
    required = [
        "schema_version", "task_id", "objective", "task_class", "decision_type", "risk_tier",
        "compute_route", "context_sources", "method_packs", "domain_packs", "cognition_graph",
        "epistemic_register", "uncertainty_register", "authority_plan", "output_mode",
    ]
    require_keys(data, required, label, result)
    if data.get("schema_version") != LEGACY_VERSION:
        result.error("ERR_TASK_VERSION", str(data.get("schema_version")))
    validate_context_sources(data.get("context_sources"), result, f"{label}.context_sources", legacy=True)
    aliases = contract["compatibility_aliases"]["method_packs"]
    methods = require_list(data.get("method_packs"), f"{label}.method_packs", result, nonempty=True)
    for method in methods:
        enum_contains(method, set(aliases), f"{label}.method_packs", result)
    for domain in require_list(data.get("domain_packs"), f"{label}.domain_packs", result, nonempty=True):
        enum_contains(domain, set(contract["compatibility_aliases"]["domain_packs"]), f"{label}.domain_packs", result)
    risk = data.get("risk_tier")
    enum_contains(risk, contract["risk_tiers"], f"{label}.risk_tier", result)
    compute = data.get("compute_route")
    enum_contains(compute, contract["compute_routes"], f"{label}.compute_route", result)
    minimum = contract["risk_requirements"].get(risk, {}).get("minimum_compute")
    if minimum and compute in contract["compute_routes"] and contract["compute_routes"].index(compute) < contract["compute_routes"].index(minimum):
        result.error("ERR_RISK_COMPUTE_TOO_LOW", f"risk={risk} compute={compute}")
    if risk in {"high", "critical"} and "red-team" not in methods:
        result.error("ERR_RISK_RED_TEAM_REQUIRED", f"risk={risk}")
    validate_epistemic_register(data.get("epistemic_register"), contract, result, f"{label}.epistemic_register")
    validate_authority_plan(data.get("authority_plan"), contract, risk, result, f"{label}.authority_plan")
    result.warn("WARN_LEGACY_TASK", f"{label} uses V3 method_packs/domain_packs aliases")


def validate_task(data: Any, result: Validation, label: str = "task", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_reference_bundle(result)
    if bundle is None or not isinstance(data, dict):
        if not isinstance(data, dict):
            result.error("ERR_OBJECT_REQUIRED", label)
        return
    primitives = validate_registry(bundle["registry"], result)
    lenses = validate_lenses(bundle["lenses"], result)
    contract = validate_contract(bundle["contract"], primitives, lenses, result)
    if contract is None:
        return
    if data.get("schema_version") == LEGACY_VERSION:
        validate_legacy_task(data, bundle, result, label)
    else:
        validate_v31_task(data, bundle, result, label)


def validate_grant(data: Any, result: Validation, label: str = "grant", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_reference_bundle(result)
    if bundle is None:
        return
    contract = bundle["contract"]
    required = [
        "schema_version", "grant_id", "status", "scope", "risk_ceiling", "allowed_actions",
        "prohibited_actions", "approval", "expires_on", "success_metric", "revocation_trigger", "review_cadence",
    ]
    require_keys(data, required, label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") not in {VERSION, LEGACY_VERSION}:
        result.error("ERR_GRANT_VERSION", str(data.get("schema_version")))
    for key in ["grant_id", "scope", "expires_on", "success_metric", "revocation_trigger", "review_cadence"]:
        require_nonempty_string(data.get(key), f"{label}.{key}", result)
    enum_contains(data.get("status"), {"proposed", "active", "suspended", "revoked", "expired"}, f"{label}.status", result)
    enum_contains(data.get("risk_ceiling"), contract["risk_tiers"], f"{label}.risk_ceiling", result)
    if data.get("risk_ceiling") == "critical":
        result.error("ERR_CRITICAL_AUTONOMY_FORBIDDEN", label)
    require_list(data.get("allowed_actions"), f"{label}.allowed_actions", result, nonempty=True)
    require_list(data.get("prohibited_actions"), f"{label}.prohibited_actions", result, nonempty=True)
    try:
        date.fromisoformat(str(data.get("expires_on")))
    except ValueError:
        result.error("ERR_GRANT_EXPIRY_DATE", str(data.get("expires_on")))
    if data.get("status") == "active":
        approval = data.get("approval")
        require_keys(approval, ["approved_by", "approved_at", "evidence_reference"], f"{label}.approval", result)
        if isinstance(approval, dict):
            for key in ["approved_by", "approved_at", "evidence_reference"]:
                require_nonempty_string(approval.get(key), f"{label}.approval.{key}", result)


def validate_state(data: Any, result: Validation, label: str = "state", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_reference_bundle(result)
    if bundle is None:
        return
    contract = bundle["contract"]
    base = [
        "schema_version", "project_id", "state_version", "accepted_decisions", "evidence_register",
        "open_questions", "risk_register", "authority_grants", "learning_events", "latest_task_ids",
        "state_write_authorization",
    ]
    required = base
    if isinstance(data, dict) and data.get("schema_version") == VERSION:
        required += ["composition_observations", "routing_policy_version", "routing_policy_auto_update"]
    require_keys(data, required, label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") not in {VERSION, LEGACY_VERSION}:
        result.error("ERR_STATE_VERSION", str(data.get("schema_version")))
    for key in ["project_id", "state_version"]:
        require_nonempty_string(data.get(key), f"{label}.{key}", result)
    list_fields = ["accepted_decisions", "evidence_register", "open_questions", "risk_register", "authority_grants", "learning_events", "latest_task_ids"]
    if data.get("schema_version") == VERSION:
        list_fields.append("composition_observations")
        if data.get("routing_policy_auto_update") is not False:
            result.error("ERR_SELF_MODIFYING_ROUTING", label)
    for key in list_fields:
        require_list(data.get(key), f"{label}.{key}", result)
    enum_contains(data.get("state_write_authorization"), {"not_authorized", "explicitly_authorized"}, f"{label}.state_write_authorization", result)
    for index, evidence in enumerate(data.get("evidence_register", [])):
        item_label = f"{label}.evidence_register[{index}]"
        require_keys(evidence, ["source_id", "class", "summary"], item_label, result)
        if isinstance(evidence, dict):
            if evidence.get("class") == "confidence":
                result.error("ERR_CONFIDENCE_AS_EVIDENCE", item_label)
            enum_contains(evidence.get("class"), contract["evidence_classes"], f"{item_label}.class", result)
    for index, grant in enumerate(data.get("authority_grants", [])):
        validate_grant(grant, result, f"{label}.authority_grants[{index}]", bundle)


def validate_outcome(data: Any, result: Validation, label: str = "outcome", bundle: dict[str, Any] | None = None) -> None:
    bundle = bundle or get_reference_bundle(result)
    if bundle is None:
        return
    required = ["schema_version", "task_id"] + bundle["contract"]["observability_fields"] + ["routing_policy_changed_automatically"]
    require_keys(data, required, label, result)
    if not isinstance(data, dict):
        return
    if data.get("schema_version") != VERSION:
        result.error("ERR_OUTCOME_VERSION", str(data.get("schema_version")))
    if data.get("routing_policy_changed_automatically") is not False:
        result.error("ERR_SELF_MODIFYING_ROUTING", label)


def validate_package(result: Validation) -> None:
    required_paths = [
        ROOT / "README.md",
        ROOT / ".gitignore",
        ROOT / "pyproject.toml",
        ROOT / ".github/workflows/validate.yml",
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "agents/openai.yaml",
        REFERENCES / "control-plane-contract.json",
        REFERENCES / "cognitive-primitive-registry.json",
        REFERENCES / "domain-lens-registry.json",
        REFERENCES / "seed-recipes.json",
        REFERENCES / "optional-personas.json",
        REFERENCES / "packs-and-routing.md",
        REFERENCES / "risk-and-authority.md",
        REFERENCES / "v3-to-v3.1-migration.md",
        ASSETS / "composition-request.template.json",
        ASSETS / "task-packet.template.json",
        ASSETS / "project-state.template.json",
        ASSETS / "authority-grant.template.json",
        ASSETS / "composition-outcome.template.json",
        ASSETS / "decision-packet.template.md",
        SKILL_ROOT / "scripts/compose_task.py",
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
        interface_text = interface.read_text(encoding="utf-8")
        expected = ["interface:", "display_name:", "short_description:", "default_prompt:", "$ai-native-control-plane"]
        if not all(item in interface_text for item in expected):
            result.error("ERR_INTERFACE_METADATA", "agents/openai.yaml")

    bundle = get_reference_bundle(result)
    if bundle is None:
        return
    primitives = validate_registry(bundle["registry"], result)
    lenses = validate_lenses(bundle["lenses"], result)
    contract = validate_contract(bundle["contract"], primitives, lenses, result)
    if contract is None:
        return
    validate_recipes(bundle["recipes"], contract, result)
    validate_personas(bundle["personas"], contract, result)

    task = load_json(ASSETS / "task-packet.template.json", result)
    state = load_json(ASSETS / "project-state.template.json", result)
    grant = load_json(ASSETS / "authority-grant.template.json", result)
    outcome = load_json(ASSETS / "composition-outcome.template.json", result)
    request = load_json(ASSETS / "composition-request.template.json", result)
    if task is not None:
        validate_v31_task(task, bundle, result, "task-packet.template")
    if state is not None:
        validate_state(state, result, "project-state.template", bundle)
    if grant is not None:
        validate_grant(grant, result, "authority-grant.template", bundle)
    if outcome is not None:
        validate_outcome(outcome, result, "composition-outcome.template", bundle)
    if isinstance(request, dict):
        try:
            composed = compose(request)
        except CompositionError as exc:
            result.error("ERR_COMPOSITION_TEMPLATE", str(exc))
        else:
            validate_v31_task(composed, bundle, result, "composition-request.template.output")

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
            validate_v31_task(composed, bundle, result, f"fixture.{path.stem}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Validate package contracts, templates, and fixtures")
    parser.add_argument("--task", type=Path, help="Validate one V3 or V3.1 task packet")
    parser.add_argument("--request", type=Path, help="Compose and validate one V3.1 request")
    parser.add_argument("--state", type=Path, help="Validate one persistent state record")
    parser.add_argument("--grant", type=Path, help="Validate one earned-autonomy grant")
    parser.add_argument("--outcome", type=Path, help="Validate one composition outcome record")
    args = parser.parse_args()
    result = Validation()
    bundle = get_reference_bundle(result)
    if args.all or not any((args.task, args.request, args.state, args.grant, args.outcome)):
        validate_package(result)
    if args.task:
        data = load_json(args.task, result)
        if data is not None:
            validate_task(data, result, str(args.task), bundle)
    if args.request:
        data = load_json(args.request, result)
        if isinstance(data, dict):
            try:
                composed = compose(data)
            except CompositionError as exc:
                result.error("ERR_COMPOSITION", str(exc))
            else:
                validate_task(composed, result, f"{args.request}.output", bundle)
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
            validate_outcome(data, result, str(args.outcome), bundle)
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
