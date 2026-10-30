# Domain, Cloudflare, and public routes

This runbook covers the registered domain `pocket-doc.app`, DNS delegation from
Name.com to Cloudflare, and the planned path for publishing approved app routes
from the single-node K3s cluster. Domain registration stays at Name.com. This
document does not change DNS or deploy cluster resources.

## Current state and target

- `pocket-doc.app` is registered at Name.com.
- Name.com delegates `pocket-doc.app` to Cloudflare nameservers. The Cloudflare
  zone is DNSSEC-signed and its DS record is published at Name.com.
- The operator reports that the Cloudflare zone currently has no DNS records.
  ExternalDNS will add app records only after approved HTTPRoutes are ready.
- The locally managed Tunnel `oracle-k3s` has been created. Its tunnel-specific
  credential is stored in OCI Vault as `cloudflared-tunnel`; a GitOps connector
  is configured to send wildcard traffic to internal Traefik. No Tunnel DNS
  route or application route has been created.
- Tailscale remains the administration path for SSH, kubectl, and Argo CD.
- The OCI VM has no public inbound rule for ports 80 or 443. Keep it that way.
- K3s has Traefik and ServiceLB disabled. Gateway API CRDs already have one
  owner: the K3s-managed chart documented under
  `clusters/oracle/k3s-host-manifests/`. Do not install a second CRD bundle.
- Traefik chart 42.1.3 / Proxy 3.7.16 is installed as an internal ClusterIP
  Gateway API controller. The `oracle-public` GatewayClass is Accepted and its
  wildcard Gateway is Programmed. It has no application routes or Cloudflare
  tunnel target yet. The Service exposes only cluster-internal port 80. Its
  cluster role has no Secret access; namespaced Secret access is limited to
  `traefik-system` and `disease-prediction`.
- The existing External Secrets Operator reconciles only the
  `disease-prediction` namespace. A second controller is configured to watch
  only `edge-system`, using ESO's experimental controller-class feature. Its
  namespaced Vault `SecretStore` reports Ready, and a disposable Vault canary
  synced through the edge controller. The generated Kubernetes Secret and
  `ExternalSecret` were removed. Delete the unused Vault canary in OCI after
  this test.
- No application route should be published until that app has a defined API
  boundary, a publishable ARM64 image, and an explicit public-route decision.

The intended request path is:

```text
Browser
  -> Cloudflare DNS and edge
  -> proxied CNAME for app.pocket-doc.app to <tunnel-uuid>.cfargotunnel.com
  -> Cloudflare Tunnel
  -> cloudflared in K3s
  -> internal Traefik ClusterIP Service
  -> Gateway API HTTPRoute
  -> app Service
```

ExternalDNS will create and reconcile one DNS record for each approved
`HTTPRoute`. A locally managed Cloudflare Tunnel will use a wildcard ingress
rule for `*.pocket-doc.app` to forward those hostnames to Traefik. ExternalDNS
does not configure tunnel ingress rules; the wildcard rule handles that part.
The tunnel opens outbound connections to Cloudflare, so the VM needs no public
HTTP or HTTPS listener. The apex `pocket-doc.app` is not covered by the wildcard;
add it only if a future app specifically needs the apex hostname.

## Set up Cloudflare and Name.com now

Do the registrar and DNS steps before deploying ExternalDNS. Do not create an A
or AAAA record for the Oracle VM. If the domain already has email or verification
records, copy and verify those records before changing nameservers.

### 1. Add the domain to Cloudflare

1. Sign in to Cloudflare and add `pocket-doc.app` as a zone. Choose the DNS plan
   that fits the account; no Cloudflare account transfer is needed.
2. Let Cloudflare scan for DNS records, then compare its import with the records
   currently shown at Name.com. Cloudflare's scan can miss records. Add missing
   records manually before delegation.
3. Preserve any records already in use: MX, SPF, DKIM, DMARC, domain
   verification TXT records, and existing application records. Keep mail
   records DNS-only; do not proxy mail hostnames.
4. Record the two Cloudflare-assigned authoritative nameservers and the zone ID.
   The zone ID is configuration metadata, not a credential.

