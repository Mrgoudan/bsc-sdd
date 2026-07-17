# bsc-sdd

**Spec-driven development for BiSheng C**, built as a standalone [forgeflow](../forgeflow)
pack. The loop:

```
requirement  →  spec (IR)  →  BiSheng C code  →  verify  →  PR
```

It is a sibling of `forgeflow-packs`, shares nothing with it, and runs on the
same generic engine.

---

## The one idea

A compiler you already have is a **sound verifier**. BiSheng C statically checks
ownership, nullability, initialization, and borrows — *inside* every function
**and at every call site**. So the whole safety design, and whether the pieces
fit together, is proven **by compiling**. We spend our own effort only on the
one thing the compiler can't see: **behavior logic**.

### Verification model

|  | **Safety** (null/own/init/borrow) | **Behavior** (counts, states, "iff full") |
|---|---|---|
| **inside a function** | BiSheng C compiler — *sound, free* | tests · LLM residual |
| **between functions** | BiSheng C compiler (annotations at call sites) — *sound, free* | tests · LLM residual |

- **`verify.compile`** is the sound gate. Green ⇒ the entire left column holds,
  end to end. Red ⇒ a real defect.
- **`verify.test`** is the behavior floor — runs the code, sound per case.
- **`behavior` (agent)** is the LLM residual — the value/state predicates the
  compiler can't express. Checked over a **structured assertion slot** today by
  an LLM, swappable for a solver later (see below).

We deliberately do **not** build a program-verification SMT stack: it would
re-derive what the compiler already proves. If the *joins* ever need to be sound
beyond param/ownership matching, that's a small, targeted Z3 check on the
handoff implications — not a foundation.

---

## The IR (`schema/schema.sql`)

- **`specs`** — one per feature, from a requirement.
- **`contracts`** — one per function. `signature` carries the BSC ownership
  shape (the compiler-checked part). Behavior rules live in:
- **`contract_assertions`** — pre/post/side-effects. `text` is always present
  (LLM reads it now); `formal` + `encodable` are the **structured slot** a Z3
  backend reads later, *without re-authoring the spec*.
- **`chains`** — the ordered call steps of a use case (the joins).
- **`verifications`** — one row per checker per target, with `sound=1` for
  compiler/test/z3 and `sound=0` for the LLM residual, so the evidence trail
  shows exactly what was proven vs argued.

## Requirement traceability

On top of the sound core sits a requirement-conformance envelope, threaded by IDs:

```
requirement (prose) --decompose--> R-* atomic items
R-* --author's `fulfills`--> contracts        (the trace)
coverage gate: every in-scope R fulfilled by >=1 contract   (deterministic)
impl --conformance--> each R checked against its mapped code (LLM, sound=0)
```

`out_of_scope` items are exclusions — excluded from coverage. The gate is
deterministic; the conformance verdict is the honest LLM layer over the sound
compiler/test floor.

## What each agent is served

Every agent step gets a deliberate slice — deterministic joins where the need is
exact, retrieval where it's similarity. All of it is provider queries over the
DB, so "why did the model see this" is always answerable.

| agent | decision | served |
|---|---|---|
| `decompose` | prose → `R-*` | raw text · previous `R-*` list (stable ids) · fidelity-gate findings on retry |
| `reqs_check` | is the list faithful? | raw text · the `R-*` list (self-contained by design) |
| `author` | design the API surface | `R-*` items · **`prior_art`** (existing APIs from other features + design idioms, ranked by the requirement texts — reuse-first) |
| `skeleton` | freeze the interface | the module's contracts (`spec_slice`) |
| `gen_fn` | one function body | frozen skeleton · the one contract · compiler errors on retry · **`similar`** (idioms + the most similar already-GREEN function as exemplar) · **`fix_hints`** (past same-error → fixed-body lessons) |
| `behavior` | judge residual predicates | each non-compiler assertion **with its generated body inline** |
| `conform` | impl → requirement | each `R-*` with its fulfilling contracts **and their bodies inline** |

Two of these corpora are self-improving: every green compile grows the exemplar
corpus, and every red-then-green fight records a `fix_lessons` row.

## Pipeline (`workflows/`)

- **`plan`** — `spec.requested` → **`decompose`** (prose → `R-*`) →
  `reqs.load` → author the IR (with `fulfills`) → `spec.load` →
  `spec.validate` (structural checks **+ coverage gate**, deterministic, *not* a
  proof) → emits `spec.validated`.
- **`code_gen`** — `spec.validated` → `codegen.plan` (units = modules) →
  worktree → `codegen` → `codegen.write` → **`verify.compile`** (sound gate;
  `red` → back to `codegen` with the errors, capped) → `verify.test` →
  `behavior` (LLM residual) → `conformance` (impl→req) → emits
  `sdd.completed` / `sdd.blocked`.

---

## Status

Real logic throughout: decompose, coverage gate, spec load/validate, the
compile/test gates, the regenerate-on-red loop (`max_visits`-capped, errors fed
back via `compile_feedback`), module-grouped codegen, and the providers/recorder
for impl→req. The codegen unit is a **module** (functions in one module share
types and must be generated together).

**Intentional "later" (design decisions, not stubs):**

- **Z3 backend for `formal` assertions** — LLM checks the `text` today; a solver
  reads the `formal` slot later. This is the deliberate "do what works now, port
  to a real solver later" call. The slot is populated and ready; nothing to
  re-author when Z3 lands.
- **Multi-module parallel fan-out** — the unit is the module and single-module
  features run as one codegen (correct). Parallelizing *across* modules uses
  `fanout.emit` + join (mechanism identified); wire it when a feature spans
  modules.
- **Forge egress (open a PR)** — no forge target is configured for this pack
  yet; `sdd.completed` is emitted, not pushed. Add a forge + `forge.open_pr`
  step to publish.

## Run

```bash
FORGEFLOW_SECRETS=~/.config/forgeflow/secrets.env \
  ./run-bsc-sdd.sh validate            # check the pack loads
  ./run-bsc-sdd.sh emit spec.requested --data '{"feature_key":"FEATURE-001","requirement":"..."}'
```

See `examples/cjson/` for a worked requirement + its rendered spec.
