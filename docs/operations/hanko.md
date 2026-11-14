# Hanko application authentication

Hanko is prepared for the Disease Prediction app. Authelia continues to protect
infrastructure services and the current app routes. The app does not yet use
Hanko. Both Hanko instances have public registration disabled; enable it only
when the app and the checks below are ready.

## Endpoints and isolation

| Environment | Public API and token issuer | Token audience | Browser origin |
|---|---|---|---|
| Dev | `https://identity-dev.pocket-doc.app` | `pocket-doc-dev` | `https://dev.pocket-doc.app` |
| Production | `https://identity.pocket-doc.app` | `pocket-doc-prod` | `https://health.pocket-doc.app` |

Hanko's public JSON Web Key Set (JWKS) is at `/.well-known/jwks.json`. The
browser origin is also the WebAuthn relying party. Google login is disabled
until its separate OAuth client and callback are configured for each
instance. Do not put client secrets in Git.

The instances use separate databases, database roles, signing-key encryption
keys, origins, and token audiences. One PostgreSQL 18 server in `auth-system`
serves both databases on a 2 GiB `local-path` volume. PostgreSQL requires TLS;
Hanko verifies the database certificate and hostname. This is one database
server on one Oracle node: there is no automatic failover or off-node backup.
**Set up and test an encrypted off-node backup and restore before enabling real
user registration.** Retain the matching Vault encryption keys with each
backup; losing them prevents Hanko from using its stored signing keys.

Only port 8000 is exposed through a ClusterIP Service and the Cloudflare
Tunnel. NetworkPolicies allow Traefik and the matching app backend to reach
that port. The unauthenticated admin API on port 8001 has no Service or public
route. Do not expose it. An operator with Kubernetes `pods/portforward` access
can use a private port-forward for maintenance.

The instances use the current Authelia SMTP account via a separate OCI Vault
secret. The Hanko secret is a copy, not an automatic sync from Authelia; update
it when the SMTP credentials change. Hanko has an in-memory rate limiter and
uses the direct peer IP by default. Behind Traefik, many users can appear to
share one IP. Verify the trusted proxy chain and rate limiting before opening
registration; do not trust client-supplied forwarding headers.

## Secrets

OCI Vault stores these JSON secrets. External Secrets Operator (ESO) copies
selected fields into `auth-system` Kubernetes Secrets. Do not print the values
or put them in Git, Terraform state, shell arguments, or logs.

| OCI secret | Fields |
|---|---|
| `hanko-runtime` | `pg_admin_password`, `dev_db_password`, `prod_db_password`, `dev_encryption_key`, `prod_encryption_key` |
| `hanko-postgres-tls` | `ca_cert`, `server_cert`, `server_key` |
| `hanko-smtp` | `host`, `port`, `username`, `password`, `from_address` |

The PostgreSQL certificate must contain
`hanko-postgres.auth-system.svc.cluster.local` as a DNS subject alternative
name. Keep its private key in Vault. Renew it before expiry. Rotate the CA by
first distributing a trust bundle containing both old and new CAs; switch the
server certificate, restart the clients, then remove the old CA after checking
all connections. Coordinate database password changes with PostgreSQL role
updates; changing the Vault value alone does not update an existing role.
Hanko signing-key rotation needs the old encryption key until its old signing
keys and sessions are retired. Follow the upstream key rotation procedure;
do not replace the key blindly.

## Preview and deploy

From the GitOps repository root, render and review the change:

```bash
kubectl kustomize clusters/oracle/auth/hanko
kubectl kustomize clusters/oracle/external-secrets/auth-system
kubectl kustomize clusters/oracle
kubectl --context oracle-k3s diff -k clusters/oracle/auth/hanko
```

Create the Vault secrets with the required values before deployment. Merge the
reviewed change into `main`; Argo CD synchronizes the `hanko` Application and
`oci-auth-vault-store`. From a workstation with private cluster access, check:

```bash
kubectl --context oracle-k3s -n argocd get application hanko oci-auth-vault-store
kubectl --context oracle-k3s -n auth-system get externalsecret hanko-dev hanko-prod hanko-postgres hanko-postgres-tls hanko-postgres-ca hanko-smtp
kubectl --context oracle-k3s -n auth-system get deployments,pods,services,pvc
kubectl --context oracle-k3s -n auth-system get httproute hanko-dev hanko-prod
kubectl --context oracle-k3s -n auth-system top pods --containers
```

The ExternalSecrets and deployments must be ready. Check that both HTTPRoutes
have `Accepted=True` and `ResolvedRefs=True`, then check their health and keys:

```bash
curl --fail https://identity-dev.pocket-doc.app/health/ready
curl --fail https://identity-dev.pocket-doc.app/.well-known/jwks.json
curl --fail https://identity.pocket-doc.app/health/ready
curl --fail https://identity.pocket-doc.app/.well-known/jwks.json
```

## Integration handoff

The frontend team can use Hanko Elements against the matching public API. Use
only the allowed browser origin for that environment. The backend must verify
the JWT signature against that environment's JWKS and check issuer, audience,
expiry, and authorization for the requested user data. Hanko is not an OpenID
Connect discovery provider; configure its JWKS URL explicitly. The backend can
reach its matching `hanko-dev` or `hanko-prod` ClusterIP on port 8000; this
internal connection is HTTP and relies on the cluster network boundary.

A revoked but unexpired JWT can pass offline signature verification. For
immediate revocation, also call Hanko's session validation endpoint and inspect
`is_valid`, or implement another reviewed revocation method. Current tokens
expire after 15 minutes. Decide the cookie, CSRF, and token storage design with
the app team before using the service.

To activate login, add the app login and API enforcement, configure production
SMTP and Google OAuth, establish tested backups, verify the proxy and rate
limits, and run end-to-end security tests. Change `account.allow_signup` only
after those checks. Remove Authelia ForwardAuth from each app route only after
the app's own authentication is ready; leave infrastructure routes protected.

## Change, recovery, and removal

Make configuration changes in `clusters/oracle/auth/hanko`, preview and merge
through a pull request, then check Argo CD and both services. ConfigMap and
Secret changes do not automatically restart pods; roll out the affected
Deployment after updating its configuration or credentials.

Before deleting data, verify an off-node backup can be restored with its
matching Vault keys. Remove the Hanko Application and resources in a reviewed
Git change. Argo CD pruning is disabled, so explicitly delete the old
resources after the change. Retain the PVC and Vault secrets until recovery is
no longer needed. ExternalDNS is upsert-only; remove the Hanko DNS and TXT
ownership records manually after confirming their owner. Never delete
Authelia resources as part of Hanko removal.

See the [public route guide](domain-ingress.md), [secret operations](secrets.md),
[Hanko backend configuration](https://github.com/teamhanko/hanko/blob/backend/v3.1.0/backend/README.md),
and [Hanko frontend components](https://github.com/teamhanko/hanko/tree/main/frontend/elements).
