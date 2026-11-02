# Log retention

Logs stay on the Oracle VM. The cluster does not run a log collector, so this
policy adds no Kubernetes workload.

| Log source | Policy |
|---|---|
| System journal | Keep up to seven days on disk, capped at 256 MiB. Runtime is capped at 64 MiB. |
| Pod logs | Kubelet rotates at 10 MiB and keeps up to five files. A daily timer deletes rotated files older than seven days. |
| K3s containerd | Rotate daily and compress old files. A daily timer deletes rotations older than seven days. |

The cleanup timer only deletes rotated files. It leaves active log files
alone. Size rotation can remove pod logs sooner when a container writes
quickly. The system journal can also remove entries sooner if it reaches its
size cap.

## Preview and apply

Connect to the cluster over Tailscale first. See the
[private access guide](tailscale.md). From the GitOps repository root, preview
the host changes:

```bash
ansible-playbook --check --diff \
  -i 'oracle-k3s,' \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  automation/ansible/playbooks/log-retention.yml
```

Review the diff, then run the same command without `--check --diff` to apply
it. This restarts journald only if its settings change. It does not restart
K3s. It also removes old rotated logs once during apply, then daily from the
systemd timer.

## Check retention

Run these commands from a private SSH session:

```bash
sudo journalctl --disk-usage
systemctl list-timers logrotate.timer k3s-log-prune.timer
sudo systemd-analyze cat-config systemd/journald.conf
sudo logrotate -d /etc/logrotate.conf
```

The journal configuration should show `MaxRetentionSec=7day` and
`SystemMaxUse=256M`. The logrotate command uses debug mode; it checks the
configuration without rotating files.

## Change or remove the policy

Edit the tracked Ansible playbook to change the limits or age, then preview and
apply it again. Keep the playbook and this guide in sync.

To remove the seven-day policies, preview and run
`automation/ansible/playbooks/remove-log-retention.yml`:

```bash
ansible-playbook --check --diff \
  -i 'oracle-k3s,' \
  -u opc \
  --private-key "$HOME/.ssh/disease-prediction-oci.key" \
  automation/ansible/playbooks/remove-log-retention.yml
```

Review the diff, then run it again without `--check --diff`. It stops the K3s
log cleanup timer and removes its script, the containerd rule, and the
journald drop-in. It keeps existing journal files and `/var/log/journal`, so
journald continues using disk storage with system defaults. The seven-day age
limit no longer applies.

## References

- [Kubernetes container log rotation](https://kubernetes.io/docs/concepts/cluster-administration/logging/)
- [K3s log locations](https://docs.k3s.io/faq#how-do-i-configure-containerd)
- [systemd journal settings](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html)
