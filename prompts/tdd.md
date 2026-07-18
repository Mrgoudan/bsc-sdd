# TDD — write the tests before any implementation exists

Emit ONE object matching `tests_result`. You are writing the feature's
executable acceptance tests **from the spec alone** — no function body has
been generated yet, and that is the point: the tests pin what the spec
PROMISES, so the implementation must come to them.

## Sources (all in context — use nothing else)

- `skeleton` — the frozen module interface (.hbs): the exact types and
  signatures your test calls must satisfy (ownership annotations included).
- `spec_slice` / `assertions` — every contract with its pre/post/side-effect
  predicates. Every `post` assertion whose `discharged_by` is `test` MUST
  have at least one case.
- `requirements` — the `success_signal` items are end-to-end scenarios;
  cover each one that is testable at this interface.

## The file

One complete BSC `.cbs` (`body`): `#include` the module's `.hbs` (bare name,
as the skeleton does), one `main`, deterministic, no external input. For each
check print a stable line (`ok <case>` / `FAIL <case>`) and exit nonzero on
the first failure. Respect BSC discipline at call sites: borrows
(`&_Const`/`&_Mut`), ownership transfer where a signature takes `_Owned`,
no use-after-move — your test must COMPILE against the skeleton with the
same soundness rules as the implementation.

Fill `cases` with `{name, covers}` so each case traces to the R-* item or
contract it pins. Keep cases independent; build the fixtures each case
needs; free everything you create exactly once.

If the interface makes a predicate untestable from outside (internal state
with no observer), skip it — do not invent accessors that are not in the
skeleton. `EMPTY` only when there is genuinely nothing testable.

On a retry, `compile_feedback` carries the compiler's errors on YOUR test
file — fix the test's BSC usage; never change the interface to suit the test.
