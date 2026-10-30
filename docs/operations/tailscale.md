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
python -m pip install -r automation/ansible/requirements.txt
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
  automation/ansible/playbooks/tailscale.yml
```

The playbook installs and enrolls Tailscale, sets the VM name to
`oracle-k3s`, and enables the Oracle Linux post-quantum SSH policy. It also
assigns `tailscale0` to a restricted firewalld zone that allows only SSH and
the Kubernetes API, and adds `oracle-k3s` to the K3s API certificate. K3s
restarts only if its certificate configuration changes.

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
  automation/ansible/playbooks/tailscale.yml
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
  automation/ansible/playbooks/remove-tailscale.yml
```

Remove `oracle-k3s` from the Tailscale admin console after the playbook
completes. Keep public SSH limited to your `/32`; never use `0.0.0.0/0`.
The removal playbook leaves the Oracle Linux SSH crypto policy and the K3s
`oracle-k3s` certificate name in place; neither exposes a public port.

## References

- [Tailscale grants](https://tailscale.com/docs/features/access-control/grants)
- [Tailscale on Linux](https://tailscale.com/docs/install/linux)
- [Tailscale auth keys](https://tailscale.com/docs/features/access-control/auth-keys)
- [K3s cluster access](https://docs.k3s.io/cluster-access)
- [K3s configuration](https://docs.k3s.io/installation/configuration)
- [K3s certificate rotation](https://docs.k3s.io/cli/certificate)
- [K9s releases](https://github.com/derailed/k9s/releases)
