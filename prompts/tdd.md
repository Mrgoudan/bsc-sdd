# TDD — write the BEHAVIOR tests before any implementation exists

Emit ONE object matching `tests_result`. You are writing the feature's
executable **behavior tests** from the spec alone — no function body has
been generated yet, and that is the point: the tests pin what the system
PROMISES TO DO for its user, so the implementation must come to them.

## Behavior tests, not unit tests

Do NOT write one test per function. Write **scenarios**: each is a user
story exercised through the public interface — a sequence of calls that
builds a situation, acts, and asserts the OBSERVABLE outcome.

- `chains` are the spec's own use cases (ordered call sequences) — turn
  each into at least one scenario.
- `requirements`' `success_signal` items are end-to-end promises — cover
  each testable one.
- `assertions` with `discharged_by: test` tell you which promises need a
  runtime witness — fold them into scenarios where they naturally occur;
  do not manufacture a micro-test per assertion.

Assert only what a USER of the interface can observe (returned values,
reported sizes/kinds, presence/absence, lifecycle effects). Never assert
internal representation.

## The environment: `test_skill`

If `test_skill` is present, it is the PROJECT'S testing environment guide
— harness, fixtures, naming, helpers, where suites live, how they run.
**Follow it over the defaults below**: write tests that belong in that
environment, reusing its fixtures/helpers instead of reinventing them.

Without a `test_skill`: one complete standalone BSC `.cbs` (`body`) —
`#include` the module's `.hbs` (bare name, as the skeleton does), one
`main`, deterministic, no external input; print a stable line per scenario
(`ok <scenario>` / `FAIL <scenario>`) and exit nonzero on first failure.

## BSC discipline (either way)

Your calls must COMPILE against the frozen `skeleton` under the same
soundness rules as the implementation: borrows (`&_Const`/`&_Mut`),
ownership transfer where a signature takes `_Owned`, no use-after-move;
every scenario builds its own fixtures and frees what it creates exactly
once. If a promise is unobservable at this interface, skip it — never
invent accessors that are not in the skeleton.

Fill `scenarios` with `{name, story, covers}` — `story` one line of
given/when/then, `covers` the chain / R-* keys it pins. `EMPTY` only when
nothing is testable.

On a retry, `compile_feedback` carries the compiler's errors on YOUR test
file — fix the test's BSC usage; never bend the interface to the test.
