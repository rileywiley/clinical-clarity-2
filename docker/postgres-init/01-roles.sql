-- Runs once on first container boot, when the data dir is empty.
-- Creates the two-role split that makes RLS meaningful:
--   app_owner — privileged role used by Alembic. BYPASSRLS so migrations can
--               create policies that the runtime role is then subject to.
--   app_user  — runtime role used by the FastAPI app. NOT BYPASSRLS, so every
--               query it issues is filtered by the RLS policies installed in
--               migrations.

CREATE ROLE app_owner WITH LOGIN PASSWORD 'app_owner_pw' BYPASSRLS;
CREATE ROLE app_user  WITH LOGIN PASSWORD 'app_user_pw';

GRANT ALL PRIVILEGES ON DATABASE clinical_clarity TO app_owner;
GRANT CONNECT ON DATABASE clinical_clarity TO app_user;

-- Make app_owner the owner of the public schema so tables it creates are owned
-- by it (and therefore inherit the BYPASSRLS escape hatch for migrations).
ALTER SCHEMA public OWNER TO app_owner;
GRANT USAGE ON SCHEMA public TO app_user;
