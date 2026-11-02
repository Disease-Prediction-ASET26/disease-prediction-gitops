# Domain and public routes

This guide covers the public edge for `pocket-doc.app`. Name.com is the
registrar, while Cloudflare hosts DNS and the public edge. The Authelia login
portal is published at `auth.pocket-doc.app`. The Argo CD UI is published at
`argocd.pocket-doc.app` behind its native Authelia OIDC configuration. Grafana
is configured for `grafana.pocket-doc.app` with the same native OIDC
integration. Its separate route remains manual-sync until the Grafana OIDC
client is ready. Product workload routes still need their own reviewed route
and authentication configuration.

## How traffic reaches an app

```mermaid
flowchart LR
  browser[Browser] -->|HTTPS| cf[Cloudflare edge]
  cf --> tunnel[Cloudflare Tunnel]
  tunnel -->|HTTP| traefik[Internal Traefik Gateway]
  traefik --> route[Opted-in HTTPRoute]
  route --> service[App Service]
```

Cloudflare handles browser-facing TLS. Traffic from `cloudflared` to Traefik,
and from Traefik to the app, uses HTTP inside the cluster. Add origin TLS if an
application requires encryption on those internal hops. The VM has no public
inbound rule for ports 80 or 443. Do not publish the Kubernetes API or SSH.
Argo CD and Grafana are reachable publicly only through their Gateway API
routes and native OIDC login; keep their Services ClusterIP-only.

## Current platform settings

- Name.com delegates the domain to Cloudflare. Cloudflare DNSSEC is enabled
  and the matching DS record is published at Name.com.
- The locally managed Tunnel `oracle-k3s` connects outbound to Cloudflare and
  forwards `*.pocket-doc.app` to Traefik's internal Service. A final catch-all
  returns 404. The tunnel credential is in OCI Vault as `cloudflared-tunnel`.
- Gateway API CRDs are owned by K3s through the checked-in host manifest. The
  Traefik CRD bundle is also installed from a version-matched K3s host
  manifest. Do not install a second CRD bundle.
- Traefik is an internal `ClusterIP` Gateway API controller. The `oracle-public`
  Gateway accepts routes only from namespaces labeled
  `pocket-doc.app/public-routes: "true"`.
