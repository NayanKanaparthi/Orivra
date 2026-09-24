# H7 thresholds, pre-registered

**Registered 2026-09-10, before any comparison arm has been run.** Committed at the design
checkpoint precisely so that no threshold can be chosen after seeing a result. Changing a number
here after an arm has executed invalidates that arm and must be recorded as a re-registration with
its reason, exactly as the deadline harness's query re-registration was.

## What is compared

Each Orivra **component**, independently, against the same corpora and cases:

| Component | Arm with it | Arm without it |
|---|---|---|
| semantic escalation (L5) | full | lexical rungs only |
| bounded reranking (L6) | full | mechanical ordering only |
| query-aware disclosure (N-1) | full | Baseline F (fixed ±2) |
| query-time graph | graph on for its query types | hybrid retrieval, no graph |
| progressive disclosure ladder | full | full-source dump within the cap |
| omission accounting | full | counts without records or handles |
| freshness verification | full | serve without revalidation |

And the whole system against two native-connector baselines: native tools used normally by a strong
agent, and native tools with explicit instructions to read full threads and files.

## The nine dimensions, and the threshold on each

A component **earns its place** if it improves at least one dimension by more than its material
threshold while degrading none past its tolerance. Thresholds are stated as absolute differences on
the pre-registered family sets, measured across all repeats, not on a single case.

| # | Dimension | Material improvement | Tolerance for degradation |
|---|---|---|---|
| 1 | essential-answer correctness | ≥ 5 percentage points | 0 pp — any drop is a fail |
| 2 | supporting-evidence recall | ≥ 8 pp | ≥ 3 pp drop is a fail |
| 3 | citation quality (cited ids that actually support the claim) | ≥ 5 pp | ≥ 3 pp drop is a fail |
| 4 | contradiction and reversal preservation | ≥ 1 case on F5/F17/F21 | 0 — any regression is a fail |
| 5 | **undeclared** omissions (evidence dropped with no record) | any reduction toward 0 | **must be 0 in every arm**; a non-zero count is a defect, not a trade |
| 6 | context characters and model tokens | ≥ 15% reduction | ≥ 25% increase without a gain on 1–4 |
| 7 | latency and source API calls | ≥ 20% reduction | ≥ 50% increase, or breaching the milestone's measured budget |
| 8 | unnecessary reads (fetched but never cited or disclosed) | ≥ 20% reduction | ≥ 30% increase |
| 9 | recovery success and required user intervention | ≥ 5 pp recovery, or fewer interventions | any increase in required interventions |

Dimension 5 is not a trade-off dimension. Undeclared omission is an I-1 violation and no
improvement elsewhere buys it.

## The decision rule

* **Keep** — improves ≥ 1 dimension past its material threshold, degrades none past tolerance.
* **Remove or disable by default** — improves nothing measurably. The component is turned off in
  the default path and the negative result is written into the release report in full: what was
  built, what it cost, and that it did not earn its place.
* **Owner decision** — improves one dimension past threshold while degrading another past
  tolerance. The trade is presented in numbers, not adjectives, and the owner rules.

For the graph specifically, the decision is **per query type** (§8.2a of the plan): a type where it
earns nothing gets it off by default; the machinery is not deleted for failing on a type it was
never built for.

## Sample sizes and what counts as measured

A dimension is measured only where the family set has ≥ 8 cases for that arm, across ≥ 3 repeats.
Below that the result is reported as *underpowered* and the component's disposition defers to the
next milestone rather than being decided on thin evidence. No comparison is reported as a
percentage without its denominator.

## What may not be claimed

Nothing public, in any document, README, résumé line or post, until the corresponding arm has run
and its numbers are committed beside this file. That is the standing rule from v0.1 and it is
unchanged.
