# Private access with Tailscale

Use your workstation for SSH, kubectl, and K9s. Tailscale carries these
connections to the Oracle VM. The Kubernetes API stays off the public internet;
you do not need an SSH tunnel.

## One-time setup

Install Tailscale on your Linux workstation, run `sudo tailscale up`, and sign
in to your tailnet. In the Tailscale policy, add the tag owner and grant below
to your existing policy. Do not replace the whole policy with this example:

```json
{
  "tagOwners": {
    "tag:oracle-k3s": ["autogroup:owner"]
  },
  "grants": [
    {
      "src": ["autogroup:owner"],
      "dst": ["tag:oracle-k3s"],
      "ip": ["tcp:22", "tcp:6443"]
    }
  ]
}
```

Check for broader rules that also grant access. Create a one-use, pre-approved
Tailscale auth key tagged `tag:oracle-k3s`. The Ansible playbook prompts for it
without echoing or logging it. Keep public SSH enabled until private SSH and
Kubernetes access both work. Do not open port 6443 in OCI.

Install Ansible from the GitOps repository. The commands below assume both
repositories are under `~/Projects/disease-prediction` and that your OCI SSH
key is `~/.ssh/disease-prediction-oci.key`. If needed, copy the key there from
its secure location; do not store it in either repository:

```bash
sudo apt update
sudo apt install -y curl git openssh-client python3-venv
install -d -m 700 "$HOME/.ssh"
chmod 600 "$HOME/.ssh/disease-prediction-oci.key"
cd "$HOME/Projects/disease-prediction/disease-prediction-gitops"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-ansible.txt
```

Before accepting the VM's SSH host key the first time, verify its fingerprint
through the OCI Console or another trusted channel. From the workspace root,
get the public IP from Terraform, then run Ansible from the GitOps repo:

```bash
cd "$HOME/Projects/disease-prediction"
ORACLE_PUBLIC_IP="$(terraform -chdir=disease-prediction-infra/terraform/oracle output -raw instance_public_ip)"
test -n "$ORACLE_PUBLIC_IP"
ssh -i "$HOME/.ssh/disease-prediction-oci.key" "opc@$ORACLE_PUBLIC_IP" true
cd disease-prediction-gitops
ansible-playbook \
  -i "${ORACLE_PUBLIC_IP}," \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  clusters/oracle/automation/ansible/playbooks/tailscale.yml
```

The playbook installs and enrolls Tailscale, sets the VM name to
`oracle-k3s`, and enables the Oracle Linux post-quantum SSH policy. It also
assigns `tailscale0` to a restricted firewalld zone that allows only SSH and
the Kubernetes API, and adds `oracle-k3s` to the K3s API certificate. K3s
restarts only if its certificate configuration changes.

The playbook sets `--accept-dns=false` so Tailscale does not replace the VM's
OCI resolver. K3s CoreDNS forwards external DNS through the VM resolver, while
the VM's Tailscale connection still supports private SSH and Kubernetes API
access. It also assigns `cni0` and `flannel.1` to firewalld's `trusted` zone so
Pod-to-Pod and Pod-to-node traffic works. Pods can then reach host services,
including the OCI metadata endpoint used by ESO. Run only trusted workloads
until network policies restrict that access. After applying, verify both host
and cluster DNS:

```bash
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s \
  'cat /etc/resolv.conf; getent ahostsv4 auth.pocket-doc.app'
kubectl -n argocd exec deploy/argocd-server -- \
  getent ahostsv4 auth.pocket-doc.app
```

The playbook also enables Oracle Linux's post-quantum SSH policy. If an older
SSH client cannot connect, restore the default policy from an existing VM
session:

```bash
sudo update-crypto-policies --set DEFAULT
sudo systemctl restart sshd
```

Confirm that your workstation sees the VM and can use SSH over Tailscale:

```bash
tailscale ping oracle-k3s
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s true
```

## Set up kubectl and K9s

Copy the K3s admin kubeconfig to your workstation. It grants unrestricted
cluster-admin access, so protect it and never commit it to Git:

