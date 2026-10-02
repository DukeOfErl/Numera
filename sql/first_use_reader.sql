-- The credential the hourly first-use job holds: it can read the trail and nothing else.
--
-- Run ONCE, by the operator, on the Neon branch the deployment writes to (`alpha`),
-- as the branch's owner role. Roles are per branch, so `dev` and `production` get
-- none of this. Then build the connection URL for the new role and store it as the
-- repository secret SCINUMBERS_TRAIL_READ_URL (SQLAlchemy form, `postgresql+psycopg://`).
-- Nothing here is committed with a real password: change CHANGE-ME first.
--
-- Why a role and not the Neon API key: the key is organisation-scoped and can delete
-- the project; this job reads one table. ADR-1260.
--
-- `accounts` is deliberately NOT granted. Nothing in the first-use query reads it, and
-- a grant nothing needs is the one that gets abused.
--
-- Statements are separate on purpose: Neon's SQL editor and its HTTP endpoint run one
-- at a time, and the live test runs this file statement by statement.

create role first_use_reader login password 'CHANGE-ME';

-- Belt as well as braces: even a statement that slipped past the missing grants
-- would run in a read-only transaction.
alter role first_use_reader set default_transaction_read_only = on;

grant connect on database neondb to first_use_reader;

grant usage on schema public to first_use_reader;

grant select on trail to first_use_reader;
