# V3 to V3.1 audit and change map

V3 already has the correct architecture: durable state, a control plane, a task-specific temporary cognition graph, and optional execution interfaces. V3.1 changes the composition vocabulary and makes selection observable; it does not replace the architecture.

## Change map

| Action | V3 element | V3.1 treatment |
| --- | --- | --- |
| KEEP | Durable state, temporary graph, optional personas, task classification, context assembly | Preserve as core architecture. |
| KEEP | `light / standard / high / maximum`, risk tiers, human authority, authority gates | Preserve names and semantics; connect compute to explicit selection signals. |
| KEEP | Evidence taxonomy, `confidence_is_evidence = false`, no implicit state write, earned autonomy | Preserve and validate as invariants. |
| KEEP | Executive compression, risk-adaptive governance, validator/test pattern | Preserve; make output modes and high-risk checks explicit. |
| MODIFY | `method_packs` | Split into `thinking_methods`, `quality_checks`, and `synthesis_steps`; keep legacy aliases for V3 packets. |
| MODIFY | `domain_packs` | Rename to first-class `domain_lenses`; keep the ten V3 identifiers as compatible lenses. |
| MODIFY | Cognition graph | Nodes now reference typed methods, lenses, checks, or synthesis and carry selection rationale. |
| MODIFY | Task packet | Add composition signals, cognitive needs, selected composition, compute rationale, deviations, and observability. |
| MODIFY | Project state | Add observation records without allowing observations to change routing policy automatically. |
| ADD | Primitive registry | Add 20 lightweight reusable definitions across methods, quality checks, and synthesis. |
| ADD | Domain lens registry | Add constraints and evidence standards without creating departments. |
| ADD | Cognitive composition engine | Compose from diagnosed needs, task signals, optional recipe priors, and explicit deviations. |
| ADD | Seed recipes | Add product adoption, investment, organization, pricing, and brand priors; all are optional. |
| ADD | Juno fixtures and validator rules | Test realistic selection, anti-overcomposition, epistemics, authority, and context relevance. |
| MOVE | `workflow` | Move from method pack to cross-domain lens because it supplies workflow-specific questions and evidence standards, not a general reasoning operation. |
| MOVE | `behavioral` | Rename to `behavior` and move to cross-domain lens; retain `behavioral` as a legacy alias. |
| MOVE | `financial` | Move to `finance` lens. Select `expected-value`, `sensitivity-analysis`, or `opportunity-cost` separately when the task needs those operations. |
| DEPRECATE | Fixed `method_packs` and `domain_packs` authoring | Accept for V3 compatibility but do not emit from new V3.1 composition. |
| DEPRECATE | Recipe-as-router and persona-as-worker assumptions | Recipes remain priors; personas remain communication/review/domain presets and cannot grant authority. |

## Compatibility mapping

| V3 value | V3.1 category and value |
| --- | --- |
| `problem-framing` | thinking method: `problem-framing` |
| `evidence` | quality check: `evidence-assumption-check` |
| `hypothesis-led` | thinking method: `hypothesis-led` |
| `MECE` | thinking method: `MECE` |
| `causal` | thinking method: `causal-analysis` |
| `workflow` | domain lens: `workflow` |
| `behavioral` | domain lens: `behavior` |
| `financial` | domain lens: `finance`; no method is inferred without a diagnosed need |
| `scenario` | thinking method: `scenario-analysis` |
| `prioritization` | thinking method: `pareto-prioritization` |
| `red-team` | quality check: `red-team` |
| `synthesis` | synthesis step: `synthesis` |

V3 `domain_packs` identifiers remain valid V3.1 lens identifiers. A V3 task packet can be normalized for validation; persistent records at schema `3.0.0` remain readable. New packets must use schema `3.1.0` and the typed composition fields.

## Deliberately unchanged

- Persistent state remains a record of accepted decisions, evidence, risks, questions, grants, and observations. It is not intelligence.
- Temporary cognition is rebuilt around each task and is not promoted to a permanent team.
- Higher compute, a persona name, a successful test, or a prior success cannot create authority.
- External action and state mutation remain behind separately scoped human authorization.
- V3.1 observes routing outcomes but does not self-modify policy.
