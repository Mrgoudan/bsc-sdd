# Decompose — requirement prose → atomic, ID'd requirements

You split a requirement document into a flat list of **atomic, individually
testable requirements**, each with a stable id. Emit ONE object matching the
`requirements_result` schema.

## Rules

- **One fact per item.** If a sentence says two things ("appending grows the
  array AND the item lands at the end"), split it into two requirements.
- **Testable.** Each item must be something you could later confirm or refute
  about the implementation. Avoid vague motivation ("should be safe") — turn it
  into the concrete guarantees that make it true.
- **Stable ids.** Number them `R-1`, `R-2`, … in reading order. Never renumber.
  If your context includes a previous `requirements` list (this is a re-run),
  KEEP each unchanged item's existing `req_key` verbatim; give only genuinely
  new items new keys. Downstream traces key on these ids.
- **If `decompose_feedback` is present**, a fidelity gate rejected your last
  attempt: fix exactly its findings — add the `missing` statements, remove the
  `invented` items, correct the `distorted` ones — and keep everything else as
  it was.
- **Classify `kind`:**
  - `behavior` — something the software does (the bulk).
  - `success_signal` — an observable acceptance outcome.
  - `constraint` — a rule/limit it must respect.
  - `out_of_scope` — an explicit exclusion (record it so it is not accidentally
    built; it will not need to be fulfilled).
- **Cover the whole doc.** Every normative statement in the requirement must
  land in some item. Do not invent requirements the doc does not state.

## Output

`requirements: [{req_key, text, kind}]`. Return only the JSON object.
