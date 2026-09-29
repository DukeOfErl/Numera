-- The accounts table: who is enrolled, as what, and funded by which credential.
--
-- Lives in the same Neon database as `trail`, read through the same engine
-- (ADR-0780). Enrolment is an operator action performed here, by hand, and
-- nowhere in the application: there is no page for it, and so no permission
-- gates it. `scinumbers_ask.accounts.lookup` reads one row by email at sign-in.
--
-- `openrouter_key` is a *runtime* key minted at OpenRouter's Management API with
-- a hard monthly limit (`limit_reset: monthly`), stored in the clear. Why that is
-- accepted, and what it obliges — the database URL stays a secret — is ADR-0780.
-- Never paste a real key or a real email into this file; it is committed.
--
-- `role` is one of: 'student', 'scientist', 'senior scientist', 'dev', 'admin'.
-- The application refuses a row whose role is none of these and says so on
-- stderr, so a typo here produces "not enrolled" rather than a grant nobody chose.
--
-- `disabled` is how an account is withdrawn without losing the row: a disabled
-- account is refused exactly as an absent one is, and the trail rows it wrote
-- keep their attribution.
--
-- **Withdrawal takes effect at the reader's next page load, not at once.** The
-- row is read when a session signs in and held for the life of that browser
-- session, so disabling an account, changing its role or replacing its key does
-- nothing to a tab that is already open. To cut off a key immediately, revoke it
-- at OpenRouter; the next model call meets that.

create table if not exists accounts (
    email          text primary key,
    role           text not null,
    openrouter_key text,
    -- OpenRouter's handle for the key above, and the only thing that can withdraw
    -- it. The Management API deletes a key by its *hash*, which is returned once,
    -- at creation -- so a deployment that stores the key and not the hash holds a
    -- live credential it cannot revoke through any API. `scinumbers-enrol` used
    -- the hash for its compensating revoke and then discarded it, which is why
    -- rows enrolled before this column exist with no way to withdraw them but the
    -- OpenRouter dashboard. Null for those rows, and for an account enrolled with
    -- no credential at all.
    openrouter_key_hash text,
    issued_at      timestamptz not null default now(),
    disabled       boolean not null default false
);

-- For a database created before the column existed. Idempotent, like the table
-- above: this file is run whole against a branch whose state nobody has checked.
alter table accounts add column if not exists openrouter_key_hash text;

-- **One row per address, whatever its case.** `accounts.lookup` matches on
-- `lower(email)`, and the primary key above is case-sensitive -- so without this
-- index `Tester@example.org` and `tester@example.org` are two enrolable rows that
-- both satisfy the lookup, and which one answers is Postgres's choice. That
-- decides the person's role, their credential *and* their conversation key, and
-- it could differ between two sign-ins by the same person.
create unique index if not exists accounts_email_lower on accounts (lower(email));

-- Enrol one tester. Replace every placeholder; `openrouter_key` may be null for
-- an account that should be able to sign in but not yet ask (the page then says
-- no credential has been issued).
--
-- insert into accounts (email, role, openrouter_key)
-- values ('tester@example.org', 'scientist', 'sk-or-v1-...');

-- Withdraw an account without deleting what it wrote. Prefer `scinumbers-withdraw`,
-- which does this *and* revokes the credential at OpenRouter; this statement alone
-- refuses the reader while leaving a live key in the hands of whoever holds it.
--
-- update accounts set disabled = true where email = 'tester@example.org';

-- Who is enrolled, without the credentials.
--
-- select email, role, issued_at, disabled,
--        openrouter_key is not null as has_key,
--        openrouter_key_hash is not null as can_be_withdrawn
-- from accounts order by issued_at;
