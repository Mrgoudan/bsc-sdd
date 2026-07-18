# bsc-sdd — high-level design

> The reviewed, human-level picture of the system. One diagram, one
> regeneration prompt, one machine-readable flow table. **High level only** —
> the live, always-current step-level graph is on the board (front page,
> expand any workflow); per-feature WHAT/HOW projections are generated into
> `run/docs/<feature>/`. This file is for review, onboarding, and as seed
> data for future design tasks.

## The system in one sentence

A requirement goes in; a **spec** (contracts + behavior assertions with
stable IDs) is negotiated with a human at real forks; **BiSheng C code** is
generated function-by-function against a frozen interface; everything is
verified by a three-tier model — **compiler (sound) → tests (sound per
case) → LLM (argued residual)** — with full requirement-to-code
traceability, and every artifact (docs, verdicts, bodies) is a projection
of one database.

## Flow (high level)

```mermaid
flowchart LR
  classDef human  fill:#f5e6bf,stroke:#9a6700,color:#5c4a00;
  classDef model  fill:#e6dcfa,stroke:#7c3aed,color:#3c1d8f;
  classDef mech   fill:#e8eaed,stroke:#5c6773,color:#1f262e;
  classDef data   fill:#dff0e4,stroke:#1a7f37,color:#0f4c22;

  REQ[/"requirement.md<br/>(+ smoke.cbs, testing.md)"/]:::data

  subgraph PLAN ["plan — requirement → verified spec"]
    DECOMP["decompose to R-items"]:::model
    FID{"fidelity gate<br/>raw ↔ R-items"}:::model
    BRIEF["design options<br/>(or SKIP)"]:::model
    DGATE{{"HUMAN:<br/>design gate"}}:::human
    WSPEC["write spec IR<br/>contracts + assertions"]:::model
    VAL{"coverage +<br/>qualifier-join check"}:::mech
  end

  subgraph CODEGEN ["code_gen — spec → verified BSC"]
    TDD["behavior tests first<br/>(optional TDD)"]:::model
    GEN["per-function codegen<br/>against frozen skeleton"]:::model
    COMP{"BSC compiler<br/>SOUND gate"}:::mech
    RUNT{"smoke + TDD suites<br/>sound per case"}:::mech
    BEH["LLM behavior check<br/>(argued residual)"]:::model
    CONF["conformance<br/>impl → every R-item"]:::model
  end

  subgraph EDIT ["fn_edit — change one function"]
    FEDIT["edit against frozen<br/>interface"]:::model
    IGATE{{"HUMAN:<br/>interface gate"}}:::human
  end

  DB[("pipeline DB<br/>single source of truth")]:::data
  DOCS[/"spec.md (WHAT)<br/>design.md (HOW)"/]:::data
  BOARD[["board: runs · decisions ·<br/>audit · entity views"]]:::data

  REQ --> DECOMP --> FID --> BRIEF --> DGATE --> WSPEC --> VAL
  FID -. FAIL: re-decompose .-> DECOMP
  DGATE -. reject all + message .-> BRIEF
  VAL -- "spec.validated" --> TDD --> GEN --> COMP --> RUNT --> BEH --> CONF
  COMP -. red: regenerate (capped) .-> GEN
  BOARD -- "change this function" --> FEDIT --> COMP
  FEDIT -- "needs interface change" --> IGATE
  IGATE -- "picked: full revision" --> DECOMP
  VAL --> DOCS
  CONF --> DOCS
  PLAN <--> DB
  CODEGEN <--> DB
  DB --> BOARD
```

Legend (matches the board): **amber = human decides**, **violet = model
works**, **steel = deterministic machinery**, **green = data/artifacts**.

## Diagram prompt (Lucidchart / draw.io / any AI diagram tool)

Paste this to regenerate or restyle the picture:

