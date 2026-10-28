-- Explicit, repeatable admin data migration. Run in a transaction after
-- operational-account-role.sql. The deployment runner supplies a transaction-local
-- huginn.bootstrap_admin JSON setting containing username, email and a scrypt hash.
-- No plaintext password or shared credential is stored in this migration.
DO $seed$
DECLARE
    seed JSONB := NULLIF(current_setting('huginn.bootstrap_admin', true), '')::jsonb;
    v_account_id UUID;
    v_user_id UUID;
    existing_role TEXT;
BEGIN
    IF seed IS NULL
       OR COALESCE(btrim(seed->>'username'), '') = ''
       OR seed->>'username' <> btrim(seed->>'username')
       OR COALESCE(seed->>'email', '') !~ '^[^@[:space:]]+@[^@[:space:]]+[.][^@[:space:]]+$'
       OR COALESCE(seed->>'password_hash', '') !~ '^scrypt:[0-9]+:[0-9]+:[0-9]+[$][^$]+[$][0-9a-f]+$'
    THEN
        RAISE EXCEPTION 'Valid bootstrap admin configuration and scrypt hash are required';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext('huginn.bootstrap_admin'));
    SELECT a.id, a.role INTO v_account_id, existing_role
      FROM operational.accounts a
      WHERE lower(a.username) = lower(seed->>'username') FOR UPDATE;
    IF FOUND THEN
        IF existing_role <> 'admin' THEN
            RAISE EXCEPTION 'Bootstrap username belongs to a non-admin account; refusing promotion';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM operational.users u
            JOIN operational.professional_profiles p ON p.user_id = u.id
            JOIN operational.account_recovery_identity r ON r.account_id = u.account_id
            WHERE u.account_id = v_account_id
        ) THEN
            RAISE EXCEPTION 'Existing admin identity is incomplete; explicit repair is required';
        END IF;
        -- Preserve password changes, disablement, recovery enrollment and profile.
        RETURN;
    END IF;

    INSERT INTO operational.accounts (username, password_hash, role)
        VALUES (seed->>'username', seed->>'password_hash', 'admin')
        RETURNING id INTO v_account_id;
    INSERT INTO operational.users
        (account_id, first_name, last_name, email, phone_number, country_of_residence, timezone)
        VALUES (v_account_id, 'Huginn', 'Administrator', lower(btrim(seed->>'email')),
                '+10000000000', 'US', 'UTC')
        RETURNING id INTO v_user_id;
    INSERT INTO operational.professional_profiles (user_id) VALUES (v_user_id);
    -- Owner-provisioned local administrator, not an assertion of email ownership.
    INSERT INTO operational.account_recovery_identity (account_id, verification_required)
        VALUES (v_account_id, false);
END
$seed$;
