# Secrets from OCI Vault

External Secrets Operator (ESO) reads secrets from OCI Vault and creates
ordinary Kubernetes Secrets for workloads. K3s is configured to encrypt those
Kubernetes Secrets at rest. Secret payloads must not be committed to Git,
Terraform state, terminal output, or logs.

The ESO controller is managed by the `external-secrets` Argo CD Application.
Its `oracle-platform` AppProject can use only the pinned upstream chart and
targets `external-secrets` plus `disease-prediction`. The chart creates
scoped `Role` and `RoleBinding` resources in the workload namespace so the
controller can watch its namespaced stores and secrets. The platform project
also permits the chart's webhook `Secret` kind; the pinned chart renders that
Secret in `external-secrets`. The workload `oracle-apps` project remains
separate and permits only `SecretStore` and `ExternalSecret` among ESO kinds;
it cannot create ordinary Kubernetes Secrets. Cluster-scoped stores, push
secrets, and other cluster-wide ESO features are disabled. ESO itself creates
the synced Secrets.

The chart and image are pinned to 2.14.0, which the ESO support matrix lists
for Kubernetes 1.37. Review the [upstream support matrix](https://external-secrets.io/v2.14.0/introduction/stability-support/)
and [OCI provider guide](https://external-secrets.io/v2.14.0/provider/oracle-vault/)
before upgrading.

## Provision OCI Vault

Use the infrastructure repository to create or adopt the Vault, HSM-backed
master key, exact-instance dynamic group, and read-only policy. Follow its
Terraform plan and apply steps. The cluster policy must only allow read access
to secrets in this Vault.

Use the OCI Console to create or update secret payloads. Do not pass a real
secret as a Terraform input or a literal command argument. The instance
principal is the VM's identity, not a separate Kubernetes identity: treat all
pods that can reach OCI's instance metadata endpoint as part of this trust
boundary. Keep the IAM permission read-only and limited to this Vault.

## Install and check ESO

Review the chart version and restricted app project in Git, then render and
preview the cluster resources. The platform project's workload-namespace
destination is required for the chart's scoped RBAC resources:

```bash
kubectl kustomize clusters/oracle
kubectl diff -k clusters/oracle
```

After the pull request is merged, Argo CD installs ESO. Check the child app and
controller pods without reading Kubernetes Secret data:

```bash
kubectl -n argocd get application external-secrets
kubectl -n external-secrets get deployments,pods
```

The Vault OCID is not secret. Once Terraform has created or adopted the Vault,
add a namespaced `SecretStore` manifest using its output and the Vault region.
Do not commit a dummy OCID. The provider configuration is:

```yaml
apiVersion: external-secrets.io/v1
kind: SecretStore
metadata:
  name: oci-vault
  namespace: disease-prediction
spec:
  provider:
    oracle:
      vault: <Vault OCID from Terraform output>
      region: <Vault region>
      principalType: InstancePrincipal
```

Add this resource only after ESO's CRDs are established and the actual Vault
OCID is available. Merge it through Git and wait for the `SecretStore` Ready
condition before adding an `ExternalSecret`.

## Verify with a temporary canary

Create a disposable secret named `eso-canary` in OCI Vault using a plainly
non-sensitive value. Add a temporary, versioned `ExternalSecret` manifest in
the `disease-prediction` namespace alongside its `SecretStore`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: oci-vault-canary
  namespace: disease-prediction
spec:
  refreshInterval: 1m
  secretStoreRef:
    name: oci-vault
    kind: SecretStore
  target:
    name: oci-vault-canary
    creationPolicy: Owner
  data:
    - secretKey: value
      remoteRef:
        key: eso-canary
```

Merge and sync the manifest after the `SecretStore` is Ready. Check resource
conditions and the key name only; never print the Secret's data:

```bash
kubectl -n disease-prediction get secretstore oci-vault
kubectl -n disease-prediction get externalsecret oci-vault-canary
kubectl -n disease-prediction get secret oci-vault-canary \
  -o go-template='{{range $key, $value := .data}}{{printf "%s\n" $key}}{{end}}'
```

The canary secret is not a workload credential. Keep its value out of command
output nonetheless. After the sync succeeds, remove the temporary
`ExternalSecret` manifest from Git. The root app has pruning disabled, so
removing the manifest will not delete the live object automatically:

```bash
kubectl -n disease-prediction delete externalsecret oci-vault-canary
```

Then schedule deletion of the `eso-canary` secret in OCI Vault. ESO's owner
policy removes the generated Kubernetes Secret when its `ExternalSecret` is
deleted. Do not delete the Vault while any workload depends on its secrets.

## Add and rotate workload secrets

Store each workload credential in OCI Vault, then add an `ExternalSecret` in
that workload's namespace. Add a namespace-scoped `SecretStore` there as well;
do not use a `ClusterSecretStore`. Workloads reference the generated
Kubernetes Secret by name. Keep the secret name, target Secret name, and key
names in Git, but keep all values in OCI Vault.

To rotate a credential, add a new OCI Vault secret version and wait for ESO's
refresh interval. Check the `ExternalSecret` Ready condition and application
health. Do not print the Kubernetes Secret to verify rotation. Follow the
application's restart or reload behavior if it does not watch Secret changes.

## Remove ESO

Remove workload `ExternalSecret` and `SecretStore` resources first and delete
their live resources explicitly because automated pruning is disabled. Confirm
no generated Secrets or consumers remain, then remove the ESO Application and
namespace through a reviewed Git change. Keep Vault data until all consumers
and recovery requirements are cleared. Do not remove ESO CRDs while ESO custom
resources remain.