> Draw a left-to-right flowchart of a spec-driven code-generation pipeline
> with three swimlane containers and four standalone shapes.
> Container "plan (requirement → verified spec)" contains, in order:
> "decompose to R-items" (violet, model), "fidelity gate" (violet diamond),
> "design options" (violet), "HUMAN design gate" (amber hexagon), "write
> spec IR" (violet), "coverage + qualifier-join check" (steel diamond).
> Container "code_gen (spec → verified BSC)" contains: "behavior tests
> first (optional TDD)" (violet), "per-function codegen against frozen
> skeleton" (violet), "BSC compiler SOUND gate" (steel diamond), "smoke +
> TDD suites" (steel diamond), "LLM behavior check" (violet), "conformance
> impl→R-items" (violet). Container "fn_edit (change one function)"
> contains: "edit against frozen interface" (violet) and "HUMAN interface
> gate" (amber hexagon). Standalone: "requirement.md + smoke.cbs +
> testing.md" (green document, far left), "pipeline DB — single source of
> truth" (green cylinder, bottom center), "spec.md + design.md" (green
> documents, right), "board" (green UI shape, bottom right).
> Solid arrows: requirement → decompose → fidelity → options → design gate
> → write spec → checks; checks —"spec.validated"→ TDD → codegen → compiler
> → suites → behavior → conformance; conformance → docs; board —"change
> this function"→ edit → compiler; edit —"needs interface change"→
> interface gate —"picked"→ decompose. Dashed loop-backs: fidelity FAIL →
> decompose; design-gate "reject all + message" → options; compiler red →
> codegen (capped). Both big containers connect bidirectionally to the DB;
> DB → board. Color rule: amber = human decision, violet = LLM work,
> steel = deterministic machinery, green = data.

## Flow data (machine-readable — for review & future tasks)

```yaml
actors: {human: amber, model: violet, machinery: steel, data: green}
nodes:
  - {id: requirement, actor: data,      in: project-folder}
  - {id: decompose,   actor: model,     wf: plan}
  - {id: fidelity,    actor: model,     wf: plan, gate: true}
  - {id: options,     actor: model,     wf: plan}
  - {id: design_gate, actor: human,     wf: plan, gate: true}
  - {id: write_spec,  actor: model,     wf: plan}
  - {id: validate,    actor: machinery, wf: plan, gate: true}
  - {id: tdd,         actor: model,     wf: code_gen, optional: true}
  - {id: codegen,     actor: model,     wf: code_gen}
  - {id: compiler,    actor: machinery, wf: code_gen, gate: true, sound: true}
  - {id: suites,      actor: machinery, wf: code_gen, gate: true, sound: true}
  - {id: behavior,    actor: model,     wf: code_gen, sound: false}
  - {id: conformance, actor: model,     wf: code_gen, sound: false}
  - {id: fn_edit,     actor: model,     wf: fn_edit}
  - {id: iface_gate,  actor: human,     wf: fn_edit, gate: true}
  - {id: db,          actor: data}
  - {id: docs,        actor: data}
  - {id: board,       actor: data}
edges:
  - [requirement, decompose]
  - [decompose, fidelity]
  - [fidelity, options]
  - {from: fidelity, to: decompose, kind: loop, on: FAIL}
  - [options, design_gate]
  - {from: design_gate, to: options, kind: loop, on: reject-all+message}
  - [design_gate, write_spec]
  - [write_spec, validate]
  - {from: validate, to: tdd, event: spec.validated}
  - [tdd, codegen]
  - [codegen, compiler]
  - {from: compiler, to: codegen, kind: loop, on: red, capped: true}
  - [compiler, suites]
  - [suites, behavior]
  - [behavior, conformance]
  - [conformance, docs]
  - [validate, docs]
  - {from: board, to: fn_edit, on: change-this-function}
  - [fn_edit, compiler]
  - {from: fn_edit, to: iface_gate, on: needs-interface-change}
  - {from: iface_gate, to: decompose, on: picked, event: spec.requested}
```

## Where the detail lives

| level | where | freshness |
|---|---|---|
| this file | high-level, reviewed by humans | update on architecture change |
| step-level graph | board front page (derived from workflow defs) | always current |
| per-feature WHAT/HOW | `run/docs/<feature>/spec.md`, `design.md` | regenerated each milestone |
| ground truth | `run/state/forgeflow.db` + `workflows/*.yaml` | is the system |
