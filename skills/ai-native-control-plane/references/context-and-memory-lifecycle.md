# Context and memory lifecycle

## Contents

1. Lifecycle boundary
2. Context planning and readiness
3. Worker planning
4. Distillation and memory classes
5. Adapter and write gate

## 1. Lifecycle boundary

V4 extends the control plane; it does not create a permanent context service,
worker hierarchy, or autonomous memory writer.

```text
intent + preliminary classification
  -> context plan -> collect -> compile -> readiness gate
  -> cognition + capability-based worker plan -> execute -> verify
  -> distill -> memory-change proposal -> authorized adapter write
  -> outcome observation
```

Context planning reads and compiles existing information. Distillation starts
only after execution and verification. Distillation proposes state changes; it
does not authorize or perform them.

## 2. Context planning and readiness

Each context requirement declares an identifier, priority, why it matters,
preferred sources, accepted statuses, freshness expectation, blocking policy,
question, answer needed, and owner. `required` requirements must set
`blocking_if_unsatisfied` to true. `optional` gaps remain warnings.

Sources are usable only when they are decision-relevant, permitted for the
task, sufficiently fresh, and in an accepted status. The compiler selects the
smallest declared set within `max_items` and `max_characters`, records every
selection and exclusion, and returns exactly one gate status:

- `ready`: cognition and worker planning may continue.
- `blocked`: cognition and worker selection remain empty; ask only the emitted
  targeted questions.

Missing, inaccessible, stale, permission-denied, untrusted, or materially
conflicting required context must never be replaced by an assumption.

## 3. Worker planning

Workers are selected by a capability contract: required capabilities, allowed
tools, compute route, compiled-context references, output contract, authority
ceiling, and prohibited actions. Provider, model, persona, and compute labels
cannot create authority. Runtime-specific worker binding remains an optional
execution adapter.

## 4. Distillation and memory classes

- `context`: reusable, source-backed project knowledge. Assumptions,
  hypotheses, unknowns, and conflicts cannot be promoted as verified context.
- `decision_log`: decisions with explicit human acceptance and an evidence
  reference.
- `backlog`: unresolved work with owner, status, and next gate.
- `working_memory`: task-scoped notes with an ISO-8601 expiry and
  `promotion_authorized: false` by default.

The semantic worker emits learning candidates. Deterministic distillation
normalizes valid candidates, rejects source references absent from the verified
execution evidence and invalid promotions with stable error codes, and emits a
proposal with `write_authorization: not_authorized`.

## 5. Adapter and write gate

The reference adapter exposes `read`, `current_revision`, and `apply`. Durable
records live under `memory/context`, `memory/decisions`, and `memory/backlog`.
Working memory lives under the Git-ignored `.control-plane/working` directory.

`apply` requires an active, scoped, unexpired authorization for the same task,
an exact expected revision, safe identifiers, and allowed memory classes. It
uses `change_id` for idempotency and rejects partial replay, path traversal, and
revision conflicts. It writes files only; it never commits, pushes, calls a
remote API, or broadens authorization.
