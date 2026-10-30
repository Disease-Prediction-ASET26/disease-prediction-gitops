# Private cluster access

Use Tailscale for SSH and the Kubernetes API. Complete the [Tailscale setup](tailscale.md)
and verify private SSH before setting `admin_ssh_cidr = null` in Terraform.

## Create a protected kubeconfig

Run these commands from PowerShell. They copy the K3s administrator kubeconfig
directly into a protected file; its client key grants cluster-admin access.

```powershell
$sshKey = Join-Path $env:USERPROFILE '.ssh\disease-prediction-oci.key'
$kubeDir = Join-Path $env:USERPROFILE '.kube'
$kubeConfig = Join-Path $kubeDir 'oracle-k3s.yaml'

New-Item -ItemType Directory -Force $kubeDir | Out-Null
ssh -i $sshKey 'opc@oracle-k3s' 'sudo cat /etc/rancher/k3s/k3s.yaml' | Set-Content -Encoding ascii $kubeConfig
icacls $kubeConfig /inheritance:r /grant:r "$($env:USERNAME):(F)"
$env:KUBECONFIG = $kubeConfig
```

Do not commit or share this kubeconfig. Keep it outside the repositories and
remove it when it is no longer needed.

## Open the Kubernetes API tunnel

In a separate PowerShell window, run:

```powershell
$sshKey = Join-Path $env:USERPROFILE '.ssh\disease-prediction-oci.key'
ssh -i $sshKey -N -L 6443:127.0.0.1:6443 opc@oracle-k3s
```

Keep this window open while using Kubernetes tools. In the first window, check
access:

```powershell
$env:KUBECONFIG = Join-Path $env:USERPROFILE '.kube\oracle-k3s.yaml'
kubectl get nodes
```

Do not set `insecure-skip-tls-verify` to work around a certificate error. Check
the tunnel and K3s certificate instead.

## Recover if Tailscale is unavailable

Before removing Tailscale or changing its policy, restore public SSH access:

1. Set `admin_ssh_cidr` in the infrastructure `terraform.tfvars` to your
   current public IPv4 address with `/32`.
2. Review the Terraform plan. It should add only the SSH ingress rule.
3. Apply it and verify SSH to the VM's current public IP.

Keep this rule limited to your `/32`. Never use `0.0.0.0/0`. See the
[infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md)
for Terraform commands.
