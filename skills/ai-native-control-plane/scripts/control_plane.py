#!/usr/bin/env python3
"""Run the AI-Native Control Plane V4 context and memory lifecycle.

The CLI is deliberately model- and storage-provider-independent. ``prepare``
builds a context-gated task packet, ``distill`` converts verified task outcomes
into a memory-change proposal, and ``apply`` sends an authorized proposal to
the local Git-backed reference adapter. No command commits or pushes Git.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _composition_v31 import CompositionError as V31CompositionError
from _composition_v31 import compose as compose_v31
from memory_adapter import GitMemoryAdapter, MemoryAdapterError


VERSION = "4.0.0"
V31_VERSION = "3.1.0"
CONTEXT_STATUSES = {
    "available",
    "missing",
    "inaccessible",
    "stale",
    "conflicting",
    "untrusted",
    "permission_denied",
}
UNUSABLE_CONTEXT_STATUSES = CONTEXT_STATUSES - {"available"}
MEMORY_CLASSES = {"context", "decision_log", "backlog", "working_memory"}
DURABLE_CONTEXT_CLASSES = {"verified_fact", "user_confirmed", "primary_source", "secondary_source"}


class LifecycleError(ValueError):
    """Raised when a lifecycle artifact cannot be prepared safely."""


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LifecycleError(f"Expected JSON object: {path}")
    return data


def _require_string(data: dict[str, Any], key: str, label: str | None = None) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LifecycleError(f"{label or key} must be a non-empty string")
    return value


def _legacy_context_plan(request: dict[str, Any]) -> dict[str, Any]:
    sources = request.get("context_sources", [])
    requirements = []
    for index, source in enumerate(sources, start=1):
        source_id = str(source.get("source_id", f"SRC-LEGACY-{index:03d}"))
        requirements.append({
            "requirement_id": f"CTX-LEGACY-{index:03d}",
            "description": f"Use compatible context source {source_id}.",
            "priority": "required",
            "why_needed": str(source.get("relevance_to_decision", "Required by the compatible V3.1 request.")),
            "preferred_source_ids": [source_id],
            "accepted_statuses": [str(source.get("status", "available"))],
            "freshness_requirement": "Use the source freshness declared by the compatible request.",
            "blocking_if_unsatisfied": True,
            "legacy_status_accepted": True,
            "question": f"What current, decision-relevant information should replace unavailable source {source_id}?",
            "answer_needed": f"A current replacement for {source_id}.",
            "owner": "human_decision_owner",
        })
    total_chars = sum(len(str(source.get("summary", ""))) for source in sources)
    return {
        "requirements": requirements,
        "budget": {
            "max_items": max(len(sources), 1),
            "max_characters": max(total_chars + 1024, 4096),
        },
    }


def normalize_request(request: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize a V4 or compatible V3.1 request without writing state."""

    if not isinstance(request, dict):
        raise LifecycleError("request must be an object")
    version = request.get("schema_version")
    normalized = copy.deepcopy(request)
    warnings: list[str] = []
    if version == V31_VERSION:
        normalized["schema_version"] = VERSION
        normalized["context_plan"] = _legacy_context_plan(normalized)
        normalized.setdefault("worker_requirements", {})
        warnings.append("WARN_LEGACY_REQUEST: V3.1 request normalized to V4 without writing state.")
    elif version != VERSION:
        raise LifecycleError(f"schema_version must be {VERSION} or compatible {V31_VERSION}")
    else:
        requirements = normalized.get("context_plan", {}).get("requirements", [])
        if isinstance(requirements, list):
            for requirement in requirements:
                if isinstance(requirement, dict):
                    requirement.pop("legacy_status_accepted", None)
    for key in ["task_id", "objective", "task_class", "decision_type", "risk_tier"]:
        _require_string(normalized, key)
    if not isinstance(normalized.get("context_sources"), list):
        raise LifecycleError("context_sources must be an array")
    if not isinstance(normalized.get("context_plan"), dict):
        raise LifecycleError("context_plan must be an object")
    return normalized, warnings


