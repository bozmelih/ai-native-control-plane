from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/ai-native-control-plane"
SCRIPTS = SKILL / "scripts"
ASSETS = SKILL / "assets"
LIFECYCLE_FIXTURES = ROOT / "tests/fixtures/lifecycle_requests"
COMPOSITION_FIXTURES = ROOT / "tests/fixtures/composition_requests"
VALIDATOR = SCRIPTS / "validate_artifacts.py"
sys.path.insert(0, str(SCRIPTS))

from compose_task import compose  # noqa: E402
from control_plane import LifecycleError, distill_outcome, normalize_project_state  # noqa: E402
from memory_adapter import GitMemoryAdapter, MemoryAdapterError  # noqa: E402


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def lifecycle_fixture(name: str) -> dict:
    return load_json(LIFECYCLE_FIXTURES / f"{name}.json")


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def validate_temp_task(task: dict) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "task.json"
        path.write_text(json.dumps(task), encoding="utf-8")
        return run_validator("--task", str(path))


class ContextLifecycleTests(unittest.TestCase):
    def test_required_gap_blocks_and_asks_targeted_question(self) -> None:
        task = compose(lifecycle_fixture("required-missing"))
        self.assertEqual(task["lifecycle_status"], "blocked_context")
        self.assertEqual(task["context_gate"]["status"], "blocked")
        self.assertEqual(len(task["clarification_questions"]), 1)
        self.assertEqual(task["clarification_questions"][0]["owner"], "human_decision_owner")
        self.assertIsNone(task["worker_plan"])
        self.assertEqual(task["cognition_graph"], [])
        self.assertIsNone(task["compute_route"])
        self.assertEqual(task["authority_plan"]["next_gate"], "context_resolution")

    def test_optional_gap_warns_and_continues(self) -> None:
        task = compose(lifecycle_fixture("optional-missing"))
        self.assertEqual(task["context_gate"]["status"], "ready")
        self.assertEqual(task["lifecycle_status"], "ready_for_worker")
        self.assertEqual(len(task["context_gate"]["warnings"]), 1)
        self.assertEqual(task["clarification_questions"], [])
        self.assertIsNotNone(task["worker_plan"])

    def test_stale_required_context_blocks(self) -> None:
        task = compose(lifecycle_fixture("stale-required"))
        self.assertEqual(task["context_gate"]["status"], "blocked")
        self.assertIn("SRC-STALE:stale", task["context_gate"]["blockers"][0]["observed_reasons"])

    def test_conflicting_required_context_blocks(self) -> None:
        task = compose(lifecycle_fixture("conflicting-required"))
        self.assertEqual(task["context_gate"]["status"], "blocked")
        self.assertIn("SRC-CONFLICT:conflicting", task["context_gate"]["blockers"][0]["observed_reasons"])

    def test_v4_cannot_accept_an_unusable_required_status(self) -> None:
        for status in ["missing", "inaccessible", "stale", "conflicting", "untrusted", "permission_denied"]:
            with self.subTest(status=status):
                request = lifecycle_fixture("optional-missing")
                source = request["context_sources"][0]
                source["status"] = status
                source["freshness"] = "current"
                source["permitted_use"] = "decision_support"
                requirement = request["context_plan"]["requirements"][0]
                requirement["accepted_statuses"] = [status]
                requirement["legacy_status_accepted"] = True
                task = compose(request)
                self.assertEqual(task["context_gate"]["status"], "blocked")
                self.assertIn(
                    f"{source['source_id']}:{status}",
                    task["context_gate"]["blockers"][0]["observed_reasons"],
                )

    def test_irrelevant_optional_source_is_excluded(self) -> None:
        request = lifecycle_fixture("optional-missing")
        request["context_sources"].append({
            "source_id": "SRC-IRRELEVANT",
            "kind": "secondary_source",
            "freshness": "current",
            "permitted_use": "decision_support",
            "summary": "Unrelated history.",
            "relevance_to_decision": "Does not affect this answer.",
            "decision_change_potential": False,
            "status": "available",
        })
        request["context_plan"]["requirements"][1]["preferred_source_ids"] = ["SRC-IRRELEVANT"]
        task = compose(request)
        excluded = {item["source_id"]: item["reason"] for item in task["compiled_context"]["excluded_sources"]}
        self.assertEqual(excluded["SRC-IRRELEVANT"], "not_decision_relevant")
        self.assertEqual(task["context_gate"]["status"], "ready")

    def test_required_context_outside_budget_blocks(self) -> None:
        request = lifecycle_fixture("optional-missing")
        request["context_plan"]["budget"]["max_characters"] = 1
        task = compose(request)
        self.assertEqual(task["context_gate"]["status"], "blocked")
        self.assertIn("context_budget_exceeded", task["context_gate"]["blockers"][0]["observed_reasons"][0])

    def test_worker_plan_is_provider_independent(self) -> None:
        task = compose(load_json(ASSETS / "composition-request.template.json"))
        worker = task["worker_plan"]
        self.assertEqual(worker["selection_basis"], "capability_contract")
        self.assertNotIn("model", worker)
        self.assertNotIn("provider", worker)
        self.assertEqual(worker["context_refs"], task["compiled_context"]["source_refs"])

    def test_context_free_simple_task_can_continue(self) -> None:
        request = lifecycle_fixture("required-missing")
        request["task_id"] = "LIFECYCLE-NO-CONTEXT"
        request["task_class"] = "retrieval"
        request["context_plan"]["requirements"] = []
        request["uncertainty_register"] = []
        task = compose(request)
        self.assertEqual(task["context_gate"]["status"], "ready")
        self.assertEqual(task["compiled_context"]["items"], [])
        self.assertEqual(task["selected_composition"]["primitive_count"], 0)

    def test_legacy_state_normalization_is_read_only(self) -> None:
        legacy = {
            "schema_version": "3.1.0",
            "project_id": "PROJECT-LEGACY",
            "state_version": "0.2.0",
            "accepted_decisions": [{"decision_id": "DEC-OLD", "decision": "Unverified legacy decision."}],
            "evidence_register": [{"source_id": "SRC-OLD", "class": "verified_fact", "summary": "Legacy fact."}],
            "open_questions": [{"question_id": "Q-OLD", "question": "What changed?", "owner": "human_decision_owner"}],
            "risk_register": [], "authority_grants": [], "learning_events": [],
            "composition_observations": [], "routing_policy_version": "3.1.0",
            "routing_policy_auto_update": False, "latest_task_ids": [],
            "state_write_authorization": "not_authorized",
        }
        original = copy.deepcopy(legacy)
        migrated = normalize_project_state(legacy)
        self.assertEqual(legacy, original)
        self.assertEqual(migrated["schema_version"], "4.0.0")
        self.assertNotIn("working_memory", migrated["corporate_memory"])
        self.assertEqual(migrated["working_memory"]["auto_promotion"], False)
        self.assertEqual(migrated["state_write_authorization"], "not_authorized")
        self.assertFalse(migrated["migration"]["write_performed"])
        self.assertEqual(migrated["corporate_memory"]["decision_log"], [])
        self.assertTrue(any(item["record_id"] == "REVIEW-DEC-OLD" for item in migrated["corporate_memory"]["backlog"]))

    def test_validator_rejects_model_specific_worker(self) -> None:
        task = compose(load_json(ASSETS / "composition-request.template.json"))
        task["worker_plan"]["model"] = "provider-specific-model"
        result = validate_temp_task(task)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_MODEL_SPECIFIC_WORKER", result.stdout)

    def test_v31_request_normalizes_without_legacy_output(self) -> None:
        task = compose(load_json(COMPOSITION_FIXTURES / "pricing.json"))
        self.assertEqual(task["schema_version"], "4.0.0")
        self.assertEqual(task["lifecycle_status"], "ready_for_worker")
        self.assertTrue(any("WARN_LEGACY_REQUEST" in warning for warning in task["compatibility_warnings"]))


class DistillationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = load_json(ASSETS / "task-packet.template.json")
        self.outcome = load_json(ASSETS / "execution-outcome.template.json")

    def _proposal_for(self, candidate: dict) -> dict:
        outcome = copy.deepcopy(self.outcome)
        outcome["learning_candidates"] = [candidate]
        return distill_outcome(self.task, outcome)

    def test_assumption_cannot_be_promoted_to_context(self) -> None:
        candidate = copy.deepcopy(self.outcome["learning_candidates"][0])
        candidate["epistemic_class"] = "assumption"
        proposal = self._proposal_for(candidate)
        self.assertEqual(proposal["changes"], [])
        self.assertEqual(proposal["rejected_candidates"][0]["code"], "ERR_CONTEXT_PROMOTION")

    def test_decision_requires_explicit_human_acceptance(self) -> None:
        candidate = copy.deepcopy(self.outcome["learning_candidates"][0])
        candidate.update({"target_memory_class": "decision_log", "epistemic_class": "user_confirmed"})
        proposal = self._proposal_for(candidate)
        self.assertEqual(proposal["rejected_candidates"][0]["code"], "ERR_DECISION_ACCEPTANCE_REQUIRED")

    def test_accepted_decision_is_proposed_not_written(self) -> None:
        candidate = copy.deepcopy(self.outcome["learning_candidates"][0])
        candidate.update({
            "target_memory_class": "decision_log",
            "epistemic_class": "user_confirmed",
            "human_acceptance": {
                "accepted_by": "human_decision_owner",
                "accepted_at": "2026-08-17T12:00:00Z",
                "evidence_reference": "DECISION-001",
            },
        })
        proposal = self._proposal_for(candidate)
        self.assertEqual(len(proposal["changes"]), 1)
        self.assertEqual(proposal["write_authorization"], "not_authorized")
        self.assertTrue(proposal["write_authorization_required"])

    def test_working_memory_requires_ttl_and_no_auto_promotion(self) -> None:
        candidate = copy.deepcopy(self.outcome["learning_candidates"][2])
        candidate.pop("expires_at")
        proposal = self._proposal_for(candidate)
        self.assertEqual(proposal["rejected_candidates"][0]["code"], "ERR_WORKING_MEMORY_TTL")
        valid = self._proposal_for(self.outcome["learning_candidates"][2])
        self.assertFalse(valid["changes"][0]["record"]["promotion_authorized"])

    def test_failed_verification_cannot_promote_durable_memory(self) -> None:
        outcome = copy.deepcopy(self.outcome)
        outcome["verification"]["status"] = "failed"
        outcome["learning_candidates"] = [copy.deepcopy(self.outcome["learning_candidates"][0])]
        proposal = distill_outcome(self.task, outcome)
        self.assertEqual(proposal["changes"], [])
        self.assertEqual(proposal["rejected_candidates"][0]["code"], "ERR_VERIFICATION_REQUIRED")

    def test_unverified_provenance_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.outcome["learning_candidates"][0])
        candidate["source_refs"] = ["SRC-NOT-VERIFIED"]
        proposal = self._proposal_for(candidate)
        self.assertEqual(proposal["changes"], [])
        self.assertEqual(proposal["rejected_candidates"][0]["code"], "ERR_UNVERIFIED_PROVENANCE")

    def test_blocked_task_cannot_be_distilled(self) -> None:
        blocked = compose(lifecycle_fixture("required-missing"))
        with self.assertRaises(LifecycleError):
            distill_outcome(blocked, self.outcome)


class MemoryAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proposal = load_json(ASSETS / "memory-change-proposal.template.json")
        self.authorization = load_json(ASSETS / "memory-write-authorization.template.json")

    def test_write_requires_active_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = GitMemoryAdapter(Path(directory))
            authorization = copy.deepcopy(self.authorization)
            authorization["status"] = "proposed"
            with self.assertRaises(MemoryAdapterError):
                adapter.apply(self.proposal, authorization, adapter.current_revision())

    def test_apply_is_revision_checked_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = GitMemoryAdapter(Path(directory))
            initial = adapter.current_revision()
            self.assertEqual(initial, self.proposal["base_revision"])
            result = adapter.apply(self.proposal, self.authorization, initial)
            self.assertEqual(result["status"], "applied")
            self.assertNotEqual(result["revision"], initial)
            repeated = adapter.apply(self.proposal, self.authorization, initial)
            self.assertEqual(repeated["status"], "no_op_already_applied")
            records = adapter.read({"memory_classes": ["context", "backlog", "working_memory"]})["records"]
            self.assertEqual({record["memory_class"] for record in records}, {"context", "backlog", "working_memory"})

    def test_revision_conflict_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = GitMemoryAdapter(Path(directory))
            with self.assertRaises(MemoryAdapterError):
                adapter.apply(self.proposal, self.authorization, "sha256:not-current")
            self.assertFalse((Path(directory) / "memory").exists())

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = GitMemoryAdapter(root)
            proposal = copy.deepcopy(self.proposal)
            proposal["changes"][0]["record_id"] = "../escape"
            proposal["changes"][0]["record"]["record_id"] = "../escape"
            with self.assertRaises(MemoryAdapterError):
                adapter.apply(proposal, self.authorization, adapter.current_revision())
            self.assertFalse((root.parent / "escape.json").exists())

    def test_partial_replay_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = GitMemoryAdapter(Path(directory))
            initial = adapter.current_revision()
            adapter.apply(self.proposal, self.authorization, initial)
            mixed = copy.deepcopy(self.proposal)
            mixed["changes"].append({
                "change_id": "CHG-NEW-001",
                "operation": "add",
                "record_id": "CTX-NEW-001",
                "target_memory_class": "context",
                "record": {
                    "record_id": "CTX-NEW-001", "memory_class": "context",
                    "epistemic_class": "verified_fact", "content": "New record.",
                    "source_refs": ["SRC-NEW"], "rationale": "Test record.",
                },
            })
            with self.assertRaises(MemoryAdapterError):
                adapter.apply(mixed, self.authorization, adapter.current_revision())

    def test_adapter_rechecks_durable_context_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = GitMemoryAdapter(Path(directory))
            proposal = copy.deepcopy(self.proposal)
            proposal["changes"][0]["record"]["epistemic_class"] = "assumption"
            with self.assertRaises(MemoryAdapterError):
                adapter.apply(proposal, self.authorization, adapter.current_revision())

    def test_adapter_rechecks_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = GitMemoryAdapter(Path(directory))
            proposal = copy.deepcopy(self.proposal)
            proposal["changes"][0]["record"]["source_refs"] = ["SRC-NOT-VERIFIED"]
            with self.assertRaises(MemoryAdapterError):
                adapter.apply(proposal, self.authorization, adapter.current_revision())


if __name__ == "__main__":
    unittest.main()