```bash
install -d -m 700 "$HOME/.kube"
umask 077
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s \
  'sudo cat /etc/rancher/k3s/k3s.yaml' > "$HOME/.kube/oracle-k3s.yaml"
chmod 600 "$HOME/.kube/oracle-k3s.yaml"
sed -i 's#server: https://127.0.0.1:6443#server: https://oracle-k3s:6443#' \
  "$HOME/.kube/oracle-k3s.yaml"
```

For Zsh, add the kubeconfig to `~/.zshrc` so new terminals use it by default:

```bash
grep -qxF 'export KUBECONFIG="$HOME/.kube/oracle-k3s.yaml"' "$HOME/.zshrc" || \
  printf '\nexport KUBECONFIG="$HOME/.kube/oracle-k3s.yaml"\n' >> "$HOME/.zshrc"
source "$HOME/.zshrc"
```

Check access, then install K9s v0.51.0 for Linux amd64 and verify its release
checksum:

```bash
kubectl get nodes
cd /tmp
version=v0.51.0
package=k9s_linux_amd64.deb
curl -fsSLO "https://github.com/derailed/k9s/releases/download/${version}/${package}"
curl -fsSLO "https://github.com/derailed/k9s/releases/download/${version}/checksums.sha256"
grep -E "^[0-9a-f]{64}  ${package}$" checksums.sha256 | sha256sum --check
sudo apt install "./${package}"
```

After setup, connect Tailscale and run:

```bash
k9s
```

K9s uses the admin kubeconfig and can read Secrets and change or delete any
cluster resource. Keep the kubeconfig private. Use `:ns` to choose a namespace,
`l` to view logs, and `:q` to exit.

## Close public SSH

Only do this after the SSH check above and `kubectl get nodes` succeed over
Tailscale. In `disease-prediction-infra/terraform/oracle/terraform.tfvars`, set
`admin_ssh_cidr = null`, then review and apply the Terraform plan:

```bash
cd "$HOME/Projects/disease-prediction/disease-prediction-infra/terraform/oracle"
terraform plan -out=infra.tfplan
terraform show infra.tfplan
terraform apply infra.tfplan
rm infra.tfplan
```

The plan should remove only public SSH ingress. Port 6443 must remain closed to
the public internet.

## Update or remove Tailscale

Preview Ansible changes from the GitOps repository with:

```bash
ansible-playbook \
  -i 'oracle-k3s,' \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  --check --diff \
  clusters/oracle/automation/ansible/playbooks/tailscale.yml
```

Apply by running the same command without `--check --diff`. The playbook does
not ask for an auth key after the VM is enrolled.

To remove Tailscale, first restore public SSH in Terraform using your current
public IPv4 `/32`; review and apply the plan, then verify SSH to the public IP.
Run the removal playbook from the GitOps repository:

```bash
ansible-playbook \
  -i '<oracle-public-ip>,' \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  clusters/oracle/automation/ansible/playbooks/remove-tailscale.yml
```

Remove `oracle-k3s` from the Tailscale admin console after the playbook
completes. Keep public SSH limited to your `/32`; never use `0.0.0.0/0`.
The removal playbook leaves the Oracle Linux SSH crypto policy and the K3s
`oracle-k3s` certificate name in place; neither exposes a public port.

## Connect selected Kubernetes services

The Proxmox and Oracle K3s clusters use overlapping Pod and Service CIDRs.
Keep them as they are. Tailscale Services expose the PostgreSQL primary and
Proxmox Prometheus to Oracle, and expose Oracle kube-state-metrics and
node-exporter to Proxmox Prometheus. The Oracle Prometheus Agent sends selected
kubelet metrics to Proxmox Prometheus through the same TCP/9090 path used by
Grafana. The PostgreSQL exporter stays inside the Proxmox cluster. This setup
does not route either cluster's Pod or Service subnet, so the overlapping
ranges do not need to change. Other cluster services stay private.

