First-time deployment of the arkestrabot to a remote server.

If `$ARGUMENTS` contains `--dry-run`, run in dry-run mode (preflight checks only, no changes). Otherwise run the full deployment.

Read `.claude/deploy.json` to get connection details. If the file doesn't exist, tell the user to copy `.claude/deploy.json.example` to `.claude/deploy.json` and fill in their values, then stop.

Extract these fields from the config and verify none are blank or missing — if any are, report which ones and stop:
- `ssh_user` — SSH username
- `ssh_host` — server IP or hostname
- `ssh_target` = `ssh_user@ssh_host`
- `remote_path` — where to clone the repo
- `service_name` — systemd service name
- `git_repo` — git clone URL

---

## Dry-run mode

If `--dry-run` was passed, perform only these checks and then print a summary:

1. **SSH key**: check if `~/.ssh/id_ed25519.pub` exists locally. Report found/missing.
2. **SSH connectivity**: run `ssh $ssh_target echo ok`. Report success/failure.
3. **Remote path**: run `ssh $ssh_target test -d $remote_path && echo exists || echo missing`. Report whether it already exists.
4. **Local config.json**: check if `config.json` exists locally. Report found/missing.
5. **Systemd service**: show the unit file that would be written (see template in Step 5 below), but do NOT write it.

Print a summary table of all checks (pass/fail), then stop. Do not proceed to the full deployment steps.

---

## Full deployment

Execute these steps in order, showing output at each step and stopping if anything fails:

### Step 1: SSH key setup

Check if `~/.ssh/id_ed25519.pub` exists locally. If not, generate one with `ssh-keygen -t ed25519`. Then run `ssh-copy-id $ssh_target` so the user can enter their password once. Verify passwordless access works with `ssh $ssh_target echo ok`.

### Step 2: Clone the repo

SSH in and clone the repo:
```
ssh $ssh_target "git clone $git_repo $remote_path"
```
If `remote_path` already exists, ask the user whether to skip this step or remove and re-clone.

### Step 3: Create venv and install deps

```
ssh $ssh_target "cd $remote_path && python3 -m venv venv && venv/bin/pip install -r requirements.txt"
```

### Step 4: Copy config.json

SCP the local `config.json` to the remote:
```
scp config.json $ssh_target:$remote_path/config.json
```
If local `config.json` doesn't exist, warn the user and stop.

### Step 5: Create systemd service

SSH in and create a systemd unit file. Use this template, substituting the variables:

```ini
[Unit]
Description=Arkestrabot
After=network.target

[Service]
Type=simple
User=$ssh_user
WorkingDirectory=$remote_path
ExecStart=$remote_path/venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Write it to `/etc/systemd/system/$service_name.service` via sudo, then enable and start:
```
sudo systemctl daemon-reload
sudo systemctl enable $service_name
sudo systemctl start $service_name
```

### Step 6: Verify

Run `sudo systemctl status $service_name` and show the output. Confirm the service is active and running.
