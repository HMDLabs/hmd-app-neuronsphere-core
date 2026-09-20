---
orphan: true
---

# Capturing user-guide screenshots

The user guide (`docs/user_guide/`) embeds screenshots stored in
`docs/images/`. Those PNGs are **not** committed as fixtures — regenerate them
against a live environment with the helper script `capture_screenshots.py`.

## One-time setup

```bash
pip install playwright
playwright install chromium
```

## Run it

```bash
# Simplest — auto-discovers an environment and a repo class you can see:
python docs/capture_screenshots.py

# Or pin the samples explicitly:
python docs/capture_screenshots.py \
    --url https://app.hmdtr1-admin-neuronsphere.io \
    --environment admin \
    --repo-class hmd-ms-deployment
```

`--url`, `--environment`, and `--repo-class` can also be supplied via the
`NS_ADMIN_URL`, `NS_ENVIRONMENT`, and `NS_REPO_CLASS` environment variables.

A Chromium window opens. On the **first** run it lands on the login page
(captured as `login.png`) and then waits for you to sign in — complete your
SSO / MFA in that window. The authenticated session is saved to
`docs/.auth.json` (git-ignored) and reused on later runs, so you won't be asked
to log in every time. Delete that file to force a fresh login.

The script walks each documented flow and writes PNGs into `docs/images/` with
the exact filenames the guide references. When it finishes it prints a summary
of which screenshots were written and which were skipped (and why).

## Safety

The script creates a throwaway ChangeSet draft (named
`guide-screenshots-demo`) to photograph the editor and review screens. It only
*opens* the **Apply** dialog to photograph it — it never confirms an apply, so
no deployments are triggered. You may want to delete the demo draft afterwards.

## Rebuild the docs

Once the images are in place, rebuild the documentation:

```bash
hmd bartleby
```