def _source_usable(source: dict[str, Any], requirement: dict[str, Any]) -> tuple[bool, str]:
    status = source.get("status")
    if status not in CONTEXT_STATUSES:
        return False, "invalid_status"
    if status in UNUSABLE_CONTEXT_STATUSES and requirement.get("legacy_status_accepted") is not True:
        return False, str(status)
    if source.get("decision_change_potential") is not True:
        return False, "not_decision_relevant"
    if source.get("permitted_use") in {None, "", "none", "prohibited"}:
        return False, "permission_denied"
    if source.get("freshness") in {"stale", "expired"} and requirement.get("legacy_status_accepted") is not True:
        return False, "stale"
    accepted = requirement.get("accepted_statuses")
    if not isinstance(accepted, list) or not accepted:
        raise LifecycleError(f"{requirement.get('requirement_id')} requires accepted_statuses")
    if status not in accepted:
        return False, str(status)
    return True, "selected"


def compile_context(request: dict[str, Any]) -> dict[str, Any]:
    """Compile the smallest declared context set and emit a readiness gate."""

    plan = request["context_plan"]
    requirements = plan.get("requirements")
    budget = plan.get("budget")
    if not isinstance(requirements, list):
        raise LifecycleError("context_plan.requirements must be an array")
    if not isinstance(budget, dict):
        raise LifecycleError("context_plan.budget must be an object")
    max_items = budget.get("max_items")
    max_characters = budget.get("max_characters")
    if not isinstance(max_items, int) or max_items < 1:
        raise LifecycleError("context_plan.budget.max_items must be a positive integer")
    if not isinstance(max_characters, int) or max_characters < 1:
        raise LifecycleError("context_plan.budget.max_characters must be a positive integer")

    sources = request.get("context_sources", [])
    source_by_id: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise LifecycleError(f"context_sources[{index}] must be an object")
        source_id = _require_string(source, "source_id", f"context_sources[{index}].source_id")
        if source_id in source_by_id:
            raise LifecycleError(f"duplicate context source: {source_id}")
        source_by_id[source_id] = source

    ordered_requirements = sorted(
        requirements,
        key=lambda item: (0 if isinstance(item, dict) and item.get("priority") == "required" else 1),
    )
    included: list[dict[str, Any]] = []
    included_ids: set[str] = set()
    selected_for: dict[str, list[str]] = {}
    exclusion_reasons: dict[str, str] = {}
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    total_characters = 0

    for index, requirement in enumerate(ordered_requirements):
        if not isinstance(requirement, dict):
            raise LifecycleError(f"context_plan.requirements[{index}] must be an object")
        requirement_id = _require_string(requirement, "requirement_id")
        priority = requirement.get("priority")
        if priority not in {"required", "optional"}:
            raise LifecycleError(f"{requirement_id}.priority must be required or optional")
        preferred = requirement.get("preferred_source_ids")
        if not isinstance(preferred, list) or not preferred or not all(isinstance(item, str) and item for item in preferred):
            raise LifecycleError(f"{requirement_id}.preferred_source_ids must be a non-empty string array")
        if priority == "required" and requirement.get("blocking_if_unsatisfied") is not True:
            raise LifecycleError(f"{requirement_id} is required and must block when unsatisfied")

        satisfied = False
        reasons: list[str] = []
        for source_id in preferred:
            source = source_by_id.get(source_id)
            if source is None:
                reasons.append(f"{source_id}:missing")
                exclusion_reasons.setdefault(source_id, "missing")
                continue
            usable, reason = _source_usable(source, requirement)
            if not usable:
                reasons.append(f"{source_id}:{reason}")
                exclusion_reasons[source_id] = reason
                continue
            if source_id in included_ids:
                selected_for.setdefault(source_id, []).append(requirement_id)
                satisfied = True
                break
            source_size = len(str(source.get("summary", "")))
            if len(included) >= max_items or total_characters + source_size > max_characters:
                reasons.append(f"{source_id}:context_budget_exceeded")
                exclusion_reasons[source_id] = "context_budget_exceeded"
                continue
            included.append(copy.deepcopy(source))
            included_ids.add(source_id)
            selected_for[source_id] = [requirement_id]
            total_characters += source_size
            satisfied = True
            break

        if not satisfied:
            gap = {
                "requirement_id": requirement_id,
                "why_it_blocks": _require_string(requirement, "why_needed"),
                "answer_needed": _require_string(requirement, "answer_needed"),
                "owner": _require_string(requirement, "owner"),
                "question": _require_string(requirement, "question"),
                "observed_reasons": reasons or ["no_usable_source"],
            }
            if priority == "required":
                blockers.append(gap)
            else:
                warnings.append(gap)

    excluded: list[dict[str, str]] = []
    for source_id in source_by_id:
        if source_id not in included_ids:
            excluded.append({
                "source_id": source_id,
                "reason": exclusion_reasons.get(source_id, "not_selected_by_context_plan"),
            })

    gate_status = "blocked" if blockers else "ready"
    return {
        "compiled_context": {
            "items": included,
            "source_refs": [item["source_id"] for item in included],
            "selected_for": selected_for,
            "excluded_sources": excluded,
            "budget": {"max_items": max_items, "max_characters": max_characters},
            "used_items": len(included),
            "used_characters": total_characters,
        },
        "context_gate": {
            "status": gate_status,
            "blockers": blockers,
            "warnings": warnings,
        },
        "clarification_questions": [
            {
                "requirement_id": item["requirement_id"],
                "question": item["question"],
                "answer_needed": item["answer_needed"],
                "owner": item["owner"],
                "why_it_blocks": item["why_it_blocks"],
            }
            for item in blockers
        ],
    }


