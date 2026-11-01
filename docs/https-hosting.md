# Serve Huginn at an HTTPS domain

Use the optional `https` Compose profile to run Traefik in front of Huginn.
Traefik obtains and renews Let's Encrypt certificates. The same domain serves
the website and API; neither NGINX nor Certbot is required.

## Prepare DNS and the instance

1. Deploy the supporting Huginn release with HTTPS disabled first. Keep the
   existing private `.env`, database and mailbox volumes. Do not regenerate
   secrets, initialize a database or run collection to test HTTPS.
2. Choose a stable public instance address, preferably an Elastic IP. If you
   retain an automatically assigned address, update DNS whenever stop/start
   changes it. The address belongs in DNS, not application code or GitHub secrets.
3. In GoDaddy DNS, configure these records using the actual instance address:

   | Type | Name | Value |
   | --- | --- | --- |
   | A | `@` | Your stable EC2 public IPv4 address |
   | CNAME | `www` | `huginn.live` |

   Remove conflicting parked-domain A/CNAME records. Preserve MX and TXT records,
   including Brevo verification, SPF, DKIM and DMARC records. Remove stale AAAA
   records unless IPv6 is configured and reachable. GoDaddy forwarding is not
   required. Check both names resolve before requesting certificates:

   ```sh
   dig +short A huginn.live
   dig +short A www.huginn.live
   dig +short AAAA huginn.live
   ```

4. In the instance security group, allow HTTP/TCP **80** and HTTPS/TCP **443**
   from Anywhere IPv4 (`0.0.0.0/0`). Keep SSH settings unchanged. Check host
   firewall rules too. Port 80 remains available for certificate HTTP validation
   and redirects. Opening 443 alone does not enable HTTPS.
5. Check no existing server owns ports 80/443:

   ```sh
   sudo ss -ltnp '( sport = :80 or sport = :443 )'
   ```

## Set private hosted configuration

Back up `.env` before editing it. Keep backups private and outside Git:

```sh
umask 077
mkdir -p .local-runtime
cp --preserve=mode .env .local-runtime/env-before-https
nano .env
```

Set these values, replacing the contact email with an address you monitor:

```dotenv
COMPOSE_PROFILES=https
HUGINN_DOMAIN=huginn.live
HUGINN_DOMAIN_ALIAS=www.huginn.live
HUGINN_ACME_EMAIL=YOUR_REAL_CONTACT_EMAIL
HUGINN_ACME_ENVIRONMENT=staging
HUGINN_WEB_ORIGIN=https://huginn.live
HUGINN_MANAGEMENT_ENVIRONMENT=production
HUGINN_BIND_ADDRESS=127.0.0.1
HUGINN_PROXY_IP=172.30.255.2
HUGINN_INGRESS_SUBNET=172.30.255.0/29
```

Preserve `HUGINN_IMAGE`, passwords, lifecycle key, source keys and SMTP settings.
The app and all workers share the public origin. The weekly job uses it too.
No frontend rebuild with an IP address is needed. Existing IP cookies do not
transfer to the domain; users sign in again.

Choose another unused private `/29` subnet if the default overlaps an existing
Docker network or route. Keep the proxy address within it, away from its network,
gateway and broadcast addresses. Only app and proxy join this network. Uvicorn
trusts that one proxy address; never set `FORWARDED_ALLOW_IPS=*`.

Validate before replacing services:

```sh
sudo python3 scripts/configure-compose.py --check
```

This resolves the repository's explicit `compose.yaml` without printing secrets.
Hosted mode rejects inconsistent domain/origin, missing contact email, nonproduction
cookies, public app binding and broad proxy trust. Local mode needs none of these
domain settings. Always run the preflight before a manual hosted `up`.

## Test staging, then enable trusted certificates

Start staging issuance only after DNS and ports are ready:

```sh
sudo docker compose --env-file .env -f compose.yaml pull
sudo docker compose --env-file .env -f compose.yaml up -d --no-build --wait
sudo docker compose --env-file .env -f compose.yaml logs --tail=100 traefik
```

Staging certificates are deliberately untrusted by browsers. Inspect their
issuer and SANs for both names without logging private key material:

