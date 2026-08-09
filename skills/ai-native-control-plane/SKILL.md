---
name: ai-native-control-plane
description: Route complex decision and execution work through a stateful, risk-adaptive AI-native control plane. Use when Codex must classify a task, assemble only the necessary context, select dynamic reasoning methods, set compute depth, separate evidence from uncertainty, coordinate optional specialists or personas, preserve authority gates, or compress a decision for an executive. Treat Project CEO, CxO, and other personas as optional interfaces rather than required organizational layers.
---

# AI-Native Control Plane

Run one stable control plane and create a temporary cognition graph per task. Do not start from a fixed human-style organization chart, permanent agent roster, or persona hierarchy.

## Start a task

1. Read `references/control-plane-contract.json` and validate the requested work against its invariants.
2. Load `assets/project-state.template.json` only when durable decisions, authority grants, or cross-session continuity matter. Treat state as a record of accepted decisions and evidence, not a substitute for reasoning.
3. Create or update a task packet from `assets/task-packet.template.json`. Classify the task before selecting methods, roles, or tools.
4. Select only the required context, method packs, domain packs, compute route, and output mode. Use `references/packs-and-routing.md` for the selection rules.
5. Run the temporary cognition graph. Rebuild it for each materially different task; do not promote it to a permanent hierarchy by default.
6. Run epistemic and authority checks. Use `references/risk-and-authority.md` when a task has material downside, regulated data, irreversible actions, or external effects.
7. Return an executive-compressed decision packet using `assets/decision-packet.template.md`. State what is decided, what is only recommended, and the next authorized gate.
8. Propose a state update. Write durable state only with explicit authorization. Validate all structured artifacts with `scripts/validate_artifacts.py`.

## Control-plane invariants

- Keep durable state, task control, temporary cognition, and execution interfaces separate.
- Separate verified fact, evidence, analysis, hypothesis, assumption, unknown, and decision. Confidence is not evidence.
- Treat a completed analysis, validator pass, acceptance, activation, and execution as different claims with different gates.
- Route compute by decision consequence and uncertainty, not by job title or task verbosity.
- Let optional persona presets change communication or review lenses only. They never create authority or a mandatory chain of command.
- Keep external action, system write, publication, procurement, and expanded autonomy disabled until explicitly authorized for a bounded scope.
- Earn autonomy from observed, scoped performance; expire and revoke it deliberately. Never infer it from a title, a successful test, or a prior task.

## Build the temporary cognition graph

Use this compact sequence unless the task packet justifies a different graph:

```text
classify -> assemble context -> form hypotheses -> test/compare
         -> synthesize -> red-team if risk warrants -> decision packet -> gate
```

Choose packs by the decision need:

- Start with `problem-framing`, `evidence`, and `synthesis` for non-trivial work.
- Add `hypothesis-led`, `MECE`, `causal`, `scenario`, `prioritization`, or `red-team` only when they reduce a named uncertainty.
- Add a domain pack for domain constraints and evidence standards, not for a permanent department identity.
- Use a persona preset only if its framing is useful to the recipient. Read `references/optional-personas.json` for its interface-only boundary.

## Risk-adaptive routing

- `low`: reversible internal work; use baseline evidence and concise review.
- `medium`: meaningful trade-offs or limited external effect; record assumptions, alternatives, and a human decision boundary.
- `high`: irreversible, regulated, financial, privacy, safety, or reputation effect; use high compute, independent challenge, provenance, and an explicit human gate.
- `critical`: potentially severe harm or legally reserved decision; do not automate the decision or execution. Escalate with a bounded decision packet.

Use `compute_route` as a reasoning budget: `light`, `standard`, `high`, or `maximum`. Higher compute increases investigation and challenge; it does not grant broader authority.

## Persist state without freezing cognition

Preserve accepted decisions, evidence references, unresolved questions, risks, authority grants, and learning events. Keep task-specific methods, working context, temporary specialists, and persona lenses ephemeral unless there is evidence that a reusable pack is justified.

Validate an individual task, state record, or authority grant with:

```text
python scripts/validate_artifacts.py --task path/to/task.json
python scripts/validate_artifacts.py --state path/to/state.json
python scripts/validate_artifacts.py --grant path/to/grant.json
```

Run the full package check with:

```text
python scripts/validate_artifacts.py --all
```
