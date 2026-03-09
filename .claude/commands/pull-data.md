Pull remote data/ files to the local data/ directory.

Read `.claude/deploy.json` to get connection details. If the file doesn't exist, tell the user to copy `.claude/deploy.json.example` to `.claude/deploy.json` and fill in their values, then stop.

Extract these fields from the config and verify none are blank or missing — if any are, report which ones and stop:
- `ssh_user` — SSH username
- `ssh_host` — server IP or hostname
- `ssh_target` = `ssh_user@ssh_host`
- `remote_path` — where the bot is deployed

---

## Steps

### Step 1: Verify SSH connectivity

Run `ssh $ssh_target echo ok`. If it fails, report the error and stop.

### Step 2: List remote data files

```
ssh $ssh_target "ls -la $remote_path/data/"
```

If the remote `data/` directory doesn't exist or is empty, warn the user and stop.

### Step 3: Ensure local data/ directory exists

```
mkdir -p data
```

### Step 4: Pull data files

Use `scp` to copy all files from the remote `data/` directory to local. Quote the remote path to avoid glob expansion issues:

```
scp '$ssh_target:$remote_path/data/*' data/
```

Show which files were copied.

### Step 5: Verify

List the local `data/` directory contents and show them:
```
ls -la data/
```