def _legacy_composition_request(request: dict[str, Any]) -> dict[str, Any]:
    compatible = copy.deepcopy(request)
    compatible["schema_version"] = V31_VERSION
    for key in ["context_plan", "worker_requirements"]:
        compatible.pop(key, None)
    return compatible


def _empty_composition(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "thinking_methods": [],
        "domain_lenses": [],
        "quality_checks": [],
        "synthesis_steps": [],
        "primitive_count": 0,
        "primitive_budget": request.get("primitive_budget", 0),
        "complex_graph_required": False,
    }


def _default_capabilities(task_class: str) -> list[str]:
    if task_class in {"retrieval", "research"}:
        return ["information_retrieval", "evidence_synthesis"]
    if task_class in {"implementation", "operation", "incident"}:
        return ["bounded_execution", "verification"]
    if task_class in {"decision", "design", "diagnosis", "review"}:
        return ["reasoning", "evidence_synthesis"]
    return ["bounded_task_completion"]


def _build_worker_plan(request: dict[str, Any], task: dict[str, Any], context_refs: list[str]) -> dict[str, Any]:
    requirements = request.get("worker_requirements") or {}
    if not isinstance(requirements, dict):
        raise LifecycleError("worker_requirements must be an object")
    capabilities = requirements.get("required_capabilities", _default_capabilities(request["task_class"]))
    tools = requirements.get("allowed_tools", [])
    prohibited = requirements.get(
        "prohibited_actions",
        ["implicit_state_write", "external_action_without_authorization", "authority_expansion"],
    )
    if not isinstance(capabilities, list) or not capabilities or not all(isinstance(item, str) and item for item in capabilities):
        raise LifecycleError("worker_requirements.required_capabilities must be a non-empty string array")
    if not isinstance(tools, list) or not all(isinstance(item, str) and item for item in tools):
        raise LifecycleError("worker_requirements.allowed_tools must be a string array")
    if not isinstance(prohibited, list) or not prohibited:
        raise LifecycleError("worker_requirements.prohibited_actions must be a non-empty array")
    return {
        "selection_basis": "capability_contract",
        "required_capabilities": capabilities,
        "allowed_tools": tools,
        "compute_route": task["compute_route"],
        "context_refs": context_refs,
        "output_contract": requirements.get("output_contract", {
            "mode": task["output_mode"],
            "required_sections": ["result", "evidence", "uncertainty", "next_gate"],
        }),
        "authority_ceiling": task["authority_plan"]["current_gate"],
        "prohibited_actions": prohibited,
    }


