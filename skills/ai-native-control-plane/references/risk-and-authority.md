# Risk, epistemics, and authority

Risk determines proof and challenge depth. Authority determines what may happen next. Compute, persona, confidence, acceptance, and validator success cannot substitute for authority.

| Tier | Required control | Execution rule |
| --- | --- | --- |
| Low | Evidence labels appropriate to the claims; light compute is permitted. | No external or system action by default. |
| Medium | Evidence-assumption check, alternatives, explicit assumptions, at least standard compute, and named human decision owner. | Require explicit authorization before implementation. |
| High | High compute, provenance, red-team, epistemic check, stop condition, and explicit human gate. | No execution without bounded authorization. |
| Critical | Maximum compute, red-team, pre-mortem, epistemic check, and qualified human/professional escalation. | Do not automate the decision or execution. |

## Epistemic control

For each material output ask:

1. What do we know?
2. What is inferred?
3. What is assumed?
4. What is missing?
5. What evidence conflicts with the current view?
6. What would materially change the recommendation?

Use `unknown`, `assumption`, `hypothesis`, or `conflicting` when appropriate. Confidence is never evidence. If missing evidence prevents a reliable conclusion, return a bounded unknown and the next evidence gate instead of pseudo-certainty.

## Authority gates

`research` permits information gathering only. `recommendation` permits advice only. `human_decision` records a decision but does not start work. `implementation_authorization`, `controlled_test_authorization`, `operation_authorization`, `publication_authorization`, `external_action_authorization`, and `system_write_authorization` must each identify scope, owner, conditions, and expiry where applicable.

State updates are proposals until `system_write_authorization` or a bounded state-write authorization reference is present. Human acceptance of a recommendation is not implicit permission to modify state or act externally.

In V4, context compilation is read-only, distillation is proposal-only, and
adapter application is the first state-write operation. The adapter must reject
missing, expired, task-mismatched, class-mismatched, or revision-conflicted
authorization. A blocked context gate cannot select a worker or inherit an
execution gate.

## Earned autonomy

Grant autonomy only after explicit human approval and recorded evidence of reliable performance in a narrow, reversible scope. Every grant needs a risk ceiling, conditions, metric, expiry, and revocation trigger. A prior success, validator pass, persona title, or higher compute route cannot create a grant.

## Observation without self-modification

Record composition outcomes for later review. Do not update routing policy from a single result. Use:

```text
Observation -> Repeated Evidence -> Policy -> Automation
```

Any policy change remains a separately reviewed and authorized state change.
