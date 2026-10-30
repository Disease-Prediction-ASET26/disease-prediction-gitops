# Private cluster access

Use Tailscale for SSH and Kubernetes API access. Follow the [Tailscale setup](tailscale.md)
to configure the private API route, copy the protected cluster-admin kubeconfig,
and install K9s. Once configured, connect Tailscale and run `k9s` from your
workstation; no SSH tunnel is needed.

The kubeconfig grants unrestricted cluster-admin access. Keep it outside Git
with file mode `600`, and remove it when you no longer need access.

## Recover if Tailscale is unavailable

Before removing Tailscale or changing its policy, restore public SSH access:

1. Set `admin_ssh_cidr` in the infrastructure `terraform.tfvars` to your
   current public IPv4 address with `/32`.
2. Review the Terraform plan. It should add only the SSH ingress rule.
3. Apply it and verify SSH to the VM's current public IP.

Keep this rule limited to your `/32`. Never use `0.0.0.0/0`. See the
[infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md)
for Terraform commands.
