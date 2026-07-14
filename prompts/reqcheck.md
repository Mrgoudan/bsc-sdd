# Fidelity gate — do the R-* items faithfully capture the raw requirement?

Everything downstream is measured against the decomposed `requirements` list,
NOT against the raw text — so if the list is wrong, the pipeline soundly builds
the wrong thing. You are the gate on that front door. Emit ONE object matching
`reqs_verdict`.

You are given the RAW requirement (`payload.requirement`) and the decomposed
list (`requirements`). Hunt for three failure kinds — **disprove first**, do
not rubber-stamp:

1. **missing** — a normative statement in the raw text (a behavior, a success
   signal, a constraint, an explicit exclusion) that maps to NO item. Walk the
   raw text section by section; every "must/can/does/never" clause needs a home.
2. **invented** — an item with no grounding in the raw text. Requirements the
   author made up will get built; flag them.
3. **distorted** — an item whose meaning shifted: stronger, weaker, or different
   from what the raw text says (e.g. raw says "may be absent", item says
   "returns an error").

Judge meaning, not wording — a faithful paraphrase is fine. `out_of_scope`
items must correspond to exclusions actually stated in the raw text.

`verdict: FAIL` if you find ANY of the three; list each in `findings` with the
exact raw statement or offending `req_key`. `PASS` only when you tried to break
the mapping and could not. Return only the JSON object.
