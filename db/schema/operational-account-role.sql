-- Additive Account authorization role. Apply after operational.sql.
ALTER TABLE operational.accounts
    ADD COLUMN role TEXT NOT NULL DEFAULT 'user'
    CONSTRAINT accounts_role_allowed CHECK (role IN ('user', 'admin'));
