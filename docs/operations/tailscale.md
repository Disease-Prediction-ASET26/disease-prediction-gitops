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

The Proxmox and Oracle K3s clusters currently use overlapping Pod and Service
CIDRs. Keep them as they are: this setup exposes only the PostgreSQL primary
and its metrics endpoint as Tailscale Services. It does not route either
cluster's Pod or Service subnet, so the overlapping ranges do not need to
change. Other cluster services stay private.

The Proxmox cluster runs one Tailscale ingress ProxyGroup. The Oracle cluster
runs one egress ProxyGroup and creates local Kubernetes Service names for the
two remote endpoints. Tailscale encrypts traffic between the proxies. The
database connection also uses PostgreSQL TLS with certificate verification.
Each ProxyGroup has one replica to limit memory use; neither cluster nor the
database becomes highly available. The operator and each proxy request 25m CPU
and 64 MiB memory, with limits of 250m CPU and 256 MiB memory.

Before merging the GitOps change, add these tag owners to the existing tailnet
policy. Keep its current `tag:oracle-k3s` entries and access rules:

`tag:oracle-k3s` identifies the Oracle VM. The new `tag:oracle-k3s-egress`
identifies only the Kubernetes egress proxies, so the database grants do not
also give the VM direct access.

```json
{
  "tagOwners": {
    "tag:k8s-operator": ["autogroup:owner"],
    "tag:k8s-proxmox": ["tag:k8s-operator"],
    "tag:oracle-k3s-egress": ["tag:k8s-operator"],
    "tag:proxmox-postgres": ["tag:k8s-operator"],
    "tag:proxmox-metrics": ["tag:k8s-operator"]
  }
}
```

Add these entries under `autoApprovers.services` so only the Proxmox ingress
proxy tag can advertise the two Tailscale Services:

```json
{
  "autoApprovers": {
    "services": {
      "tag:proxmox-postgres": ["tag:k8s-proxmox"],
      "tag:proxmox-metrics": ["tag:k8s-proxmox"]
    }
  }
}
```

Append these grants to the existing `grants` list. The Oracle proxy can reach
only PostgreSQL TCP/5432 and metrics TCP/9187 on the tagged services:

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
      "ip": ["tcp:9187"]
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
privileged Pod Security level. Namespace policies limit the Proxmox database
namespace to the ingress group and the Oracle application and monitoring
namespaces to the egress group.

Oracle workloads connect to
`proxmox-postgres.disease-prediction.svc.cluster.local:5432`. Prometheus
scrapes the PostgreSQL exporter at
`proxmox-postgres-metrics.monitoring.svc.cluster.local:9187`. Prometheus
collects metrics; this connection does not ship logs. A log collector such as
Alloy with a log store needs a separate design and bounded retention.

The Oracle proxy group has a shared tailnet identity, so tailnet policy cannot
distinguish individual pods behind it. PostgreSQL still requires its database
credentials and a trusted TLS certificate. Before running untrusted workloads
in the Oracle application or monitoring namespaces, add Kubernetes
NetworkPolicies that restrict which pods can use these egress Services.

After sync, inspect status without displaying Secret values:

```bash
kubectl --kubeconfig "$HOME/.kube/proxmox-k3s.yaml" -n argocd get applications tailscale-operator tailscale-config
kubectl --kubeconfig "$HOME/.kube/proxmox-k3s.yaml" -n tailscale get proxygroups
kubectl --kubeconfig "$HOME/.kube/proxmox-k3s.yaml" -n postgres get services postgres-tailnet postgres-metrics-tailnet
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n disease-prediction get service proxmox-postgres
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n disease-prediction get externalsecrets postgres-app-credentials postgres-server-ca
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n monitoring get services proxmox-postgres-metrics
kubectl --kubeconfig "$HOME/.kube/oracle-k3s.yaml" -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090
```

In Prometheus, query `up{job="proxmox-cnpg"}`. A value of `1` means the
remote exporter scrape succeeded. The scrape target is configured in
`clusters/oracle/observability/values.yaml`.

To remove this connectivity, first remove the Oracle egress Service mirrors
and the Proxmox CNPG `managed.services.additional` entries in a reviewed Git
change. Sync and verify that traffic has stopped, then remove the ProxyGroup
policies, ProxyGroups, operator Applications, Projects, and namespace
manifests. Removing the Tailscale Services does not delete PostgreSQL data.
Clean up the matching grants, auto-approvers, OAuth clients, and Tailscale
devices in the admin console. Keep the Oracle database password and CA in OCI
Vault only while a workload still uses them.

## References

- [Tailscale grants](https://tailscale.com/docs/features/access-control/grants)
- [Tailscale Kubernetes Operator quickstart](https://tailscale.com/docs/kubernetes-operator/quickstart)
- [Tailscale service egress](https://tailscale.com/docs/kubernetes-operator/egress)
- [Tailscale cross-cluster services](https://tailscale.com/docs/kubernetes-operator/ingress/multi-cluster-service-mirroring)
- [Tailscale ProxyGroup policies](https://tailscale.com/docs/kubernetes-operator/manage-and-configure/proxy-group-policy)
- [Tailscale on Linux](https://tailscale.com/docs/install/linux)
- [Tailscale auth keys](https://tailscale.com/docs/features/access-control/auth-keys)
- [K3s cluster access](https://docs.k3s.io/cluster-access)
- [K3s configuration](https://docs.k3s.io/installation/configuration)
- [K3s certificate rotation](https://docs.k3s.io/cli/certificate)
- [K9s releases](https://github.com/derailed/k9s/releases)
