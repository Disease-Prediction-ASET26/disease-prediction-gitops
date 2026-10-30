# Tailscale access

Tailscale gives the VM a private address that stays the same when your laptop
changes networks. The VM still uses its public IP for outbound updates. After
you verify private access, Terraform can close public SSH.

## Prepare the tailnet

1. Install Tailscale on your Linux workstation using the
   [official Linux instructions](https://tailscale.com/docs/install/linux),
   then sign in to the tailnet you will use for this cluster:

   ```bash
   sudo tailscale up
   ```

   Open the sign-in URL shown by the command and approve the workstation.
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

Use an Ubuntu 24.04 Linux control host. From the infrastructure repository,
get the current public IP while the temporary SSH rule is still enabled:

```bash
terraform -chdir=terraform/oracle output -raw instance_public_ip
```

Install the required Linux tools and the pinned Ansible version. Copy the
existing private SSH key from its secure location into your SSH directory; keep
the key outside the repositories:

```bash
sudo apt update
sudo apt install -y git openssh-client python3-venv
install -d -m 700 "$HOME/.ssh"
install -m 600 /path/to/oracle-private-key "$HOME/.ssh/disease-prediction-oci.key"
git clone https://github.com/Disease-Prediction-ASET26/disease-prediction-gitops.git
cd disease-prediction-gitops
python3 -m venv "$HOME/.venvs/disease-prediction-ansible"
. "$HOME/.venvs/disease-prediction-ansible/bin/activate"
python -m pip install -r automation/ansible/requirements.txt
```

Replace `/path/to/oracle-private-key` with the key's current location. Check the
VM's SSH host key through the OCI Console before accepting it. Then run the
playbook, using the public IP printed by Terraform:

```bash
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

Enable MagicDNS in the tailnet DNS settings. On your Linux workstation, confirm
that `oracle-k3s` appears in Tailscale, then check SSH:

```bash
tailscale status
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s
```

In a second terminal, start the Kubernetes API tunnel:

```bash
ssh -i "$HOME/.ssh/disease-prediction-oci.key" \
  -N -L 6443:127.0.0.1:6443 opc@oracle-k3s
```

In the first window, confirm `kubectl get nodes` reports the node as `Ready`.
Follow [private cluster access](access.md) to create a protected kubeconfig.
Only after SSH and `kubectl` both work over Tailscale, set
`admin_ssh_cidr = null` in the Terraform variables and review the plan. It
should remove only the public SSH ingress rule.

## Preview and modify

Preview the Ansible changes without applying them:

```bash
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
