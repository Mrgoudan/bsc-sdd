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
    -- content hash of (signature + assertions + fulfills). On a spec
    -- modification, reconcile diffs by this: unchanged hash => keep the done
    -- codegen unit; changed => re-codegen only that function.
    hash          TEXT,
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
    -- who proves this predicate. `compiler` = a safety/ownership/init fact the
    -- BSC compiler already proves (via the signature + destructor) -> the LLM
    -- business/conformance checks SKIP it (no unsound re-proving). `test`/`llm`
    -- = a value/state fact for the sound test floor / the LLM residual.
    discharged_by TEXT NOT NULL DEFAULT 'llm',      -- compiler | test | llm
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

-- RAG corpus: vetted BSC idioms retrieved per-function by the `similar`
-- provider (query = the active function's summary + signature). Lexical
-- retrieval, same class as the engine's embed_with: hashing. Seed from
-- data/idioms.jsonl via scripts/seed_idioms.py.
CREATE TABLE IF NOT EXISTS bsc_idioms (
    id            TEXT PRIMARY KEY,                -- stable idiom id
    title         TEXT NOT NULL,                   -- short name
    pattern       TEXT NOT NULL,                   -- the idiom (shown to codegen)
    tags          TEXT                             -- extra retrieval terms
);

-- Incremental within-module codegen. A module is generated as: a frozen
-- skeleton (the .hbs interface + the .cbs preamble) produced ONCE, then one
-- function body at a time, compiling after each. This avoids the whole-file
-- timeout and lets a compile error localize to (and regenerate) a single
-- function instead of the whole module.
--   codegen_modules: the frozen skeleton for a module.
CREATE TABLE IF NOT EXISTS codegen_modules (
    feature_key   TEXT NOT NULL,
    module        TEXT NOT NULL,
    hbs_path      TEXT NOT NULL,                   -- worktree-relative .hbs path
    cbs_path      TEXT NOT NULL,                   -- worktree-relative .cbs path
    hbs           TEXT NOT NULL,                   -- the interface (struct + all decls)
    cbs_head      TEXT NOT NULL,                   -- .cbs preamble (includes + private helpers)
    PRIMARY KEY (feature_key, module)
);

-- codegen_units: one row per function; `body` accumulates as it's generated.
-- The .cbs is rebuilt from cbs_head + every non-null body (ordered by seq), so
-- regenerating one function REPLACES its body rather than appending a duplicate.
--   status: pending -> active (being generated) -> done (compiled green)
CREATE TABLE IF NOT EXISTS codegen_units (
    id            INTEGER PRIMARY KEY,
    feature_key   TEXT NOT NULL,
    module        TEXT NOT NULL,
    contract_key  TEXT NOT NULL,
    seq           INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending', -- pending | active | done
    attempts      INTEGER NOT NULL DEFAULT 0,      -- per-function regenerate count
    behavior_repairs INTEGER NOT NULL DEFAULT 0,  -- behavior-tier repair rounds (escalate past cap)
    body          TEXT,
    last_error    TEXT,                            -- last red compile's stderr (fix-lesson capture)
    UNIQUE (feature_key, module, contract_key)
);

-- The green-functions corpus, as a VIEW the engine's select: cascade reads:
-- one row per compiled-green function, text = its contract's summary +
-- signature + body (searchable AND servable). Self-improving: every green
-- compile adds a row. Declared in project.yaml corpora as `green_bodies`
-- (embed_with: hashing today; flip to a pinned model via models: later —
-- vectors are cached per row by the engine either way).
CREATE VIEW IF NOT EXISTS green_bodies AS
    SELECT u.contract_key                        AS key,
           u.feature_key                         AS feature_key,
           COALESCE(c.summary, '') || ' ' || c.signature || char(10) || u.body AS text
    FROM codegen_units u
    JOIN specs s      ON s.feature_key = u.feature_key
    JOIN contracts c  ON c.spec_id = s.id AND c.contract_key = u.contract_key
    WHERE u.status = 'done' AND u.body IS NOT NULL;

-- The requirement dialogue: questions the spec-side agents raised, and their
-- answers. Multi-turn: an agent re-runs with the full history in context and
-- may ask follow-ups. answered_by='default' rows are ASSUMPTIONS (the agent
-- proceeded on its recommended option — reviewable, overridable);
-- answered_by='user' rows are decisions. Rendered into spec.yaml.
CREATE TABLE IF NOT EXISTS dialogue (
    id            INTEGER PRIMARY KEY,
    feature_key   TEXT NOT NULL,
    stage         TEXT NOT NULL,                   -- decompose | author
    q_key         TEXT NOT NULL,                   -- agent's id, e.g. Q-1
    question      TEXT NOT NULL,
    why           TEXT,                            -- why it matters
    options       TEXT,                            -- JSON list of choices
    recommended   TEXT,
    blocking      INTEGER NOT NULL DEFAULT 0,
    answer        TEXT,                            -- NULL = awaiting the user
    answered_by   TEXT,                            -- default | user
    asked_at      TEXT NOT NULL DEFAULT (datetime('now')),
    answered_at   TEXT,
    UNIQUE (feature_key, stage, q_key)
);

-- Error->fix memory: when a function goes red then GREEN, record the error it
-- hit and the body that fixed it. The fix_hints provider retrieves the closest
-- past lesson when a NEW function hits a similar error — the pipeline learns
-- from its own compiler fights.
CREATE TABLE IF NOT EXISTS fix_lessons (
    id            INTEGER PRIMARY KEY,
    feature_key   TEXT NOT NULL,
    contract_key  TEXT NOT NULL,
    error         TEXT NOT NULL,                   -- the compiler error that was overcome
    body          TEXT NOT NULL,                   -- the body that went green
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
