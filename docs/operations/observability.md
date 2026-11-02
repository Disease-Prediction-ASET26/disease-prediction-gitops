# Prometheus and Grafana

The `monitoring` Argo CD Application installs Prometheus, Alertmanager,
Grafana, kube-state-metrics, and node-exporter. Chart version and values are in
[`observability.yaml`](../../clusters/oracle/applications/observability.yaml)
and [`values.yaml`](../../clusters/oracle/observability/values.yaml).

Monitoring enforces the Baseline Pod Security Standard because Grafana's data
volume init container changes file ownership. Node exporter runs in the
separate `node-exporter` namespace, which allows its read-only host filesystem
mounts. Its host network and PID namespace are disabled.

Grafana uses native Authelia OIDC at `grafana.pocket-doc.app`. The `admins`
group gets the Grafana admin role; other signed-in users are Viewers. Local
password login is disabled. Its public route is a separate Application. Sync
that route only after the Grafana OIDC secret is ready. See the
[public route guide](domain-ingress.md) for route requirements.

Prometheus keeps seven days of metrics, up to 8 GiB, on a 10 GiB local volume.
Grafana uses a 1 GiB local volume. Both are stored on the K3s node; they are
lost if its disk is lost. Traefik can read Secrets in `monitoring`, including
Grafana's OIDC Secret. Grafana uses Traefik NativeLB because direct Pod IP
connections failed in this cluster.

Logs from Prometheus, Alertmanager, Grafana, and other monitoring pods use
Kubernetes pod logs on the node. Kubelet rotates them at 10 MiB and keeps up to
five files. A daily host timer deletes rotated pod logs older than seven days
across all namespaces, including `monitoring`. Active logs remain, and size
rotation can remove older entries sooner. There is no log collector, so logs
are only available on the node. This is separate from Prometheus metric
retention. See the [log retention guide](log-retention.md).

The local Grafana admin Secret is for recovery only. Do not commit it or use
it as the public login.

## Resource sizing

Recent metrics show Grafana using up to 434 MiB and Prometheus up to 505 MiB.
Grafana's request is 384 MiB, close to its earlier 364 MiB p95; its 512 MiB
limit stays above the measured peak. Prometheus keeps a 512 MiB request and a
1.5 GiB limit until data covers its full seven-day retention and normal query
use.

Recent peaks were 18 MiB for Alertmanager, 35 MiB for the operator, 36 MiB for
kube-state-metrics, and 9 MiB for node-exporter. Their new request/limit pairs
are 32/64, 64/128, 48/96, and 16/32 MiB. The Grafana dashboard sidecar peaked
at 79 MiB, so its 64/128 MiB settings stay. Requests reserve scheduler
capacity; limits cap use. Neither setting lowers a running process's current
memory. Check for restarts and OOM events after changing limits.

```bash
kubectl top pods -n monitoring --containers
kubectl top node
```

Use at least a seven-day sample before lowering the Prometheus or Grafana
limits. The node journal and rotated logs also have local retention rules; see
the [log retention guide](log-retention.md).

## Prepare and sync

Before the first sync, create the local Grafana admin Secret. Choose a unique
password at the prompt:

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

The manual-sync `monitoring` Application needs this Secret before it starts
Grafana. Create the OIDC client secret pair in OCI Vault by following the
[Authelia guide](authelia.md#prepare-the-oci-vault-secrets). ESO syncs the
plaintext secret to `monitoring/grafana-oidc-client`. Never put it in Git. The
Grafana chart also uses the checked-in Origin CA bundle for its private OIDC
connection to Authelia. Render the manifests and chart, then review the diff:

```bash
kubectl kustomize clusters/oracle > /dev/null
helm template monitoring kube-prometheus-stack \
  --repo https://prometheus-community.github.io/helm-charts \
  --version 92.17.0 \
  --namespace monitoring \
  --values clusters/oracle/observability/values.yaml > /dev/null
argocd app diff monitoring
```

After ESO syncs the new Grafana OIDC secret, restart Authelia so it loads the
client configuration:

```bash
kubectl -n auth-system rollout restart deployment/authelia
kubectl -n auth-system rollout status deployment/authelia --timeout=180s
```

After reviewing the diff and merging the Git change, confirm the root
Application has created the `node-exporter` namespace. Review the monitoring
diff, then sync the Application. The first sync after moving node-exporter
from `monitoring` uses pruning to remove its old DaemonSet, Service, and
ServiceMonitor:

```bash
kubectl get namespace node-exporter
argocd app sync monitoring --prune
argocd app wait monitoring --sync --health --timeout 300
kubectl -n monitoring get pods,pvc,services
kubectl -n node-exporter rollout status daemonset/monitoring-prometheus-node-exporter --timeout=180s
kubectl -n node-exporter get daemonset,service,servicemonitor
kubectl -n monitoring get daemonset,service,servicemonitor
```

Review the diff before running the one-time prune. Later syncs do not need
`--prune`. The exporter ServiceMonitor remains visible to Prometheus because
the chart selects ServiceMonitors across all namespaces.

The root sync can warn that the old exporter Pod violates Baseline until this
sync replaces it. Complete the child sync promptly; a replacement Pod in
`monitoring` would be rejected.

Check that the OIDC `ExternalSecret` is Ready. Do not print its Secret value.
Then sync the separate route Application:

```bash
kubectl -n monitoring wait --for=condition=Ready externalsecret/grafana-oidc-client --timeout=5m
argocd app diff grafana-route
argocd app sync grafana-route
argocd app wait grafana-route --sync --health --timeout 120
```

Check that the HTTPRoute is accepted, then open
[`grafana.pocket-doc.app`](https://grafana.pocket-doc.app) and sign in with
Authelia. ExternalDNS creates the DNS record. It does not delete old records;
remove them in Cloudflare after deleting the route.

## Open Grafana and Prometheus

Use the private Tailscale context. Forward Grafana to localhost for recovery:

```bash
kubectl -n monitoring port-forward service/monitoring-grafana 3000:80
```

Open `http://127.0.0.1:3000`. For recovery, temporarily enable Grafana's local
login form in the values and sync the change. Revert it after access is restored.
To inspect Prometheus, use a second terminal:

```bash
kubectl -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090
```

Grafana loads the chart's Kubernetes dashboards from ConfigMaps in `monitoring`.
Scrapes for unavailable K3s control-plane services and CoreDNS are disabled.
Default alerts load into Prometheus and Alertmanager, but no notification
receiver is configured.

## Update or remove

For changes, edit the values or pinned chart version and use the render, diff,
and sync steps above. Keep the chart version pinned. Check upgrade notes before
changing chart versions or Prometheus Operator CRDs.

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