Cloudflare's [zone setup guide](https://developers.cloudflare.com/dns/get-started/)
covers adding a domain and checking the imported records.

### 2. Handle DNSSEC before changing nameservers

Check whether DNSSEC is enabled at Name.com. A stale DS record at the parent
registrar can make the domain return `SERVFAIL` after nameserver delegation.

1. If DNSSEC is enabled at Name.com, remove the existing DS record there before
   switching nameservers. Wait for its old TTL to expire. If DNSSEC is not
   enabled, skip this step.
2. After Cloudflare reports the zone as **Active**, enable DNSSEC in Cloudflare.
3. Copy Cloudflare's new DS values into Name.com's DNSSEC settings. Confirm the
   values match exactly; do not reuse the old DS record.

See Cloudflare's [DNSSEC setup](https://developers.cloudflare.com/dns/dnssec/)
and [stale DS troubleshooting](https://developers.cloudflare.com/dns/zone-setups/troubleshooting/cannot-add-domain/),
and Name.com's [DNSSEC instructions](https://cs.name.com/hc/en-us/articles/205439058-Managing-DNSSEC).

### 3. Delegate the domain at Name.com

1. Sign in to Name.com and open **My Domains**.
2. Select `pocket-doc.app`, then open **Manage Nameservers**.
3. Remove the current nameservers and enter both nameservers Cloudflare assigned.
   Use the exact hostnames Cloudflare shows; do not add extra nameservers.
4. Save the change. Keep the domain registered at Name.com; this only changes
   which provider is authoritative for DNS.
5. Wait for delegation to propagate. Cloudflare should report the zone as
   **Active** before you rely on it.

Name.com's [nameserver change guide](https://cs.name.com/hc/en-us/articles/205934547-Changing-nameservers-for-DNS-management)
shows the registrar steps. Cloudflare's [nameserver update guide](https://developers.cloudflare.com/dns/nameservers/update-nameservers/)
explains the activation check.

### 4. Verify the delegation and retained records

Run these checks from a machine with `dig` installed. Compare the results with
Cloudflare's assigned nameservers and the records you intend to keep:

```sh
dig NS pocket-doc.app +short
dig SOA pocket-doc.app +short
dig DS pocket-doc.app +short
dig MX pocket-doc.app +short
dig TXT pocket-doc.app +short
dig +dnssec pocket-doc.app A
```

Do not proceed to DNS automation until Cloudflare reports **Active**, the
authoritative NS records are Cloudflare's assigned pair, and required MX/TXT
records resolve correctly. Enable Cloudflare DNSSEC only after activation, then
verify the new DS record at Name.com has propagated.

## Target cluster design

### DNS and route ownership

- **Name.com** remains the registrar. It delegates DNS to Cloudflare.
- **Cloudflare DNS** is the only public DNS zone. There is no Oracle VM A/AAAA
  record and no direct public load balancer.
- **ExternalDNS** reads only Gateway API `HTTPRoute` resources. It is configured
  for the Cloudflare provider, the `pocket-doc.app` domain, the exact Cloudflare
  zone ID, and CNAME records only.
- A route must opt in with the `external-dns-public=true` label. The Gateway
  must also carry a dedicated label and the ExternalDNS Gateway label filter
  must match it. This keeps ordinary in-cluster routes out of public DNS.
- Put `external-dns.kubernetes.io/target: "<tunnel-uuid>.cfargotunnel.com"`
  on the public Gateway. Put
  `external-dns.kubernetes.io/cloudflare-proxied: "true"` on approved routes.
  Gateway API's ExternalDNS source reads the target from the Gateway and
  provider annotations from the Route.
- Add the Gateway target annotation only after the locally managed tunnel
  exists and its UUID is known. Until then, keep the Cloudflare zone empty;
  ExternalDNS will not be enabled before a real route and tunnel target exist.
- Start with `--policy=upsert-only` and ExternalDNS dry-run during validation.
  Once the zone filters, TXT ownership, and a real app route have been reviewed,
  move to `--policy=sync` if route removal should remove its DNS records
  automatically. `sync` is the intended steady state for automatic lifecycle
  management; it can delete records owned by this ExternalDNS instance.
- Use a stable TXT owner ID such as `oracle-k3s-pocket-doc-app` and a stable TXT
  prefix such as `external-dns-`. Never change either value after records have
  been created. The prefix gives the TXT ownership record a different name from
  the CNAME, which cannot share the same DNS name.
- Keep ExternalDNS at one replica. It must have read-only Kubernetes access to
  the required Gateway and HTTPRoute resources; it gets DNS write access only
  through the Cloudflare token.

The relevant upstream references are the ExternalDNS
[Gateway API source](https://github.com/kubernetes-sigs/external-dns/blob/master/docs/sources/gateway-api.md),
[annotations](https://github.com/kubernetes-sigs/external-dns/blob/master/docs/annotations/annotations.md),
[TXT registry](https://github.com/kubernetes-sigs/external-dns/blob/master/docs/registry/txt.md),
and [Cloudflare provider](https://github.com/kubernetes-sigs/external-dns/blob/master/docs/tutorials/cloudflare.md).

## Prepare Cloudflare credentials

The DNS zone can remain empty while these credentials are prepared. Do not add
placeholder A records or run `cloudflared tunnel route dns`; ExternalDNS will
own app records after a real route is approved. Name.com already delegates to
Cloudflare and publishes the Cloudflare DNSSEC DS record, so no registrar
change is needed.

### Create a zone-scoped ExternalDNS token

1. In Cloudflare, open **My Profile → API Tokens → Create Token → Create
   Custom Token**.
2. Grant **Zone → DNS → Edit** and **Zone → Zone → Read** permissions.
3. Under Zone Resources, include only **Specific zone → pocket-doc.app**.
4. Create the token and enter it directly into the existing OCI Vault using
   the OCI Console. Name the Vault secret `cloudflare-api-token` and use the
   existing Vault key. Do not put the token in Git, Terraform, a terminal
   command, or a message.
5. Copy the zone ID from the Cloudflare zone overview. The ID is configuration
   metadata; provide it with the tunnel UUID when the GitOps configuration is
   prepared.

Cloudflare documents [custom API token creation](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)
and the [token permission names](https://developers.cloudflare.com/fundamentals/api/reference/permissions/).

### Create a locally managed Tunnel

Run these steps on a trusted workstation with `cloudflared` installed:

```sh
cloudflared tunnel login
cloudflared tunnel create oracle-k3s
```

`tunnel login` creates an account-wide `cert.pem`; keep it only on that
workstation and never copy it to Kubernetes or OCI Vault. `tunnel create`
prints the tunnel UUID and creates a tunnel-specific JSON credentials file.
Store only that JSON file in OCI Vault as a secret named `cloudflared-tunnel`,
using the existing Vault key. Do not display or share the JSON contents. The
UUID is not secret and is needed in the Gateway target and tunnel config.

Cloudflare explains the difference between the account certificate and
tunnel-specific credentials in its [local tunnel setup](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/)
and [tunnel permissions guide](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/tunnel-permissions/).

Delete the temporary `edge-eso-canary` Vault secret after the successful ESO
test. Do not remove the `cert.pem` from the workstation until you no longer
need to manage the locally managed tunnel.

### Traffic, TLS, and exposure

- Run Traefik as an internal `ClusterIP` Service. Its Gateway API provider
  handles the `Gateway` and `HTTPRoute` objects. Keep the installed K3s Gateway
  API CRDs as the sole CRD owner.
- Restrict Traefik's provider watch to `traefik-system` and the app namespace.
  Bind namespaced Secret and route permissions only in those namespaces; keep
  its cluster binding limited to node, namespace, and GatewayClass access.
- Run `cloudflared` with a locally managed tunnel configuration. Its
  `*.pocket-doc.app` ingress rule points to Traefik's internal Service and ends
  with a catch-all `http_status:404` rule. Keep the configuration in Git, but
  keep the tunnel credential JSON out of Git.
- Cloudflare's local tunnel configuration supports wildcard host matching and
  requires a final catch-all rule. See the
  [configuration reference](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/).
- Cloudflared requires outbound connectivity to Cloudflare, including port
  7844 over TCP or UDP. The current OCI network allows outbound traffic; no
  inbound security-list rule is needed. See
  [Tunnel firewall requirements](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/).
- Use Cloudflare's proxied edge for public HTTPS. The first origin hop from
  cloudflared to Traefik can use cluster-internal HTTP. Add cert-manager only
  if an app needs a Kubernetes-managed certificate or the origin path needs
  TLS.
- Do not publish Argo CD, the Kubernetes API, SSH, or any admin-only service.
  Treat every opted-in HTTPRoute as Internet-accessible and require application
  authentication or a reviewed Cloudflare Access policy where appropriate.

See the official [Traefik Helm chart](https://github.com/traefik/traefik-helm-chart)
and [Gateway API provider guide](https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/gateway-api/).

## Work plan for implementation agents

Create separate pull requests by repository and keep each workstream inside its
file ownership. Do not apply a cluster change as part of a documentation or
render-only task. The operator performs the Name.com and Cloudflare dashboard
steps above; an agent must not change registrar or zone settings.

### Workstream 1 — DNS delegation and record audit

- Owner: operator, with a documentation reviewer
- Repository: no repository changes
- Depends on: access to the Name.com account and Cloudflare account

1. Confirm Cloudflare reports the zone as Active and review the current DNS
   records. The operator has removed all records; add back only records that
   are intentionally needed before app routes are published.
2. Verify the registrar delegates only to Cloudflare's assigned nameservers.
3. Verify Cloudflare DNSSEC is active and Name.com publishes the matching DS.
   Do not repeat the old-DS removal and nameserver cutover steps unless the DNS
   provider is changed again.

**Acceptance:** Cloudflare reports Active; authoritative NS answers match the
assigned pair; DNSSEC validates with the matching DS; any required email and
verification records resolve. Do not deploy ExternalDNS before this gate.

### Workstream 2 — External Secrets credential isolation decision

- Owner: GitOps security/design agent
- Repository: `disease-prediction-gitops`
- Depends on: current namespace-scoped ESO and OCI Vault setup

1. Keep the Cloudflare API token and tunnel credential in OCI Vault. The
   ExternalDNS token must be a custom Cloudflare API token with **Zone Read**
   and **DNS Edit**, scoped only to the `pocket-doc.app` zone. Do not use a
   Global API Key.
2. The existing ESO release watches only `disease-prediction`. The edge release
   is separately scoped to `edge-system`, uses controller class
   `oracle-edge-secrets`, disables CRD/webhook/cert-controller installation,
   and has no cluster-scoped RBAC. ESO documents controller classes as
   experimental, so verify the pinned release with a canary before adding
   credentials. Do not broaden the existing release cluster-wide or put edge
   credentials in the app-deployable namespace.
3. Document secure creation, initial entry into OCI Vault, rotation, status
   checks that do not print secret data, and revocation. Keep secret values out
   of Terraform, Terraform state, Git, command arguments, logs, and issue/PR
   text.

**Acceptance:** each ESO instance watches only its assigned namespace; the edge
store reports Ready and a disposable canary syncs without exposing its value;
the edge release creates no cluster-scoped RBAC or duplicate CRDs/webhooks. Do
not add edge credential manifests until these checks pass.

### Workstream 3 — Traefik and Gateway API foundation

- Owner: GitOps platform agent
- Repository: `disease-prediction-gitops`
- Depends on: Workstream 1; Workstream 2 decision; current K3s CRDs

1. Add a dedicated `traefik-system` namespace and a restricted Argo CD
   AppProject/Application for the official Traefik chart. Pin a reviewed chart
   and image version; confirm it supports the cluster's Kubernetes and the
   existing Gateway API bundle `v1.6.1`.
2. Render the chart and grant the AppProject only the exact namespaced and
   cluster-scoped kinds the selected values render. Keep the Gateway API CRDs
   disabled in the chart because K3s already owns them.
3. Set the Traefik Service to `ClusterIP`, one replica, and modest explicit
   resource requests/limits suitable for the 2 OCPU/12 GB node. Do not enable
   K3s Traefik, ServiceLB, a public LoadBalancer, or node ports.
4. Add platform-owned `GatewayClass` and `Gateway` manifests. Use a wildcard
   listener for `*.pocket-doc.app`, an internal HTTP listener, and
   `allowedRoutes` limited to explicitly labeled namespaces. Label the Gateway
   for the ExternalDNS gateway filter and place the tunnel CNAME target
   annotation on it.
5. Keep app `HTTPRoute` objects out of this PR. Add only the minimal
   `HTTPRoute` namespaced resource permission to `oracle-apps` when a real app
   route is ready.

**Acceptance:** Kustomize and Argo renders are reviewed; chart kinds match the
AppProject allowlist; no second Gateway API CRD owner is rendered; the Traefik
Service is ClusterIP; the GatewayClass is accepted and the Gateway is accepted
and programmed; OCI inbound ports 80/443 remain closed.

### Workstream 4 — Cloudflare Tunnel connector

- Owner: GitOps edge agent
- Repository: `disease-prediction-gitops`
- Depends on: Workstreams 1–3 and the credential isolation decision

1. Create a locally managed Cloudflare Tunnel named for this cluster. Protect
   the account certificate used to create it; do not copy that account-wide
   certificate into Kubernetes. Keep only the tunnel-specific credential JSON
   in OCI Vault. The tunnel UUID is non-secret configuration.
2. Do not run `cloudflared tunnel route dns` for app hostnames. ExternalDNS is
   the sole DNS-record writer for approved app routes.
3. Add a version-pinned `cloudflared` Deployment in `edge-system` and a
   ConfigMap with the locally managed ingress
   config. The wildcard rule forwards `*.pocket-doc.app` to the actual internal
   Traefik Service and port; the last rule returns 404.
4. Mount the tunnel credential through the accepted Vault/ESO path. Use a
   read-only filesystem where supported, a non-root security context, resource
   requests/limits, and readiness/liveness checks that do not expose secrets.
5. Document tunnel credential rotation, connector health checks, and teardown.

**Acceptance:** config validation passes; the connector is healthy; traffic
from the connector reaches the internal Traefik listener; no DNS record is
created by tunnel setup; OCI ingress 80/443 remains closed; no credential is
printed or checked in.

Official references: [create a locally managed tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/create-local-tunnel/),
[tunnel credential permissions](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/tunnel-permissions/),
and the [wildcard ingress configuration](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/).

### Workstream 5 — ExternalDNS for Cloudflare

- Owner: GitOps DNS agent
- Repository: `disease-prediction-gitops`
- Depends on: Workstreams 1–4 and the credential isolation decision

1. Install ExternalDNS in `edge-system` under a restricted AppProject and
   Application for the official chart. The same namespace is reserved for
   platform edge services and is not an app namespace. Pin chart and image
   versions; confirm the selected release supports the Gateway API source and
   current CRDs.
2. Use only `gateway-httproute` as a source. Configure Cloudflare as provider,
   `pocket-doc.app` as domain filter, the exact zone ID as zone filter, and
   CNAME as the only managed record type.
3. Require both an approved Gateway label filter and the
   `external-dns-public=true` HTTPRoute label filter. Use the Gateway target
   annotation for `<tunnel-uuid>.cfargotunnel.com`; use the route's Cloudflare
   proxy annotation. Do not also enable Service, Ingress, or Node sources.
4. Use a single replica, TXT registry, stable owner ID
   `oracle-k3s-pocket-doc-app`, and stable prefix `external-dns-`. Keep these
   values unchanged after the first record is written.
5. Supply `CF_API_TOKEN` from an ESO-created Secret in `edge-system`.
   Never put the token in chart values, a ConfigMap, Terraform, Git, or command
   output. Give the ExternalDNS ServiceAccount only read access to the required
   Gateway and HTTPRoute objects; it does not need Kubernetes write access.
6. Limit the initial route source to `disease-prediction`, which is the only
   namespace currently allowed by `oracle-apps`. Give its ServiceAccount
   read-only access to HTTPRoutes there and to the public Gateway in
   `traefik-system`; do not grant Kubernetes write access or cluster-wide
   Secret access. When a future app namespace needs public routes, add it as a
   separate reviewed scope change.
7. First run the pinned controller in dry-run mode and review its planned
   changes. Start live validation with `upsert-only`. After a real app route
   demonstrates correct zone scoping and TXT ownership, switch to `sync` if
   automatic record deletion on route removal is desired. Export the zone
   before that first deletion-capable rollout.

**Acceptance:** render and inspect all chart kinds and RBAC; dry-run output is
limited to an approved in-zone route and a CNAME target at the tunnel hostname;
Cloudflare shows a proxied CNAME and the prefixed TXT owner record after live
validation; no unrelated records change; ExternalDNS is healthy at one replica.

### Workstream 6 — Publish each app route

- Owner: application agent, with platform review
- Repository: `disease-prediction-gitops` plus that app's source repository
- Depends on: app API boundary and ARM64 image readiness; Workstreams 1–5

For each app, use a separate pull request that:

1. Documents the public API boundary, authentication, health behavior, and
   public hostname.
2. Confirms a publishable ARM64 image exists and is deployed in the intended
   namespace.
3. Adds an `HTTPRoute` to the internal Gateway with only the required host and
   backend service. Add the public opt-in label and Cloudflare proxy annotation.
4. Does not publish admin endpoints, internal APIs, or Argo CD. Do not add
   direct node ports, LoadBalancer services, or OCI inbound rules.
5. Verifies Gateway route status, ExternalDNS reconciliation, Cloudflare
   proxy/TLS, application authentication, and a real request over HTTPS.

**Acceptance:** only the approved hostname is created; its proxied CNAME points
to the tunnel; the TXT ownership record has the configured prefix and owner;
the app responds as expected; removing the route follows the configured DNS
deletion policy.

## Rollout and review order

1. Complete the Cloudflare and Name.com delegation checklist.
2. Merge the ESO credential-isolation design before writing any DNS-token
   `ExternalSecret` or broadening controller permissions.
3. Merge the Traefik/Gateway foundation and verify it through Argo CD.
4. Create and store the tunnel-specific credential securely; merge and verify
   the connector with no DNS changes.
5. Merge ExternalDNS with dry-run and strict Cloudflare filters. Review the
   rendered chart kinds, RBAC, target, label filters, TXT prefix, and owner ID.
6. Only then publish a real application route that meets Workstream 6. Keep
   `upsert-only` during initial DNS verification; change to `sync` only after
   ownership and deletion behavior have been reviewed.

For every GitOps pull request, render `clusters/oracle`, inspect the manifests
and Argo Project permissions, and review `kubectl diff` before syncing. Check
Argo sync/health, pod readiness, Gateway status, tunnel health, and DNS record
metadata without printing Secret data. Public DNS and route changes are separate
from Terraform; no Terraform network rule should be needed.

## Rotation, removal, and recovery

- **Rotate the Cloudflare token:** create a replacement token with the same
  zone-only permissions, update its OCI Vault secret value through the approved
  secure workflow, verify ESO sync without reading the Secret value, confirm
  ExternalDNS works, then revoke the old token in Cloudflare.
- **Rotate the tunnel credential:** use Cloudflare's supported tunnel
  credential procedure, update the Vault value, wait for the connector to
  become healthy, then revoke/remove the prior credential. Do not rotate by
  editing a Secret manifest in Git.
- **Remove one app:** remove its `HTTPRoute`. With `sync`, ExternalDNS removes
  DNS records it owns after reconciliation. With `upsert-only`, manually remove
  that route's CNAME and prefixed TXT record in Cloudflare after confirming
  their owner metadata.
- **Remove the edge stack:** remove approved app routes first; export the DNS
  zone; remove ExternalDNS and the tunnel connector; manually remove any
  remaining ExternalDNS-owned CNAME/TXT records; remove the Gateway and
  Traefik last. Argo's root app has pruning disabled, so deleting Git manifests
  alone does not uninstall live objects. Retain the Name.com delegation until
  all required DNS records have been moved or deliberately removed.
- **Recover administration:** use the Tailscale recovery path in
  [the cluster recovery runbook](recovery.md). Do not expose the API or Argo CD
  as a DNS workaround.
