# Generate the module — YOU decide the pace and when to verify

Emit ONE object matching `module_result`. You have two decisions each turn,
and you own both:

1. **How much to implement now.** Put the bodies you're confident about in
   `functions` (`{contract_key, body}` each). That can be one function,
   several, or all of them — your call. Functions call each other, so
   implementing related ones together keeps their wiring consistent (a
   caller and callee must agree on ownership and who does what).

2. **Whether to compile now.** Set `verdict`:
   - `READY` — you've implemented enough to want the compiler's judgment.
     The whole module (everything stored so far + this turn) is compiled as
     an EXTERNAL sound gate; if it's red you'll get the errors and another
     turn.
   - `CONTINUE` — you want another turn before compiling (e.g. you did the
     hard core first and want to add the rest with it fresh in mind). You'll
     re-enter with your progress in `module_bodies`.

You are NOT forced into whole-module or one-at-a-time — pick what fits the
module. A small, tightly-coupled module: do it all, `READY`. A big one:
implement in coherent chunks with `CONTINUE`, then `READY` when the last
piece lands.

## Context
- `skeleton` — the frozen `.hbs`: signatures VERBATIM, do not change them.
- `module_contracts` — every contract: signature, assertions, and how they
  call each other. Honor the wiring.
- `bsc_skill` — BSC borrow/ownership discipline (enforced mechanically).
- `module_bodies` — what you've stored so far (previous turns). Add to it or
  fix it; don't rewrite unchanged bodies needlessly.
- `compile_feedback` — on a red: the compiler's errors on the whole module.
  Each names file:line — map it to the function and fix.
- `behavior_findings` — assertions the code failed; make them hold.

`EMPTY` only if there is genuinely nothing to implement.
