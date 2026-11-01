## Why

Huginn currently runs on EC2 through a public HTTP IP address and port. The owner has registered `huginn.live` and needs a normal HTTPS address with automatically renewed certificates, working authentication, and compatibility with the existing image deployment pipeline.

## What Changes

1. Add an optional Traefik HTTPS deployment to the existing Docker Compose stack, with certificates obtained and renewed through Let's Encrypt.
2. Serve the frontend and API at the single canonical origin `https://huginn.live`. Support `www.huginn.live` as an HTTPS redirect to the canonical hostname.
3. Redirect ordinary HTTP requests to HTTPS and preserve the ACME HTTP challenge endpoint.
4. Persist certificate account and key material outside container filesystems; keep application, database, mailbox and proxy administration ports private.
5. Enable existing production session-cookie and public-origin settings. Configure narrowly scoped proxy trust so browser authentication and client-address handling work behind TLS termination.
6. Keep local development unchanged. Preserve HTTPS configuration and certificate storage across automated image deployments and supported recovery.
7. Document GoDaddy DNS, AWS network prerequisites, first activation, certificate verification, renewal, and recovery.

## Capabilities

### New Capabilities

1. `https-ingress`: Domain routing, HTTPS issuance and renewal, private upstream connectivity, production origin handling, and deployment verification.

### Modified Capabilities

None. Existing authentication and deployment protections remain requirements; this change adds their hosted HTTPS integration.

## Impact

1. Deployment configuration: `compose.yaml`, `compose.env.example`, and focused configuration under `docker/traefik/`.
2. Deployment orchestration: `scripts/deploy-ec2.py` and its regression tests, only where needed for HTTPS preflight, enabled-service verification and recovery.
3. Application composition: Uvicorn proxy-trust configuration; no domain, ranking, ingestion or database-schema changes.
4. Operator documentation: `docs/docker-compose.md`, with HTTPS setup guidance split into a focused operator page if needed.
5. External prerequisites: GoDaddy DNS records, reachable AWS TCP ports 80/443, a stable EC2 public address, and an operator-supplied ACME contact email.
6. One additional pinned open-source Traefik container and persistent certificate volume. No NGINX, separate Certbot process, paid certificate, load balancer, GoDaddy API integration or Kubernetes.

## Non-goals

1. Fixing EU-Startups collection, integrating Brevo, or scheduling weekly jobs.
2. Managing DNS or security groups automatically; the owner controls those settings.
3. Wildcard certificates, arbitrary customer domains, public proxy dashboards, high availability, or a new hosting platform.
4. Deploying or issuing a live certificate as part of writing this proposal.
