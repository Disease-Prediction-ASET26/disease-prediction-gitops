# Prometheus and Grafana

Each cluster has a `monitoring` Argo CD Application using kube-prometheus-stack
92.17.0. The Oracle stack currently runs Grafana and the existing monitoring
data plane. The Proxmox stack runs Prometheus, Alertmanager, the operator,
kube-state-metrics, and node-exporter with Grafana disabled. Its values are in
[`clusters/proxmox/observability/values.yaml`](../../clusters/proxmox/observability/values.yaml)
and its Application is in
[`clusters/proxmox/applications/observability.yaml`](../../clusters/proxmox/applications/observability.yaml).
Oracle's chart values remain in [`clusters/oracle/observability/values.yaml`](../../clusters/oracle/observability/values.yaml).

The migration is staged. Keep the Oracle data plane running until the Oracle
egress Service can reach `proxmox-prometheus.monitoring.svc.cluster.local:9090`
and Grafana has been switched to it. The tailnet policy is external to this
repository; add TCP/9090 from `tag:oracle-k3s-egress` to `tag:proxmox-metrics`
before switching. The Proxmox Prometheus starts with an empty data volume; the
existing Oracle data remains on its PVC during this overlap.

Both `monitoring` namespaces enforce the Baseline Pod Security Standard.
Grafana's Oracle data-volume init container changes file ownership. Node
exporter runs in the separate `node-exporter` namespace with Privileged
enforcement for its host filesystem access. It uses host networking and does
not use the host PID namespace.

Grafana uses native Authelia OIDC at `grafana.pocket-doc.app`. The `admins`
group gets the Grafana admin role; other signed-in users are Viewers. Local
password login is disabled. Its public route is managed by a separate
Application. Argo CD automatically syncs and self-heals both the monitoring
stack and its public route. Automatic pruning is disabled. The root
Application's sync waves order child Application creation but do not wait for
child health, so during a fresh bootstrap the route can be created before
Grafana and OIDC are ready. Do not rely on the wave as a readiness or
authentication gate.
See the [public route guide](domain-ingress.md) for route requirements.

Prometheus keeps seven days of metrics, up to 8 GiB, on a 10 GiB local volume.
Grafana uses a 1 GiB local volume. These are stored on their cluster nodes and
are lost if the disk is lost. Traefik can read Secrets in Oracle's `monitoring`
namespace, including Grafana's OIDC Secret. Grafana uses Traefik NativeLB
because direct Pod IP connections failed in this cluster.

During the overlap, Oracle Prometheus scrapes the CloudNativePG exporter over
Tailscale through `proxmox-postgres-metrics.monitoring.svc.cluster.local:9187`.
Proxmox Prometheus scrapes the local exporter Service at
`postgres-metrics-tailnet.postgres.svc.cluster.local:9187`. Both use a
60-second interval and the `proxmox-cnpg` job name. Check the Proxmox target
with `up{job="proxmox-cnpg"}`. These scrapes collect database metrics, not
logs; logs remain on their cluster nodes until a separate log collector is
configured.

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

Recent Oracle metrics show Grafana using up to 434 MiB and Prometheus up to
505 MiB.
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

The Proxmox stack needs no credentials. Oracle Grafana still needs its local
admin Secret and OIDC client Secret. If those are not already present, create
the local admin Secret with a unique password at the prompt:

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

The `monitoring` Application needs this Secret before Grafana can start. Create
the OIDC client secret pair in OCI Vault by following the
[Authelia guide](authelia.md#prepare-the-oci-vault-secrets). ESO syncs the
plaintext secret to `monitoring/grafana-oidc-client`. Never put it in Git. The
Grafana chart also uses the checked-in Origin CA bundle for its private OIDC
connection to Authelia. Render the manifests and chart, then review the diff:

```bash
kubectl kustomize clusters/oracle > /dev/null
kubectl kustomize clusters/proxmox > /dev/null
helm template monitoring kube-prometheus-stack \
  --repo https://prometheus-community.github.io/helm-charts \
  --version 92.17.0 \
  --namespace monitoring \
  --values clusters/oracle/observability/values.yaml > /dev/null
helm template monitoring kube-prometheus-stack \
  --repo https://prometheus-community.github.io/helm-charts \
  --version 92.17.0 \
  --namespace monitoring \
  --values clusters/proxmox/observability/values.yaml > /dev/null
argocd app diff monitoring
```

After ESO syncs the new Grafana OIDC secret, restart Authelia so it loads the
client configuration:

```bash
kubectl -n auth-system rollout restart deployment/authelia
kubectl -n auth-system rollout status deployment/authelia --timeout=180s
```

After reviewing and merging the Git change, check the child `monitoring`
Application in both clusters. Each root Application creates its own
`node-exporter` namespace. Automated sync is enabled and pruning is disabled.
Wait for the Proxmox stack and check its resources:

```bash
kubectl get namespace node-exporter
argocd app wait monitoring --sync --health --timeout 300
kubectl -n monitoring get pods,pvc,services
kubectl -n node-exporter rollout status daemonset/monitoring-prometheus-node-exporter --timeout=180s
kubectl -n node-exporter get daemonset,service,servicemonitor
kubectl -n monitoring get daemonset,service,servicemonitor
kubectl -n monitoring get service prometheus-tailnet
```

Run the Argo and Kubernetes checks with the matching cluster context. Confirm
`prometheus-tailnet` is configured by the Tailscale operator, then test the
Oracle egress Service from Oracle after adding the TCP/9090 tailnet grant.
Switch Grafana only after a query through the new endpoint succeeds. The
Oracle Prometheus PVC and its historical data remain until a separate cleanup
after the cutover and retention review.

If migrating an older installation that still has the previous node-exporter
resources in `monitoring`, review the diff and run this one-time prune to remove
its old DaemonSet, Service, and ServiceMonitor:

```bash
argocd app diff monitoring
argocd app sync monitoring --prune
argocd app wait monitoring --sync --health --timeout 300
```

During this migration, the root sync can warn that the old exporter Pod
violates Baseline. Complete the child sync promptly; a replacement Pod in
`monitoring` would be rejected.

This cluster has completed that migration. The exporter ServiceMonitor remains
visible to Prometheus because the chart selects ServiceMonitors across all
namespaces.

Check that the OIDC `ExternalSecret` is Ready and the route Application is
healthy. Do not print the Secret value:

```bash
kubectl -n monitoring wait --for=condition=Ready externalsecret/grafana-oidc-client --timeout=5m
argocd app wait grafana-route --sync --health --timeout 120
```

Check that the HTTPRoute is accepted, then open
[`grafana.pocket-doc.app`](https://grafana.pocket-doc.app) and sign in with
Authelia. ExternalDNS creates the DNS record. It does not delete old records;
remove them in Cloudflare after deleting the route.

## Open Grafana and Prometheus

Use the private cluster context. Forward Oracle Grafana to localhost for
recovery:

```bash
kubectl -n monitoring port-forward service/monitoring-grafana 3000:80
```

Open `http://127.0.0.1:3000`. For recovery, temporarily enable Grafana's local
login form in the values and sync the change. Revert it after access is restored.
To inspect the existing Oracle Prometheus during migration, use a second
terminal:

```bash
kubectl -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090
```

Open `http://127.0.0.1:9090/targets` and query
`up{job="proxmox-cnpg"}`. To inspect Proxmox Prometheus, select the Proxmox
context and forward its service in a separate terminal:

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
