# Local Proxmox K3s node

This guide manages the existing isolated Ubuntu VM. It does not change Proxmox,
pfSense, or guest networking. The node is an independent single-server K3s
cluster with SQLite. It does not join Oracle or deploy applications.

The VM uses `192.168.30.10/24` and gateway `192.168.30.1`. K3s uses the
inventory's pinned release, Secret encryption, and the default Flannel,
CoreDNS, Traefik, ServiceLB, local-path provisioner, and metrics-server.
Local-path volumes use the VM disk. Check CPU, RAM, disk, DNS and outbound
HTTPS against the [K3s requirements](https://docs.k3s.io/installation/requirements).

Both clusters use pod CIDR `10.42.0.0/16` and service CIDR `10.43.0.0/16`.
They overlap, so do not route pods or services between clusters. Check other
networks and tailnet routes for conflicts before adding routes. Do not change
an existing cluster's CIDRs without a migration plan.

## Bootstrap access

On the VM console, install Tailscale and complete browser authentication:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --accept-routes=false
tailscale ip -4
```

Approve the device if required. Manage Tailscale updates and reauthentication
manually. Do not advertise subnets or an exit node. The Oracle Linux Tailscale
playbook is not for this VM. See [Tailscale's Linux guide](https://tailscale.com/docs/install/linux).

Add a narrow rule to the existing tailnet `grants` list. The working rule for
this WSL device and VM was:

```json
{
  "src": ["100.78.215.70"],
  "dst": ["100.70.61.105"],
  "ip": ["tcp:22"]
}
```

Keep the Oracle grant and review any broader grants or ACLs. Check the current
Tailscale IPs before reuse; re-enrolling a device can change its address. Add
`tcp:6443` only when direct API access is needed. The API certificate must also
include the VM's Tailscale IP or MagicDNS name as a SAN. Restrict access to
trusted devices; do not publish port 6443. A SAN does not grant access.
Tailscale policy and guest firewall rules are separate from Proxmox's firewall.
See [Tailscale grants](https://tailscale.com/docs/features/access-control/grants).

On the VM console, verify the SSH host key fingerprint:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

On the WSL workstation, create a key if it does not already exist. Do not
overwrite an existing key. Compare the fingerprint above when prompted:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/local-k3s -C local-k3s
ssh-copy-id -i ~/.ssh/local-k3s.pub k3s@100.70.61.105
ssh -i ~/.ssh/local-k3s -o IdentitiesOnly=yes k3s@100.70.61.105 true
```

`ssh-copy-id` needs working password authentication. Otherwise, add the public
key from `~/.ssh/local-k3s.pub` to the VM user's `~/.ssh/authorized_keys`
through the console. Keep the private key private. SSH must be installed and
listening on the VM. Ubuntu can use `ssh.socket`, so an inactive `ssh.service`
by itself does not mean SSH is unavailable.

## Preview and apply K3s

Install the pinned Ansible Core using [workstation setup](README.md#install-workstation-tools).
The commands below use the tested user, key and Tailscale IP. Update them if
the VM or workstation changes. Run from the GitOps repository root:

```bash
ansible -i clusters/proxmox/automation/ansible/inventories/proxmox.yml proxmox_k3s \
  -e 'proxmox_tailscale_ip=100.70.61.105' \
  -u k3s --private-key ~/.ssh/local-k3s -m ping
```

Ubuntu 26.04 used `sudo-rs`, which timed out waiting for Ansible's password
prompt. The VM also had `/usr/bin/sudo.ws`; using it for Ansible worked without
changing the system default. Confirm the path on a replacement VM:

```bash
ssh -i ~/.ssh/local-k3s k3s@100.70.61.105 \
  'readlink -f /usr/bin/sudo; ls -l /usr/bin/sudo.ws'
ansible -i clusters/proxmox/automation/ansible/inventories/proxmox.yml proxmox_k3s \
  -e 'proxmox_tailscale_ip=100.70.61.105 ansible_become_exe=/usr/bin/sudo.ws' \
  -u k3s --private-key ~/.ssh/local-k3s -b -K -m command -a id
```

Enter the VM user's sudo password when prompted. The result should show
`uid=0(root)`. Remove the `ansible_become_exe` override if the replacement VM
does not need it. Never put the password in a command, Git, or shell history.

Preview first. On a fresh VM, check mode skips the configuration template and
installer, so it cannot show or test the full installation:

```bash
ansible-playbook -i clusters/proxmox/automation/ansible/inventories/proxmox.yml \
  clusters/proxmox/automation/ansible/playbooks/proxmox-k3s.yml \
  -u k3s --private-key ~/.ssh/local-k3s \
  -e '{"proxmox_tailscale_ip":"100.70.61.105","k3s_api_sans":["100.70.61.105"],"ansible_become_exe":"/usr/bin/sudo.ws"}' \
  --check --diff --ask-become-pass
```

Review the diff, then run the same command without `--check`:

```bash
ansible-playbook -i clusters/proxmox/automation/ansible/inventories/proxmox.yml \
  clusters/proxmox/automation/ansible/playbooks/proxmox-k3s.yml \
  -u k3s --private-key ~/.ssh/local-k3s \
  -e '{"proxmox_tailscale_ip":"100.70.61.105","k3s_api_sans":["100.70.61.105"],"ansible_become_exe":"/usr/bin/sudo.ws"}' \
  --diff --ask-become-pass
```

The playbook writes `/etc/rancher/k3s/config.yaml`, downloads the official
installer, and starts the pinned K3s service. The installer script itself can
change upstream. Kubeconfig stays root-only. It also configures logrotate and
host journal limits: 256 MiB persistent, 64 MiB runtime, and seven days.
Changing journal settings restarts journald. A later K3s config change restarts
K3s and interrupts the cluster. The playbook does not reboot or reset the VM.

Use the same SAN list on every run; omitting it removes the SAN. For a later
SAN change, follow [K3s certificate rotation](https://docs.k3s.io/cli/certificate)
and verify the new endpoint. Rotation interrupts the API. If the playbook
finds K3s files without its install marker, it stops. After a partial install,
inspect the installer output and `sudo journalctl -u k3s`; do not delete data
or create a marker to bypass the guard.

## Verify

On the VM:

```bash
k3s --version
sudo systemctl is-active k3s
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl get pods -A -o wide
curl -fsS -o /dev/null --max-time 10 https://github.com
```

The node should be `Ready`; system pods should be running or completed. Test
pod scheduling, image availability and cluster DNS:

```bash
sudo k3s kubectl run k3s-check --image=busybox:1.36.1 --restart=Never --command -- sleep 300
sudo k3s kubectl wait --for=condition=Ready pod/k3s-check --timeout=180s
sudo k3s kubectl exec k3s-check -- nslookup kubernetes.default.svc.cluster.local
sudo k3s kubectl delete pod k3s-check --ignore-not-found
```

Delete `k3s-check` even if a test fails. For diagnostics, use
`sudo journalctl -u k3s -n 100 --no-pager`, `sudo k3s kubectl describe pod k3s-check`,
`sudo k3s kubectl get events -A --sort-by=.lastTimestamp`, and `df -h`.

On the VM, test Proxmox management access:

```bash
nc -vz -w 3 192.168.30.1 8006
nc -vz -w 3 192.168.1.4 8006
```

On 2026-11-10 both probes timed out; the laptop could reach
`192.168.1.4:8006`. The node was Ready, system pods were running or completed,
DNS and host HTTPS worked, and a second Ansible check reported `changed=0`.
This was a check-mode preview, not a full second apply. Firewall counters,
other LAN services, inbound paths, IPv6, pod outbound traffic, and denied
Tailscale clients were not verified. Test those separately; a timeout alone
does not prove a firewall rule blocked traffic. Do not change Proxmox rules as
part of this workflow.

## Optional Argo CD bootstrap

After the node is healthy and this change is merged to `main`, install Argo CD
only if the VM has capacity. Its local root tracks `clusters/proxmox`, not
Oracle. No application workloads or public routes are included. The local
admin account is disabled; use `argocd --core` with Kubernetes credentials.

For direct API access, first add `tcp:6443` to the narrow Tailscale grant.
The commands below copy cluster-admin credentials to a private local file.
They temporarily create a user-owned copy on the VM; remove it even if the
copy fails. Never commit either kubeconfig.

```bash
install -d -m 700 "$HOME/.kube"
umask 077
ssh -t -i ~/.ssh/local-k3s k3s@100.70.61.105 \
  'sudo install -m 0600 -o k3s /etc/rancher/k3s/k3s.yaml /home/k3s/.local-k3s-kubeconfig'
scp -i ~/.ssh/local-k3s k3s@100.70.61.105:/home/k3s/.local-k3s-kubeconfig "$HOME/.kube/proxmox-k3s.yaml"
ssh -i ~/.ssh/local-k3s k3s@100.70.61.105 'rm -f /home/k3s/.local-k3s-kubeconfig'
export KUBECONFIG="$HOME/.kube/proxmox-k3s.yaml"
kubectl config set-cluster default --server=https://100.70.61.105:6443
kubectl get nodes -o wide
```

K3s refreshes local kubeconfig certificates; recopy the file when remote
credentials expire. Verify the context and node before applying:

```bash
kubectl config current-context
kubectl get nodes -o wide
kubectl diff -f clusters/proxmox/bootstrap/argocd/namespace.yaml
kubectl apply -f clusters/proxmox/bootstrap/argocd/namespace.yaml
helmfile -f clusters/proxmox/bootstrap/argocd/helmfile.yaml diff --diff-args "--allow-unreleased" --suppress-secrets
helmfile -f clusters/proxmox/bootstrap/argocd/helmfile.yaml apply --interactive --diff-args "--allow-unreleased" --suppress-secrets
kubectl -n argocd rollout status deployment/argocd-server --timeout=300s
kubectl diff -k clusters/proxmox
kubectl apply -k clusters/proxmox
kubectl -n argocd get applications,appprojects
argocd --core app get proxmox-root
```

Use `unset KUBECONFIG` when finished to return to the normal kubeconfig.

## Backup, recovery, upgrade, and removal

Back up before upgrades and rehearse recovery on an isolated VM. Stop K3s for a
consistent copy of the SQLite database, TLS and encryption state, configuration,
and server token. The archive below does not contain PVC data. Back up
application volumes separately using application-consistent methods.

```bash
sudo sh -c '
  set -eu
  umask 077
  systemctl stop k3s
  trap "systemctl start k3s" EXIT
  tar -C / -czf /root/k3s-server-backup.tar.gz \
    etc/rancher/k3s var/lib/rancher/k3s/server
'
sudo systemctl is-active k3s
```

This overwrites the previous local archive and interrupts the cluster. The trap
attempts to restart K3s even if the backup fails. The archive contains secrets;
store it encrypted off-VM with restricted access and a retention policy, check
it securely, then remove the temporary local copy. A VM snapshot alone is not
an application-consistent backup. The destination and retention are not yet set.

Restore the matching database, token, server state and configuration to a
stopped K3s installation using the same release. Preserve permissions, start
K3s, and verify the node, API and encrypted Secret access. Restore PVC data
separately. The token is required to decrypt datastore bootstrap data. See
[K3s backup and restore](https://docs.k3s.io/datastore/backup-restore).

For an upgrade, review [K3s upgrade guidance](https://docs.k3s.io/upgrades/manual)
and release notes, follow supported minor-version ordering, and verify a backup.
Change `k3s_version` in the inventory, preview, then apply with
`-e k3s_allow_upgrade=true` and the same address, SAN and sudo variables. The
installer replaces the binary and restarts K3s. Remove the override after the
upgrade. Restore a tested backup instead of downgrading.

To remove Argo CD, check the local context, review the Helmfile diff, then use
`helmfile -f clusters/proxmox/bootstrap/argocd/helmfile.yaml destroy`. Remove the local
root and project deliberately. To remove K3s, back up first; the upstream
`/usr/local/bin/k3s-uninstall.sh` removes cluster data and local-path volumes.
The playbook does not automate uninstall. Tailscale and the VM remain separate.
