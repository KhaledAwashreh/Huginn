## Purpose

Provide a stable HTTPS address for Huginn with automatic certificate management, working browser authentication, private upstream services, and verifiable deployments.

## ADDED Requirements

### Requirement: Canonical domain serves the complete application

The hosted deployment SHALL serve the frontend, static assets, API and existing client-side routes at the canonical origin `https://huginn.live` on standard port 443. It SHALL route the frontend and API through the same origin without requiring a browser-visible backend IP or nonstandard port. The canonical hostname SHALL be operator-configurable; the EC2 address SHALL NOT be embedded in application code or built frontend assets.

#### Scenario: Open and refresh the platform

- **WHEN** a browser opens `https://huginn.live` or refreshes an existing application route
- **THEN** the platform and its referenced assets load through the canonical origin
- **AND** API calls use that same origin without mixed-content requests

#### Scenario: Domain alias

- **WHEN** a client opens `https://www.huginn.live/path?query=value`
- **THEN** the service presents a trusted certificate covering the alias
- **AND** permanently redirects to `https://huginn.live/path?query=value`

#### Scenario: Unknown hostname

- **WHEN** an incoming HTTP request names a hostname outside the configured canonical hostname and alias
- **THEN** ingress does not forward that request to the application or expose proxy administration

### Requirement: HTTP redirects to HTTPS

Ingress SHALL permanently redirect ordinary requests for the configured hostnames on port 80 to the canonical HTTPS origin while preserving path and query. Redirects SHALL return 301 for GET requests and method-preserving 308 for other methods. The certificate authority's HTTP validation requests SHALL remain reachable without authentication and SHALL NOT be intercepted by application routing.

#### Scenario: Plain HTTP visit

- **WHEN** a client requests `http://huginn.live/path?query=value`
- **THEN** it receives a permanent redirect (301 for GET, 308 for other methods) to `https://huginn.live/path?query=value`
- **AND** the application does not process the request over plaintext HTTP

#### Scenario: Certificate validation request

- **WHEN** the configured certificate authority validates an active HTTP challenge on port 80
- **THEN** ingress serves the challenge through its certificate management facility
- **AND** validation does not require a logged-in Huginn session

### Requirement: Automatic trusted certificates persist across restarts

The hosted deployment SHALL obtain publicly trusted certificates covering the configured hostnames and renew them automatically before expiration. Certificate account data and private keys SHALL survive container recreation, application-image deployment and EC2 reboot. Private certificate material SHALL NOT be committed, printed in logs or served through HTTP. Issuance SHALL use public HTTP validation without requiring GoDaddy API credentials.

#### Scenario: First activation

- **WHEN** the configured DNS names resolve to the instance, ports 80 and 443 are reachable, and the operator activates HTTPS
- **THEN** the service obtains and serves trusted certificates for both configured hostnames
- **AND** clients can validate the certificate chain and hostname without disabling TLS verification

#### Scenario: Restart and renewal

- **WHEN** the proxy container is recreated or a certificate reaches its renewal window
- **THEN** the proxy reuses persisted account and certificate state
- **AND** renews eligible certificates automatically without a manually scheduled certificate command

#### Scenario: Issuance failure

- **WHEN** certificate issuance fails because DNS, connectivity or authority validation is unavailable
- **THEN** hosted activation is reported as incomplete with an actionable diagnostic
- **AND** deployment does not treat an untrusted default certificate or plaintext application response as successful HTTPS activation

### Requirement: Only ingress is publicly exposed

In hosted mode, public application traffic SHALL enter through ports 80 and 443. The application HTTP port SHALL be reachable only through private proxy connectivity or host loopback. PostgreSQL, mailbox interfaces, worker interfaces, proxy administration and proxy health endpoints SHALL NOT become publicly accessible. Ingress SHALL NOT require the Docker daemon socket or AWS credentials.

#### Scenario: Hosted network exposure

- **WHEN** the HTTPS deployment is active
- **THEN** external clients can reach the application through HTTPS
- **AND** cannot connect directly to the application on port 8080, database, mailbox or proxy administration
- **AND** the operator can continue to diagnose application readiness privately

### Requirement: Browser security works behind TLS termination

