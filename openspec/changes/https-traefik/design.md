## Context

See `proposal.md` for motivation and `specs/https-ingress/spec.md` for the behavioral contract.

1. Current master `101d8f6` provides a single app image serving both the Vue frontend and FastAPI API. Compose publishes container port 8000 through a configurable host port, normally 8080. Production currently binds that port publicly.
2. The GitHub workflow publishes a digest-pinned image and dispatches an AWS Systems Manager command. `scripts/deploy-ec2.py` explicitly selects `compose.yaml`, preserves private `.env`, verifies the running image and checks private readiness. It does not currently verify public HTTPS.
3. `ManagementConfig` already supports a trusted HTTPS origin and production Secure cookies. `require_same_origin_browser_mutation` compares Origin against the request URL, so TLS termination needs correct server-level handling of proxy headers. Client addresses also feed existing authentication throttling.
4. PostgreSQL and Mailpit use persistent Compose volumes. A proxy must not require reinitializing either service. Brevo SMTP configuration and EU-Startups collection fixes are independent.
5. The registered domain is `huginn.live`, managed through GoDaddy. The previously observed EC2 public address is `13.53.218.50`; DNS and address stability must be verified at cutover rather than assumed.
6. `docs/docker-compose.md` already directs hosted deployments to use an HTTPS proxy. Architecture section 10 still describes containerization as future work; reconcile that deployment description only as part of the operator documentation update.

## Goals / Non-Goals

1. Introduce one ingress proxy while retaining one application image, one database and the existing worker processes.
2. Keep first HTTPS activation an explicit operator step. Once activated, the existing automated image deployment must preserve and verify it.
3. Exercise actual TLS routing and browser authentication. Do not equate a healthy proxy process with valid certificates or working sessions.
4. Scope implementation to hosting configuration and necessary composition/deployment adapters. Do not change domain policies, data models or ingestion behavior.

## Decisions

### One Traefik proxy with built-in ACME

1. Use the open-source Traefik image, pinned to a supported exact release and digest selected and verified at implementation time.
2. Traefik terminates TLS on 443 and forwards to `http://app:8000` through a private Compose network. Requests to canonical and alias hostnames are explicitly matched; there is no catch-all application router.
3. Use a file provider with a read-only configuration directory under `docker/traefik/`, rather than mounting the Docker socket for service discovery. There is one known upstream, so daemon access provides no necessary benefit.
4. Keep the Traefik API/dashboard disabled and its health endpoint private. Retain normal restart behavior and bounded health checks.
5. NGINX plus Certbot and Caddy are viable alternatives. Traefik matches the user's chosen setup and includes the certificate client; a second reverse proxy or certificate manager is unnecessary.

### Explicit HTTPS profile in the existing Compose file

1. Add the proxy under the `https` Compose profile, enabled persistently through `COMPOSE_PROFILES=https` in the instance's private `.env`.
2. Keep `compose.yaml` as the deployment entry point. This avoids implicit overrides or a second production Compose command that the deployment script might omit.
3. Optional-profile variables must not make local `docker compose config` or startup fail when HTTPS is disabled. Compose interpolates inactive services too; required hosted-field validation must be mode-aware.
4. Configuration remains external to the frontend build. New documented settings are `HUGINN_DOMAIN`, `HUGINN_DOMAIN_ALIAS`, and `HUGINN_ACME_EMAIL`. For this instance their domain values are `huginn.live` and `www.huginn.live`; the owner supplies an actual contact email.
5. Hosted activation also sets existing `HUGINN_WEB_ORIGIN=https://huginn.live`, `HUGINN_MANAGEMENT_ENVIRONMENT=production`, and `HUGINN_BIND_ADDRESS=127.0.0.1`. Retaining loopback port 8080 supports operator diagnosis; public requests use ingress only.
6. Add mode-aware preflight to the existing configuration/deployment entry points rather than introducing a general deployment framework. It validates canonical/alias hostnames, public origin, contact email, private app binding and proxy trust before service replacement. Never evaluate `.env` as shell code or log resolved credentials.

### HTTP validation and canonical routing

1. Use Let's Encrypt HTTP-01 on port 80, with a separate ACME certificate resolver and persistent account/certificate storage. GoDaddy API access and wildcard certificates are unnecessary.
2. The TLS router covers canonical and alias hostnames so HTTPS alias redirects have a valid certificate before the redirect occurs.
3. Explicit hostname-matched HTTP and alias redirect rules produce permanent 301 responses for GET and method-preserving 308 responses for other methods, preserving path and query. ACME's challenge route remains functional. Unknown HTTP hostnames receive no application route.
4. Use Let's Encrypt staging for end-to-end issuance tests and production only after DNS/network prerequisites pass. Keep staging and production certificate stores separate and activate only the selected resolver, so inactive staging state cannot enter the shared TLS store or suppress production issuance.
5. Store account/certificate material in a dedicated named volume with restrictive permissions. Container replacement and application rollback never remove this volume. Document backup and restore without printing private keys.
6. Avoid HTTP Strict Transport Security preload and broad subdomain policies in this first activation, so certificate/debugging mistakes do not create a persistent browser lockout.

### Trust only the private ingress connection

