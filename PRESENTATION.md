# bsc-sdd — the 20-minute talk (no live demo)

> Pure talk track. Slide suggestions in [brackets]; everything else is
> speakable. LEAD: deterministic adherence, then requirement fulfillment.
> Supporting: auditable · context management · data flywheel.

## The one-liner (say it twice: open and close)

**A requirement goes in; verified BiSheng C comes out — on rails a model
cannot leave, with every requirement provably traced to code that checks
against it.**

---

## 0:00–1:30 · Open with the two questions

- Every AI-codegen pitch dies on the same two questions. One: **"does the
  process adhere to anything?"** — or does the model freewheel,
  differently every run, un-reproducibly? Two: **"does the generated
  code actually do what was asked?"** — not "does it look right", but
  *fulfill the requirement, item by item, with evidence*.
- This talk leads with our answers to exactly those two, because they are
  the two things we designed for. The rest — auditability, context
  discipline, a data flywheel — falls out of the same architecture.

## 1:30–3:30 · The flow, in two minutes (context for everything after)

[slide: the flow — one straight stem, forks off it]

```
 requirement.md (pure behavior, English)
   │ PLAN      decompose → R-items (stable IDs) → fidelity gate
   │           design options → ██ HUMAN picks ██ → write spec:
   │           one CONTRACT per function (BSC ownership signature +
   │           behavior assertions + fulfills-trace to R-items)
   │           → mechanical coverage + call-handoff checks
   │           → spec.md / design.md generated
   │ CODE_GEN  freeze interface → (optional TDD tests first) →
   │           per-function: generate → COMPILE (sound) → tests →
   │           LLM behavior check → per-requirement conformance
   │           → docs refreshed with the verification trail
   │ FN_EDIT   later changes: body-only = compile+test, no ceremony;
   │           interface-touching = human gate → only the delta re-runs
```

- One database is the single source of truth; the spec, the documents,
  the dashboards, the code files are all **projections** of it. The
  human appears at exactly two kinds of moments: real design forks, and
  interface changes.

## 3:30–7:30 · LEAD PILLAR 1: DETERMINISTIC ADHERENCE

- The claim: **the model works inside rails a human declared, and the
  same input gives the same process.** Concretely:
- Every workflow is a declared graph, proven **total at startup**: an
  agent must answer with a verdict from a human-authored enum, and
  every possible verdict — including "the model produced garbage" — has
  a mapped destination. A model chooses among edges; it can never
  invent one.
- Duplicates are structurally impossible: every task is keyed by a
  content hash of its payload. Double-clicks, replayed events,
  crashed-and-restarted emitters — all collapse into the same task.
  Repetition on purpose is an explicit flag.
- The load-bearing gates are not model calls: requirement coverage and
  the qualifier-join check are pure mechanics — milliseconds,
  unarguable. This week that gate **rejected the model's proposed
  design before any code existed** — a phantom parameter and two
  borrow-versus-value handoffs. The recovery was equally disciplined: a
  dedicated repair agent saw only the three broken joins and the
  human-picked design, fixed exactly those, every gate re-ran over the
  merged whole, green. The 19 minutes of spec authoring were **not**
  repeated — recovery cost one small model call.
- Adherence extends across time: stable requirement IDs and
  content-hashed contracts make every re-run **incremental by
  construction**. Change one sentence of the requirement and exactly
  the functions that sentence touches regenerate — in the JSON run, 10
  of 34. Human decisions are durable too: a picked design survives
  retries and is never re-asked; only a genuinely new question asks
  again.

## 7:30–13:00 · LEAD PILLAR 2: REQUIREMENT FULFILLMENT

[slide: three-tier table]

| tier | what it checks | soundness |
|---|---|---|
| BiSheng C compiler | ownership / null / init / borrow — inside every function AND at every call site | **sound** |
| test suites (smoke + optional TDD) | real behavior, executed | **sound per case** |
| LLM residual | behavior assertions; per-requirement conformance | argued — labelled sound=0 |

- Start from the requirement side: the English document is decomposed
  into **atomic requirement items with stable IDs** — and a fidelity
  gate checks the decomposition against the original text (nothing
  dropped, nothing invented, nothing distorted) before anything else
  happens. The spec can only be built on requirements that survived
  that gate.
- Traceability is **total and two-way**: every requirement item maps to
  the functions that fulfill it — many-to-many — and a mechanical gate
  guarantees totality: *no orphan requirement, no untraceable function*.
  Code that serves no stated requirement is rejected at spec time.