def prepare_task(request: dict[str, Any]) -> dict[str, Any]:
    """Prepare a context-gated V4 task packet."""

    normalized, compatibility_warnings = normalize_request(request)
    context = compile_context(normalized)
    base = {
        "schema_version": VERSION,
        "task_id": normalized["task_id"],
        "objective": normalized["objective"],
        "task_class": normalized["task_class"],
        "decision_type": normalized["decision_type"],
        "risk_tier": normalized["risk_tier"],
        "context_plan": copy.deepcopy(normalized["context_plan"]),
        "context_sources": copy.deepcopy(normalized.get("context_sources", [])),
        **context,
        "compatibility_warnings": compatibility_warnings,
        "memory_update_status": "not_started",
    }
    if context["context_gate"]["status"] == "blocked":
        return {
            **base,
            "lifecycle_status": "blocked_context",
            "composition_signals": copy.deepcopy(normalized.get("signals", {})),
            "cognitive_needs": copy.deepcopy(normalized.get("cognitive_needs", [])),
            "domain_needs": copy.deepcopy(normalized.get("domain_needs", [])),
            "quality_needs": copy.deepcopy(normalized.get("quality_needs", [])),
            "seed_recipe": normalized.get("seed_recipe"),
            "selected_composition": _empty_composition(normalized),
            "composition_deviations": [],
            "cognition_graph": [],
            "compute_route": None,
            "compute_rationale": [],
            "epistemic_register": copy.deepcopy(normalized.get("epistemic_register", [])),
            "uncertainty_register": copy.deepcopy(normalized.get("uncertainty_register", [])),
            "authority_plan": {
                "current_gate": "research",
                "human_decision_required": True,
                "state_write": "propose_only",
                "external_action": "none",
                "system_write": "none",
                "next_gate": "context_resolution",
            },
            "optional_persona_presets": copy.deepcopy(normalized.get("optional_persona_presets", [])),
            "output_mode": "working-note",
            "composition_observability": {
                "selected_composition": {"thinking_methods": [], "domain_lenses": [], "quality_checks": [], "synthesis_steps": []},
                "selected_methods": [],
                "selected_domain_lenses": [],
                "selected_checks": [],
                "composition_deviations": [],
                "human_override": None,
                "recommendation_accepted_or_rejected": None,
                "missed_escalation": None,
                "unnecessary_escalation": None,
                "composition_failure_note": "Required context is unresolved.",
                "downstream_rework_if_known": None,
            },
            "worker_plan": None,
        }
    try:
        task = compose_v31(_legacy_composition_request(normalized))
    except V31CompositionError as exc:
        raise LifecycleError(str(exc)) from exc
    task["schema_version"] = VERSION
    task.update(base)
    task["lifecycle_status"] = "ready_for_worker"
    task["worker_plan"] = _build_worker_plan(normalized, task, context["compiled_context"]["source_refs"])
    return task


