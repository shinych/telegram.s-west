Update the band-name-bot on the remote server: pull latest code, update deps, restart.

Read `.claude/deploy.json` to get connection details. If the file doesn't exist, tell the user to run `/deploy` first, then stop.

Extract these fields from the config:
- `ssh_user` — SSH username
- `ssh_host` — server IP or hostname
- `ssh_target` = `ssh_user@ssh_host`
- `remote_path` — where the repo lives
- `service_name` — systemd service name

Then execute these steps in order, showing output at each step:

## Step 1: Pull latest code

```
ssh $ssh_target "cd $remote_path && git pull"
```

If there are merge conflicts or the pull fails, show the output and stop.

## Step 2: Update dependencies

```
ssh $ssh_target "cd $remote_path && venv/bin/pip install -r requirements.txt"
```

## Step 3: Restart the service

```
ssh $ssh_target "sudo systemctl restart $service_name"
```

## Step 4: Verify

Run `ssh $ssh_target "sudo systemctl status $service_name"` and show the output. Confirm the service is active and running.
