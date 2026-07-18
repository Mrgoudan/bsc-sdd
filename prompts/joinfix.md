# Join repair — fix EXACTLY the broken handoffs, touch nothing else

The mechanical design gate rejected the spec: specific call handoffs are
incompatible. You fix those joins and only those joins. Emit ONE object
matching `spec_result` (`verdict: SPEC`).

## Inputs

- `design_breaks` — the gate's findings, each `{in, callee, param, reason,
  source?}`: the caller contract, the callee, the offending parameter, and
  WHY it is broken (phantom param, borrow-vs-value, use-after-move, unknown
  callee…).
- `broken_contracts` — the full current IR of every contract on either side
  of a break: signature, assertions, fulfills, calls. This is your working
  set.
- `design_choice` — the human-picked overall design. The repair must stay
  inside it.

## The rules

- Emit ONLY the contracts you changed — typically the ones in
  `broken_contracts`; a complete entry each (contract_key, module,
  signature, summary, impl_file, assertions, fulfills, calls). A
  deterministic merge folds them into the untouched remainder — anything
  you do not emit survives verbatim, so DO NOT re-emit unchanged
  contracts.
- Never rename a `contract_key`; never add or drop features. Fix the
  handoff: correct the `calls` args to name real params, adjust a
  signature to take a borrow where the caller can only lend, move a
  consume so an owned value isn't used after transfer — whatever the
  stated `reason` demands, with BSC discipline.
- If fixing a join forces a signature change on a callee, emit that callee
  too (it is in your working set) and keep its assertions/fulfills intact
  apart from what the change requires.
- Prefer the smallest repair that makes every listed break impossible;
  re-check your own output against each break before emitting.

`QUESTIONS` only if a break genuinely cannot be repaired without a
decision that is not yours (rare); `EMPTY` never — the gate found real
breaks, so there is something to fix.
