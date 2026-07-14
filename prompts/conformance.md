# Conformance — does the code fulfill the requirements?

The compiler already proved the safety design and the build is green; the tests
and the behavior check already ran. This is the OUTER, end-to-end check: for
each atomic requirement, does the generated code actually **do what the
requirement asked**? Emit ONE object matching `conformance_result`.

You are given `req_trace`: each requirement with the contracts that claim to
fulfill it (the trace). For each requirement:

1. Read the code of its fulfilling contracts.
2. **Disprove first**: try to find a case where the code does NOT satisfy the
   requirement. If you find one → `violated`, with the concrete case.
3. If you can't, and the code clearly does what the requirement states →
   `fulfilled`, citing the line(s). If the code shown is insufficient to judge →
   `cannot_determine`.

Judge the requirement as written — do not re-derive the spec. If a requirement
maps to several contracts, it is fulfilled only if the code across them together
delivers it.

`verdict: FAIL` if any requirement is `violated`; otherwise `PASS`.
Return only the JSON object.
