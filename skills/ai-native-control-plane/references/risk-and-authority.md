# Risk and authority

Risk determines proof and review depth. Authority determines what may happen next. Never use one as a substitute for the other.

| Tier | Typical exposure | Required controls | Execution rule |
| --- | --- | --- | --- |
| Low | Reversible internal analysis | Evidence labels and clear scope | No external or system action by default. |
| Medium | Material trade-off or limited external effect | Alternatives, assumptions, and named human decision | Require explicit authorization before implementation. |
| High | Privacy, security, finance, legal, safety, reputational, or hard-to-reverse effect | High compute, provenance, red-team, stop condition, and human decision | No execution without a bounded authorization. |
| Critical | Potential severe harm or legally reserved judgment | Maximum compute, independent challenge, professional/human escalation | Do not automate decision or execution. |

## Authority gates

`research` permits information gathering only. `recommendation` permits advice only. `human_decision` records a decision but does not start work. `implementation_authorization`, `controlled_test_authorization`, `operation_authorization`, `publication_authorization`, `external_action_authorization`, and `system_write_authorization` must each identify scope, owner, conditions, and expiry where applicable.

## Earned autonomy

Grant autonomy only after explicit human approval and recorded evidence of reliable performance in a narrow, reversible scope. Every grant needs a risk ceiling, conditions, metric, expiry, and revocation trigger. A prior success, validator pass, or persona title cannot create a grant.
