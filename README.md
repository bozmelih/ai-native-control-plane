# AI-Native Control Plane V4

AI-Native Control Plane is a model-independent project operating system for
context-gated work, minimal task cognition, capability-based worker routing,
and governed organizational memory.

It is not a prompt, model, permanent agent hierarchy, or autonomous knowledge
writer. Its competitive surface is the working system around AI workers:

```text
Versioned Durable Memory
  -> Context Planning and Compilation
  -> Context Readiness Gate
  -> Control Plane and Temporary Cognition
  -> Capability-Based Worker Interface
  -> Execution and Verification
  -> Distillation
  -> Memory-Change Proposal
  -> Authorized Local Adapter Write
```

The core rule remains **persistent memory, ephemeral cognition**. V4 adds two
explicit phases around V3.1 composition:

- At the start, plan, collect, and compile only decision-relevant context.
- At the end, distill verified learning and propose a typed memory update.

If required context is unavailable, stale, permission-denied, untrusted, or
materially conflicting, the lifecycle stops and asks targeted questions. It
does not fill the gap with an assumption or select a worker.

## Runtime

```text
intent + preliminary classification
  -> context plan -> collect -> compile -> readiness gate
  -> cognition + capability-based worker plan -> execute -> verify
  -> distill -> memory-change proposal -> authorized adapter write
  -> outcome observation
```

Context requirements are `required` or `optional`. Required gaps block;
optional gaps remain warnings. Context budgets use `max_items` and
`max_characters`, so the core does not depend on a model tokenizer.

Workers are described by capabilities, allowed tools, compute route, compiled
context, output contract, authority ceiling, and prohibited actions. No model,
provider, persona, or compute label grants authority.

## Memory classes

| Class | Persistence rule |
| --- | --- |
| `context` | Reusable, source-backed project knowledge only. |
| `decision_log` | Requires explicit human acceptance and evidence reference. |
| `backlog` | Requires owner, status, and next gate. |
| `working_memory` | Task-scoped, TTL-bound, Git-ignored, and never auto-promoted. |

The local reference adapter stores durable JSON records in
`memory/context`, `memory/decisions`, and `memory/backlog`. Working memory lives
under `.control-plane/working`. The adapter validates authorization, exact base
revision, path safety, allowed memory classes, and idempotent `change_id`
values. It never invokes Git or a remote API.

## CLI

Prepare a task:

```text
python skills/ai-native-control-plane/scripts/control_plane.py prepare \
  --request skills/ai-native-control-plane/assets/composition-request.template.json
```

Distill a verified outcome:

```text
python skills/ai-native-control-plane/scripts/control_plane.py distill \
  --task path/to/task.json \
  --outcome skills/ai-native-control-plane/assets/execution-outcome.template.json
```

Apply an explicitly authorized local write:

```text
python skills/ai-native-control-plane/scripts/control_plane.py apply \
  --proposal path/to/memory-proposal.json \
  --authorization path/to/memory-write-authorization.json \
  --memory-root path/to/repository
```

`compose_task.py` remains a compatibility entry point for V3.1 requests and
always emits a V4 packet.

Normalize legacy project state without writing it:

```text
python skills/ai-native-control-plane/scripts/control_plane.py migrate-state \
  --state path/to/v3-project-state.json
```

## Repository layout

```text
skills/ai-native-control-plane/
  SKILL.md
  references/                       contracts, lifecycle, routing, migration
  assets/                           request, task, outcome, memory templates
  scripts/control_plane.py          prepare, distill, and apply lifecycle CLI
  scripts/compose_task.py            V3.1-compatible prepare wrapper
  scripts/memory_adapter.py          local Git-backed reference adapter
  scripts/validate_artifacts.py      deterministic package validator
tests/                               regression and V4 lifecycle fixtures
```

## Validation

Python 3.10+ is sufficient; runtime has no third-party dependencies.

```text
python skills/ai-native-control-plane/scripts/validate_artifacts.py --all
python -m unittest discover -s tests -p "test_*.py"
```

Validation covers V3/V3.1 compatibility, context blocking, targeted
clarification, capability-based worker planning, evidence promotion,
verified provenance, decision/backlog/working-memory rules, write authorization, optimistic
revision, idempotency, path traversal, and non-self-modifying routing.

## Compatibility and limits

- V3.0 task packets remain readable through legacy aliases.
- V3.1 requests and state remain readable through explicit normalization.
- V4 emits only `4.0.0` artifacts and never performs migration writes.
- The package does not include a remote GitHub API adapter, credentials,
  automatic commits, pull requests, releases, installation, or activation.
- Validator success proves contract conformance, not strategic correctness,
  human approval, publication authority, or operational readiness.