- Then three tiers of checking, honestly labelled:
  - the **compiler** proves the entire safety column — and because
    generated signatures carry ownership annotations, it also proves
    every *call handoff* between functions. Whether the pieces fit
    together is proven by compiling.
  - **tests** execute the behavior — the human-authored smoke floor,
    plus optionally a TDD suite the system derives from the spec
    *before any implementation exists* (implementation-blind by
    construction).
  - the **LLM residual** judges what neither can see: behavior
    assertions, and finally **conformance per requirement — each item
    judged against exactly the code that claims to fulfill it**. In our
    JSON-library run: 77 of 77 fulfilled, recorded item by item.
- Every verdict lands in a ledger with a soundness flag. **We never
  launder a model opinion into a proof** — "was this proven or argued?"
  is a column, not a debate. And every assertion carries a structured
  formal slot: attach a solver later, re-author nothing.
- War stories — one catch per tier, each invisible to the other two:
  1. compiler: ownership misuse in model-written code — plausible,
     provably wrong;
  2. tests: a length-includes-terminator bug that type-checks
     perfectly;
  3. LLM: a **specification contradiction** (duplicate keys promised
     two incompatible behaviors) — no compiler or test can catch a spec
     that is wrong about itself.

## 13:00–15:00 · Supporting: AUDITABLE

- Every run keeps its complete story: every task, attempt, and step —
  which block ran, what went in, what came out, how long it took.
- Every model call keeps **the exact prompt bytes**, raw output, parsed
  verdict, and a context manifest listing every piece of context and
  its origin. "Why did the model see this?" is a query.
- Human decisions are rows, not chat: options offered, pick, rejections,
  comments, rounds. The design discussion IS the audit trail.
- Documents cannot drift: spec.md and design.md are regenerated from
  the database at every milestone — they can't disagree with the system.

## 15:00–16:30 · Supporting: CONTEXT MANAGEMENT

- No agent inhales the repository. Each call gets a **measured slice**:
  this one contract, the frozen interface, the compiler's errors on a
  retry, one retrieved exemplar — tens of kilobytes.
- Retrieval is an engine-level cascade: independent channels — lexical,
  semantic, recency, learned utility — rank-fused, de-duplicated, packed
  into a **hard byte budget** that fails loudly *before* the call. No
  silent truncation, ever.
- Model-written summaries (cached by content hash) keep long knowledge
  findable — under a strict rule: summaries are **claims that inform
  context, never decisions that gate transitions**.

## 16:30–18:00 · Supporting: THE DATA FLYWHEEL

- The system labels its own training data as a side effect of running:
  - every green-compiled function becomes a **retrievable exemplar** for
    the next one;
  - every red-then-green fight records *(compiler error → the body that
    fixed it)* — the next similar error retrieves the lesson. **It
    learns from its own compiler fights.**
  - what-was-shown is joined against how-tasks-ended: context that
    co-occurs with success earns retrieval rank. Trained on the outcome
    ledger, no annotators.
- One substrate, many consumers: the same database powers the docs, the
  review board, future tooling — and would be the fine-tuning set if we
  ever want one.

## 18:00–20:00 · Close

- The one breath: **a process that cannot leave its rails, cannot run
  twice by accident, and re-runs only what changed; every requirement
  traced to code and checked by the strongest available checker; fully
  recorded; improving with every run — on an engine that contains zero
  compiler knowledge and runs other domains as packs.**
- Roadmap, honestly: harvest existing headers into contracts (the
  design gate then covers the whole brownfield boundary), adopt legacy
  modules for surgical edits on code we didn't generate, a landing step
  committing verified milestones, Z3 on the encodable assertion slot.
- Landing line: *"Spec-driven development is usually a methodology
  slide. This is a running machine with an audit trail — every claim in
  this talk is a row in a database, and I can show you any of them
  after."*

---

## If asked (backup answers)

- **"What if the model hallucinates?"** It answers within a declared
  verdict enum; malformed output is re-asked, then parked as a declared
  failure state. It cannot route the workflow anywhere a human didn't
  wire.
- **"What if the LLM check is wrong?"** It's labelled *argued*, never
  sound; the sound tiers gate independently; the solver slot exists to
  promote argued checks to proofs.
- **"Very large existing codebases?"** Honest: today's unit is a fresh
  module; calls *into* existing code are already compiler-checked at
  build. Harvest + module adoption (roadmap) extend the gates to the
  brownfield.
- **"Cost?"** Per-function calls with measured context; retries capped;
  repairs scoped to the affected contracts; unchanged stages resume free
  from recorded results; duplicates structurally impossible.
- **"Why not fine-tune?"** Orthogonal — this is process infrastructure;
  any model plugs in, and the flywheel data is the fine-tuning set if
  ever wanted.