Each cluster runs one ingress and one egress ProxyGroup, with one replica per
group. Proxmox ingress serves PostgreSQL and Prometheus; Oracle ingress serves
the two metrics endpoints. The egress groups provide the reverse connections.
Tailscale encrypts traffic between the proxies. The database connection also
uses PostgreSQL TLS with certificate verification. Single replicas keep
resource use low, but a proxy outage interrupts its connections. Each proxy
requests 25m CPU and 64 MiB memory, with limits of 250m CPU and 256 MiB memory.
The Proxmox forwarding init container requests 10m CPU and 16 MiB memory, with
limits of 100m CPU and 64 MiB memory.

The two Oracle exporters and Oracle ingress proxy add 75m CPU and 128 MiB
memory requests. The Oracle Prometheus Agent requests 25m CPU and 64 MiB memory,
with limits of 100m CPU and 128 MiB. The Proxmox egress proxy adds 25m CPU and
64 MiB. Together, the bridge requests 125m CPU and 256 MiB memory, with limits
totaling 800m CPU and 768 MiB memory. The Agent has no persistent volume; its
128 MiB temporary WAL buffers failed remote writes for up to two hours. Oracle
metrics use Proxmox's existing seven-day, 8 GiB Prometheus retention limit.

Before merging the GitOps change, add these tag owners to the existing tailnet
policy. Keep its current `tag:oracle-k3s` entries and access rules:

`tag:oracle-k3s` identifies the Oracle VM. The new `tag:oracle-k3s-egress`
identifies only the Kubernetes egress proxies, so the database grants do not
also give the VM direct access. The metrics tags identify only the new proxy
groups and the two Oracle exporter services.

```json
{
  "tagOwners": {
    "tag:k8s-operator": ["autogroup:owner"],
    "tag:k8s-proxmox": ["tag:k8s-operator"],
    "tag:oracle-k3s-egress": ["tag:k8s-operator"],
    "tag:oracle-k3s-ingress": ["tag:k8s-operator"],
    "tag:oracle-metrics": ["tag:k8s-operator"],
    "tag:proxmox-postgres": ["tag:k8s-operator"],
    "tag:proxmox-metrics": ["tag:k8s-operator"],
    "tag:proxmox-metrics-egress": ["tag:k8s-operator"]
  }
}
```

Add this entry under `autoApprovers.services` so only the Oracle ingress
proxy group can advertise the Oracle metrics services. Keep the existing
Proxmox service entries:

```json
{
  "autoApprovers": {
    "services": {
      "tag:proxmox-postgres": ["tag:k8s-proxmox"],
      "tag:proxmox-metrics": ["tag:k8s-proxmox"],
      "tag:oracle-metrics": ["tag:oracle-k3s-ingress"]
    }
  }
}
```

Append this grant to the existing `grants` list. Proxmox's metrics egress
proxy can reach only the Oracle exporters on TCP/8080 and TCP/9100. Keep the
existing Oracle grants to PostgreSQL TCP/5432 and Proxmox Prometheus TCP/9090.
The TCP/9090 grant allows Grafana queries and the Oracle Agent's remote writes;
keep this destination limited to the Oracle egress ProxyGroup tag:

```json
{
  "grants": [
    {
      "src": ["tag:oracle-k3s-egress"],
      "dst": ["tag:proxmox-postgres"],
      "ip": ["tcp:5432"]
    },
    {
      "src": ["tag:oracle-k3s-egress"],
      "dst": ["tag:proxmox-metrics"],
      "ip": ["tcp:9090"]
    },
    {
      "src": ["tag:proxmox-metrics-egress"],
      "dst": ["tag:oracle-metrics"],
      "ip": ["tcp:8080", "tcp:9100"]
    }
  ]
}
```

Check the full policy for broader grants that would also permit access. These
rules are not stored in this repository and must be added in the Tailscale
admin console.

Create a separate OAuth client for each cluster in the Tailscale admin
console. Give each client `Devices:Core`, `Keys:Auth Keys`, and `Services`
Read/Write scopes, and allow it to use `tag:k8s-operator`. Before the Argo CD
Applications sync, create the Kubernetes Secret `tailscale/operator-oauth` in
each cluster. The Helm chart reads files named `client_id` and
`client_secret` from this Secret. The following function prompts for the
credentials without echoing the secret or putting it in shell history:

