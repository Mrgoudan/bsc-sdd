-- bsc-sdd pack schema: the spec-driven-development IR + verification data
-- model. Layered on the engine core (tasks, items, code_objects, transitions).
--
-- This schema IS the design. It encodes the decisions from the design dialogue:
--   * contracts.signature holds the BSC I/O shape (_Owned/_Nonnull/&_Mut/...).
--     The COMPILER verifies it, inside functions AND at call sites -> that is
--     the safety column AND the "do the pieces fit" join check, for free.
--   * contract_assertions is the business logic. `text` is always present
--     (human-readable); `formal` + `encodable` are the STRUCTURED SLOT that
--     lets an LLM check it now and Z3 check it later WITHOUT re-authoring.
--   * verifications.sound records WHICH tool discharged each obligation
--     (compiler/test/z3 = sound; llm = plausible) so soundness is auditable.

-- One spec = one feature's IR, produced from a requirement.
CREATE TABLE IF NOT EXISTS specs (
    id            INTEGER PRIMARY KEY,
    feature_key   TEXT NOT NULL UNIQUE,            -- stable id, e.g. FEATURE-001
    requirement   TEXT NOT NULL,                   -- the source requirement text
    goal          TEXT,                            -- user-value statement
    status        TEXT NOT NULL DEFAULT 'draft',   -- draft | validated | implemented
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One contract per function/API in the spec. The BSC I/O shape lives in
-- `signature` — that is the part the compiler proves (safety + composition).
-- Business pre/post/side-effects live in contract_assertions.
CREATE TABLE IF NOT EXISTS contracts (
    id            INTEGER PRIMARY KEY,
    spec_id       INTEGER NOT NULL REFERENCES specs(id),
    contract_key  TEXT NOT NULL,                   -- stable id, e.g. API-ACCEPT-TASK
    module        TEXT,                            -- owning module
    signature     TEXT NOT NULL,                   -- BSC sig w/ ownership annotations (compiler-checked)
    summary       TEXT,                            -- natural-language description
    impl_file     TEXT,                            -- planned implementation file (.cbs)
    status        TEXT NOT NULL DEFAULT 'active',  -- active | superseded
    UNIQUE (spec_id, contract_key)
);

-- One row per pre/post/side-effect predicate. THE crown-jewel table.
--   kind      : pre | post | side_effect
--   text      : the predicate, human-readable (ALWAYS present)
--   formal    : the structured decidable form (the Z3 slot); NULL = prose-only
--   encodable : 1 iff `formal` is filled and in the decidable kernel
--               (arith/sets/enums/equality) -> Z3-ready. 0 = LLM-only forever.
CREATE TABLE IF NOT EXISTS contract_assertions (
    id            INTEGER PRIMARY KEY,
    contract_id   INTEGER NOT NULL REFERENCES contracts(id),
    kind          TEXT NOT NULL,                   -- pre | post | side_effect
    text          TEXT NOT NULL,                   -- the predicate (always)
    formal        TEXT,                            -- structured form; Z3 reads this later
    encodable     INTEGER NOT NULL DEFAULT 0,
    seq           INTEGER NOT NULL DEFAULT 0
);

-- Use-case chains: the ordered function calls of an end-to-end scenario. The
-- JOIN check walks these edges. For now the join is param/ownership matching
-- (the compiler); later, post(step_i) => pre(step_i+1) over the `formal`
-- assertions (Z3).
CREATE TABLE IF NOT EXISTS chains (
    id            INTEGER PRIMARY KEY,
    spec_id       INTEGER NOT NULL REFERENCES specs(id),
    chain_key     TEXT NOT NULL,                   -- stable id, e.g. UC-ACCEPT-FLOW
    step_seq      INTEGER NOT NULL,                -- position in the chain (0-based)
    contract_key  TEXT NOT NULL,                   -- the api called at this step
    UNIQUE (spec_id, chain_key, step_seq)
);

-- One verification result per (contract | join) per checker. Records which
-- tool discharged it and the verdict, so the audit trail shows the SOUND
-- floor (compiler/test/z3) vs the LLM residual.
CREATE TABLE IF NOT EXISTS verifications (
    id            INTEGER PRIMARY KEY,
    spec_id       INTEGER NOT NULL REFERENCES specs(id),
    contract_id   INTEGER REFERENCES contracts(id),
    checker       TEXT NOT NULL,                   -- compiler | test | llm | z3
    target        TEXT NOT NULL,                   -- safety | join:<chain> | assertion:<id> | tests
    verdict       TEXT NOT NULL,                   -- pass | fail | unknown
    sound         INTEGER NOT NULL DEFAULT 0,      -- 1 = compiler/test/z3, 0 = llm
    evidence      TEXT,                            -- line ref / counterexample / build-log path
    run_id        TEXT,
    at            TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Requirement decomposition: the prose requirement split into atomic, ID'd
-- items. Produced by `decompose` BEFORE the spec, so the coverage gate is an
-- INDEPENDENT completeness check (did the author's spec cover every R?).
CREATE TABLE IF NOT EXISTS requirements (
    id            INTEGER PRIMARY KEY,
    feature_key   TEXT NOT NULL,                   -- ties to specs.feature_key
    req_key       TEXT NOT NULL,                   -- stable id, e.g. R-1
    text          TEXT NOT NULL,                   -- one atomic requirement
    kind          TEXT,                            -- behavior | success_signal | constraint | out_of_scope
    UNIQUE (feature_key, req_key)
);

-- The trace: which requirement(s) each contract helps fulfill. The coverage
-- gate checks every requirement has >=1 fulfilling contract (nothing dropped)
-- and every contract fulfills >=1 requirement (no gold-plating). req_key is
-- validated against the requirements table at load time.
CREATE TABLE IF NOT EXISTS contract_fulfills (
    contract_id   INTEGER NOT NULL REFERENCES contracts(id),
    req_key       TEXT NOT NULL,
    PRIMARY KEY (contract_id, req_key)
);
