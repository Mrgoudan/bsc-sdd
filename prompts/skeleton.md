# Skeleton — the frozen module interface

You design the module's shared foundation ONCE. Every function body is generated
later against this, so it must be complete and self-consistent. Emit ONE object
matching `skeleton_result`.

You are given `spec_slice`: all the contracts (signatures + summaries) of this
module.

## `hbs` — the interface

- The `#include`s the module needs (libcbs: `bishengc_safety.hbs`, `string.hbs`,
  `vec.hbs`, etc.).
- The type set / enum the contracts imply (kinds, tags, variants).
- The **struct**, defined **once**. Name it **exactly** the type used in the
  contract signatures — never introduce a second synonym name for the same
  type. This single naming decision is the thing most likely to break every
  function if it drifts.
- The destructor for the owned struct (so the delete/free contract frees the
  whole tree).
- A **declaration for every function** in `spec_slice`, matching each contract's
  signature exactly (ownership annotations included).

## `cbs_head` — the .cbs preamble

- `#include` of this module's own `.hbs`.
- Declarations (and, if trivial and shared, definitions) of any **private
  helpers** the function bodies will call (e.g. a node allocator). Anything a
  body calls must be reachable from here or from the `.hbs`.

Do NOT implement the public functions here — those come one at a time next.
Return only the JSON object.

## BSC discipline (hard rules)

- Never `_Mut`/`_Const` in any declaration — they are call-site borrow
  operators only. Mutable borrow param: `T *_Borrow`; read-only:
  `const T *_Borrow`; transfer: `T *_Owned`.
- `typedef` every struct the signatures use by bare name, in the .hbs,
  before any declaration that mentions it.
- On a retry, `compile_feedback` carries the compiler's errors on YOUR
  skeleton — fix the interface; contract signatures stay verbatim.
