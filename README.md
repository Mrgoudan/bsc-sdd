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
one thing the compiler can't see: **business logic**.

### Verification model

|  | **Safety** (null/own/init/borrow) | **Business** (counts, states, "iff full") |
|---|---|---|
| **inside a function** | BiSheng C compiler — *sound, free* | tests · LLM residual |
| **between functions** | BiSheng C compiler (annotations at call sites) — *sound, free* | tests · LLM residual |

- **`verify.compile`** is the sound gate. Green ⇒ the entire left column holds,
  end to end. Red ⇒ a real defect.
- **`verify.test`** is the business floor — runs the code, sound per case.
- **`business` (agent)** is the LLM residual — the value/state predicates the
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
  shape (the compiler-checked part). Business rules live in:
- **`contract_assertions`** — pre/post/side-effects. `text` is always present
  (LLM reads it now); `formal` + `encodable` are the **structured slot** a Z3
  backend reads later, *without re-authoring the spec*.
- **`chains`** — the ordered call steps of a use case (the joins).
- **`verifications`** — one row per checker per target, with `sound=1` for
  compiler/test/z3 and `sound=0` for the LLM residual, so the evidence trail
  shows exactly what was proven vs argued.

## Pipeline (`workflows/`)

- **`spec_author`** — `spec.requested` → author the IR → `spec.load` →
  `spec.validate` (deterministic structural checks, *not* a proof) →
  emits `spec.validated`.
- **`sdd_build`** — `spec.validated` → `codegen.plan` → worktree → `codegen`
  → `codegen.write` → **`verify.compile`** (sound gate) → `verify.test`
  → `business` (LLM residual) → emits `sdd.completed` / `sdd.blocked`.

---

## Status: skeleton

Loadable shape with real deterministic logic (spec load/validate, compile/test
gates, providers). Clearly-marked stubs remain:

- `codegen.plan` enumerates units but does not yet fan out per-unit in parallel
  (a group/`_join` — the payload-optimization win).
- `verify.compile` on `red` dead-ends at `sdd.blocked`; the regenerate/fix loop
  is TODO.
- Worktree-path threading into `codegen.write` is best-effort.
- No forge egress yet (PR open).
- The Z3 backend for `formal` assertions is a later swap; today it's LLM-only.

## Run

```bash
FORGEFLOW_SECRETS=~/.config/forgeflow/secrets.env \
  ./run-bsc-sdd.sh validate            # check the pack loads
  ./run-bsc-sdd.sh emit spec.requested --data '{"feature_key":"FEATURE-001", ...}'
```