- Traefik's provider watch scope and Kubernetes RBAC are separate settings.
  Its Gateway provider watches `traefik-system`, `disease-prediction`,
  `auth-system`, and `monitoring`; namespaced Roles are managed in
  `managed-traefik-access/reader-roles.yaml`. The `monitoring` Role includes
  read access to ConfigMaps and Secrets (including Grafana's OIDC Secret),
  discovery access to Services, Pods, EndpointSlices, and Gateway API objects,
  plus updates to selected Gateway API status subresources. Treat each watched
  namespace and its Secrets as accessible to Traefik; do not place unrelated
  high-trust credentials there.
- Traefik's web port allows pod-originated traffic only from the `cloudflared`
  pods in `edge-system`; Kubernetes NetworkPolicy does not restrict
  node-originated traffic. Its trusted forwarded-header range matches the K3s
  pod CIDR (`10.42.0.0/16`). Keep this range and the NetworkPolicy aligned if
  the pod network changes.
- Authelia and its HTTPRoute live in `auth-system`. Traefik has namespaced read
  access there, including Secrets; keep the namespace limited to authentication
  components. The login route has the `external-dns-public: "true"` label and
  Cloudflare proxy annotation.
- The `argocd-route` Application is in `argocd`, but its HTTPRoute and web proxy
  are in `auth-system`. The route uses Argo CD's native OIDC client against
  Authelia and does not use generic ForwardAuth. The manual-sync route has been
  published after OIDC was configured.
- The Grafana route is a separate manual-sync Application in `monitoring`.
  Grafana uses native OIDC with Authelia, disables local basic authentication,
  and maps the `admins` group to Grafana server administrator. The namespace is
  opted into public routes so the route can attach to `oracle-public`. Traefik
  can read Secrets in `monitoring`. Grafana's Service uses NativeLB because
  direct Pod IP connections from Traefik failed; its private HTTPS listener
  also accepts OIDC back-channel requests from Grafana pods.
- Traefik has no namespaced role in `argocd` and cannot read the OIDC client
  Secret there. The proxy forwards to Argo CD's ClusterIP Service.
- ExternalDNS watches Gateway API HTTPRoutes only. A route must have
  `external-dns-public: "true"`, and its Gateway must pass the configured
  label filter. DNS is limited to `pocket-doc.app`, the configured Cloudflare
  zone, and CNAME records. Cloudflare proxying is requested on the route.
- ExternalDNS uses the TXT owner `oracle-k3s-pocket-doc-app`, prefix
  `external-dns-`, and policy `upsert-only`. It creates or updates records but
  never deletes them. Remove stale CNAME and TXT records manually in Cloudflare.
- The Cloudflare API token is stored in OCI Vault as `cloudflare-api-token`.
  ESO syncs it to `edge-system`; do not place its value in Git or Terraform.
  ExternalDNS's configured route and zone filters limit its behavior, while
  its Kubernetes ServiceAccount still has read permissions defined by its
  installed ClusterRole: Gateway and HTTPRoute resources, plus Namespaces,
  across the cluster. This is read-only discovery access; inspect the rendered
  ClusterRole when changing the chart or source configuration.

The DNS ownership path is:

```mermaid
flowchart LR
  route[Reviewed, labeled HTTPRoute] --> extdns[ExternalDNS]
  gateway[Eligible Gateway target] --> extdns
  extdns -->|proxied CNAME| zone[Cloudflare zone]
  extdns -->|TXT owner record| zone
  delete[Route removed] -. upsert-only leaves records .-> zone
  operator[Operator] -->|manual cleanup| zone
```

The ExternalDNS domain, zone, label, and record-type filters limit what it
considers. The Cloudflare token still has DNS edit permission across the
selected zone; the filters are controller settings, not Cloudflare permission
boundaries.

## Internal OIDC traffic and geo restrictions

Argo CD keeps the public OIDC issuer `https://auth.pocket-doc.app`, so browser
redirects and issuer validation use the canonical host. A host alias in the
Argo pods sends server-side discovery, token, and userinfo requests for that
host to Traefik's ClusterIP. Traefik terminates TLS on a private HTTPS Gateway
listener using an Authelia Origin CA certificate, then forwards the request to
Authelia over the existing cluster HTTP Service. Argo CD trusts Cloudflare's
Origin CA root. This internal path avoids Cloudflare's country check for
Argo's back-channel requests while public browser traffic still passes through
Cloudflare.

The Origin certificate and private key come from OCI Vault and are synced into
`auth-system/authelia-origin-tls`; see the [Authelia runbook](authelia.md#prepare-the-internal-oidc-certificate).
Keep the Romania-only Cloudflare block for public requests. After confirming
Argo CD login works through the internal listener, remove any temporary
Cloudflare exception made for the Oracle egress IP and OIDC paths. Do not add
a broad IP allow rule. Cloudflare Origin CA certificates are not browser-
trusted, so browser traffic must continue to use Cloudflare's edge
certificate. The Origin CA root currently expires in 2029; rotate Argo CD's
trusted root before then. See Cloudflare's [Origin CA documentation](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/).

## Set up the registrar and Cloudflare zone

This setup is already complete. Use these steps if you move DNS providers or
rebuild the zone:

1. Add `pocket-doc.app` to Cloudflare. Compare imported DNS records with the
   registrar's current records and restore any required mail or verification
   records before delegation.
2. At Name.com, set the domain's nameservers to the exact pair Cloudflare
   assigns. Keep the registration at Name.com.
3. Wait until Cloudflare reports the zone as **Active**. Verify with
   `dig NS pocket-doc.app +short` and `dig SOA pocket-doc.app +short`.
4. Enable DNSSEC in Cloudflare. Publish Cloudflare's current DS values at
   Name.com; remove any stale DS before changing providers. Check with
   `dig +dnssec pocket-doc.app A` and `dig DS pocket-doc.app +short`.
5. Do not create VM A/AAAA records or use `cloudflared tunnel route dns` for
   app names. ExternalDNS owns approved app records.

Cloudflare documentation: [zone setup](https://developers.cloudflare.com/dns/get-started/),
[DNSSEC](https://developers.cloudflare.com/dns/dnssec/), and
[custom API tokens](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/).

## Credentials and rotation

The ExternalDNS token is a Cloudflare custom API token with **Zone → DNS →
Edit** and **Zone → Zone → Read**, scoped to `pocket-doc.app`. ExternalDNS
also receives the zone ID as non-secret configuration. Prefer an expiration
when Cloudflare supports one for this account; otherwise set a review and
rotation reminder. Zone DNS Edit can change records throughout the zone even
though ExternalDNS is configured to manage only CNAMEs.

To rotate the token, create a replacement with the same scope, update the
`cloudflare-api-token` value in OCI Vault, confirm the ESO resource is Ready
and ExternalDNS has recovered, then revoke the old token. Never print the
Kubernetes Secret value.

The tunnel credential JSON belongs in OCI Vault secret `cloudflared-tunnel`.
The account certificate used to manage a locally managed tunnel stays on the
trusted workstation. Do not copy it to Kubernetes or Git.

## Publish an application route

Only publish an app after its API boundary, authentication, health behavior,
and ARM64 image are ready and public access is approved. Keep the Service
internal (`ClusterIP`); the Gateway and Cloudflare Tunnel provide public
ingress.

### Choose how Authelia protects the app

- **ForwardAuth:** use this for an app without its own OIDC login. Traefik
  checks each request with Authelia; the app does not receive an app-specific
  OIDC session. Add the `ExtensionRef` filter to every route rule and retain
  the rule's backend reference. The shared Middleware is
  `disease-prediction/authelia-forwardauth`, so this works only for routes in
  `disease-prediction`. For another namespace, create a Middleware there, add
  that namespace to Traefik's CRD provider watch scope and namespaced RBAC, and
  allow the resource in its Argo CD AppProject. Do not enable cross-namespace
  Middleware references cluster-wide as a shortcut.
- **Native OIDC:** use this when the app supports OIDC and needs its own
  session, scopes, or role mapping. Register the exact callback URL in
  Authelia, sync the plaintext client secret only to the app namespace through
  ESO, and configure the app's issuer, claims, and local-login policy. Do not
  also add ForwardAuth to that route. Grafana and Argo CD use this pattern;
  their runbooks cover their app-specific callback and internal OIDC network
  paths.

### Add and publish the route

In the app namespace, check all the routing gates before adding the HTTPRoute:

| Setting | Value | Purpose |
|---|---|---|
| Namespace label | `pocket-doc.app/public-routes: "true"` | Allows attachment to `oracle-public` |
| Route label | `external-dns-public: "true"` | Opts the hostname into ExternalDNS |
| Route annotation | `external-dns.kubernetes.io/cloudflare-proxied: "true"` | Requests Cloudflare proxying |
| Gateway label | `external-dns.pocket-doc.app/eligible: "true"` | Allows the Gateway to be an ExternalDNS target |

The app's Argo CD AppProject must allow the namespace destination and route
resources. Traefik's Gateway provider must watch the route namespace, and the
matching Role in `managed-traefik-access/reader-roles.yaml` must grant the
provider's namespaced API access. The Helm chart's `rbac.enabled` is false, so
changing watch scope alone does not create these Roles. If the route uses a
Traefik Middleware, check the separate CRD provider watch scope and RBAC too.

The following is a ForwardAuth example for an app in `disease-prediction`,
where the shared Middleware lives. For another namespace, create the Middleware
there with the same name and add its CRD provider scope and RBAC. For native
OIDC, omit the `filters` block and configure the app as described above:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: <app-name>
  namespace: <app-namespace>
  labels:
    external-dns-public: "true"
  annotations:
    external-dns.kubernetes.io/cloudflare-proxied: "true"
spec:
  parentRefs:
    - name: oracle-public
      namespace: traefik-system
      sectionName: web
  hostnames:
    - <app-host>.pocket-doc.app
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      filters:
        - type: ExtensionRef
          extensionRef:
            group: traefik.io
            kind: Middleware
            name: authelia-forwardauth
      backendRefs:
        - name: <app-service>
          port: <service-port>
```

Keep the route manifest and namespace opt-in label in the same reviewed Git
change. Render `clusters/oracle`, review the Argo CD AppProject and diff, then
merge and sync the relevant Application. Do not use a direct public IP,
NodePort, or LoadBalancer.

Check discovery, backend connectivity, route status, DNS, and authentication:

```sh
kubectl -n <app-namespace> get service,endpointslices
kubectl -n <app-namespace> get httproute <route-name> -o yaml
kubectl -n traefik-system get gateway oracle-public
dig <app-host>.pocket-doc.app A
curl -I https://<app-host>.pocket-doc.app/
```

The HTTPRoute's parent conditions must show `Accepted=True` and
`ResolvedRefs=True`.
Test in a private browser session: unauthenticated access should go to
Authelia; after login, verify both allowed and denied application paths. Check
that the app has no public Service, NodePort, or LoadBalancer bypass. A
Cloudflare-proxied public response may be a redirect or app response; check
the expected authentication result, not only for HTTP 200.

ExternalDNS writes a proxied CNAME to the tunnel hostname and a prefixed TXT
ownership record. It does not create Tunnel ingress rules; the wildcard Tunnel
rule already forwards subdomains to Traefik. The apex `pocket-doc.app` is not
covered by `*.pocket-doc.app`.

## Remove a route or test records

Remove the route through a reviewed Git change. The root Argo CD app has
pruning disabled, so deleting a manifest alone does not remove the live
resource. Delete the child Application only if removing the entire app; for a
single route, delete the live HTTPRoute after its Git manifest is removed.

Because ExternalDNS is `upsert-only`, delete records manually only after
confirming they belong to the removed route. For the completed NGINX test,
remove these two records in **Cloudflare → pocket-doc.app → DNS → Records**:

- CNAME `external-dns-test` (`external-dns-test.pocket-doc.app`)
- TXT `external-dns-cname-external-dns-test`
  (`external-dns-cname-external-dns-test.pocket-doc.app`), with owner
  `oracle-k3s-pocket-doc-app`

Do not remove other domain, mail, or verification records. After deletion,
check the host in Cloudflare DNS; proxied records may resolve to Cloudflare edge
IPs instead of showing their CNAME target in ordinary DNS lookups.

To remove the edge platform, remove public routes first, then ExternalDNS and
its ESO-managed token, the Tunnel connector, Gateway, and Traefik. Manually
remove owned DNS records. Keep Vault secrets until their consumers are gone.

## Troubleshooting

- **No DNS record:** check ExternalDNS is Ready, the route's opt-in label, the
  Gateway label filter, route status, zone ID/domain filters, and controller
  logs. Do not print Secret values.
- **DNS resolves but the page fails:** check Cloudflare Tunnel health, the
  wildcard config, Gateway status, route parent conditions, and backend
  Service endpoints. Check Traefik informer logs for namespace-scoped RBAC
  denials if the route is not accepted or references remain unresolved.
- **HTTPS works with curl but not a browser:** check local DNS cache and
  browser secure-DNS settings. Compare `Resolve-DnsName`/`dig` with a public
  resolver and try a clean browser session.
- **Accepted route returns 502:** check that the Service port maps to a ready
  EndpointSlice. Test Service ClusterIP and Pod IP connectivity from the
  cluster path Traefik uses. On this cluster, Grafana's Pod IP was unreachable
  while its Service ClusterIP worked; `traefik.io/service.nativelb: "true"`
  fixed it. Apply NativeLB only after confirming the same connectivity issue.

## References

- [Traefik Gateway API provider](https://doc.traefik.io/traefik/reference/install-configuration/providers/kubernetes/kubernetes-gateway/)
- [Traefik Gateway API routing](https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/gateway-api/)
- [Authelia with Traefik](https://www.authelia.com/integration/proxies/traefik/)
- [Authelia forwarded headers](https://www.authelia.com/integration/proxies/forwarded-headers/)
- [Gateway API security](https://gateway-api.sigs.k8s.io/docs/concepts/security/)

For admin access and cluster recovery, use the [Tailscale guide](tailscale.md),
[Authelia runbook](authelia.md), and [recovery runbook](recovery.md). Keep the
Kubernetes API private. Argo CD is only exposed through its Authelia OIDC
route.
