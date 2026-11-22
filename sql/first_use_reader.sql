-- The credential the hourly first-use job holds: it can read the trail and nothing else.
--
-- Run ONCE, by the operator, on the Neon branch the deployment writes to (`alpha`),
-- as the branch's owner role. Roles are per branch, so `dev` and `production` get
-- none of this. Then build the connection URL for the new role and store it as the
-- repository secret NUMERA_TRAIL_READ_URL (SQLAlchemy form, `postgresql+psycopg://`).
--
-- **Before running, replace the whole token <PASSWORD> -- angle brackets included --
-- with your password in single quotes**, e.g. password 'a1b2...'. Left as it is the
-- statement is a syntax error, on purpose: a forgotten edit must fail, not create a
-- login role whose password is in the repository. Use characters that survive a URL
-- (`openssl rand -hex 24` does).
--
-- Why a role and not the Neon API key: the key is organisation-scoped and can delete
-- the project; this job reads one table. ADR-1260.
--
-- `accounts` is deliberately NOT granted, and neither are the trail's other columns.
-- Nothing in the first-use query reads them, and a grant nothing needs is the one that
-- gets abused.
--
-- Statements are separate on purpose: Neon's SQL editor and its HTTP endpoint run one
-- at a time, and the live test runs this file statement by statement.

create role first_use_reader login password <PASSWORD>;

-- Belt as well as braces: even a statement that slipped past the missing grants
-- would run in a read-only transaction.
alter role first_use_reader set default_transaction_read_only = on;

grant connect on database neondb to first_use_reader;

grant usage on schema public to first_use_reader;

-- Three columns, not the table: the question reads `at`, `event` and `user_email` and
-- nothing else. The other columns hold question text, feedback comments and session
-- ids, which a leaked secret should not expose.
grant select (at, event, user_email) on trail to first_use_reader;
