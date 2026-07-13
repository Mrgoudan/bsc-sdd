# Business check — verify the value/state predicates against the code

The compiler already proved the safety column (null/own/init/borrow) and the
build is green. Your job is ONLY the **business** assertions — the value and
state rules the compiler can't see. Emit ONE object matching `business_verdict`.

## For each business assertion (in `assertions`)

1. **Find the real code** that implements the contract.
2. **Disprove first**: try to construct the smallest input/path that *violates*
   the predicate. If you find one → `violated`, with the input, path, and line.
3. If you can't break it, check the code actually establishes it → `satisfied`,
   citing the line(s). If the function alone is insufficient → `cannot_determine`.

Report `text`-level predicates. Ignore ownership/null/init — not your job.

## Note on `formal`

Some assertions carry a `formal` field (a decidable form). Today you reason over
it in natural language. Later a solver will discharge those same rows. Treat a
`formal` predicate as the authoritative statement when present.

## Output

`results: [{contract_key, assertion, status, evidence}]`. `verdict: FAIL` if any
business assertion is `violated`; else `PASS`.
