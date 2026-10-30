# Private cluster access

Use Tailscale for SSH and the Kubernetes API. Complete the [Tailscale setup](tailscale.md)
and verify private SSH before setting `admin_ssh_cidr = null` in Terraform.

## Create a protected kubeconfig

Run these commands from a Linux terminal. They copy the K3s administrator
kubeconfig into a protected file; its client key grants cluster-admin access.

```bash
install -d -m 700 "$HOME/.kube"
umask 077
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s \
  'sudo cat /etc/rancher/k3s/k3s.yaml' > "$HOME/.kube/oracle-k3s.yaml"
chmod 600 "$HOME/.kube/oracle-k3s.yaml"
export KUBECONFIG="$HOME/.kube/oracle-k3s.yaml"
```

Do not commit or share this kubeconfig. Keep it outside the repositories and
remove it when it is no longer needed.

## Open the Kubernetes API tunnel

In a separate terminal, run:

```bash
ssh -i "$HOME/.ssh/disease-prediction-oci.key" \
  -N -L 6443:127.0.0.1:6443 opc@oracle-k3s
```

Keep this window open while using Kubernetes tools. In the first window, check
access:

```bash
export KUBECONFIG="$HOME/.kube/oracle-k3s.yaml"
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
