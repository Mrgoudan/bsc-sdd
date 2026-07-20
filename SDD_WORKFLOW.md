---
name: sdd
description: Spec-driven BiSheng C — a plain-English requirement to compiler-verified code, followed as a markdown workflow by an agent (no engine).
inputs:
  requirement: projects/<FEATURE>/requirement.md   # pure behavior, no impl vocabulary
  smoke:       projects/<FEATURE>/smoke.cbs         # the runnable behavior floor
tools:
  model:   an LLM you can prompt and get JSON back
  compile: "{clang} -fsyntax-only -Wno-nullability-completeness {-I libcbs dirs} {-I outdir} <module>.cbs"
  link:    "{clang} ... <module>.cbs <smoke.cbs> {all libcbs *.cbs} -lpthread -lm -o smoke_bin && ./smoke_bin"
state: a folder (out/<FEATURE>/) holding requirements.json, spec.json, <module>.hbs/.cbs
---

# SDD workflow

Follow the steps in order. Each step says what to send the model, what to save,
and — the important part — **where to go next based on the result**. The
`on <result> → <step>` lines ARE the control flow; obey them exactly. That is
how this markdown reproduces the engine's behavior (repair loops, verification
tiers) without the engine. The only thing dropped is the human decision gates
(this runs headless); where one would occur, the note says so.

---

## 1 · Decompose  (model)

Send: the requirement + —
> Decompose this requirement into ATOMIC, checkable items. Each: a stable id
> (R-1…), one sentence of pure behavior, a kind (behavior | success_signal |
> constraint | out_of_scope). Cover the whole doc; invent nothing. Return ONLY
> JSON: `{ "requirements": [ {"req_key":"R-1","text":"...","kind":"behavior"} ] }`

Save → `requirements.json`.  **→ step 2**

## 2 · Fidelity gate  (model)

Send: the raw requirement + the R-items + —
> Are these R-items a FAITHFUL decomposition — nothing dropped, invented, or
> distorted? Return ONLY JSON: `{ "verdict":"PASS"|"FAIL", "findings":[...] }`

- on **PASS** → step 3
- on **FAIL** → back to **step 1** with the findings appended (max 2 times, then stop and report).

## 3 · Author spec  (model)

Send: requirement + R-items + —
> Author one CONTRACT per function: a BiSheng C signature with ownership
> annotations (borrows after `*`; `_Owned` only when you keep/free; NEVER
> `_Mut`/`_Const` in a declaration), a summary, the R-item keys it fulfills,
> and behavior assertions (pre/post/side_effect). Every in-scope R-item must be
> fulfilled by ≥1 contract; every contract must cite ≥1 R-item. Return ONLY
> JSON: `{ "feature_key":"F", "contracts":[ {"contract_key","module","signature",
> "summary","fulfills":[...],"assertions":[{"kind","text"}]} ] }`

Save → `spec.json`.  **→ step 4**

## 4 · Coverage check  (mechanical — you check, no model)

Confirm every in-scope R-item is fulfilled by ≥1 contract, and every contract
cites ≥1 known R-item.
- on **complete** → step 5
- on **gap** → back to **step 3** naming the orphan requirement / untraceable contract (max 2, then stop).

## 5 · Skeleton  (model)

Send: the contract signatures + —
> Produce the module interface ONCE: the `.hbs` (includes; every struct
> typedef'd by bare name; a declaration for EVERY signature VERBATIM) and a
> `.cbs` preamble. Do not implement the public functions. Return ONLY JSON:
> `{ "hbs":"...", "cbs_head":"..." }`

Save → `<module>.hbs`, remember `cbs_head`.

Compile the skeleton alone (preamble + header, `-fsyntax-only`).
- on **green** → step 6
- on **red** → back to **step 5** with the compiler errors (max 3, then stop). *(This is the preflight: an interface that can't compile is unfixable downstream.)*

## 6 · Generate the module  (model)  ← the repair loop

Send: the frozen `.hbs` + all contracts (signature + assertions) + —
> Implement EVERY function in one go so caller/callee wiring stays consistent
> (agree on ownership; don't pass the same input twice; don't use a value after
> it's moved). Signatures VERBATIM. BSC discipline: borrows after `*`, `_Unsafe`
> scoped to raw-pointer/syscall work only. Return ONLY JSON:
> `{ "functions":[ {"contract_key","body"} ] }`
> On a re-run you'll also get the previous bodies + the compiler errors — fix
> those, re-emit the rest unchanged.

Assemble `<module>.cbs` = `cbs_head` + all bodies. **Compile it** (the SOUND gate).
- on **green** → step 7
- on **red** → back to **step 6**, appending the previous bodies + the compiler errors (map each `file:line` to its function). Max 12 times, then stop and report the last errors. *(This IS the compile-repair loop — the reason a red doesn't kill the run.)*

## 7 · Smoke test  (machinery)

Link `<module>.cbs` + `smoke.cbs` + libcbs and run it.
- on **pass** → step 8
- on **fail** → stop and report (a runtime failure with a green compile is a real behavior bug; a human decides). *(Engine would route to a repair; headless, we stop.)*

## 8 · Behavior check  (model)  ← repair loop

Send: the assertions + the generated bodies + —
> Do the code's bodies satisfy every behavior assertion? Return ONLY JSON:
> `{ "verdict":"PASS"|"FAIL", "results":[ {"contract_key","assertion","status":
> "satisfied"|"violated","evidence"} ] }`

- on **PASS** → step 9
- on **FAIL** → back to **step 6**, appending the violated assertions + evidence (regenerate the guilty functions to make them hold), then re-compile (step 6 gate) and re-smoke (7). Max 2 behavior rounds, then stop. *(Engine escalates a stuck behavior fault to a human; headless, we stop after the cap.)*

## 9 · Conformance  (model)

Send: each requirement + the code of its fulfilling contracts + —
> Does the implementation fulfill each requirement? Return ONLY JSON:
> `{ "results":[ {"req_key","status":"fulfilled"|"violated","evidence"} ] }`

- if **all fulfilled** → step 10
- if **any violated** → this is the deepest catch. If the violation is one root
  cause in a body, go back to **step 6** with it (max 1 round); if it's a spec
  contradiction, stop — the requirement itself is wrong (a human decides).

## 10 · Done

Report: the module compiles GREEN (sound), smoke PASS, behavior PASS,
conformance N/N. Emit the docs if you want (spec.md = the R-items; design.md =
the contracts + assertion table + verification trail).

---

## The behavior this preserves (vs the engine)

- **Sound gate**: step 6's compile and step 7's smoke are *external* — the model
  asks for them, never self-reports them green. Same trust boundary as the engine.
- **Repair loops**: steps 5, 6, and 8 loop on their gate with the feedback,
  capped. Same as the engine's regenerate-on-red / behavior-repair.
- **Three tiers**: compiler (sound) → smoke (sound per case) → behavior +
  conformance (argued). Same model.
- **Dropped (headless)**: the human decision gates (design fork, interface
  change, stuck-behavior escalation). Each is marked "a human decides" so it's
  explicit where a person would step in.
