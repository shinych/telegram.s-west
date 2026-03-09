Copy local data/ files to the remote server.

Read `.claude/deploy.json` to get connection details. If the file doesn't exist, tell the user to copy `.claude/deploy.json.example` to `.claude/deploy.json` and fill in their values, then stop.

Extract these fields from the config and verify none are blank or missing — if any are, report which ones and stop:
- `ssh_user` — SSH username
- `ssh_host` — server IP or hostname
- `ssh_target` = `ssh_user@ssh_host`
- `remote_path` — where to clone the repo

---

## Steps

### Step 1: Verify local data

Check that the local `data/` directory exists and list its files. If it doesn't exist or is empty, warn the user and stop.

### Step 2: Verify SSH connectivity

Run `ssh $ssh_target echo ok`. If it fails, report the error and stop.

### Step 3: Ensure remote data/ directory exists

```
ssh $ssh_target "mkdir -p $remote_path/data"
```

### Step 4: Copy data files

Use `scp` to copy all files from the local `data/` directory to the remote:
```
scp data/* $ssh_target:$remote_path/data/
```

Show which files were copied.

### Step 5: Verify

List the remote `data/` directory contents and show them:
```
ssh $ssh_target "ls -la $remote_path/data/"
```
