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

- **`plan`** — `spec.requested` → `decompose` (prose → `R-*`) →
  `req_questions` → `persist_reqs` → `fidelity_check` (raw ↔ R-items) →
  `design_brief` → **`design_gate`** (human) → `write_spec` →
  `spec_questions` → `persist_spec` → `validate_spec` (coverage gate) →
  `design_check` (mechanical qualifier-join gate) → `write_docs` → emits
  `spec.validated`.
- **`code_gen`** — `spec.validated` → worktree → skeleton (frozen interface)
  → per-function loop: `gen_function` → **`compile`** (sound gate; `red` →
  regenerate with errors, capped) → `smoke_test` → `behavior_check` (LLM
  residual) → `conformance_check` (impl→req) → `record_verdicts` →
  `write_docs` → emits `sdd.completed` / `sdd.blocked`.
- **`fn_route` + `fn_edit`** — "change this function" from the board:
  body-only edits re-run gen→compile→smoke with no spec ceremony; an
  interface-touching edit raises a human decision (**`interface_gate`**) and
  only a *picked* verdict escalates into the full pipeline
  (`spec.requested` + `edit_request`).

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

## Running it

**Prereqs (machine-specific, all declared in `project.yaml paths:`):**
a BiSheng clang build (`paths.bsc_clang`), the libcbs sources
(`paths.libcbs_src`), an anchor git repo for build worktrees
(`paths.repo` — any repo with one commit), a projects folder
(`paths.projects`), and a secrets env file (mode **0600**) holding
`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` for the agents. Optional:
`dot` (graphviz) on PATH makes the board's pipeline graphs pretty.

**1. Start the daemon (one per state dir, flock-enforced):**

```bash
FORGEFLOW_SECRETS=~/.config/forgeflow/secrets.env ./run-bsc-sdd.sh run
```

The board serves at **http://127.0.0.1:8791** (loopback; SSH-tunnel it
from elsewhere). `./run-bsc-sdd.sh validate` checks the pack loads
without starting anything.

**2. Start a feature.** Put the human inputs in the projects folder —
this repo stays infra-only:

```
~/bsd/bsc-sdd-projects/<FEATURE-KEY>/
  requirement.md      # pure behavior, no implementation vocabulary
  smoke.cbs           # the runnable behavior floor for this feature
```

Then on the board's front page, open **"start a feature run"**: feature
key, paste the requirement *path or text*, base branch, click start.
(CLI twin: `./run-bsc-sdd.sh emit spec.requested --data '{...}'`.)

**3. While it runs.** The front page shows the run as a live pipeline
(expand any workflow for its step graph; click a block for what it
does). You will be pulled in at exactly two kinds of moments:

- **Decisions** (`/decisions`, desktop-notified): design forks and
  interface-change gates. Click a card to choose it; one "Reject all &
  regenerate" button with an optional message sends the agent back.
- **Questions**: `./run-bsc-sdd.sh questions`, answer with
  `./run-bsc-sdd.sh answer Q-1=<choice>` (or `--accept-defaults`);
  `./run-bsc-sdd.sh discuss` opens an interactive session over a
  decision thread.

**4. What you get.** `run/docs/<FEATURE-KEY>/spec.md` (WHAT) +
`design.md` (HOW), regenerated at every milestone; the verification
trail (sound vs argued, per assertion) on the board and in the DB; the
green code itself in the DB (`codegen_units`), rehydratable into any
worktree. `/run/<FEATURE-KEY>` is the complete audit trail.

**5. Change something later.**

- *A function*: click it on the board → "ask AI to change this
  function". Body-only edits skip the spec ceremony; interface-touching
  edits come back as a decision.
- *The requirement*: edit the doc, then "revise →" on the finished run
  (re-launches with the same feature key). Only what actually changed
  re-runs — R-keys and contract hashes are stable.

---

## Making changes to the pack

Anatomy — each concern lives in exactly one place:

| you want to change… | edit |
|---|---|
| paths, models/agents, concurrency, board, launch forms | `project.yaml` |
| the shape of a workflow (steps, routing, gates, caps) | `workflows/*.yaml` |
| what an agent is told | `prompts/*.md` |
| what an agent must return (verdict enum = routable outcomes) | `schemas/*.yaml` |
| deterministic logic (blocks) and context providers | `blocks/*.py` |
| pack tables / the IR | `schema/schema.sql` (+ `scripts/migrate_db.py` for column adds) |
| test harness / notifications / CLI helpers | `scripts/` |

Rules of the game (the engine enforces them **fail-loud at startup** —
`./run-bsc-sdd.sh validate` after every edit):

- A step's `outcomes:` must map the block's outcome set **exactly**; an
  llm step's schema `verdict.enum` extends that set — enum values *are*
  the routable outcomes.
- Every referenced file (prompt, schema, block, path) must exist at
  load; events must be declared under `emits:`; a `select:`/corpus must
  name real tables.
- New blocks: `@block("name", exec_class, {outcomes})` in a
  `blocks/*.py` file registered under `blocks:` in `project.yaml`. New
  context: `@context_provider("name")` in `blocks/providers.py`, then
  list it under the step's `context:`.
- The board is config, not code: panels/views/launch forms are
  SELECT-only SQL + field lists in `project.yaml board:`; a column
  aliased `link:<view>` becomes a cross-link; `thread_key` is what
  groups tasks into runs.
- **Restart the daemon to pick up changes.** In-flight tasks park as
  `definition_changed` rather than continuing on a stale definition —
  prefer editing between runs; `queue unpark` resumes after you're done.
- Keep it three-layered: engine = mechanism (generic, separate repo),
  this pack = meaning (BSC + SDD), `paths.projects/<key>/` = per-feature
  human inputs. Project material never lands in this repo.