The namespace does not exist in either cluster yet. From the GitOps repository
root, create it from the versioned manifest first; Argo CD will manage it
after the change is merged:

```bash
kubectl --kubeconfig "$HOME/.kube/proxmox-k3s.yaml" \
  apply -f clusters/proxmox/namespaces/tailscale.yaml
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" \
  apply -f clusters/oracle/namespaces/tailscale.yaml
```

```bash
umask 077
secret_dir="$(mktemp -d /dev/shm/tailscale-operator.XXXXXX)"
trap 'rm -rf "$secret_dir"' EXIT

create_operator_secret() {
  local kubeconfig="$1"
  read -r -p 'Tailscale OAuth client ID: ' oauth_client_id
  read -r -s -p 'Tailscale OAuth client secret: ' oauth_client_secret
  printf '\n'
  printf '%s' "$oauth_client_id" > "$secret_dir/client_id"
  printf '%s' "$oauth_client_secret" > "$secret_dir/client_secret"
  unset oauth_client_id oauth_client_secret
  kubectl --kubeconfig "$kubeconfig" -n tailscale \
    create secret generic operator-oauth \
    --from-file=client_id="$secret_dir/client_id" \
    --from-file=client_secret="$secret_dir/client_secret" \
    --dry-run=client -o yaml |
    kubectl --kubeconfig "$kubeconfig" apply -f -
}

create_operator_secret "$HOME/.kube/proxmox-k3s.yaml"
create_operator_secret "$HOME/.kube/oracle-k3s.yaml"
```

From the GitOps repository, render both cluster manifests and the pinned
operator chart before merging:

```bash
kubectl kustomize clusters/proxmox > /dev/null
kubectl kustomize clusters/oracle > /dev/null
helm template tailscale-operator tailscale-operator \
  --repo https://pkgs.tailscale.com/helmcharts \
  --version 1.104.4 \
  --namespace tailscale \
  --values clusters/proxmox/tailscale/values.yaml > /dev/null
helm template tailscale-operator tailscale-operator \
  --repo https://pkgs.tailscale.com/helmcharts \
  --version 1.104.4 \
  --namespace tailscale \
  --values clusters/oracle/tailscale/values.yaml > /dev/null
git diff --check
```

Do not save the generated Secret YAML in Git or print it. After the tailnet
policy and both Secrets are ready, merge the change. Argo CD installs the
operator and its ProxyGroups in each cluster. The operator requires privileged
pod access, so its pods are isolated in a dedicated namespace with the
privileged Pod Security level. Namespace policies allow Proxmox ingress in
`postgres` and `monitoring`, and Proxmox egress only in `monitoring`. Oracle
allows egress in `disease-prediction` and `monitoring`, plus ingress in
`monitoring` and the privileged `node-exporter` namespace.

Oracle workloads connect to
`proxmox-postgres.disease-prediction.svc.cluster.local:5432`. Oracle Grafana
uses Proxmox Prometheus through
`proxmox-prometheus.monitoring.svc.cluster.local:9090`. Proxmox Prometheus
scrapes the PostgreSQL exporter over the cluster-local
`postgres-metrics.postgres.svc.cluster.local:9187` Service and Oracle's
exporters through the local `oracle-kube-state-metrics` and
`oracle-node-exporter` Services. Oracle exposes dedicated Tailscale
LoadBalancer Services for these exporters; their chart Services stay
cluster-local. Tailnet access is limited by the narrow metrics grant. This
collects metrics, not logs. A log collector such as Alloy with a log store
needs a separate design and bounded retention.
Argo CD ignores only the operator-managed external name and finalizer on the
two Proxmox metric mirrors.

The Oracle proxy group has a shared tailnet identity, so tailnet policy cannot
distinguish individual pods behind it. PostgreSQL still requires its database
credentials and a trusted TLS certificate. Before running untrusted workloads
in the Oracle application or monitoring namespaces, add Kubernetes
NetworkPolicies that restrict which pods can use these egress Services.

After sync, inspect status without displaying Secret values:

