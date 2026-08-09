# AI-Native Control Plane V3

A reusable Codex skill for high-quality decision and execution work. It replaces a mandatory hierarchy of permanent Project CEO, CxO, and specialist personas with one stable control plane plus a task-specific cognition graph.

The core separates four concerns:

```text
Durable state -> Control plane -> Temporary cognition graph -> Optional execution interface
```

State preserves accepted decisions, evidence, risks, and bounded autonomy grants. The control plane classifies work, chooses context and method packs, routes compute, checks knowledge quality and authority, and emits an executive decision packet. Cognition is created for the task and discarded or retained only as evidence supports. Personas are optional presentation and review presets.

## What V3 keeps and changes

| Source | Keep | Change in V3 |
| --- | --- | --- |
| `strategic-right-hand-advisor` | Evidence labels, state continuity, gate separation, human approval boundary, standard-library validation | Remove the required Advisor -> Director chain from the core; treat it as an optional interface preset. |
| `ai-chief-of-staff` | Decision routing, evidence provenance, lifecycle thinking, deterministic package checks | Remove mandatory organization profiles, registered specialists, and fixed role ownership from the default route. |
| Both | Explicit authority, reversible progress, bounded work, decision-ready synthesis | Merge into one compact task packet and risk-adaptive control plane. |

## Repository layout

```text
skills/ai-native-control-plane/  distributable Codex skill
tests/                           positive and negative validator coverage
.github/workflows/validate.yml   GitHub Actions validation
```

## Local validation

Python 3.10+ is sufficient; the package has no runtime dependencies.

```text
python skills/ai-native-control-plane/scripts/validate_artifacts.py --all
python -m unittest discover -s tests -p "test_*.py"
python /path/to/skill-creator/scripts/quick_validate.py skills/ai-native-control-plane
```

## Publication status

The repository is structurally ready for a GitHub push. A public release still requires an explicit human license choice and a separate decision to publish; neither a passing validator nor a local commit grants that authority.
