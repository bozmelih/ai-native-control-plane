#!/usr/bin/env python3
"""Internal V3.1 cognition composer retained behind the V4 lifecycle.

The engine is deliberately small and deterministic. It does not perform the
reasoning and does not grant authority. Seed recipes are optional priors; task
signals, named needs, risk controls, and justified deviations determine the
emitted composition.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
REFERENCES = SKILL_ROOT / "references"
VERSION = "3.1.0"

METHOD_NEEDS = {
    "frame-problem": "problem-framing",
    "rebuild-from-fundamentals": "first-principles",
    "decompose-without-gaps": "MECE",
    "test-competing-explanations": "hypothesis-led",
    "identify-causal-mechanism": "causal-analysis",
    "understand-user-progress": "jobs-to-be-done",
    "model-feedback-and-interactions": "systems-thinking",
    "trace-downstream-effects": "second-order-effects",
    "compare-coherent-futures": "scenario-analysis",
    "test-key-variable-ranges": "sensitivity-analysis",
    "compare-probability-weighted-outcomes": "expected-value",
    "compare-foregone-alternatives": "opportunity-cost",
    "identify-binding-constraints": "constraint-analysis",
    "select-vital-few": "pareto-prioritization",
}

CHECK_NEEDS = {
    "challenge-leading-recommendation": "red-team",
    "anticipate-plan-failure": "pre-mortem",
    "separate-evidence-and-assumptions": "evidence-assumption-check",
    "resolve-material-conflicts": "contradiction-check",
    "calibrate-knowledge-claims": "epistemic-check",
}

METHOD_ORDER = [
    "problem-framing",
    "jobs-to-be-done",
    "first-principles",
    "MECE",
    "hypothesis-led",
    "causal-analysis",
    "constraint-analysis",
    "systems-thinking",
    "scenario-analysis",
    "expected-value",
    "sensitivity-analysis",
    "opportunity-cost",
    "second-order-effects",
    "pareto-prioritization",
]

CHECK_ORDER = [
    "evidence-assumption-check",
    "contradiction-check",
    "red-team",
    "pre-mortem",
    "epistemic-check",
]

LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}
COMPUTE = ["light", "standard", "high", "maximum"]


class CompositionError(ValueError):
    """Raised when a request cannot produce a valid bounded composition."""


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CompositionError(f"Expected JSON object: {path}")
    return data


def reference_data() -> tuple[dict[str, Any], dict[str, dict[str, Any]], set[str], dict[str, dict[str, Any]]]:
    contract = load_json(REFERENCES / "control-plane-contract.json")
    registry = load_json(REFERENCES / "cognitive-primitive-registry.json")
    lenses = load_json(REFERENCES / "domain-lens-registry.json")
    recipes = load_json(REFERENCES / "seed-recipes.json")
    primitive_by_id = {item["id"]: item for item in registry["primitives"]}
    lens_ids = {item["id"] for item in lenses["lenses"]}
    recipe_by_id = {item["id"]: item for item in recipes["recipes"]}
    return contract, primitive_by_id, lens_ids, recipe_by_id


def require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CompositionError(f"{key} must be a non-empty string")
    return value


def add_selection(
    target: dict[str, dict[str, Any]],
    item_id: str,
    why: str,
    uncertainty: str,
    selected_by: str,
) -> None:
    if not why.strip() or not uncertainty.strip():
        raise CompositionError(f"{item_id} requires why_selected and uncertainty_reduced")
    if item_id not in target:
        target[item_id] = {
            "id": item_id,
            "why_selected": why,
            "uncertainty_reduced": uncertainty,
            "selected_by": selected_by,
        }


def signal_level(signals: dict[str, Any], key: str) -> int:
    value = signals.get(key, "low")
    if value not in LEVELS:
        raise CompositionError(f"signals.{key} must be one of {sorted(LEVELS)}")
    return LEVELS[value]


def is_simple_request(request: dict[str, Any], signals: dict[str, Any]) -> bool:
    if request.get("task_class") not in {"retrieval", "transform"}:
        return False
    if request.get("cognitive_needs") or request.get("quality_needs"):
        return False
    if int(signals.get("materially_plausible_alternatives", 0)):
        return False
    if signals.get("evidence_gaps") or signals.get("conflicting_context") or signals.get("need_for_independent_challenge"):
        return False
    level_keys = [
        "ambiguity",
        "uncertainty",
        "decision_consequence",
        "expected_error_cost",
        "cross_domain_complexity",
        "context_complexity",
        "context_staleness",
        "validation_requirement",
    ]
    return all(signal_level(signals, key) == 0 for key in level_keys)


def select_compute(request: dict[str, Any], signals: dict[str, Any], contract: dict[str, Any], cognitive_count: int) -> tuple[str, list[str]]:
    risk = request["risk_tier"]
    minimum = contract["risk_requirements"][risk]["minimum_compute"]
    route_index = COMPUTE.index(minimum)
    reasons = [f"Risk tier {risk} sets minimum {minimum}."]

    high_keys = [
        "complexity",
        "uncertainty",
        "decision_consequence",
        "expected_error_cost",
        "context_complexity",
        "cross_domain_complexity",
        "validation_requirement",
    ]
    highest = max((signal_level(signals, key) for key in high_keys), default=0)
    if highest >= 3:
        route_index = max(route_index, 3)
        reasons.append("At least one compute signal is critical.")
    elif highest >= 2:
        route_index = max(route_index, 2)
        reasons.append("At least one compute signal is high.")
    elif (
        highest >= 1
        or cognitive_count >= 3
        or int(signals.get("materially_plausible_alternatives", 0)) >= 2
        or request["task_class"] in {"decision", "design", "incident"}
    ):
        route_index = max(route_index, 1)
        reasons.append("The task has a material trade-off or multi-primitive composition.")

    if cognitive_count >= 7:
        route_index = max(route_index, 2)
        reasons.append("Cross-method validation requires high compute.")

    requested = request.get("requested_compute_route")
    if requested is not None:
        if requested not in COMPUTE:
            raise CompositionError(f"requested_compute_route={requested!r} is invalid")
        if COMPUTE.index(requested) > route_index:
            route_index = COMPUTE.index(requested)
            reasons.append("The caller requested deeper compute without changing authority.")
    return COMPUTE[route_index], reasons


def apply_deviations(
    methods: dict[str, dict[str, Any]],
    lenses: dict[str, dict[str, Any]],
    checks: dict[str, dict[str, Any]],
    deviations: list[Any],
    primitive_by_id: dict[str, dict[str, Any]],
    lens_ids: set[str],
) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    categories = {
        "thinking_method": methods,
        "domain_lens": lenses,
        "quality_check": checks,
    }
    for index, deviation in enumerate(deviations):
        if not isinstance(deviation, dict):
            raise CompositionError(f"composition_deviations[{index}] must be an object")
        action = deviation.get("action")
        category = deviation.get("category")
        item_id = deviation.get("id")
        reason = deviation.get("reason")
        if action not in {"add", "remove"} or category not in categories:
            raise CompositionError(f"Invalid composition deviation at index {index}")
        if not isinstance(item_id, str) or not isinstance(reason, str) or not reason.strip():
            raise CompositionError(f"Deviation {index} requires id and reason")
        target = categories[category]
        if action == "remove":
            if item_id not in target:
                raise CompositionError(f"Deviation removes an unselected {category}: {item_id}")
            target.pop(item_id)
        else:
            if category == "domain_lens":
                if item_id not in lens_ids:
                    raise CompositionError(f"Unknown domain lens in deviation: {item_id}")
            elif item_id not in primitive_by_id or primitive_by_id[item_id]["category"] != category:
                raise CompositionError(f"Unknown {category} in deviation: {item_id}")
            if item_id in target:
                raise CompositionError(f"Deviation adds an already selected {category}: {item_id}")
            add_selection(
                target,
                item_id,
                reason,
                str(deviation.get("uncertainty_reduced", "The documented recipe mismatch is resolved.")),
                "justified_deviation",
            )
        applied.append({"action": action, "category": category, "id": item_id, "reason": reason})
    return applied


def ordered(items: dict[str, dict[str, Any]], order: list[str]) -> list[dict[str, Any]]:
    rank = {item_id: index for index, item_id in enumerate(order)}
    return sorted(items.values(), key=lambda item: (rank.get(item["id"], 999), item["id"]))


def build_graph(
    methods: list[dict[str, Any]],
    lenses: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    include_synthesis: bool,
    primitive_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = []
    previous: list[str] = []
    lens_ids = [item["id"] for item in lenses]
    for index, selection in enumerate(methods, start=1):
        item_id = selection["id"]
        node_id = f"method-{index}-{item_id}"
        graph.append({
            "node_id": node_id,
            "category": "thinking_method",
            "primitive_id": item_id,
            "purpose": primitive_by_id[item_id]["purpose"],
            "why_selected": selection["why_selected"],
            "applied_domain_lenses": lens_ids,
            "depends_on": previous[-1:],
        })
        previous = [node_id]
    for index, selection in enumerate(checks, start=1):
        item_id = selection["id"]
        node_id = f"check-{index}-{item_id}"
        graph.append({
            "node_id": node_id,
            "category": "quality_check",
            "primitive_id": item_id,
            "purpose": primitive_by_id[item_id]["purpose"],
            "why_selected": selection["why_selected"],
            "applied_domain_lenses": lens_ids,
            "depends_on": previous[-1:],
        })
        previous = [node_id]
    if include_synthesis:
        graph.append({
            "node_id": "synthesis",
            "category": "synthesis",
            "primitive_id": "synthesis",
            "purpose": primitive_by_id["synthesis"]["purpose"],
            "why_selected": "Material findings require decision-ready integration.",
            "applied_domain_lenses": lens_ids,
            "depends_on": previous[-1:],
        })
    return graph


def compose(request: dict[str, Any]) -> dict[str, Any]:
    contract, primitive_by_id, lens_ids, recipe_by_id = reference_data()
    if request.get("schema_version") != VERSION:
        raise CompositionError(f"schema_version must be {VERSION}")
    for key in ["task_id", "objective", "task_class", "decision_type", "risk_tier"]:
        require_string(request, key)
    if request["task_class"] not in contract["task_classes"]:
        raise CompositionError(f"Unknown task_class: {request['task_class']}")
    if request["decision_type"] not in contract["decision_types"]:
        raise CompositionError(f"Unknown decision_type: {request['decision_type']}")
    if request["risk_tier"] not in contract["risk_tiers"]:
        raise CompositionError(f"Unknown risk_tier: {request['risk_tier']}")

    signals = request.get("signals", {})
    if not isinstance(signals, dict):
        raise CompositionError("signals must be an object")
    signals = {
        "ambiguity": "low",
        "uncertainty": "low",
        "evidence_gaps": False,
        "decision_consequence": "low",
        "expected_error_cost": "low",
        "reversibility": "high",
        "cross_domain_complexity": "low",
        "context_complexity": "low",
        "context_staleness": "low",
        "conflicting_context": False,
        "need_for_independent_challenge": False,
        "materially_plausible_alternatives": 0,
        "complexity": "low",
        "validation_requirement": "low",
        **signals,
    }
    for key in [
        "ambiguity", "uncertainty", "decision_consequence", "expected_error_cost",
        "cross_domain_complexity", "context_complexity", "context_staleness",
        "complexity", "validation_requirement",
    ]:
        signal_level(signals, key)
    if signals["reversibility"] not in {"low", "medium", "high"}:
        raise CompositionError("signals.reversibility must be low, medium, or high")
    alternatives = signals["materially_plausible_alternatives"]
    if not isinstance(alternatives, int) or alternatives < 0:
        raise CompositionError("signals.materially_plausible_alternatives must be a non-negative integer")

    simple = is_simple_request(request, signals)
    methods: dict[str, dict[str, Any]] = {}
    lenses: dict[str, dict[str, Any]] = {}
    checks: dict[str, dict[str, Any]] = {}

    recipe_id = request.get("seed_recipe")
    recipe = None
    if recipe_id is not None:
        if recipe_id not in recipe_by_id:
            raise CompositionError(f"Unknown seed recipe: {recipe_id}")
        recipe = recipe_by_id[recipe_id]
    if recipe and request.get("apply_seed_prior", False) and not simple:
        prior_why = f"Optional {recipe_id} prior matches the diagnosed task structure."
        for item_id in recipe.get("thinking_methods", []):
            add_selection(methods, item_id, prior_why, f"Recipe candidate {item_id} requires task-specific verification.", "seed_prior")
        for item_id in recipe.get("domain_lenses", []):
            add_selection(lenses, item_id, prior_why, f"The {item_id} domain constraints may change the decision.", "seed_prior")
        for item_id in recipe.get("quality_checks", []):
            add_selection(checks, item_id, prior_why, f"The prior identifies a material {item_id} failure mode.", "seed_prior")

    for index, need in enumerate(request.get("cognitive_needs", [])):
        if not isinstance(need, dict) or need.get("need") not in METHOD_NEEDS:
            raise CompositionError(f"Unknown cognitive need at index {index}")
        item_id = METHOD_NEEDS[need["need"]]
        add_selection(
            methods,
            item_id,
            require_string(need, "why_selected"),
            require_string(need, "uncertainty_reduced"),
            "cognitive_need_diagnosis",
        )

    for index, need in enumerate(request.get("domain_needs", [])):
        if not isinstance(need, dict) or need.get("id") not in lens_ids:
            raise CompositionError(f"Unknown domain need at index {index}")
        add_selection(
            lenses,
            need["id"],
            require_string(need, "why_selected"),
            require_string(need, "uncertainty_reduced"),
            "domain_need_diagnosis",
        )

    for index, need in enumerate(request.get("quality_needs", [])):
        if not isinstance(need, dict) or need.get("need") not in CHECK_NEEDS:
            raise CompositionError(f"Unknown quality need at index {index}")
        item_id = CHECK_NEEDS[need["need"]]
        add_selection(
            checks,
            item_id,
            require_string(need, "why_selected"),
            require_string(need, "uncertainty_reduced"),
            "quality_need_diagnosis",
        )

    if not simple:
        if signal_level(signals, "ambiguity") >= 2:
            add_selection(methods, "problem-framing", "High ambiguity requires an explicit decision boundary.", "Ambiguity about the actual decision.", "task_signal")
        if signals["evidence_gaps"] or signal_level(signals, "context_staleness") >= 1:
            add_selection(checks, "evidence-assumption-check", "Evidence is incomplete or may be stale.", "Which material claims are supported versus assumed.", "task_signal")
        if signals["conflicting_context"]:
            add_selection(checks, "contradiction-check", "Material context conflicts before synthesis.", "Which evidence can be reconciled and which remains conflicting.", "task_signal")
        if signals["need_for_independent_challenge"]:
            add_selection(checks, "red-team", "The task explicitly requires independent challenge.", "Whether the leading recommendation survives the strongest countercase.", "task_signal")
        if signal_level(signals, "uncertainty") >= 2:
            add_selection(checks, "epistemic-check", "Uncertainty is high enough to risk pseudo-certainty.", "How strongly the available evidence supports the conclusion.", "task_signal")
        if signals["reversibility"] == "low" and signal_level(signals, "decision_consequence") >= 2:
            add_selection(checks, "pre-mortem", "A consequential commitment is hard to reverse.", "Plausible failure paths and early warning signs.", "task_signal")

    risk_requirements = contract["risk_requirements"][request["risk_tier"]]
    for item_id in risk_requirements["required_quality_checks"]:
        add_selection(
            checks,
            item_id,
            f"Risk tier {request['risk_tier']} requires this check.",
            f"Consequential decision risk addressed by {item_id}.",
            "risk_requirement",
        )

    deviations = request.get("composition_deviations", [])
    if not isinstance(deviations, list):
        raise CompositionError("composition_deviations must be an array")
    applied_deviations = apply_deviations(methods, lenses, checks, deviations, primitive_by_id, lens_ids)

    missing_required_checks = set(risk_requirements["required_quality_checks"]) - set(checks)
    if missing_required_checks:
        raise CompositionError(f"A deviation removed required risk checks: {sorted(missing_required_checks)}")

    include_synthesis = not simple and bool(methods or checks) and request.get("include_synthesis", True)
    cognitive_count = len(methods) + len(checks) + int(include_synthesis)
    if "primitive_budget" not in request:
        raise CompositionError("primitive_budget is required to enforce minimal composition")
    budget = request.get("primitive_budget")
    if not isinstance(budget, int) or budget < 0:
        raise CompositionError("primitive_budget must be a non-negative integer")
    if cognitive_count > budget:
        raise CompositionError(f"Composition selects {cognitive_count} primitives but budget is {budget}")
    if simple and cognitive_count > contract["anti_bureaucracy"]["simple_task_max_cognitive_primitives"]:
        raise CompositionError("Simple task is over-composed")

    methods_list = ordered(methods, METHOD_ORDER)
    checks_list = ordered(checks, CHECK_ORDER)
    lenses_list = sorted(lenses.values(), key=lambda item: item["id"])
    synthesis_steps = []
    if include_synthesis:
        synthesis_steps = [{
            "id": "synthesis",
            "why_selected": "Material reasoning must become a decision-ready output.",
            "uncertainty_reduced": "How material findings and unresolved uncertainty affect the conclusion.",
            "selected_by": "finalization_requirement",
        }]

    compute_route, compute_reasons = select_compute(request, signals, contract, cognitive_count)
    graph = build_graph(methods_list, lenses_list, checks_list, include_synthesis, primitive_by_id)

    authority_plan = request.get("authority_plan")
    if authority_plan is None:
        human_required = risk_requirements["human_decision_required"] or request["decision_type"] != "none"
        authority_plan = {
            "current_gate": "recommendation",
            "human_decision_required": human_required,
            "state_write": "propose_only",
            "external_action": "none",
            "system_write": "none",
            "next_gate": "human_decision" if human_required else "recommendation",
        }

    output_mode = request.get("output_mode")
    if output_mode is None:
        if request["risk_tier"] in {"high", "critical"}:
            output_mode = "full-traceability"
        elif request["decision_type"] != "none":
            output_mode = "decision-packet"
        else:
            output_mode = "executive-compact"

    selected = {
        "thinking_methods": methods_list,
        "domain_lenses": lenses_list,
        "quality_checks": checks_list,
        "synthesis_steps": synthesis_steps,
        "primitive_count": cognitive_count,
        "primitive_budget": budget,
        "complex_graph_required": not simple,
    }
    observation = {
        "selected_composition": {
            "thinking_methods": [item["id"] for item in methods_list],
            "domain_lenses": [item["id"] for item in lenses_list],
            "quality_checks": [item["id"] for item in checks_list],
            "synthesis_steps": [item["id"] for item in synthesis_steps],
        },
        "selected_methods": [item["id"] for item in methods_list],
        "selected_domain_lenses": [item["id"] for item in lenses_list],
        "selected_checks": [item["id"] for item in checks_list],
        "composition_deviations": applied_deviations,
        "human_override": None,
        "recommendation_accepted_or_rejected": None,
        "missed_escalation": None,
        "unnecessary_escalation": None,
        "composition_failure_note": None,
        "downstream_rework_if_known": None,
    }
    return {
        "schema_version": VERSION,
        "task_id": request["task_id"],
        "objective": request["objective"],
        "task_class": request["task_class"],
        "decision_type": request["decision_type"],
        "risk_tier": request["risk_tier"],
        "composition_signals": signals,
        "context_sources": request.get("context_sources", []),
        "cognitive_needs": request.get("cognitive_needs", []),
        "domain_needs": request.get("domain_needs", []),
        "quality_needs": request.get("quality_needs", []),
        "seed_recipe": recipe_id,
        "selected_composition": selected,
        "composition_deviations": applied_deviations,
        "cognition_graph": graph,
        "compute_route": compute_route,
        "compute_rationale": compute_reasons,
        "epistemic_register": request.get("epistemic_register", []),
        "uncertainty_register": request.get("uncertainty_register", []),
        "authority_plan": authority_plan,
        "optional_persona_presets": request.get("optional_persona_presets", []),
        "output_mode": output_mode,
        "composition_observability": observation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path, help="V3.1 composition request JSON")
    parser.add_argument("--output", type=Path, help="Optional output task-packet path")
    args = parser.parse_args()
    try:
        request = load_json(args.request)
        result = compose(request)
    except (OSError, json.JSONDecodeError, CompositionError) as exc:
        print(f"ERROR ERR_COMPOSITION: {exc}")
        return 1
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