def _rejected(candidate: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    return {"candidate_id": candidate.get("candidate_id"), "code": code, "reason": reason}


def _validate_candidate(
    candidate: dict[str, Any],
    durable_promotion_allowed: bool,
    verified_evidence_refs: set[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        candidate_id = _require_string(candidate, "candidate_id")
        target = _require_string(candidate, "target_memory_class")
        epistemic = _require_string(candidate, "epistemic_class")
        content = _require_string(candidate, "content")
        rationale = _require_string(candidate, "rationale")
        record_id = _require_string(candidate, "record_id")
    except LifecycleError as exc:
        return None, _rejected(candidate, "ERR_CANDIDATE_REQUIRED_FIELD", str(exc))
    if target not in MEMORY_CLASSES:
        return None, _rejected(candidate, "ERR_MEMORY_CLASS", target)
    source_refs = candidate.get("source_refs")
    if not isinstance(source_refs, list) or not all(isinstance(item, str) and item for item in source_refs):
        return None, _rejected(candidate, "ERR_PROVENANCE_REQUIRED", "source_refs must be a string array")
    unknown_refs = sorted(set(source_refs) - verified_evidence_refs)
    if unknown_refs:
        return None, _rejected(
            candidate,
            "ERR_UNVERIFIED_PROVENANCE",
            f"source_refs were not verified by the execution outcome: {', '.join(unknown_refs)}",
        )
    if target in {"context", "decision_log"} and not durable_promotion_allowed:
        return None, _rejected(candidate, "ERR_VERIFICATION_REQUIRED", "durable promotion requires passed verification")
    if target == "context" and (epistemic not in DURABLE_CONTEXT_CLASSES or not source_refs):
        return None, _rejected(candidate, "ERR_CONTEXT_PROMOTION", "durable context requires supported evidence and provenance")
    if target == "decision_log":
        acceptance = candidate.get("human_acceptance")
        if epistemic != "user_confirmed" or not isinstance(acceptance, dict):
            return None, _rejected(candidate, "ERR_DECISION_ACCEPTANCE_REQUIRED", "decision log requires explicit human acceptance")
        for key in ["accepted_by", "accepted_at", "evidence_reference"]:
            if not isinstance(acceptance.get(key), str) or not acceptance[key].strip():
                return None, _rejected(candidate, "ERR_DECISION_ACCEPTANCE_REQUIRED", f"human_acceptance.{key} is required")
        try:
            accepted_at = datetime.fromisoformat(acceptance["accepted_at"].replace("Z", "+00:00"))
        except ValueError:
            return None, _rejected(candidate, "ERR_DECISION_ACCEPTANCE_REQUIRED", "human_acceptance.accepted_at must be ISO-8601")
        if accepted_at.tzinfo is None:
            return None, _rejected(candidate, "ERR_DECISION_ACCEPTANCE_REQUIRED", "human_acceptance.accepted_at must include a timezone")
    if target == "backlog":
        for key in ["owner", "status", "next_gate"]:
            if not isinstance(candidate.get(key), str) or not candidate[key].strip():
                return None, _rejected(candidate, "ERR_BACKLOG_CONTRACT", f"{key} is required")
        if candidate["status"] not in {"open", "deferred", "blocked"}:
            return None, _rejected(candidate, "ERR_BACKLOG_CONTRACT", "status must be open, deferred, or blocked")
    if target == "working_memory":
        expires_at = candidate.get("expires_at")
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError:
            return None, _rejected(candidate, "ERR_WORKING_MEMORY_TTL", "expires_at must be ISO-8601")
        if expiry.tzinfo is None:
            return None, _rejected(candidate, "ERR_WORKING_MEMORY_TTL", "expires_at must include a timezone")
        if expiry <= datetime.now(timezone.utc):
            return None, _rejected(candidate, "ERR_WORKING_MEMORY_TTL", "expires_at must be in the future")
        if candidate.get("promotion_authorized") is not False:
            return None, _rejected(candidate, "ERR_WORKING_MEMORY_PROMOTION", "working memory cannot auto-promote")
    operation = candidate.get("operation", "add")
    if operation not in {"add", "update", "supersede"}:
        return None, _rejected(candidate, "ERR_MEMORY_OPERATION", str(operation))
    change = {
        "change_id": candidate_id,
        "operation": operation,
        "record_id": record_id,
        "target_memory_class": target,
        "record": {
            "record_id": record_id,
            "memory_class": target,
            "epistemic_class": epistemic,
            "content": content,
            "source_refs": source_refs,
            "rationale": rationale,
        },
    }
    for key in ["human_acceptance", "owner", "status", "next_gate", "expires_at", "promotion_authorized"]:
        if key in candidate:
            change["record"][key] = copy.deepcopy(candidate[key])
    return change, None


def distill_outcome(task: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    """Normalize verified learning candidates into a write-gated proposal."""

    if task.get("schema_version") != VERSION:
        raise LifecycleError("distillation requires a V4 task packet")
    if task.get("lifecycle_status") == "blocked_context":
        raise LifecycleError("blocked tasks cannot be distilled")
    if outcome.get("schema_version") != VERSION:
        raise LifecycleError("execution outcome must use schema_version 4.0.0")
    if outcome.get("task_id") != task.get("task_id"):
        raise LifecycleError("task_id mismatch between task and outcome")
    if outcome.get("completion_status") not in {"completed", "partial", "blocked", "failed"}:
        raise LifecycleError("completion_status is invalid")
    verification = outcome.get("verification")
    if not isinstance(verification, dict) or verification.get("status") not in {"passed", "partial", "failed"}:
        raise LifecycleError("verification.status must be passed, partial, or failed")
    evidence_refs = verification.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not all(isinstance(item, str) and item for item in evidence_refs):
        raise LifecycleError("verification.evidence_refs must be a string array")
    verified_evidence_refs = set(evidence_refs)
    durable_promotion_allowed = verification["status"] == "passed"
    proposal_id = _require_string(outcome, "memory_proposal_id")
    base_revision = _require_string(outcome, "base_revision")
    candidates = outcome.get("learning_candidates")
    if not isinstance(candidates, list):
        raise LifecycleError("learning_candidates must be an array")
    changes: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            rejected.append({"candidate_id": None, "code": "ERR_CANDIDATE_OBJECT", "reason": "candidate must be an object"})
            continue
        candidate_id = candidate.get("candidate_id")
        if isinstance(candidate_id, str) and candidate_id in seen:
            rejected.append(_rejected(candidate, "ERR_DUPLICATE_CHANGE_ID", candidate_id))
            continue
        if isinstance(candidate_id, str):
            seen.add(candidate_id)
        change, rejection = _validate_candidate(candidate, durable_promotion_allowed, verified_evidence_refs)
        if change is not None:
            changes.append(change)
        if rejection is not None:
            rejected.append(rejection)
    return {
        "schema_version": VERSION,
        "proposal_id": proposal_id,
        "task_id": task["task_id"],
        "base_revision": base_revision,
        "verified_evidence_refs": sorted(verified_evidence_refs),
        "write_status": "proposed",
        "write_authorization_required": True,
        "write_authorization": "not_authorized",
        "changes": changes,
        "rejected_candidates": rejected,
        "routing_policy_changed_automatically": False,
    }


def normalize_project_state(state: dict[str, Any]) -> dict[str, Any]:
    """Normalize V3/V3.1 state into a V4, non-written migration proposal."""

    if not isinstance(state, dict):
        raise LifecycleError("state must be an object")
    version = state.get("schema_version")
    if version == VERSION:
        normalized = copy.deepcopy(state)
        normalized.setdefault("migration", {
            "source_schema_version": VERSION,
            "write_performed": False,
            "warnings": [],
        })
        return normalized
    if version not in {"3.0.0", V31_VERSION}:
        raise LifecycleError("state schema_version must be 3.0.0, 3.1.0, or 4.0.0")
    project_id = _require_string(state, "project_id")
    state_version = _require_string(state, "state_version")
    context_records: list[dict[str, Any]] = []
    for index, evidence in enumerate(state.get("evidence_register", []), start=1):
        if not isinstance(evidence, dict):
            continue
        source_id = str(evidence.get("source_id", f"LEGACY-SOURCE-{index:03d}"))
        context_records.append({
            "record_id": source_id,
            "memory_class": "context",
            "epistemic_class": str(evidence.get("class", "unknown")),
            "content": str(evidence.get("summary", "Legacy evidence record.")),
            "source_refs": [source_id],
            "migration_status": "proposed_not_written",
        })
    decision_records: list[dict[str, Any]] = []
    backlog_records: list[dict[str, Any]] = []
    for index, decision in enumerate(state.get("accepted_decisions", []), start=1):
        if not isinstance(decision, dict):
            continue
        record_id = str(decision.get("decision_id", f"LEGACY-DECISION-{index:03d}"))
        acceptance = decision.get("human_acceptance")
        if isinstance(acceptance, dict) and acceptance.get("accepted_by") and acceptance.get("evidence_reference"):
            decision_records.append({
                **copy.deepcopy(decision),
                "record_id": record_id,
                "memory_class": "decision_log",
                "migration_status": "proposed_not_written",
            })
        else:
            backlog_records.append({
                "record_id": f"REVIEW-{record_id}",
                "memory_class": "backlog",
                "content": f"Confirm acceptance evidence for legacy decision {record_id}.",
                "owner": "human_decision_owner",
                "status": "blocked",
                "next_gate": "human_decision",
                "migration_status": "proposed_not_written",
            })
    for index, question in enumerate(state.get("open_questions", []), start=1):
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("question_id", f"LEGACY-QUESTION-{index:03d}"))
        backlog_records.append({
            "record_id": question_id,
            "memory_class": "backlog",
            "content": str(question.get("question", "Legacy open question.")),
            "owner": str(question.get("owner", "human_decision_owner")),
            "status": "open",
            "next_gate": "research",
            "migration_status": "proposed_not_written",
        })
    return {
        "schema_version": VERSION,
        "project_id": project_id,
        "state_version": state_version,
        "corporate_memory": {
            "context": context_records,
            "decision_log": decision_records,
            "backlog": backlog_records,
        },
        "working_memory": {
            "storage": ".control-plane/working",
            "default_ttl_hours": 72,
            "auto_promotion": False,
        },
        "governance": {
            "risk_register": copy.deepcopy(state.get("risk_register", [])),
            "authority_grants": copy.deepcopy(state.get("authority_grants", [])),
            "learning_events": copy.deepcopy(state.get("learning_events", [])),
            "composition_observations": copy.deepcopy(state.get("composition_observations", [])),
            "routing_policy_version": str(state.get("routing_policy_version", version)),
            "routing_policy_auto_update": False,
            "latest_task_ids": copy.deepcopy(state.get("latest_task_ids", [])),
        },
        "state_write_authorization": "not_authorized",
        "migration": {
            "source_schema_version": version,
            "write_performed": False,
            "warnings": ["Legacy records were normalized as proposals; no state was written."],
        },
    }


def _write_result(data: dict[str, Any], path: Path | None) -> None:
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path:
        path.write_text(serialized, encoding="utf-8")
    else:
        sys.stdout.write(serialized)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Compile context and prepare a V4 task packet")
    prepare.add_argument("--request", required=True, type=Path)
    prepare.add_argument("--output", type=Path)

    distill = subparsers.add_parser("distill", help="Create a write-gated memory proposal")
    distill.add_argument("--task", required=True, type=Path)
    distill.add_argument("--outcome", required=True, type=Path)
    distill.add_argument("--output", type=Path)

    apply_parser = subparsers.add_parser("apply", help="Apply an authorized proposal to a local Git-backed store")
    apply_parser.add_argument("--proposal", required=True, type=Path)
    apply_parser.add_argument("--authorization", required=True, type=Path)
    apply_parser.add_argument("--memory-root", required=True, type=Path)
    apply_parser.add_argument("--expected-revision")
    apply_parser.add_argument("--output", type=Path)

    migrate = subparsers.add_parser("migrate-state", help="Normalize V3/V3.1 state without writing it")
    migrate.add_argument("--state", required=True, type=Path)
    migrate.add_argument("--output", type=Path)

    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare_task(load_json(args.request))
        elif args.command == "distill":
            result = distill_outcome(load_json(args.task), load_json(args.outcome))
        elif args.command == "apply":
            proposal = load_json(args.proposal)
            authorization = load_json(args.authorization)
            expected = args.expected_revision or str(proposal.get("base_revision", ""))
            result = GitMemoryAdapter(args.memory_root).apply(proposal, authorization, expected)
        else:
            result = normalize_project_state(load_json(args.state))
        _write_result(result, args.output)
        return 0
    except (OSError, json.JSONDecodeError, LifecycleError, MemoryAdapterError) as exc:
        print(f"ERROR ERR_{args.command.upper()}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
