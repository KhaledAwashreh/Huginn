## 1. Compose ingress and private configuration

- [x] 1.1 Add a pinned Traefik service under an opt-in HTTPS profile and file-provider configuration under `docker/traefik/`; verify the resolved local configuration has no active ingress and the hosted configuration publishes only the intended ingress ports.
- [x] 1.2 Add canonical-host and alias routing, permanent HTTP/canonical redirects (301 for GET, 308 for other methods), private upstream connectivity, and persistent certificate storage; verify routing with the real proxy and a disposable upstream, including query preservation, unknown hosts and HTTP challenge handling.
- [x] 1.3 Document the private domain/contact/profile settings in `compose.env.example` and add mode-aware preflight to the existing configuration entry point; verify invalid hosted settings fail before service replacement while ordinary local startup needs no domain or ACME email.
- [x] 1.4 Pin supported proxy network/trust settings and keep the app loopback-bound in hosted mode; verify resolved exposure, absence of a Docker socket mount and isolation of the proxy health/administration endpoints.

## 2. Application origin and authentication

- [x] 2.1 Configure Uvicorn to reconstruct scheme and client address only from the designated ingress connection; verify through the actual proxy that HTTPS same-origin login works and fabricated forwarding headers do not control client identity.
- [x] 2.2 Verify production mode and the public origin reach the app, workers and weekly job; check Secure/HttpOnly cookies, rejected cross-origin login/logout and generated lifecycle/digest link origins without sending email.
- [x] 2.3 Run an HTTPS browser flow against a harness-owned disposable database: login, current session, deep-link refresh, a reversible user-owned mutation and logout; confirm frontend/API share one origin and existing HTTP-local browser behavior still passes.

## 3. Existing image deployment integration

- [x] 3.1 Add hosted preflight and a bounded canonical HTTPS readiness check to `scripts/deploy-ec2.py`; write failing regression cases first and verify that private readiness alone, an invalid certificate or an unavailable proxy cannot produce deployment success.
- [x] 3.2 Preserve exact image verification, explicit Compose-file selection, shared time budgets, operator configuration edits and certificate volumes; verify existing deployment tests plus profile-preservation, changed-proxy-configuration and recovery cases.
- [x] 3.3 Handle first-cutover rollback to a pre-HTTPS revision explicitly; verify it requires manual recovery without silently exposing HTTP or removing certificate state, and retain existing unconfirmed-termination behavior.

## 4. Operator guide and local verification

- [x] 4.1 Update the hosting guide with exact GoDaddy records, AWS ports, stable-address selection, new `.env` values, staging/production state separation, activation commands and recovery; verify commands against resolved Compose configuration and preserve unrelated MX/TXT records in the instructions.
- [x] 4.2 Verify actual proxy startup, trusted test TLS, canonical redirects and certificate-store persistence in an isolated local stack; retain logs under ignored `.local-runtime` and leave the persistent development/production databases untouched.
- [x] 4.3 Run relevant Compose, deployment and authentication checks plus `uv run ruff check .` and `uv run ruff format --check .`; review the complete changed tree and verify no keys, certificate state, raw logs or unrelated feature changes are tracked.
- [x] 4.4 Complete the repository pre-MR review and required push checks when publishing is authorized; record exact checks and limitations in the reviewable change description.

## 5. Owner prerequisites and production cutover

- [ ] 5.1 Owner confirms the stable instance address, GoDaddy DNS for canonical/alias hostnames, ACME contact email and inbound TCP 80/443; verify live DNS and port ownership before enabling HTTPS.
- [ ] 5.2 After the supporting release reaches EC2, back up private settings and activate staging then production using separate certificate stores; verify certificate SANs, trust chain and canonical/alias routing without insecure TLS flags in production checks.
- [ ] 5.3 Verify public readiness, assets and authenticated platform behavior through the domain; record production evidence separately from disposable-stack tests, with no collection runs, migrations or outbound emails.
- [ ] 5.4 Owner removes public port 8080 access after HTTPS works; verify that direct external access fails, private diagnosis still works and the domain remains reachable.
- [ ] 5.5 Recreate the proxy and observe a normal automated application deployment; verify persisted certificate state and working HTTPS, and validate renewal with the staging authority rather than forcing production reissuance.
