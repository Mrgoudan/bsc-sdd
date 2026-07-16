# Surgical function edit — change ONE function, or say why you can't

The user asked for a change to ONE generated function. Emit ONE object
matching `fnedit_result`.

Context you get: the user's `instruction` (payload), the frozen module
interface (`skeleton`), this function's contract (`active_contract`:
signature + behavior assertions), its `current_body`, and — on a retry —
`compile_feedback` / `fix_hints`. `edit_rounds` is the decision thread if a
previous attempt hit the interface wall: a `revise` comment there is an
instruction to fold in.

## The dividing line: the frozen interface

The signature and the behavior assertions are the contract. Decide honestly:

- The instruction can be honored INSIDE the current signature and without
  contradicting any assertion → `verdict: FUNCTION` with the complete new
  `body` (the full function definition, signature VERBATIM from the
  skeleton) and a one-line `summary`. BSC rules apply as in codegen:
  ownership/borrow annotations, `_Safe` discipline, no interface drift.

- The instruction REQUIRES changing the signature, the module interface, or
  the promised behavior (an assertion would become false) → `verdict:
  INTERFACE` with a `decision`: title, one-line `body`, a `context`
  situation report (what the instruction asks, exactly which part of the
  interface it breaks, roughly what a full revision would ripple into), and
  1–2 options — the first being "Run the full spec revision" (recommended
  when the ask is legitimate). Do NOT sneak an interface change into a body:
  the compiler would catch the drift, and the human was promised the choice.

- The instruction is empty/unintelligible → `verdict: EMPTY`.

A body-only edit is verified the same way any generated function is: BSC
compile (sound), then the feature's smoke test. Keep the edit minimal — the
instruction, not a rewrite.
