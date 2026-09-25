# Deploy

Push to `main` → GitHub Actions SSHes into EC2 → `git pull` → `docker compose up -d --build`.

Workflow: `.github/workflows/deploy.yml` (see the comment header for the full picture).

## One-time setup

### 1. Repo on GitHub

This working copy has no `.git`. If the GitHub repo exists, restore history instead of starting over:

```bash
git clone git@github.com:<owner>/<repo>.git /tmp/rrag
cp -a /tmp/rrag/.git /path/to/Responsible-RAG/.git
cd /path/to/Responsible-RAG && git status
```

Only if there is no remote at all:

```bash
git init -b main && git add -A && git status --short   # .env must NOT appear
git commit -m "Initial commit"
git remote add origin git@github.com:<owner>/<repo>.git && git push -u origin main
```

### 2. Deploy key

Create the key **once**. `ssh-keygen` overwrites without asking twice, and a re-created private
key silently orphans the public key already authorized on the server (the failure only shows up
later as `Permission denied`):

```bash
[ -f ~/.ssh/rrag_deploy ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/rrag_deploy
ssh-keygen -lf ~/.ssh/rrag_deploy.pub      # note this fingerprint
```

Then authorize that public key on the instance. `ssh-copy-id` alone will fail here
(`Permission denied (publickey,...)`) unless the **account's existing key** is offered at the
same time — on EC2 that is the `.pem` from the launch key pair, which is not in `~/.ssh`.
Pick one:

```bash
# a) ssh-copy-id, authenticating with the EC2 .pem
ssh-copy-id -i ~/.ssh/rrag_deploy.pub -o IdentityFile=/path/to/awskey.pem <EC2_USER>@<EC2_HOST>

# b) no ssh-copy-id: append the key over a PEM-authenticated session (idempotent)
# NB: read stdin into a variable once — calling $(cat) twice returns "" the second time.
ssh -i /path/to/awskey.pem <EC2_USER>@<EC2_HOST> \
  'k=$(cat); mkdir -p ~/.ssh; chmod 700 ~/.ssh; touch ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys;
   if grep -qxF "$k" ~/.ssh/authorized_keys; then echo ALREADY_PRESENT;
   else printf "%s\n" "$k" >> ~/.ssh/authorized_keys; echo INSTALLED; fi' \
  < ~/.ssh/rrag_deploy.pub
```

Verify the key works **on its own** (no `.pem`, no agent):

```bash
ssh -i ~/.ssh/rrag_deploy -o IdentitiesOnly=yes -o BatchMode=yes <EC2_USER>@<EC2_HOST> 'whoami'
```

`IdentitiesOnly=yes` matters: it proves GitHub Actions will authenticate with exactly this key.

### 3. Four secrets (GitHub → Settings → Secrets and variables → Actions)

| Secret | Value |
|---|---|
| `EC2_HOST` | public IP or DNS |
| `EC2_USER` | e.g. `ubuntu` |
| `EC2_APP_DIR` | e.g. `/home/ubuntu/Responsible-RAG` — no spaces |
| `EC2_SSH_KEY` | contents of `~/.ssh/rrag_deploy` (the private key) |

### 4. Server

```bash
git clone <repo-url> $EC2_APP_DIR     # branch: main
cd $EC2_APP_DIR && docker compose version
ls -A ../storage/mongo/data ../storage/qdrant     # both must be non-empty
```

`$EC2_APP_DIR`'s parent must contain `storage/`, because the compose files bind-mount
`../storage/mongo/data` and `../storage/qdrant`. `.env` stays on the host.

## Everyday use

```bash
git push origin main
```

Watch it under the repo's **Actions** tab. The last lines show `commit: <sha>` and the container list.

## Rollback

```bash
cd $EC2_APP_DIR
git log --oneline -5
git revert <bad-sha> && git push        # the revert deploys itself
```

Manual, without GitHub:

```bash
cd $EC2_APP_DIR && git reset --hard <good-sha>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Permission denied (publickey)` | `EC2_SSH_KEY` is not the full private key, or the public key is not in the server's `~/.ssh/authorized_keys` |
| `ssh-copy-id` fails with `Permission denied (publickey,gssapi-keyex,gssapi-with-mic)` | The remote identity wasn't offered. `ssh-copy-id -i new.pub` only sends *that* key, so it cannot bootstrap itself over a PEM-only account (a `.pem` in `~/` is not a default identity). Add `-o IdentityFile=<the existing .pem>`, or use the append command in §2. |
| `ssh: no such identity` / key ignored | A `.pem` needs `600` or stricter; `chmod 400 file.pem` |
| `Permission denied` **after** it previously worked | `~/.ssh/rrag_deploy` was regenerated, so the authorized key no longer matches the private key. Compare `ssh-keygen -lf ~/.ssh/rrag_deploy.pub` against the server's `ssh-keygen -lf ~/.ssh/authorized_keys` — if the fingerprints differ, the installed entry is orphaned: re-install (§2) and delete the stale line. Also update the `EC2_SSH_KEY` secret. |
| `EC2_USER` wrong | Amazon Linux uses `ec2-user`, Ubuntu uses `ubuntu`. Check with `ssh -i <pem> <user>@<host> whoami`. |
| `Host key verification failed` | `EC2_HOST` unreachable for `ssh-keyscan`, or an IP change — re-run and check the host |
| `git pull` fails: "local changes would be overwritten" | The server's working tree has hand-edits. Commit or `git checkout -- .` on the host. This is what stops the pipeline from silently overwriting server-side changes. |
| `git pull` fails: "There is no tracking information" | The server checkout is not on a branch tracking `main` (e.g. it was cloned while empty, or sits on `master`). Fix once: `cd $EC2_APP_DIR && git checkout main && git branch --set-upstream-to=origin/main` |
| `ABORT: ../storage/... is missing or empty` | Docker would start an empty database. Restore that path from a backup before deploying. |
| `docker: command not found` | The SSH user is not in the `docker` group (`sudo usermod -aG docker $USER`) |
| Build fails / instance hangs | Images are built on the host. Add swap, or build elsewhere and pull. |

## Before risky changes

`scripts/backup.sh dump` takes a full Mongo + Qdrant restore point (598 MB, ~25 s) into
`../storage/backups/<timestamp>/`. Verify it with `scripts/backup.sh verify <dir>` and restore with
`scripts/backup.sh restore <dir> --yes`.

## Optional

- **PR checks:** `.github/workflows/ci.yml` runs lint/tests/build on pull requests. Delete it if
  you always push straight to `main`.
- **Approval gate:** create a `production` environment under Settings → Environments and add
  `environment: production` to the job.
