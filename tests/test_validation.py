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
REFERENCES = SKILL / "references"
ASSETS = SKILL / "assets"
FIXTURES = ROOT / "tests/fixtures/composition_requests"
VALIDATOR = SCRIPTS / "validate_artifacts.py"
sys.path.insert(0, str(SCRIPTS))

from compose_task import CompositionError, compose  # noqa: E402


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fixture(name: str) -> dict:
    return load_json(FIXTURES / f"{name}.json")


def selected_ids(task: dict, key: str) -> list[str]:
    return [item["id"] for item in task["selected_composition"][key]]


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


class PackageTests(unittest.TestCase):
    def test_01_package_templates_and_fixtures_pass(self) -> None:
        result = run_validator("--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS errors=0 warnings=0", result.stdout)

    def test_02_registry_is_minimal_complete_and_typed(self) -> None:
        registry = load_json(REFERENCES / "cognitive-primitive-registry.json")
        self.assertEqual(len(registry["primitives"]), 20)
        self.assertEqual({item["category"] for item in registry["primitives"]}, {"thinking_method", "quality_check", "synthesis"})
        required = {
            "id", "category", "purpose", "use_when", "avoid_when", "required_inputs",
            "evidence_needs", "reasoning_operation", "expected_outputs",
            "relative_compute_cost", "complements", "common_failure_modes",
        }
        self.assertTrue(all(required <= set(item) for item in registry["primitives"]))

    def test_03_taxonomy_separates_methods_lenses_and_checks(self) -> None:
        contract = load_json(REFERENCES / "control-plane-contract.json")
        self.assertNotIn("finance", contract["thinking_methods"])
        self.assertIn("finance", contract["domain_lenses"])
        self.assertIn("red-team", contract["quality_checks"])
        self.assertNotIn("red-team", contract["thinking_methods"])
        self.assertEqual(contract["synthesis_steps"], ["synthesis"])

    def test_04_v3_packet_remains_compatible(self) -> None:
        legacy = {
            "schema_version": "3.0.0",
            "task_id": "LEGACY-001",
            "objective": "Validate a legacy product decision packet.",
            "task_class": "decision",
            "decision_type": "bounded_commitment",
            "risk_tier": "medium",
            "compute_route": "standard",
            "context_sources": [{
                "source_id": "SRC-LEGACY-001", "kind": "user_confirmed",
                "freshness": "current", "permitted_use": "decision_support",
                "summary": "Legacy packet evidence.",
            }],
            "method_packs": ["problem-framing", "evidence", "synthesis"],
            "domain_packs": ["product"],
            "cognition_graph": [{"node_id": "frame", "purpose": "Frame", "method_packs": ["problem-framing"]}],
            "epistemic_register": [{"claim_id": "CLM-LEGACY-001", "class": "user_confirmed", "statement": "Legacy input is confirmed.", "source_ids": ["SRC-LEGACY-001"]}],
            "uncertainty_register": ["Legacy normalization remains visible."],
            "authority_plan": {"current_gate": "recommendation", "human_decision_required": True, "state_write": "propose_only", "external_action": "none", "system_write": "none", "next_gate": "human_decision"},
            "output_mode": "decision-packet",
        }
        result = validate_temp_task(legacy)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARN_LEGACY_TASK", result.stdout)