```sh
openssl s_client -connect huginn.live:443 -servername huginn.live </dev/null 2>/dev/null |
  openssl x509 -noout -issuer -subject -dates -ext subjectAltName
```

When staging issuance works, change only `HUGINN_ACME_ENVIRONMENT=production`
in `.env`, rerun preflight, and recreate Traefik:

```sh
sudo python3 scripts/configure-compose.py --check
sudo docker compose --env-file .env -f compose.yaml up -d --no-build --force-recreate traefik
curl --fail --show-error https://huginn.live/ready
curl --head 'http://huginn.live/login?from=setup'
curl --head 'https://www.huginn.live/login?from=setup'
```

Production checks must validate TLS normally. An untrusted/default certificate,
redirected `/ready` or unavailable route is incomplete activation. Inspect proxy
logs and DNS/port prerequisites instead of disabling certificate verification.
Both names must validate: HTTPS aliases need certificates before redirecting.
Unknown hostnames receive no application route. Redirects preserve path/query;
unsafe request methods use method-preserving permanent redirects.

The profile is retained in `.env`, so subsequent automated image deployments keep
ingress enabled. They verify both private app readiness and trusted canonical
HTTPS readiness, resolving the hostname to host loopback for the latter. This
avoids public-IP hairpin routing and does not replace external DNS/network checks.
Proxy configuration changes recreate the proxy. Deployment does not add time
beyond its existing deadline or change AWS rules.

## Complete acceptance

1. From another machine, verify both DNS names, trusted certificate chains and
   SANs, canonical redirects, `/ready`, and assets.
2. Open the domain in a browser. Sign in, reload a protected deep link, verify
   current-session access, make and restore a harmless profile edit, and sign
   out. Check Secure/HttpOnly cookies and same-origin API requests. Test rejected
   cross-origin authentication requests separately without sending real mail.
3. Remove the security-group rule exposing port 8080 after HTTPS works. Verify
   `http://INSTANCE_IP:8080` is unreachable externally and the domain still works.
   On the instance, `curl --fail http://127.0.0.1:8080/ready` remains available.
4. Recreate Traefik and verify the trusted certificate remains available with
   the same serial/expiry. Observe one normal automated image deployment and
   confirm HTTPS still works. Keep local disposable test evidence distinct from
   these production checks; a passing homepage alone is insufficient.

## Certificate storage and recovery

Separate named volumes hold production and staging account/certificate state.
Traefik automatically renews eligible certificates; no renewal cron job is needed.
Keep port 80 and DNS working. Inspect certificate expiry and proxy logs when
diagnosing renewal. Exercise forced renewal only against staging, never by
repeatedly deleting production state or requesting production reissuance.

Back up both certificate volumes together with the private configuration and
database backups. Stop Traefik briefly for a consistent certificate-state archive,
use a trusted local backup tool/container to copy each named volume into private
storage, preserve restrictive file permissions, and start it again. Inspect volume
names with `docker volume ls` for your Compose project. Never print `acme.json`,
commit it, or serve backups through the web root. Restore the same volume contents
and `.env` before recreating the proxy. Do not use `down --volumes`.

After activation, automatic recovery refuses a prior checkout without HTTPS
support and reports manual inspection rather than restoring a plaintext stack.
If command termination is unconfirmed, inspect the previous SSM command before
running anything else. Preserve the current checkout, `.env`, certificate volumes
and operator edits. A pre-HTTPS revision is not an automatic rollback target.
Choose a supporting revision and compatible image explicitly, validate its hosted
configuration, then recreate services and verify TLS. There is no automatic
database or container rollback. Do not restore an old public binding as a shortcut.

For failed first issuance, fix DNS, contact settings or connectivity, then retry
staging with its existing state. Keep users off the domain until production TLS
and authentication checks pass. Restoring settings is an explicit operator action;
never delete database/certificate volumes to recover ingress.

References: [Traefik ACME](https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/),
[file provider](https://doc.traefik.io/traefik/reference/install-configuration/providers/others/file/),
[GoDaddy A records](https://www.godaddy.com/en-uk/help/add-or-edit-an-a-record-42546).