Hosted mode SHALL use the canonical HTTPS origin for application-generated links and existing browser-origin checks. Session cookies SHALL retain the existing production protections, including Secure and HttpOnly. The application SHALL accept proxy-provided scheme and client-address information only from the designated trusted proxy connection. Untrusted forwarded headers SHALL NOT override request identity or bypass same-origin mutation checks. Domain migration SHALL require a new login and SHALL NOT transfer browser cookies from the IP address.

#### Scenario: Login over the domain

- **WHEN** a user signs in through `https://huginn.live`
- **THEN** authentication succeeds, a protected session cookie is issued and authenticated navigation works
- **AND** a valid same-origin JSON mutation succeeds behind the proxy

#### Scenario: Cross-origin mutation

- **WHEN** a browser submits an authentication mutation with an unauthorized Origin
- **THEN** the existing same-origin policy rejects it even when forwarded headers claim the canonical origin

#### Scenario: Spoofed proxy information

- **WHEN** a public client supplies fabricated forwarded scheme or client-address headers
- **THEN** ingress normalizes those values before forwarding
- **AND** the application does not trust attacker-supplied values as the original client identity

#### Scenario: Generated account links

- **WHEN** the system generates verification, password-reset or digest links
- **THEN** their public origin is `https://huginn.live`, without the EC2 IP address, internal service name or port 8080
- **AND** no email needs to be sent to verify link generation

### Requirement: Hosted activation is explicit and local development remains usable

HTTPS SHALL be an explicit opt-in deployment mode. Existing local Compose startup SHALL remain usable without domain ownership, certificate issuance, an ACME contact email or public ports 80/443. Hosted activation SHALL reject missing or inconsistent hostname, production origin, proxy-trust and certificate settings before replacing running services. Private credentials and certificate state SHALL remain outside version control.

#### Scenario: Local startup

- **WHEN** an operator starts the ordinary local stack without enabling HTTPS
- **THEN** the application remains available on its configured local HTTP port
- **AND** no certificate request is attempted

#### Scenario: Invalid hosted settings

- **WHEN** HTTPS is enabled with an HTTP public origin, a mismatched hostname, missing required contact information or overly broad proxy trust
- **THEN** activation fails with a setting-specific diagnostic before replacing running services
- **AND** the previous private configuration and running deployment are preserved

### Requirement: Automated deployments preserve and verify HTTPS

The existing image publication and EC2 deployment flow SHALL retain its revision checks, deadline, configuration preservation and recovery protections. After initial HTTPS activation, ordinary deployments SHALL keep HTTPS enabled, retain certificate storage and require both application readiness and verified HTTPS routing for success. Future deployments SHALL NOT require manual image pulls or manual certificate renewal. Deployment SHALL use repository-owned configuration paths and SHALL NOT load arbitrary untracked Compose overrides.

#### Scenario: Routine application release

- **WHEN** the deployment pipeline installs a newly published application image on an HTTPS-enabled instance
- **THEN** it verifies the expected running image, private readiness and canonical HTTPS readiness within a bounded deadline
- **AND** the domain continues to serve the frontend and API using trusted certificates
- **AND** existing SMTP credentials, collection credentials and certificate state are preserved

#### Scenario: Proxy regression

- **WHEN** the application is privately ready but HTTPS routing, hostname verification or certificate validation fails
- **THEN** the deployment does not report success
- **AND** recovery follows existing bounded termination and operator-edit preservation protections

#### Scenario: Recovery cannot be confirmed

- **WHEN** command termination is unconfirmed or the previous release cannot support the active HTTPS configuration
- **THEN** the deployment reports that manual inspection is required
- **AND** does not race unfinished commands, destroy certificate storage or silently restore public plaintext application access

### Requirement: Operator setup and acceptance evidence are reproducible

Operator guidance SHALL document DNS records, stable-address selection, AWS inbound rules, required private settings, activation order, certificate storage backup and recovery. It SHALL distinguish local test evidence, live HTTPS checks and authenticated application checks. Reaching the homepage alone SHALL NOT establish complete acceptance.

#### Scenario: Complete domain cutover

- **WHEN** an operator follows the setup guide and completes cutover
- **THEN** evidence records DNS resolution, trusted certificates, canonical redirects, HTTPS readiness, static assets, login and a reversible authenticated mutation
- **AND** verifies certificate-state persistence after recreation and that port 8080 is no longer publicly reachable
- **AND** avoids database migrations, ingestion runs and outbound email as side effects of verification
