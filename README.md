# AI-Native Control Plane V3.1

A reusable Codex skill for decision-quality work built on one invariant:

> **Persistent state, ephemeral cognition. The control plane dynamically composes a small set of reasoning primitives, domain lenses, and quality checks for each task.**

```text
Durable State -> Control Plane -> Temporary Cognition Graph -> Optional Execution Interface
```

The architecture asks a different question from a human organization chart:

- Human-organization question: “Which AI employee should do this?”
- AI-native question: **“Which context, reasoning methods, domain lenses, quality checks, compute level, and authority are required to solve this task reliably?”**

Project CEO, CFO, CMO, CxO, and specialist personas remain available as optional communication, review, or domain presets. They are not permanent organizational dependencies and cannot grant authority.

## V3 audit outcome

V3’s core was kept: durable state, temporary task graphs, task classification, smallest-sufficient context, four compute routes, four risk tiers, explicit human authority, evidence taxonomy, no implicit state write, earned autonomy, executive compression, risk-adaptive governance, and standard-library validation.

V3.1 changes only the composition layer:

- Splits mixed `method_packs` into typed `thinking_methods`, `domain_lenses`, `quality_checks`, and optional `synthesis_steps`.
- Adds a 20-item primitive registry and a domain-lens registry with constraints and evidence standards.
- Adds cognitive-need diagnosis, task-signal routing, primitive budgets, typed cognition graphs, and selection rationale.
- Adds optional seed recipes that may be changed or ignored with a recorded reason.
- Adds composition outcome observations without self-modifying routing.
- Retains V3 packet compatibility through explicit aliases.

The full KEEP / MODIFY / ADD / MOVE / DEPRECATE map is in [`v3-to-v3.1-migration.md`](skills/ai-native-control-plane/references/v3-to-v3.1-migration.md).

## Runtime

```text
Human intent
  -> task classification
  -> smallest sufficient context
  -> cognitive need diagnosis
  -> methods + lenses + checks
  -> temporary cognition graph
  -> minimum sufficient compute
  -> reasoning and epistemic checks
  -> synthesis
  -> authority gate
  -> output or state proposal
```

A primitive is selected only when it reduces a named uncertainty, tests a material alternative, or materially lowers consequential decision risk. Simple retrieval and transformation should not create a complex graph.

## Repository layout

```text
skills/ai-native-control-plane/
  SKILL.md
  references/                       contracts, registries, routing, migration
  assets/                           request, task, state, outcome, and decision templates
  scripts/compose_task.py           deterministic composition helper
  scripts/validate_artifacts.py     contracts and invariant validator
tests/fixtures/composition_requests Juno composition fixtures
tests/test_validation.py            27 behavioral and guardrail tests
```

## Compose a task

```text
python skills/ai-native-control-plane/scripts/compose_task.py \
  --request skills/ai-native-control-plane/assets/composition-request.template.json
```

The request carries task signals and named cognitive/domain/quality needs. The output carries selected methods, lenses, checks, `why_selected`, `uncertainty_reduced`, graph order, compute rationale, epistemic register, authority gate, and observability fields.

## Validate

Python 3.10+ is sufficient; runtime has no third-party dependencies.

```text
python skills/ai-native-control-plane/scripts/validate_artifacts.py --all
python -m unittest discover -s tests -p "test_*.py"
python /path/to/skill-creator/scripts/quick_validate.py skills/ai-native-control-plane
```

`--all` validates contracts, templates, the registry, all Juno fixtures, composition outputs, context relevance, risk/compute requirements, epistemic controls, persona boundaries, state-write gates, and non-self-modification.

## Backward compatibility

- V3.1 is the emitted format.
- V3 `3.0.0` task packets remain readable through `method_packs` and `domain_packs` aliases and produce a deprecation warning.
- V3 project-state and earned-autonomy grant records remain readable.
- `workflow`, `behavioral`, and `financial` are intentionally reclassified through aliases; no incorrect taxonomy is preserved in new output.

## Deliberate limits

- The composer sequences cognitive operations; it does not perform the reasoning itself.
- Recipes are priors, not learned routing policy.
- Observations do not update policy automatically.
- There is no framework marketplace or 50–100-item encyclopedia.
- Validation proves structure and invariants, not decision correctness or human authorization.
