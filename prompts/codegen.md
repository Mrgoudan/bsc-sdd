# Codegen — spec slice → BiSheng C

Implement the contracts in your slice as BiSheng C. Emit ONE object matching
the `codegen_result` schema (a list of full files).

## Non-negotiable

- **Honor every signature exactly** — parameter types, return type, and the
  ownership annotations (`_Owned` / `_Nonnull` / `&_Mut` / `&_Const` / ...).
  The compiler checks these at every call site; a mismatch fails the build.
- **Call other contracts by their given signatures** (in `contracts`), so the
  cross-function safety checks pass first time.
- **Implement the business post-conditions** in `assertions` — the value/state
  rules. These aren't compiler-checked, so they must actually be in the code.

## Use the BiSheng C skills

Load and follow the `bsc-*` skills for ownership, borrowing, nullability, safe
zones, and stdlib types. Write idiomatic BiSheng C, not C with annotations.

## Output

`files: [{path, content}]` — repo-relative `.cbs`/`.hbs` paths from `impl_file`,
full contents each. No prose outside the JSON object.