```bash
kubectl --kubeconfig "$HOME/.kube/proxmox-k3s.yaml" -n argocd get applications tailscale-operator tailscale-config
kubectl --kubeconfig "$HOME/.kube/proxmox-k3s.yaml" -n tailscale get proxygroups
kubectl --kubeconfig "$HOME/.kube/proxmox-k3s.yaml" -n postgres get services postgres-tailnet postgres-metrics
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n disease-prediction get service proxmox-postgres
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n disease-prediction get externalsecrets postgres-app-credentials postgres-server-ca
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n monitoring get service proxmox-prometheus
kubectl --kubeconfig "$HOME/.kube/proxmox-k3s.yaml" -n monitoring get service prometheus-tailnet
kubectl --kubeconfig "$HOME/.kube/proxmox-k3s.yaml" -n monitoring get service oracle-kube-state-metrics oracle-node-exporter
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n monitoring get service monitoring-kube-state-metrics
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n monitoring get service oracle-kube-state-metrics-tailnet
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n node-exporter get daemonset,service monitoring-prometheus-node-exporter
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n node-exporter get service oracle-node-exporter-tailnet
```

In Proxmox Prometheus, query `up{job="proxmox-cnpg"}`. A value of `1` means
the local exporter scrape succeeded. Its target is configured in
`clusters/proxmox/observability/values.yaml`.
Check Oracle's two targets with
`up{job=~"oracle-kube-state-metrics|oracle-node-exporter"}`; both should be
`1`. Oracle Grafana's fleet dashboards use these samples to show both clusters.

### Egress proxy misses a newly advertised service

The pinned Tailscale proxy version `1.104.4` may not retry an egress target if
its Tailscale Service was not advertised during the first lookup. If the Oracle
Services report `TailscaleIngressSvcConfigured=True` but Proxmox Prometheus
still gets `connection refused`, restart the Proxmox egress proxy to reload
the service addresses:

```bash
kubectl --context proxmox-k3s -n tailscale delete pod egress-proxies-0
kubectl --context proxmox-k3s -n tailscale wait --for=condition=Ready pod/egress-proxies-0 --timeout=180s
```

This briefly interrupts traffic through that ProxyGroup. The upstream issue is
[Tailscale #21426](https://github.com/tailscale/tailscale/issues/21426).

To remove this connectivity, first remove the Oracle egress mirrors and
metrics exporters and Tailscale Services, Proxmox's Oracle scrape jobs and
service mirrors, the Proxmox PostgreSQL and Prometheus Tailscale Services, and
the PostgreSQL `managed.services.additional` entry in a reviewed Git change.
Keep the cluster-local `postgres-metrics` Service for Prometheus scraping.
Sync and verify that traffic has stopped, then remove the ProxyGroup policies,
ProxyGroups, operator Applications, Projects, and namespace manifests.
Removing the Tailscale Services does not delete PostgreSQL data. Clean up the
matching grants, auto-approvers, OAuth clients, and Tailscale devices in the
admin console. Keep the Oracle database password and CA in OCI Vault only while
a workload still uses them.

## References

- [Tailscale grants](https://tailscale.com/docs/features/access-control/grants)
- [Tailscale Kubernetes Operator quickstart](https://tailscale.com/docs/kubernetes-operator/quickstart)
- [Tailscale service egress](https://tailscale.com/docs/kubernetes-operator/egress)
- [Tailscale cross-cluster services](https://tailscale.com/docs/kubernetes-operator/ingress/multi-cluster-service-mirroring)
- [Tailscale ProxyGroup policies](https://tailscale.com/docs/kubernetes-operator/manage-and-configure/proxy-group-policy)
- [Tailscale operator permissions and RBAC](https://tailscale.com/docs/kubernetes-operator/reference/rbac)
- [Tailscale on Linux](https://tailscale.com/docs/install/linux)
- [Tailscale auth keys](https://tailscale.com/docs/features/access-control/auth-keys)
- [K3s cluster access](https://docs.k3s.io/cluster-access)
- [K3s configuration](https://docs.k3s.io/installation/configuration)
- [K3s certificate rotation](https://docs.k3s.io/cli/certificate)
- [K9s releases](https://github.com/derailed/k9s/releases)
