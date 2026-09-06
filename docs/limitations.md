# MealMesh Limitations & Honest Scope

This is a hackathon prototype and a learning project. Read this before drawing
operational conclusions.

## Data

- **All operational data is simulated.** Resources, capacities, locations, and
  map positions are synthetic demo data (`synthetic_data=True` on the models).
  Nothing here reflects real volunteers, organizations, or meal sites.
- Capacities and reliabilities are illustrative constants, not measurements.

## Model scope

- The capability ontology is intentionally tiny (`van_certified_driver`,
  `food_handler`, `site_keyholder`). Real meal-program doctrine is far larger.
- Capability derivation is keyword/synonym based. It is deterministic and
  testable, but it is not a substitute for coordinator judgment.
- The solver optimizes **fewest resources** subject to capability coverage and a
  capacity floor. It does not model routing, food quantity, vehicle scheduling,
  shift overlap, or cost trade-offs.
- Because the solver has no notion of distance, "who can reach this site" is
  handled by scoping the catalog to each site's roster before CP-SAT runs (the
  same pattern as the opt-in filter) rather than as a solver constraint. Many
  coalitions therefore tie on cost, and catalog order breaks the tie — that
  order is a presentation choice, not an optimality claim.
- A driver resource implies access to one of the food bank's vans for one site.
  Vans are displayed as assets but are not independently paired with drivers in
  v1.
- Resilience testing is single-resource removal (one failure at a time), not
  correlated or cascading failures.
- The hypergraph `lambda2` metric is a structural connectivity signal only; it is
  explicitly **not** used for operational criticality (that stays with
  remove-and-re-solve).

## LLM scope

- The LLM only extracts facts and can hallucinate or mis-parse; the HITL review
  gate and strict schemas contain this, but extraction is not guaranteed correct.
- Prompt-injection guardrails are heuristic and can have false positives/negatives.
  They are defense-in-depth; the real protection is that the LLM cannot allocate.

## Operational readiness

- Not deployed to AgentCore; runs locally. See `docs/architecture.md` for the
  deployment path.
- No persistence, authn/authz, rate limiting, or audit trail beyond structured
  logs.
- SLOs in `docs/slos.md` are starting targets, not validated production numbers.

## Non-negotiable rule (kept)

MealMesh may silently restaff only from the explicitly opted-in bench, and only
from volunteers on that site's roster. Recruiting Jordan, Marcus, Tom, or any
other non-opted-in person always remains a human decision.
