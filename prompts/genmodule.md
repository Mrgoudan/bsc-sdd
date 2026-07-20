# Generate the WHOLE module — every function at once

Emit ONE object matching `module_result` (`verdict: MODULE`) whose
`functions` array has one `{contract_key, body}` for EVERY contract in the
module. You see the entire module together, on purpose: the functions call
each other, so generating them in isolation causes integration bugs (a
caller and callee disagreeing about who owns/compiles what). Write them as
one coherent unit.

## Sources (context)
- `skeleton` — the frozen `.hbs` interface: the exact signatures every body
  must match (ownership annotations included). Do not change them.
- `module_contracts` — every contract: signature, summary, behavior
  assertions, and its `calls` (which other functions it invokes and how the
  arguments flow). Honor the call wiring — the argument a caller passes must
  be what the callee expects; do not pass the same input twice, do not use a
  value after it is moved.
- `bsc_skill` — BSC signature/borrow discipline (enforced mechanically).
- `similar` / `select` — green exemplars from past work (reuse idioms).
- `module_bodies` — on a REGEN: the bodies you wrote last time. Fix what the
  feedback flags; re-emit the rest unchanged.
- `compile_feedback` — on a compile RED: the compiler's errors on the whole
  module. Each error names a file:line — map it to the function and fix it.
- `behavior_findings` — on a behavior REGEN: the assertions the code failed,
  with evidence. Make those hold.

## Rules
- Emit a body for EVERY contract (a missing one blocks the build).
- Signatures VERBATIM from the skeleton; BSC discipline (borrows after `*`,
  `_Owned` only when you keep/free, `_Unsafe` scoped to raw-pointer/syscall
  work — see `bsc_skill`).
- Cross-function consistency is the whole point: trace each `calls` edge and
  make caller/callee agree.
`EMPTY` only if there is genuinely nothing to generate.
