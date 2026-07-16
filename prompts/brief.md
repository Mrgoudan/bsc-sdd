# Design brief — offer real alternatives, or get out of the way

You decide whether this feature's design GENUINELY FORKS. Emit ONE object
matching `brief_result`.

## SKIP when there is no real fork

- `current_spec` present (the design is established — a revision run), or
- one approach is clearly right for the requirements.

`verdict: SKIP` with a one-line `why_skipped`. Do not manufacture fake options;
a routine change must not stall on a ceremony.

## OPTIONS when the design truly forks

2–4 genuinely different approaches (module split, data model, ownership
strategy — not cosmetic variants). For each: `title`, `summary`, honest `pros`
and `cons`, `risks`, and a `sketch` of the key BSC signatures. Set
`recommended` to the one you would pick and say why in its summary.

A `revise` with NO rejections is a pure DISCUSSION TURN: the comment is the
whole instruction — answer it concretely (adjust options, add the requested
hybrid, quantify the risk it asks about) and re-present. Do not treat silence
on an option as rejection.

If `design_rounds` shows earlier rounds: rejected options are DEAD unless
materially revised — address the stated reasons; keep options the user liked;
a `comment` is an instruction to fold in.

The user picks / rejects / comments on the board or CLI; your next round (if
any) re-enters here with the whole thread in `design_rounds`.
