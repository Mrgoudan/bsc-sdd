# Codegen — one function

Implement the **single** function in `active_contract`, and only that one. Emit
ONE object matching `function_result` (its full definition in `body`).

You are given:
- `skeleton.interface` — the frozen module `.hbs`: the struct, the type set, the
  destructor, and every function's declaration. **Code against this.** Use the
  struct name and the callee signatures exactly as declared here.
- `active_contract` — the one function to write: its `signature` (match it
  exactly, ownership annotations included) and its behavior `assertions` (the
  value/state rules the body must actually implement).
- `compile_feedback` — present only when you are **regenerating**: the BSC
  compiler's errors from the last attempt. Fix exactly those (almost always an
  ownership/borrow/nullability mismatch, or a use-after-move).

## Rules

- Write **only** the definition of the active function. Do not redefine the
  struct, other functions, or helpers — they already exist in the skeleton.
- Match the declared signature exactly; the compiler checks it at every call site.
- Implement the behavior assertions — the compiler won't, so they must be in the
  code.
- Call other functions by their skeleton declarations; don't invent new ones.

Use the `bsc-*` skills for idiomatic ownership/borrowing. Return only the JSON.