1. Preserve the public Host header and have ingress overwrite untrusted client-provided forwarding information with the observed scheme and source address.
2. Configure Uvicorn's proxy-header support with an explicit trusted proxy address or narrowly allocated dedicated proxy-network CIDR. Do not use universal forwarded-header trust. Only the proxy and app attach to the ingress network; choose a configurable non-conflicting network range during implementation.
3. Continue to use the existing browser-origin dependency. Do not make it trust raw forwarded headers or relax same-origin checks to accommodate the proxy.
4. Add actual proxy integration checks for HTTPS scheme reconstruction and client-address handling, including forged forwarding headers. Keep proxy trust settings on the app entry point rather than adding them to domain code or every worker.
5. Set production mode and the public origin consistently for the app, workers and weekly job so generated links use the domain. Existing cookies scoped to the IP do not migrate; users sign in again.

### Verify ingress without extending deployment deadlines

1. Preserve exact image checks, explicit Compose-file selection, bounded command execution, operator-edit protection, and the special handling for unconfirmed process termination.
2. Validate the post-checkout resolved hosted configuration before changing `.env` or running Compose. Local mode keeps its current readiness check; hosted mode adds an ingress check within the existing aggregate deadline.
3. Verify `https://<canonical-host>/ready` through the actual local Traefik listener using the public hostname for TLS SNI and HTTP Host. Resolving that hostname to loopback for this host-side check avoids dependence on EC2 public-address hairpin routing; certificate validation remains enabled. This does not replace the separate external DNS/network acceptance check.
4. Require HTTP 200 with the readiness response. A self-signed/default certificate, unexpected redirect, 404 or unavailable router is a failure. Bound retries for certificate issuance and report failure when the existing time budget is exhausted.
5. Preserve the enabled profile and certificate volume on normal release and rollback. The first release that introduces HTTPS needs explicit cutover handling: a pre-HTTPS revision is not a supported automatic rollback target after activation. In that case report manual recovery instead of restarting an old public-HTTP stack.
6. Changes under `docker/traefik/` must not be mistaken for database-schema changes; leave the existing schema/bootstrap guard scoped to its current database paths.

## Risks / Trade-offs

1. Incorrect DNS or an unreachable port can prevent issuance. Mitigation: verify both names and both required ports before production activation, keep staging separate, and fail visibly.
2. An auto-assigned EC2 address can change after stop/start. Mitigation: associate an Elastic IP before final DNS cutover, or explicitly document the manual DNS update requirement if the owner keeps the current address. No address allocation is part of this change.
3. Certificates do not solve SMTP delivery. Mitigation: preserve Brevo settings and keep email delivery checks outside this hosting change. Link-origin checks can run without sending mail.
4. Broad proxy trust can let forged headers affect origin checks or login throttling. Mitigation: private ingress network, narrow trust, header normalization and negative integration tests.
5. Certificate issuance can exceed the deployment's wait budget. Mitigation: perform first issuance through the explicit activation procedure, use bounded checks, and avoid claiming a live certificate exists based on process health alone.
6. File-provider configurations require deliberate reload/recreation when deployed. Mitigation: recreate/reload the proxy when its tracked configuration changes and verify the resulting live route rather than assuming a bind mount reload occurred.

## Migration Plan

1. Owner verifies a stable EC2 address. In GoDaddy, replace conflicting parking records with A `@` pointing to that address and CNAME `www` pointing to `huginn.live`. Preserve unrelated MX/TXT records, including Brevo records. Do not leave an AAAA record unless IPv6 is intentionally configured and reachable.
2. Owner verifies AWS inbound TCP 80 and 443 are open. Keep SSH rules unchanged. Check that nothing else binds those host ports.
3. Prepare and validate the release with HTTPS disabled. Merge/deploy through the existing pipeline; this first deployment adds support without changing the existing private credentials or activating public TLS automatically.
4. Back up the private `.env` with restrictive permissions. Record its prior origin/binding settings without printing passwords or tokens. Supply domain, alias, actual ACME email, HTTPS profile, production environment, loopback binding and narrow proxy trust.
5. Run configuration preflight and staging issuance using separate staging certificate state; inspect routing and certificate coverage. Then activate the production resolver/store and wait for a trusted certificate.
6. Verify canonical/alias DNS, certificate chain and SANs, HTTP redirects, public `/ready`, frontend assets, new login, authenticated navigation and a reversible user-owned mutation. Confirm unauthorized Origin and forged proxy headers remain rejected/normalized. Do not trigger collection, migrations or outbound mail.
7. Remove inbound public 8080 access after HTTPS acceptance. Independently verify it is unreachable while domain access works.
8. Recreate the proxy and verify certificate-state persistence. Test renewal against staging rather than forcing production renewals. Trigger or observe a routine digest-pinned image deployment and verify HTTPS survives.
9. For ordinary later rollback, retain HTTPS mode and certificate storage. For initial cutover failures, use the saved private configuration and an explicitly chosen recovery procedure; do not automatically re-expose plaintext service or delete volumes. Report which services are reachable and which acceptance checks remain incomplete.

## Implementation references

1. [Traefik ACME configuration and renewal](https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/).
2. [Traefik file provider](https://doc.traefik.io/traefik/reference/install-configuration/providers/others/file/).
3. [GoDaddy A records](https://www.godaddy.com/en-uk/help/add-or-edit-an-a-record-42546).
4. Existing repository contracts: `compose.yaml`, `compose.env.example`, `scripts/deploy-ec2.py`, `src/huginn/management/config.py`, and `src/huginn/management/presentation/api/dependencies/browser_origin.py`.
