# Domain and public routes

This guide covers the public edge for `pocket-doc.app`. Name.com is the
registrar; Cloudflare hosts DNS and the public edge. No application route is
currently published. The temporary NGINX route used to test the path has been
removed.

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
inbound rule for ports 80 or 443. Do not publish the Kubernetes API, SSH, or
Argo CD.

## Current platform settings

- Name.com delegates the domain to Cloudflare. Cloudflare DNSSEC is enabled
  and the matching DS record is published at Name.com.
- The locally managed Tunnel `oracle-k3s` connects outbound to Cloudflare and
  forwards `*.pocket-doc.app` to Traefik's internal Service. A final catch-all
  returns 404. The tunnel credential is in OCI Vault as `cloudflared-tunnel`.
- Gateway API CRDs are owned by K3s through the checked-in host manifest. Do
  not install a second CRD bundle.
- Traefik is an internal `ClusterIP` Gateway API controller. The `oracle-public`
  Gateway accepts routes only from namespaces labeled
  `pocket-doc.app/public-routes: "true"`.
- Traefik has read access to Secrets in `traefik-system` and
  `disease-prediction`, bound only in those namespaces. This is broader than
  the current HTTP route needs; treat those namespaces' Secrets as readable
  by Traefik and review this permission before adding sensitive values there.
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
and ARM64 image are ready and public access is approved. In the app namespace:

1. Add namespace label `pocket-doc.app/public-routes: "true"` in the same
   reviewed change as its route.
2. Create an HTTPRoute attached to `oracle-public` in `traefik-system`. Use
   the app's hostname under `pocket-doc.app` and the app's internal Service.
3. Add the ExternalDNS opt-in label and Cloudflare proxy annotation:

   ```yaml
   metadata:
     labels:
       external-dns-public: "true"
     annotations:
       external-dns.kubernetes.io/cloudflare-proxied: "true"
   ```

4. Render `clusters/oracle`, review the Argo CD project permissions and diff,
   then merge the change. Do not use a direct public IP, NodePort, or
   LoadBalancer.
5. Check route and Gateway status, DNS, TLS, and an HTTPS request:

   ```sh
   kubectl -n <app-namespace> get httproute <route-name>
   kubectl -n traefik-system get gateway oracle-public
   dig <app-host>.pocket-doc.app A
   curl -I https://<app-host>.pocket-doc.app/
   ```

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
  Service endpoints.
- **HTTPS works with curl but not a browser:** check local DNS cache and
  browser secure-DNS settings. Compare `Resolve-DnsName`/`dig` with a public
  resolver and try a clean browser session.
- **Traefik cannot reach a backend Pod IP:** the smoke test succeeded through
  the Service ClusterIP when the Service had
  `traefik.io/service.nativelb: "true"`. Diagnose cluster pod networking before
  choosing that setting for another app.

For admin access and cluster recovery, use the [Tailscale guide](tailscale.md)
and [recovery runbook](recovery.md). Keep the Kubernetes API and Argo CD
private.
