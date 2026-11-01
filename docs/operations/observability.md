# Prometheus and Grafana

The `monitoring` Argo CD Application installs the Prometheus Operator stack,
Prometheus, Alertmanager, Grafana, kube-state-metrics, and node-exporter. The
chart and its values are pinned in
[`clusters/oracle/applications/observability.yaml`](../../clusters/oracle/applications/observability.yaml)
and [`clusters/oracle/observability/values.yaml`](../../clusters/oracle/observability/values.yaml).
Grafana stays on a ClusterIP Service. Its public route is separately managed
and manually synced only after the Authelia OIDC client and Grafana are ready.
The route publishes `https://grafana.pocket-doc.app` through Cloudflare and
requires Authelia's two-factor login. The `admins` Authelia group receives
Grafana server administrator access; other authenticated users receive the
Viewer role. Grafana's local login form and basic authentication are disabled.

Prometheus keeps seven days of metrics on a 10 GiB `local-path` volume, with an
8 GiB retention cap. Grafana uses a 1 GiB `local-path` volume. Both volumes are
stored on the single K3s node and are lost if that node's local storage is
lost. The initial Grafana administrator password is supplied from a
Kubernetes Secret created locally; it is not the public login path and must
not be committed to Git.

## First install

Before syncing the monitoring chart, create the Grafana admin Secret. Choose a
unique password at the prompt:

```bash
set +x
password_file=$(mktemp)
chmod 600 "$password_file"
trap 'rm -f "$password_file"' EXIT
printf 'Grafana admin password: '
IFS= read -r -s grafana_admin_password
printf '\n'
printf '%s' "$grafana_admin_password" > "$password_file"
unset grafana_admin_password
kubectl -n monitoring create secret generic monitoring-grafana-admin \
  --from-literal=admin-user=admin \
  --from-file=admin-password="$password_file" \
  --dry-run=client -o yaml | kubectl apply -f -
```

The `monitoring` child Application uses manual sync so it cannot start Grafana
before this Secret exists. Also follow the
[Authelia runbook](authelia.md#prepare-the-oci-vault-secrets) to create the
Grafana OIDC client secret pair in OCI Vault. ESO syncs the plaintext client
secret to `monitoring/grafana-oidc-client`; never create it in Git. The Grafana
chart references that Secret and the checked-in public Cloudflare Origin CA
bundle used for its internal Authelia OIDC back-channel. This is the same CA
root Argo CD uses; rotate it before its 2029 expiry. Render the repository
manifests and chart before syncing:

```bash
kubectl kustomize clusters/oracle > /dev/null
helm template monitoring prometheus-community/kube-prometheus-stack \
  --repo https://prometheus-community.github.io/helm-charts \
  --version 92.17.0 \
  --namespace monitoring \
  --values clusters/oracle/observability/values.yaml > /dev/null
argocd app diff monitoring
```

After the Grafana Vault secrets are synced, restart Authelia so it loads the
new client configuration:

```bash
kubectl -n auth-system rollout restart deployment/authelia
kubectl -n auth-system rollout status deployment/authelia --timeout=180s
```

After reviewing the diff, sync the application and wait for its workloads:

```bash
argocd app sync monitoring
argocd app wait monitoring --sync --health --timeout 300
kubectl -n monitoring get pods,pvc,services
```

Check that the monitoring OIDC `ExternalSecret` is Ready without printing its
Secret value. Then sync the separate public route Application to publish DNS:

```bash
kubectl -n monitoring wait --for=condition=Ready externalsecret/grafana-oidc-client --timeout=5m
argocd app diff grafana-route
argocd app sync grafana-route
argocd app wait grafana-route --sync --health --timeout 120
```

Verify the HTTPRoute is accepted and programmed, then open
[`https://grafana.pocket-doc.app`](https://grafana.pocket-doc.app) and sign in
with Authelia. ExternalDNS creates the proxied DNS record after the route is
synced. Because its policy is `upsert-only`, remove stale DNS records manually
after deleting the route.

## Open Grafana and Prometheus

Use the private Tailscale Kubernetes context. Forward Grafana to localhost for
recovery:

```bash
kubectl -n monitoring port-forward service/monitoring-grafana 3000:80
```

Open `http://127.0.0.1:3000`. Normal Grafana access uses the public Authelia
route. For login recovery, temporarily restore the Grafana login form and basic
authentication in the values, sync the chart, then revert that temporary
change. To inspect Prometheus directly, use a second terminal:

```bash
kubectl -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090
```

Grafana includes the chart's Kubernetes dashboards. K3s-specific control plane
jobs that are not exposed as separate services by default (controller manager,
scheduler, kube-proxy, and etcd) are disabled. The kubelet job label uses the
`k3s-server` name expected by the chart's K3s dashboards and rules. Default
alert rules are loaded into Prometheus and Alertmanager, but no external
notification receiver is configured.

## Preview and update

Edit the values file or update the pinned chart version in the Application.
Render both the Kustomize root and Helm chart, then review Argo CD's diff:

```bash
kubectl kustomize clusters/oracle > /dev/null
helm template monitoring prometheus-community/kube-prometheus-stack \
  --repo https://prometheus-community.github.io/helm-charts \
  --version 92.17.0 \
  --namespace monitoring \
  --values clusters/oracle/observability/values.yaml > /dev/null
argocd app diff monitoring
```

After the Git change is merged, run `argocd app sync monitoring` and check
`argocd app wait monitoring --sync --health`. Keep the chart version pinned.
Review upstream chart upgrade notes before changing major chart versions or
Prometheus Operator CRDs.

Keep the Authelia client secret and Grafana's synchronized Secret in place
while the client is configured. To remove public access, delete the
`grafana-route` Application and remove the Grafana client from Authelia after
the route is gone. Remove the OCI Vault secret only after Grafana and ESO no
longer consume it.

## Remove the stack

Back up any Grafana dashboards or Prometheus data you need. Remove the child
Application manifest, project, and namespace from the root Kustomization in a
reviewed Git change. The root Application has pruning disabled, so these live
resources remain until they are explicitly removed. Then delete the child app
with cascading enabled and delete the leftover project and namespace:

```bash
argocd app delete monitoring --cascade
kubectl -n argocd delete appproject oracle-observability
kubectl delete namespace monitoring
```

Deleting the namespace removes its PVCs and monitoring data. Argo CD tracks
the Prometheus Operator CRDs from the chart source, so cascading deletion
removes them too. Confirm no other application uses those CRDs first.

## References

- [kube-prometheus-stack chart](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack)
- [Prometheus storage and retention](https://prometheus.io/docs/prometheus/latest/storage/)
- [K3s metrics](https://docs.k3s.io/reference/metrics)
- [Argo CD Helm charts and values](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/)
- [Argo CD multiple sources](https://argo-cd.readthedocs.io/en/stable/user-guide/multiple_sources/)
- [K3s local-path storage](https://docs.k3s.io/add-ons/storage)
- [Grafana Generic OAuth](https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-authentication/generic-oauth/)
- [Authelia Grafana OIDC integration](https://www.authelia.com/integration/openid-connect/clients/grafana/)
