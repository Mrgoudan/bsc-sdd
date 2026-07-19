# BSC signature skill (served into every design-phase call)

Distilled from the BiSheng C borrowing/ownership skills. These rules govern
every signature you author. They are enforced mechanically — a violation is
rejected before codegen.

## Choosing a parameter's pointer type (the default table)

| the function… | parameter type |
|---|---|
| only READS through the pointer | `const T *_Borrow name` |
| MUTATES through it but does not keep/free it | `T *_Borrow name` |
| takes OWNERSHIP (frees it, stores it, hands it on) | `T *_Owned name` |
| does pointer arithmetic / iteration | raw `T *name` (or `T *_Borrow _ArrayElem`) |

Default to `_Borrow`, not `_Owned`: an `_Owned` param consumes the caller's
variable — most functions don't do that, and over-owning forces ugly
re-allocation at every call site.

## Hard syntax rules

- Qualifiers go AFTER the `*`: `int *_Borrow p` — never `_Borrow int *p`.
- `_Mut` and `_Const` are CALL-SITE borrow operators (`&_Mut x`,
  `&_Const x`). They NEVER appear in a declaration. A mutable borrow
  param is `T *_Borrow`; immutable is `const T *_Borrow`.
- Nullability: `_Nonnull` / `_Nullable` follow the `*` (and compose:
  `T *_Owned _Nullable`). Borrows are non-null by nature — do not add
  `_Nonnull` to a `*_Borrow` param.
- A `_Borrow` RETURN requires at least one `_Borrow` parameter (the
  return's lifetime ties to it); otherwise it does not compile.
- No borrow-of-borrow (`*_Borrow *_Borrow`), no `_Owned _Borrow` on one
  pointer, no borrow globals/statics, no `_Borrow` in a struct that gets
  borrowed itself.
- Mark functions `_Safe` when the body can live in the safe zone
  (default for new APIs); raw-pointer tricks and syscalls need unsafe
  wrappers instead of leaking raw pointers through the public interface.
- Every struct named in a signature must be `typedef`ed (bare-name use),
  declared in the module's `.hbs` before first use.

## Examples (correct)

```c
_Safe _Bool parse_args(int argc, char *const *_Nonnull argv,
                       Parsed *_Borrow out);          // out-param: mutable borrow
_Safe size_t vec_len(const Vec *_Borrow v);           // read-only view
_Safe void list_push(List *_Borrow l, Node *_Owned n); // list TAKES the node
_Safe const char *_Borrow name_of(const Obj *_Borrow o); // borrow-in, borrow-out
```

## Examples (rejected mechanically)

```c
_Bool parse(Cfg *_Mut c);          // _Mut is not a qualifier -> *_Borrow
void f(_Borrow int *p);            // qualifier before * -> int *_Borrow p
char *_Borrow head(void);          // borrow return, no borrow param
void g(Thing *_Borrow _Nonnull t); // _Nonnull redundant on a borrow
```
