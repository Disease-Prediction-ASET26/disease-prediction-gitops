# Tailscale access

Tailscale gives the VM a private address that stays the same when your laptop
changes networks. The VM still uses its public IP for outbound updates. After
you verify private access, Terraform can close public SSH.

## Prepare the tailnet

1. Install the [Tailscale Windows app](https://tailscale.com/docs/install/windows)
   and sign in to the tailnet you will use for this cluster.
2. In the tailnet policy editor, merge these top-level entries into the
   existing policy. Do not replace the full tailnet policy with this example:

   ```json
   {
     "tagOwners": {
       "tag:oracle-k3s": ["autogroup:owner"]
     },
     "grants": [
       {
         "src": ["autogroup:owner"],
         "dst": ["tag:oracle-k3s"],
         "ip": ["tcp:22"]
       }
     ]
   }
   ```

   Keep existing policy entries that you need. Remove any broad rule that gives
   all members access to all devices if you want this SSH grant to be the only
   access to the VM. Grants add permissions; a narrow grant does not cancel a
   broad one. Review the policy before saving it.
3. In the Tailscale admin console, create an auth key with these settings:
   **one-off**, **pre-approved**, and tagged `tag:oracle-k3s`. Choose a short
   expiry. Do not paste the key into Git, chat, Terraform, or a command line.

## Install and enroll the VM

Run Ansible from Linux or macOS. On this Windows laptop, install Ubuntu on WSL
if needed; Ansible does not run natively as a Windows control node. WSL is a
workstation option, not a supported production control host. From PowerShell,
install WSL if it is not already set up:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart Windows if prompted, open Ubuntu, and clone this public repository into
the Linux home directory. From the infrastructure repository, get the current
public IP while the temporary SSH rule is still enabled:

```powershell
terraform -chdir=terraform/oracle output -raw instance_public_ip
```

In Ubuntu, install the pinned Ansible version and copy the existing SSH key into
the Linux home directory. Install Python virtual-environment support first.
Keep the key outside the repositories:

```sh
sudo apt update
sudo apt install -y git openssh-client python3-venv
git clone https://github.com/Disease-Prediction-ASET26/disease-prediction-gitops.git
cd disease-prediction-gitops
python3 -m venv ~/.venvs/disease-prediction-ansible
. ~/.venvs/disease-prediction-ansible/bin/activate
python -m pip install -r automation/ansible/requirements.txt
mkdir -p ~/.ssh
cp /mnt/c/Users/<windows-user>/.ssh/disease-prediction-oci.key ~/.ssh/
chmod 600 ~/.ssh/disease-prediction-oci.key
```

Replace `<windows-user>` with your Windows account name. Check the VM's SSH
host key through the OCI Console before accepting it. Then run the playbook,
using the public IP printed by Terraform:

```sh
ssh -i ~/.ssh/disease-prediction-oci.key opc@<oracle-public-ip> exit
ansible-playbook \
  -i '<oracle-public-ip>,' \
  -u opc \
  --private-key ~/.ssh/disease-prediction-oci.key \
  automation/ansible/playbooks/tailscale.yml
```

Ansible asks for the one-use key with hidden input. It passes the key to
Tailscale for enrollment and does not save it in this repository or Terraform
state. The playbook installs Tailscale from its official Oracle Linux 9 stable
repository, enables the service, sets the `oracle-k3s` hostname and server tag,
and confirms the private address. Tagged server devices do not use a personal
user identity.

## Verify before closing public SSH

Enable MagicDNS in the tailnet DNS settings. On Windows, confirm `oracle-k3s`
appears as connected in Tailscale, then check SSH:

```powershell
$sshKey = Join-Path $env:USERPROFILE '.ssh\disease-prediction-oci.key'
ssh -i $sshKey opc@oracle-k3s
```

Open a second PowerShell window and start the Kubernetes API tunnel:

```powershell
ssh -i $sshKey -N -L 6443:127.0.0.1:6443 opc@oracle-k3s
```

In the first window, confirm `kubectl get nodes` reports the node as `Ready`.
Follow [private cluster access](access.md) to create a protected kubeconfig.
Only after SSH and `kubectl` both work over Tailscale, set
`admin_ssh_cidr = null` in the Terraform variables and review the plan. It
should remove only the public SSH ingress rule.

## Preview and modify

Preview the Ansible changes without applying them:

```sh
ansible-playbook \
  -i '<oracle-public-ip>,' \
  -u opc \
  --private-key ~/.ssh/disease-prediction-oci.key \
  --check --diff \
  automation/ansible/playbooks/tailscale.yml
```

Apply or reapply the desired setup by running the same command without
`--check --diff`. Once the VM is enrolled, the playbook does not prompt for an
auth key again.

## Remove Tailscale

First restore public SSH in Terraform by setting `admin_ssh_cidr` to your
current public IPv4 `/32`, reviewing the plan, and applying it. Confirm SSH over
the public address works. Then run the removal playbook using that address:

```sh
ansible-playbook \
  -i '<oracle-public-ip>,' \
  -u opc \
  --private-key ~/.ssh/disease-prediction-oci.key \
  automation/ansible/playbooks/remove-tailscale.yml
```

This removes the package, repository, and local device identity. Remove
`oracle-k3s` from the Tailscale admin console after the playbook completes.
Keep public SSH limited to your `/32`; never open it to `0.0.0.0/0`.

## References

- [Tailscale on Linux](https://tailscale.com/docs/install/linux)
- [Tailscale server setup](https://tailscale.com/docs/how-to/set-up-servers)
- [Tailscale grants](https://tailscale.com/docs/features/access-control/grants)
- [Tailscale tags](https://tailscale.com/docs/features/tags)
- [Ansible installation](https://docs.ansible.com/projects/ansible/latest/intro_installation.html)
