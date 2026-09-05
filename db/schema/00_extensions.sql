-- gen_random_uuid() is built into Postgres 13+; pgcrypto is enabled
-- defensively for compatibility with older Postgres.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
