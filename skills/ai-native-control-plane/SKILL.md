---
name: ai-native-control-plane
description: Dynamically compose a small task-specific cognition graph from durable state, relevant context, thinking methods, domain lenses, quality checks, compute needs, and authority boundaries. Use when Codex must make or review a material decision, diagnose uncertainty, route multi-domain work, challenge evidence, select minimum sufficient compute, prepare an executive decision packet, or preserve project continuity without recreating a permanent CEO/CxO/persona hierarchy. Treat personas as optional interfaces or review presets only.
---

# AI-Native Control Plane

Preserve this architecture:

```text
Durable State -> Control Plane -> Temporary Cognition Graph -> Optional Execution Interface
```

Apply the paradigm: persistent state, ephemeral cognition. Rebuild reasoning around each task; do not start from a permanent role roster or organization chart.

## Run the control plane

1. Read `references/control-plane-contract.json` and preserve its invariants.
2. Classify the task and authority boundary before selecting methods, personas, tools, or compute.
3. Load the smallest sufficient context: objective, accepted decisions, relevant evidence and constraints, authority boundary, and unresolved material questions. Add context only if it may change the decision.
4. Diagnose cognitive needs from ambiguity, uncertainty, evidence gaps, consequence, error cost, reversibility, cross-domain/context complexity, staleness, conflicts, challenge need, and material alternatives.
5. Read `references/cognitive-primitive-registry.json` and `references/domain-lens-registry.json` as needed. Select the smallest justified set of thinking methods, domain lenses, quality checks, and synthesis.
6. Record `why_selected` and `uncertainty_reduced` for every method and check. Record the decision-relevant constraint or evidence standard for each lens.
7. Sequence actual dependencies as a temporary cognition graph. Do not duplicate cognition unless independent validation is deliberately required.
8. Choose minimum sufficient compute using `references/packs-and-routing.md`. Higher compute never creates authority.
9. Run reasoning, then the selected epistemic and quality checks. Read `references/risk-and-authority.md` for material or regulated downside.
10. Synthesize using high linguistic compression and low information compression. Use `assets/decision-packet.template.md` for material decisions.
11. Stop at the current authority gate. Propose state changes; write state only with explicit bounded authorization.
12. Record outcome observations without changing routing policy automatically.

## Compose without bureaucracy

Add a primitive only when it:

- reduces a named uncertainty;
- tests a material alternative; or
- materially reduces consequential decision risk.

Do not call eight primitives when three are sufficient. Do not build a complex graph for simple retrieval or transformation. A domain lens is not a department. A persona is not authority. Framework count is not quality.

Use `references/seed-recipes.json` only as an optional prior. The task label alone never determines composition. Add or remove recipe items when task signals justify the deviation and record the reason.

## Preserve epistemic control

For each material output distinguish:

- what is known;
- what is inferred;
- what is assumed;
- what is missing;
- what conflicts; and
- what would materially change the recommendation.

Use `unknown`, `assumption`, `hypothesis`, and `conflicting` explicitly. Confidence is not evidence. Return a bounded unknown rather than pseudo-certainty when evidence is insufficient.

## Keep interfaces optional

Read `references/optional-personas.json` only when a communication or review preset helps. Project CEO, CFO, CMO, and other labels may suggest context, methods, lenses, checks, or output framing. They cannot create persistence, mandatory delegation, compute entitlement, or authority.

## Work with artifacts

- Start a composition request from `assets/composition-request.template.json`.
- Store the emitted task packet in the shape of `assets/task-packet.template.json`.
- Load `assets/project-state.template.json` only when cross-session continuity matters; state is an input, not intelligence.
- Record routing outcomes with `assets/composition-outcome.template.json`.
- Use `assets/authority-grant.template.json` only for explicitly approved, scoped, expiring, and revocable earned autonomy.
- Read `references/v3-to-v3.1-migration.md` when consuming a V3 packet.

Compose deterministically when a structured request is available:

```text
python scripts/compose_task.py --request path/to/request.json
```

Validate all contracts, templates, and Juno fixtures:

```text
python scripts/validate_artifacts.py --all
```

Validate one artifact with `--request`, `--task`, `--state`, `--grant`, or `--outcome`.
