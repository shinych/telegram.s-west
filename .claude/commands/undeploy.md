Completely remove the arkestrabot installation from the remote server.

Read `.claude/deploy.json` to get connection details. If the file doesn't exist, tell the user to copy `.claude/deploy.json.example` to `.claude/deploy.json` and fill in their values, then stop.

Extract these fields from the config and verify none are blank or missing — if any are, report which ones and stop:
- `ssh_user` — SSH username
- `ssh_host` — server IP or hostname
- `ssh_target` = `ssh_user@ssh_host`
- `remote_path` — where the bot is installed
- `service_name` — systemd service name

---

## Preflight

1. Verify SSH connectivity: `ssh $ssh_target echo ok`. If it fails, report and stop.
2. Check if the service exists: `ssh $ssh_target sudo systemctl cat $service_name 2>/dev/null`. Report whether it's found.
3. Check if the remote path exists: `ssh $ssh_target test -d $remote_path && echo exists || echo missing`.

Print a summary of what will be removed, then **ask the user to confirm** before proceeding. Do NOT proceed without explicit confirmation.

---

## Removal steps

Execute in order, showing output at each step:

### Step 1: Stop and disable the systemd service

```
ssh $ssh_target "sudo systemctl stop $service_name && sudo systemctl disable $service_name"
```

### Step 2: Remove the unit file

```
ssh $ssh_target "sudo rm /etc/systemd/system/$service_name.service && sudo systemctl daemon-reload"
```

### Step 3: Remove the application directory

```
ssh $ssh_target "sudo rm -rf $remote_path"
```

### Step 4: Verify

Confirm the service is gone:
```
ssh $ssh_target "sudo systemctl status $service_name"
```
Should report "not found". Confirm the directory is gone:
```
ssh $ssh_target "test -d $remote_path && echo 'still exists' || echo 'removed'"
```

Print a final summary confirming everything was removed.