class CompositionFixtureTests(unittest.TestCase):
    def test_05_product_adoption_composition(self) -> None:
        task = compose(load_json(ASSETS / "composition-request.template.json"))
        self.assertEqual(selected_ids(task, "thinking_methods"), ["jobs-to-be-done", "hypothesis-led", "causal-analysis", "pareto-prioritization"])
        self.assertEqual(set(selected_ids(task, "domain_lenses")), {"product", "education", "workflow", "behavior"})
        self.assertIn("evidence-assumption-check", selected_ids(task, "quality_checks"))

    def test_06_investment_composition(self) -> None:
        task = compose(fixture("investment"))
        self.assertEqual(set(selected_ids(task, "thinking_methods")), {"expected-value", "scenario-analysis", "sensitivity-analysis", "opportunity-cost"})
        self.assertEqual(set(selected_ids(task, "domain_lenses")), {"finance", "strategy"})
        self.assertIn("pre-mortem", selected_ids(task, "quality_checks"))
        self.assertEqual(task["compute_route"], "high")

    def test_07_organization_design_composition(self) -> None:
        task = compose(fixture("organization"))
        self.assertEqual(set(selected_ids(task, "thinking_methods")), {"first-principles", "systems-thinking", "constraint-analysis", "second-order-effects"})
        self.assertIn("red-team", selected_ids(task, "quality_checks"))
        self.assertEqual(set(selected_ids(task, "domain_lenses")), {"organization", "strategy"})

    def test_08_pricing_composition(self) -> None:
        task = compose(fixture("pricing"))
        self.assertEqual(set(selected_ids(task, "thinking_methods")), {"hypothesis-led", "sensitivity-analysis", "opportunity-cost"})
        self.assertEqual(set(selected_ids(task, "domain_lenses")), {"customer", "pricing", "finance"})

    def test_09_brand_strategy_composition(self) -> None:
        task = compose(fixture("brand"))
        self.assertEqual(set(selected_ids(task, "thinking_methods")), {"jobs-to-be-done", "first-principles"})
        self.assertEqual(set(selected_ids(task, "domain_lenses")), {"brand", "strategy", "customer"})
        self.assertIn("red-team", selected_ids(task, "quality_checks"))
        registry = load_json(REFERENCES / "cognitive-primitive-registry.json")
        self.assertNotIn("competitive-differentiation", {item["id"] for item in registry["primitives"]})

    def test_10_simple_task_is_not_over_composed(self) -> None:
        task = compose(fixture("simple-transform"))
        self.assertEqual(task["selected_composition"]["primitive_count"], 0)
        self.assertFalse(task["selected_composition"]["complex_graph_required"])
        self.assertEqual(task["cognition_graph"], [])
        self.assertEqual(task["compute_route"], "light")

    def test_11_high_risk_task_has_challenge_and_human_gate(self) -> None:
        task = compose(fixture("high-risk"))
        checks = set(selected_ids(task, "quality_checks"))
        self.assertTrue({"red-team", "epistemic-check", "pre-mortem"} <= checks)
        self.assertEqual(task["compute_route"], "high")
        self.assertTrue(task["authority_plan"]["human_decision_required"])
        self.assertEqual(task["authority_plan"]["next_gate"], "human_decision")

    def test_12_seed_recipe_allows_justified_deviation(self) -> None:
        task = compose(fixture("recipe-deviation"))
        methods = set(selected_ids(task, "thinking_methods"))
        self.assertNotIn("hypothesis-led", methods)
        self.assertIn("expected-value", methods)
        self.assertEqual(len(task["composition_deviations"]), 2)

    def test_13_persona_labels_are_not_required_for_same_composition(self) -> None:
        request_with = fixture("organization")
        request_without = copy.deepcopy(request_with)
        request_without["optional_persona_presets"] = []
        task_with = compose(request_with)
        task_without = compose(request_without)
        self.assertEqual(task_with["selected_composition"], task_without["selected_composition"])
        self.assertEqual(task_with["cognition_graph"], task_without["cognition_graph"])

    def test_14_three_sufficient_primitives_do_not_expand_to_eight(self) -> None:
        request = fixture("pricing")
        request["task_id"] = "JUNO-MINIMAL-003"
        request["risk_tier"] = "low"
        request["decision_type"] = "reversible"
        request["signals"].update({
            "evidence_gaps": False,
            "context_staleness": "low",
            "decision_consequence": "low",
            "expected_error_cost": "low",
            "cross_domain_complexity": "low",
            "complexity": "low",
            "validation_requirement": "low",
        })
        request["cognitive_needs"] = request["cognitive_needs"][:2]
        request["quality_needs"] = []
        request["primitive_budget"] = 3
        task = compose(request)
        self.assertEqual(task["selected_composition"]["primitive_count"], 3)

    def test_durable_knowledge_is_separate_from_rebuilt_cognition(self) -> None:
        contract = load_json(REFERENCES / "control-plane-contract.json")
        state = load_json(ASSETS / "project-state.template.json")
        product = compose(load_json(ASSETS / "composition-request.template.json"))
        pricing = compose(fixture("pricing"))
        self.assertEqual(contract["architecture_layers"], ["durable_state", "control_plane", "temporary_cognition_graph", "optional_execution_interface"])
        self.assertNotIn("cognition_graph", state)
        self.assertNotIn("selected_composition", state)
        self.assertNotEqual(product["selected_composition"], pricing["selected_composition"])


