---
name: ai-native-control-plane
description: Operate a model-independent project control plane that plans and compiles decision-relevant context, blocks on missing required context, composes minimal task cognition, defines capability-based worker requirements, verifies outcomes, distills learning into typed memory-change proposals, and applies only explicitly authorized local memory writes. Use for material decisions, long-running projects, multi-worker routing, cross-session continuity, evidence and authority governance, or context/memory lifecycle work. Treat personas and provider-specific workers as optional execution interfaces only.
---

# AI-Native Control Plane

Preserve the V4 architecture:

```text
Versioned Durable Memory -> Context Lifecycle -> Control Plane
  -> Temporary Cognition Graph -> Capability-Based Worker Interface
  -> Verification and Distillation -> Authorized Memory Adapter
```

Apply persistent memory, ephemeral cognition, and explicit write authority. The
control plane is a project operating system; it is not a prompt, model, persona,
permanent worker roster, or autonomous memory writer.

## Run the lifecycle

1. Read `references/control-plane-contract.json` and preserve every invariant.
2. Classify intent, task, risk, decision type, and current authority without
   selecting a worker yet.
3. Read `references/context-and-memory-lifecycle.md`. Plan required and optional
   context, collect permitted sources, and compile the smallest sufficient set.
4. Stop when `context_gate.status` is `blocked`. Return only the targeted
   clarification questions; do not assume missing facts or select cognition,
   compute, or a worker.
5. When the gate is `ready`, diagnose cognitive needs and compose the smallest
   justified methods, lenses, checks, and synthesis graph. Read
   `references/packs-and-routing.md` as needed.
6. Define the worker through required capabilities, tools, context references,
   output contract, compute, authority ceiling, and prohibited actions. A model,
   provider, persona, or compute route never creates authority.
7. Run reasoning and the selected checks. Read
   `references/risk-and-authority.md` for consequential or regulated downside.
8. Verify the outcome before distillation. Keep facts, inferences, assumptions,
   hypotheses, unknowns, and conflicts distinct.
9. Distill reusable learning into `context`, `decision_log`, `backlog`, or
   TTL-bound `working_memory`. Reject unsupported context promotion and decisions
   without explicit human acceptance.
10. Emit a memory-change proposal. Apply it only with a scoped, active,
    unexpired authorization and exact revision. The adapter writes files only;
    it never commits, pushes, or contacts GitHub.
11. Record outcomes without changing routing policy automatically.

## Keep context and memory bounded

- Add context only when it can change the task, evidence standard, risk, or
  authority decision.
- Treat every optional gap as a warning, not a blocker.
- Keep working memory under `.control-plane/working`, require a TTL, and never
  auto-promote it.
- Store durable local records under `memory/context`, `memory/decisions`, and
  `memory/backlog` through the reference adapter.
- Propose state changes before requesting write authority. Human acceptance of
  advice is not implicit state-write authorization.

## Use the artifacts

- Start from `assets/composition-request.template.json`.
- Emit `assets/task-packet.template.json`.
- Capture execution in `assets/execution-outcome.template.json`.
- Emit `assets/memory-change-proposal.template.json`.
- Use `assets/memory-write-authorization.template.json` only for explicit,
  bounded writes.
- Use `assets/project-state.template.json` for cross-session corporate memory
  and governance state.
- Read `references/v3.1-to-v4-migration.md` for legacy artifacts.

## Run deterministically

```text
python scripts/control_plane.py prepare --request path/to/request.json
python scripts/control_plane.py distill --task path/to/task.json --outcome path/to/outcome.json
python scripts/control_plane.py apply --proposal path/to/proposal.json \
  --authorization path/to/authorization.json --memory-root path/to/repository
python scripts/control_plane.py migrate-state --state path/to/v3-project-state.json
```

`scripts/compose_task.py` remains a V3.1-compatible preparation entry point and
always emits V4 task packets.

Validate contracts, templates, fixtures, and lifecycle invariants:

```text
python scripts/validate_artifacts.py --all
```

A validator pass proves structural conformance only. It does not prove decision
quality, human acceptance, publication authority, installation, or activation.
