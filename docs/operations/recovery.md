# Recover the single-node Oracle cluster

This runbook rebuilds the VM and recreates the GitOps-managed cluster after a
VM or boot-volume loss. The cluster has one node and no high availability.
Terraform remote state and OCI Vault are separate from the VM and must remain
available. Use the [infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md)
for the full Terraform setup and destroy procedures, and the
[bootstrap guide](../bootstrap.md) to reinstall Argo CD.

## Before recovery

- Restore `terraform.tfvars`, the OCI API signing key, and the SSH private key
  from your secure backup. Do not retrieve or copy these from Git.
- Confirm the versioned `disease-prediction-tfstate` Object Storage bucket is
  available. Do not initialize against a new empty state file if OCI resources
  already exist; restore a prior bucket version or import the existing resources
  before planning.
- Check the current OCI boot-volume backup in the Console. The infrastructure
  inventory records one full backup; verify its age and restore status before
  relying on it.

## Restore Terraform access

Install the pinned Terraform version and install the OCI CLI using the
infrastructure guide. Configure the local OCI CLI profile, then initialize the
existing remote backend from `disease-prediction-infra/terraform/oracle`:

```bash
cd "$HOME/Projects/disease-prediction/disease-prediction-infra/terraform/oracle"
namespace=$(oci os ns get --query data --raw-output)
terraform init \
  -backend-config="bucket=disease-prediction-tfstate" \
  -backend-config="namespace=${namespace}" \
  -backend-config="region=eu-frankfurt-1" \
  -backend-config="key=disease-prediction/terraform.tfstate" \
  -backend-config="config_file_profile=DEFAULT"
terraform state list
terraform plan -out=infra.tfplan
terraform show infra.tfplan
```

Review the saved plan before applying it. It must not destroy the VCN, subnet,
Vault, or key. Stop if Terraform proposes creating duplicate resources or if
the state does not match the OCI Console. Apply only the reviewed plan:

```bash
terraform apply infra.tfplan
rm infra.tfplan
terraform output secrets_vault_id
terraform output secrets_vault_region
```

If the VM must be recreated, cloud-init installs the pinned K3s release
(`v1.37.1+k3s1` in the current inventory), enables Kubernetes Secret
encryption, and keeps Traefik and ServiceLB disabled. Changing the cloud-init
template does not update a running VM; use the infrastructure guide's VM
replacement steps.

## Re-establish private access

A replacement VM has a new SSH host key and Tailscale identity. Verify the SSH
host-key fingerprint through the OCI Console. After confirming the old VM is
gone, retire its device in the Tailscale admin console and create a fresh
one-use, pre-approved auth key tagged `tag:oracle-k3s`. If public SSH is
disabled, set `admin_ssh_cidr` to your current public IPv4 `/32` temporarily,
then review and apply a Terraform plan that opens SSH only to that address. Do
not open port 6443 or application ports publicly.

After verifying the new SSH fingerprint, remove the stale `oracle-k3s` entry
from the workstation's `known_hosts` with `ssh-keygen -R oracle-k3s`. Follow
the [Tailscale runbook](tailscale.md) to enroll the VM and configure the
workstation kubeconfig. Verify all three paths:

```bash
tailscale ping oracle-k3s
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s true
kubectl get nodes
```

After private SSH and kubectl both work, set `admin_ssh_cidr = null`, review
the Terraform plan, and apply only the change that removes the temporary
public SSH rule.

## Reinstall K3s services and Argo CD

Check cloud-init and K3s on the replacement VM:

```bash
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s \
  'sudo cloud-init status --long && sudo systemctl is-active k3s && sudo /usr/local/bin/k3s kubectl get nodes'
```

The node must be Ready. Then follow the
[Argo CD bootstrap guide](../bootstrap.md): install the pinned Helmfile
release. Before installing Argo CD, restore the K3s-owned Gateway API chart
from the versioned source file. From the GitOps repo root:

```bash
scp -i "$HOME/.ssh/disease-prediction-oci.key" \
  clusters/oracle/k3s-host-manifests/gateway-api-crd.yaml \
  opc@oracle-k3s:/tmp/gateway-api-crd.yaml
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s \
  'sudo install -o root -g root -m 0644 /tmp/gateway-api-crd.yaml /var/lib/rancher/k3s/server/manifests/gateway-api-crd.yaml && rm -f /tmp/gateway-api-crd.yaml'
kubectl -n kube-system get helmchart gateway-api-crd
kubectl get crd gateways.gateway.networking.k8s.io
```

Then review `kubectl diff -k clusters/oracle` and apply the checked-in cluster
configuration once. Argo CD restores the Applications, projects, namespaces,
and platform add-ons from Git. Check that the root Application and all child
Applications are Synced and Healthy.

Argo CD restores Kubernetes configuration, not persistent application data.
Only add application workloads after their API contract and publishable ARM64
image are ready.

## Restore secrets from OCI Vault

Vault and its HSM-backed key are managed outside the VM in OCI. Do not recreate
or destroy them as part of a VM recovery. Use the infrastructure Terraform
outputs for the non-secret Vault OCID and region. Once ESO is Healthy, check
that its `SecretStore` and `ExternalSecret` resources report Ready without
printing Secret data:

```bash
kubectl -n external-secrets get deployments,pods
kubectl -n disease-prediction get secretstore,externalsecret
```

The OCI dynamic group is matched to the K3s instance ID. Terraform must update
that matching rule for a replacement VM before ESO can read Vault. Add or
rotate secret payloads through OCI Console or another secure, non-logged
workflow; never place them in Terraform state, Git, or command output.

## Backups before stateful workloads

There are no application PVCs in the current cluster. Its 200 GB boot volume
uses the full Always Free block-storage allowance, and the infrastructure
inventory records one full boot-volume backup. K3s `local-path` PVC data lives
on that VM's boot volume; VM replacement can delete the volume. A volume
backup is not a substitute for an application-consistent database backup or a
tested restore of an individual workload.

Before merging a stateful workload, its operations guide must name the PVC and
storage class, the application's consistent backup command or operator, an
off-VM destination, retention, recovery point objective, and recovery time
objective. Check OCI storage and backup quotas before provisioning storage.
Then take an initial backup and restore it to a separate PVC before the app
stores important data. During recovery, keep writers stopped, provision the
PVC, restore and validate the backup, and only then start the workload. Record
the actual commands and validation checks in that app's guide; they depend on
the database or file format. Argo CD and ESO can recreate configuration and
secrets, but do not back up application data.
