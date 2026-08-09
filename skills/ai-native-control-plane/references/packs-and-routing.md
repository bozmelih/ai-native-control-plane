# Cognitive composition and routing

Compose the smallest sufficient temporary cognition graph. Do not start from a job title, department, fixed prompt chain, or recipe lookup.

## Runtime

```text
intent -> classify -> assemble smallest context -> diagnose cognitive needs
       -> select methods + lenses + checks -> sequence graph -> route compute
       -> reason -> epistemic/quality checks -> synthesize -> authority gate
```

## Diagnose before selecting

Evaluate ambiguity, uncertainty, evidence gaps, consequence, expected error cost, reversibility, cross-domain complexity, context complexity, staleness, conflicts, need for independent challenge, and the number of materially plausible alternatives.

For every selected method or check, record:

- `why_selected`: the task condition that justifies the cost.
- `uncertainty_reduced`: the named uncertainty, alternative, or risk it addresses.

For every lens, record the domain constraint or evidence standard it contributes. A lens does not create a department or agent.

## Selection discipline

1. Select a thinking method only for a diagnosed reasoning operation.
2. Select a domain lens only when its constraints or evidence standards could change the recommendation.
3. Select a quality check only when it can catch a material failure mode.
4. Sequence only real dependencies; parallel nodes are allowed when outputs do not depend on each other.
5. Add synthesis for material multi-finding decisions, not for trivial retrieval or transformation.
6. Apply a seed recipe only as a prior. Add or remove items when task signals justify the deviation, and record why.
7. Reject duplicate cognition unless deliberate independent validation is required.

### Anti-bureaucracy invariant

A primitive is justified only when it reduces a named uncertainty, tests a material alternative, or materially reduces consequential decision risk. Three sufficient primitives beat eight decorative ones. Framework count is not quality.

Simple retrieval and transformation tasks should normally have no complex cognition graph. If more than two methods/checks/synthesis steps are selected for a simple task, the validator rejects the packet unless the task is no longer classified as simple.

## Context assembly

Start with only:

- current objective;
- accepted decisions;
- relevant evidence;
- relevant constraints;
- authority boundary; and
- unresolved material questions.

Every selected context source must explain its relevance and whether it can change the decision. Mark inaccessible, stale, conflicting, or untrusted context. Do not retransmit stable project history merely because it exists. Persistent state is an input to reasoning, not reasoning itself.

## Minimum sufficient compute

Choose the lowest route that can meet acceptable decision quality:

| Route | Typical conditions |
| --- | --- |
| `light` | Bounded retrieval/transform or reversible work with low uncertainty and validation need. |
| `standard` | Routine trade-offs, moderate uncertainty, or a small multi-method composition. |
| `high` | Material consequence, error cost, uncertainty, cross-domain synthesis, or independent challenge. |
| `maximum` | Critical exposure, severe downside, regulated judgment, or unusually complex high-stakes synthesis. |

Compute is based on complexity, uncertainty, consequence, error cost, reversibility, context complexity, cross-domain synthesis, and validation requirement. Routine work is cost-first; critical work is quality-first. Higher compute never widens authority.

## Seed recipes

Read `seed-recipes.json` only when one resembles the task. Treat it as a candidate set, not a template requirement. A task label such as `pricing` is insufficient by itself; actual uncertainty, evidence, alternatives, consequence, and reversibility determine the final composition.

## Executive compression

Use high linguistic compression and low information compression:

- `executive-compact`: default answer; preserve all material decisions, evidence, assumptions, uncertainty, constraints, risks, authority, and next action.
- `decision-packet`: material choice with alternatives, acceptance criteria, and gate.
- `full-traceability`: high-risk audit or governance work with sources, reasoning selections, checks, and authorization trail.

Compress introductions, transitions, repeated context, restatements, filler, and obvious prose. Never compress away material alternatives, conflicts, evidence gaps, gates, or rollback conditions.
