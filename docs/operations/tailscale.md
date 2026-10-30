# Private access with Tailscale

Tailscale provides the private network path between your workstation and the
VM. SSH is still the tool that logs you into the VM, and it travels over that
private path. This setup uses regular OpenSSH with your OCI SSH key; it does
not enable the separate Tailscale SSH feature. K9s runs on your workstation
and connects directly to the Kubernetes API over Tailscale. Keep the public SSH
rule until private SSH and Kubernetes access both work.

## Prepare the tailnet

1. Install Tailscale on your Linux workstation using the
   [official Linux instructions](https://tailscale.com/docs/install/linux),
   then join your tailnet:

   ```bash
   sudo tailscale up
   ```

   Open the sign-in URL and approve your workstation. Check that the
   workstation is an approved device in the Tailscale admin console.
2. In the tailnet policy editor, merge these entries into the existing policy.
   Do not replace your policy with this snippet:

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

   Keep other entries you need. Remove broad rules such as `*` to `*` if you
   want this SSH grant to be the only access to the VM. Grants add permissions;
   a narrow grant does not cancel a broad one. Review and test the policy before
   saving it.
3. Create an auth key with **one-off**, **pre-approved**, and
   **`tag:oracle-k3s`** selected. Give it a short expiry. Use it only for this
   enrollment. The playbook prompts for it with hidden input and suppresses
   task logging. Do not put the key in Git, a shell command, or Terraform.

## Install and enroll the VM

Use a Linux workstation such as Ubuntu or WSL. Keep both repositories under
the same workspace directory, for example `~/Projects/disease-prediction/`.
The infrastructure repository must be initialized and its temporary SSH rule
must still be enabled.

Install the tools and the pinned Ansible version. Keep the SSH private key
under your Linux home directory, outside both repositories:

```bash
sudo apt update
sudo apt install -y git openssh-client python3-venv
install -d -m 700 "$HOME/.ssh"
install -m 600 /path/to/oracle-private-key "$HOME/.ssh/disease-prediction-oci.key"
chmod 600 "$HOME/.ssh/disease-prediction-oci.key"
cd "$HOME/Projects/disease-prediction"
if [ ! -d disease-prediction-gitops ]; then
  git clone https://github.com/Disease-Prediction-ASET26/disease-prediction-gitops.git
fi
cd disease-prediction-gitops
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r automation/ansible/requirements.txt
```

Before accepting the VM's SSH host key on first connection, verify its
fingerprint through the OCI Console or another trusted channel. Do not bypass
host-key checking. From the workspace directory that contains both
repositories, set the public IP variable and change into the GitOps repository.
The commands then use that same value for the SSH check and Ansible inventory:

```bash
cd "$HOME/Projects/disease-prediction"
set -e
ORACLE_PUBLIC_IP="$(terraform \
  -chdir=disease-prediction-infra/terraform/oracle \
  output -raw instance_public_ip)"
test -n "$ORACLE_PUBLIC_IP"
cd disease-prediction-gitops

ssh -i "$HOME/.ssh/disease-prediction-oci.key" "opc@$ORACLE_PUBLIC_IP" true

ansible-playbook \
  -i "${ORACLE_PUBLIC_IP}," \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  automation/ansible/playbooks/tailscale.yml
```

Ansible asks for the one-use key with hidden input. The playbook installs
Tailscale from its signed Oracle Linux 9 stable repository, enables the service,
sets hostname `oracle-k3s` and tag `tag:oracle-k3s`, and confirms the private
address. Check that `tailscale status` on your workstation shows both your
workstation and `oracle-k3s`.

## Enable post-quantum SSH key exchange

The SSH warning means the connection worked, but the two SSH servers did not
negotiate a post-quantum key exchange. On this VM, OpenSSH 9.9 supports it, but
Oracle Linux's current `DEFAULT` crypto policy does not enable it. The Ansible
playbook adds Oracle Linux's `PQ` policy module and restarts `sshd` when the
policy changes. This policy applies system-wide, so older clients or services
that use system crypto settings could be affected.

From the GitOps repository root, rerun the playbook over the active Tailscale
connection:

```bash
ansible-playbook \
  -i 'oracle-k3s,' \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  automation/ansible/playbooks/tailscale.yml
```

Keep the current SSH session open while it restarts `sshd`. In another
workstation terminal, check that a new connection negotiates the hybrid ML-KEM
key exchange and no longer prints the warning:

```bash
ssh -vv -i "$HOME/.ssh/disease-prediction-oci.key" \
  -o BatchMode=yes opc@oracle-k3s true 2>&1 | grep -E 'kex: algorithm|post-quantum key exchange'
```

The negotiated algorithm should be `mlkem768x25519-sha256`. If older clients
or services have compatibility problems, restore the previous `DEFAULT`
policy from an existing SSH session and restart `sshd`:

```bash
sudo update-crypto-policies --set DEFAULT
sudo systemctl restart sshd
```

## Connect from your workstation

Make sure Tailscale is running on your Linux **workstation**. It normally
starts automatically after setup; use `sudo tailscale up` and sign in if it is
not connected. Check the private link, then SSH to the VM's Tailscale name:

```bash
tailscale status
tailscale ping oracle-k3s
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s
```

The SSH command opens a shell on the VM as `opc`. Type `exit` to close that
shell. Run these commands in your workstation terminal, where the prompt shows
your workstation user (for example, `picalexs@...`), not at `[opc@vm ~]$`.

The public and Tailscale routes reach the same VM and should use the same SSH
host key. If SSH reports a different key, stop and verify it through the OCI
Console before accepting it.

If you want to run Kubernetes commands inside that VM shell, use K3s's bundled
kubectl with `sudo`. It reads the root-owned K3s kubeconfig, so you do not need
to copy a kubeconfig to your workstation or start an SSH tunnel:

```bash
sudo /usr/local/bin/k3s kubectl get nodes
sudo /usr/local/bin/k3s kubectl get pods -A
```

## Use kubectl and K9s from your workstation

The policy above lets your tailnet owner account reach the VM on SSH and the
Kubernetes API port. Keep OCI ingress port 6443 closed; this access is through
Tailscale only. Review the full tailnet policy for broader rules, because
grants add permissions and do not cancel other grants or ACLs.

From the GitOps repository root, apply the playbook again over Tailscale. It
adds `oracle-k3s` to the K3s API certificate names and rotates the API server
certificate if the configuration changed. The API is briefly unavailable
while K3s restarts:

```bash
ansible-playbook \
  -i 'oracle-k3s,' \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  automation/ansible/playbooks/tailscale.yml
```

Copy the K3s admin kubeconfig to the workstation. It grants full cluster-admin
access, so keep it outside Git and restrict it to your user:

```bash
install -d -m 700 "$HOME/.kube"
umask 077
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s \
  'sudo cat /etc/rancher/k3s/k3s.yaml' > "$HOME/.kube/oracle-k3s.yaml"
chmod 600 "$HOME/.kube/oracle-k3s.yaml"
sed -i 's#server: https://127.0.0.1:6443#server: https://oracle-k3s:6443#' \
  "$HOME/.kube/oracle-k3s.yaml"
grep 'server:' "$HOME/.kube/oracle-k3s.yaml"
```

Set this as the default kubeconfig in new Zsh terminals, so `kubectl` and
K9s find it without extra flags:

```bash
grep -qxF 'export KUBECONFIG="$HOME/.kube/oracle-k3s.yaml"' "$HOME/.zshrc" || \
  printf '\nexport KUBECONFIG="$HOME/.kube/oracle-k3s.yaml"\n' >> "$HOME/.zshrc"
source "$HOME/.zshrc"
```

Verify the private connection and cluster access:

```bash
tailscale ping oracle-k3s
kubectl get nodes
kubectl get pods -A
```

Install K9s on the WSL workstation. This example uses K9s v0.51.0 for Linux
amd64 and verifies the published release checksum:

```bash
cd /tmp
version=v0.51.0
package=k9s_linux_amd64.deb
curl -fsSLO "https://github.com/derailed/k9s/releases/download/${version}/${package}"
curl -fsSLO "https://github.com/derailed/k9s/releases/download/${version}/checksums.sha256"
grep -E "^[0-9a-f]{64}  ${package}$" checksums.sha256 | sha256sum --check
sudo apt install "./${package}"
```

Then start K9s whenever you want to inspect or manage the cluster:

```bash
k9s
```

This works in later terminals whenever Tailscale is connected. K9s has normal
write access: the kubeconfig grants cluster-admin rights, so it can change and
delete resources. Keep the file protected with mode `600`. Use `:ns` to switch
namespaces, `l` to view pod logs, and `:q` to exit.

If kubectl tries `localhost:8080`, check that the kubeconfig exists and the
`KUBECONFIG` line is in `~/.zshrc`. If an API request times out, confirm that
the tailnet policy grants `tcp:6443` and rerun the Ansible playbook to apply the
VM's restricted Tailscale firewall zone. If you see a TLS name error, rerun the
playbook to confirm the API certificate includes `oracle-k3s`.

## Close public SSH

After private SSH and direct Kubernetes access work, change `admin_ssh_cidr` to
`null` in the infrastructure repository's `terraform.tfvars`. From
`disease-prediction-infra/terraform/oracle`, review and apply the plan:

```bash
terraform plan -out=infra.tfplan
terraform show infra.tfplan
terraform apply infra.tfplan
rm infra.tfplan
```

The plan should remove only the public SSH ingress rule. Apply only after
confirming that. Then confirm you can still SSH over Tailscale and use your
chosen Kubernetes workflow. The VM will still have a public IP for outbound
updates, but inbound SSH will be private.

## Security checks

- Keep the tailnet policy limited to the people who administer this VM and
  `tcp:22` plus `tcp:6443`. Check for older broad ACLs or grants that still give
  wider access.
- Protect the tailnet owner account with MFA and approve only trusted
  workstations. Review the Machines page and remove devices you no longer use.
- Keep the one-use auth key short-lived and out of shell history and logs. The
  auth key is revoked after use; the VM's tagged node key is separate. Tailscale
  disables key expiry by default for tagged devices, so review that setting and
  keep a recovery path before changing it. An expired key can disconnect this
  remote server.
- Keep SSH private keys and the kubeconfig out of Git. On Linux, use mode `600`
  for private keys and kubeconfig files, and `700` for `.ssh` and `.kube`
  directories.
- Keep the VM and workstation patched. Do not disable the SSH warning or weaken
  host-key checking to hide a key-exchange issue.

## Preview, reapply, and remove Tailscale

Preview the Ansible changes from the GitOps repository root:

```bash
ansible-playbook \
  -i '<oracle-public-ip>,' \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  --check --diff \
  automation/ansible/playbooks/tailscale.yml
```

Apply or reapply by running the same command without `--check --diff`. Once
the VM is enrolled, the playbook does not ask for an auth key again.

To remove Tailscale, first restore public SSH in Terraform with your current
public IPv4 `/32`, review and apply the plan, and verify SSH to the public IP.
Then run the removal playbook from the GitOps repository root:

```bash
ansible-playbook \
  -i '<oracle-public-ip>,' \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  automation/ansible/playbooks/remove-tailscale.yml
```

This removes the package, repository, and local device identity. Remove
`oracle-k3s` from the Tailscale admin console after the playbook completes.
Keep public SSH limited to your `/32`; never open it to `0.0.0.0/0`.

## References

- [Tailscale on Linux](https://tailscale.com/docs/install/linux)
- [Set up a Tailscale server](https://tailscale.com/docs/how-to/set-up-servers)
- [Tailscale grants](https://tailscale.com/docs/features/access-control/grants)
- [Tailscale tags](https://tailscale.com/docs/features/tags)
- [Auth keys](https://tailscale.com/docs/features/access-control/auth-keys)
- [Key expiry](https://tailscale.com/docs/features/access-control/key-expiry)
- [K9s installation](https://k9scli.io/topics/install/)
- [K9s commands](https://k9scli.io/topics/commands/)
- [K3s cluster access](https://docs.k3s.io/cluster-access)
- [K3s configuration](https://docs.k3s.io/installation/configuration)
- [K3s certificate rotation](https://docs.k3s.io/cli/certificate)
- [Ansible installation](https://docs.ansible.com/projects/ansible/latest/intro_installation.html)