class GuardrailTests(unittest.TestCase):
    def test_15_unknown_primitive_fails_validation(self) -> None:
        task = compose(fixture("pricing"))
        task["selected_composition"]["thinking_methods"][0]["id"] = "unknown-method"
        result = validate_temp_task(task)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_ENUM", result.stdout)

    def test_16_wrong_taxonomy_category_fails_validation(self) -> None:
        task = compose(fixture("pricing"))
        task["selected_composition"]["thinking_methods"][0]["id"] = "red-team"
        result = validate_temp_task(task)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_ENUM", result.stdout)

    def test_17_persona_cannot_create_authority(self) -> None:
        contract = load_json(REFERENCES / "control-plane-contract.json")
        personas = load_json(REFERENCES / "optional-personas.json")
        self.assertFalse(contract["invariants"]["persona_grants_authority"])
        self.assertTrue(all(item["authority_effect"] == "none" for item in personas["presets"]))

    def test_18_compute_route_cannot_create_authority(self) -> None:
        contract = load_json(REFERENCES / "control-plane-contract.json")
        request = fixture("pricing")
        normal = compose(request)
        deeper_request = copy.deepcopy(request)
        deeper_request["requested_compute_route"] = "maximum"
        deeper = compose(deeper_request)
        self.assertFalse(contract["invariants"]["compute_route_grants_authority"])
        self.assertEqual(normal["authority_plan"], deeper["authority_plan"])
        self.assertEqual(deeper["compute_route"], "maximum")

    def test_19_state_write_requires_explicit_authorization_reference(self) -> None:
        task = compose(fixture("pricing"))
        task["authority_plan"]["state_write"] = "authorized_bounded_scope"
        result = validate_temp_task(task)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_IMPLICIT_STATE_WRITE", result.stdout)

    def test_20_confidence_is_not_evidence(self) -> None:
        task = compose(fixture("pricing"))
        task["epistemic_register"][0]["class"] = "confidence"
        result = validate_temp_task(task)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_CONFIDENCE_AS_EVIDENCE", result.stdout)

    def test_21_simple_task_unnecessary_primitive_count_fails(self) -> None:
        task = compose(fixture("simple-transform"))
        selection = {
            "id": "problem-framing",
            "why_selected": "Artificial test selection.",
            "uncertainty_reduced": "None; this should fail.",
            "selected_by": "test",
        }
        task["selected_composition"]["thinking_methods"] = [selection, {**selection, "id": "first-principles"}, {**selection, "id": "MECE"}]
        task["selected_composition"]["primitive_count"] = 3
        task["selected_composition"]["primitive_budget"] = 3
        result = validate_temp_task(task)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_SIMPLE_TASK_OVERCOMPOSED", result.stdout)

    def test_22_context_pack_rejects_irrelevant_source(self) -> None:
        task = compose(fixture("pricing"))
        task["context_sources"][0]["decision_change_potential"] = False
        result = validate_temp_task(task)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_CONTEXT_NOT_DECISION_RELEVANT", result.stdout)

    def test_23_high_risk_uncertainty_requires_explicit_human_gate(self) -> None:
        task = compose(fixture("high-risk"))
        task["authority_plan"]["current_gate"] = "recommendation"
        task["authority_plan"]["next_gate"] = "recommendation"
        result = validate_temp_task(task)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_HIGH_RISK_HUMAN_GATE", result.stdout)

    def test_24_high_risk_required_check_cannot_be_deviated_away(self) -> None:
        request = fixture("high-risk")
        request["composition_deviations"] = [{
            "action": "remove", "category": "quality_check", "id": "red-team",
            "reason": "Attempt to remove a mandatory risk check.",
        }]
        with self.assertRaises(CompositionError):
            compose(request)

    def test_25_observations_do_not_self_modify_routing(self) -> None:
        state = load_json(ASSETS / "project-state.template.json")
        outcome = load_json(ASSETS / "composition-outcome.template.json")
        contract = load_json(REFERENCES / "control-plane-contract.json")
        self.assertFalse(state["routing_policy_auto_update"])
        self.assertFalse(outcome["routing_policy_changed_automatically"])
        self.assertFalse(contract["invariants"]["observations_auto_modify_routing_policy"])

    def test_26_output_modes_preserve_compression_levels(self) -> None:
        contract = load_json(REFERENCES / "control-plane-contract.json")
        defaults = contract["output_mode_defaults"]
        self.assertEqual(defaults["default"], "executive-compact")
        self.assertEqual(defaults["material_decision"], "decision-packet")
        self.assertEqual(defaults["high_risk_audit_or_governance"], "full-traceability")


if __name__ == "__main__":
    unittest.main()
