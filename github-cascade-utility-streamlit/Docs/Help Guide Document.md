# Cascade Workflow Bootstrapper – User Help Guide

## 1. What this utility does

This utility prepares one or more GitHub repositories so they can participate in a release‑branch “cascade merge” process.

For every repository you list in the input JSON, the utility:

- Ensures a standard set of **cascade labels** exist (creating any that are missing).
- Creates or verifies the `CASCADE_GITHUB_TOKEN` **repository secret** that holds a GitHub personal access token (PAT).
- Enables **repository‑level auto‑merge**, so clean pull requests can be merged automatically where rules allow.
- Creates or updates the cascade workflow files (`cascade-next-pr.yml` and `cascade-conflict-check.yml`) on a **feature branch**, opens a pull request, and attempts to auto‑merge that PR into the default branch.

The end result is that each repository is fully wired for automated cascade PRs between release branches, with consistent labels, secrets, and workflow configuration.

***

## 2. Prerequisites and permissions

Before using the utility, a new developer should have:

- **GitHub access**: Admin or maintainer rights on each target repository (needed for labels, secrets, settings, and workflow PRs).
- **Personal Access Token (PAT)**: A GitHub PAT that:
    - Has **no expiration** (or as long‑lived as your org allows).
    - Has at least these scopes on each target repo:
        - `contents` (read/write) – to push workflow files.
        - `pull_requests` – to open and merge PRs.
        - `issues` – to create/apply labels.
        - `administration` or equivalent repo‑admin permission – to change auto‑merge settings and manage secrets.
- **Workflow templates available** in the local project at `templates/workflows/cascade-next-pr.yml` and `templates/workflows/cascade-conflict-check.yml`.

The same PAT is used both as the **API credential** for running the utility and as the value stored in the `CASCADE_GITHUB_TOKEN` secret inside each repository.

***

## 3. Input configuration JSON

You configure the run via a JSON object pasted into the Streamlit UI under **“Configuration JSON”**.

### 3.1. Overall structure

The JSON must be an object with a single key:

```json
{
  "repositories": [
    {
      "repository": "owner/repo-name",
      "patToken": "your_personal_access_token_here"
    }
  ]
}
```

- `repositories` (required):
A non‑empty array. Each item describes one GitHub repository to bootstrap.


### 3.2. Per‑repository fields

Each repository entry must include:

- `repository` (string, required):
Must be of the form `"owner/name"`, for example `"ShreyashVijayPawar/FlyAway"`.
    - Validation: If this is missing, not a string, or does not contain exactly one `/`, validation will fail with a message like:
        - `repository must be of form 'owner/name'.`
- `patToken` (string, required):
The PAT to use for that repository. In most cases you will reuse the same PAT for all repos, but the format allows per‑repo tokens.
    - Validation: If this is missing, empty, or whitespace only, validation fails with:
        - ``patToken` is required and must be non-empty.`

Example with two repositories:

```json
{
  "repositories": [
    {
      "repository": "CitInternal/172598.onb-vm-gbl.hnw-services",
      "patToken": "paste_your_token_here"
    },
    {
      "repository": "CitInternal/172598.icg.onboarding-services.hnw-services",
      "patToken": "paste_your_token_here"
    }
  ]
}
```

The **“Run setup \& propagate”** button first validates this JSON; if it fails, nothing is applied to any repo and validation errors are listed in the Streamlit UI.

***

## 4. What happens when you run it

After you click **“Run setup \& propagate”** and validation passes, the utility processes each repository in turn.

### 4.1. Labels step

For each repository:

1. It fetches the existing labels from GitHub.
2. It ensures these labels exist, creating any that are missing:
    - `cascade-pr` – for PRs created by the cascade workflow.
    - `cascade-merge-conflicts` – for cascade PRs that hit merge conflicts.
    - `cascade-manual-review` – for PRs needing manual attention.

The result of this step is shown in the **“Labels”** column:

- `created: ...` – labels that were successfully created.
- `existed: ...` – labels that already existed.
- `failed: ...` – label names that could not be created (for example, missing permissions).

If labels failed, the header includes a link to **manual-create-labels**, where manual creation instructions are documented.

### 4.2. Secret step

The utility then ensures the `CASCADE_GITHUB_TOKEN` secret is present.

1. It checks `Settings > Secrets and variables > Actions > CASCADE_GITHUB_TOKEN`.
2. If already present, status is `alreadyPresent`.
3. If missing, it fetches the repo’s **public key**, encrypts the `patToken` value from your JSON with that key, and creates the secret through the GitHub API.

In the table:

- **Repository secret** column shows `SUCCESS` if the step succeeded or the secret already existed.
- It shows `FAILED` if the API call failed (e.g., insufficient rights or unexpected response). Detailed error text is kept in the raw JSON output but summarized in the UI.

If it fails, the column header links to **manual-create-secret**, which explains how to add the secret manually in GitHub.

### 4.3. Auto‑merge step

Next, the utility ensures repository‑level auto‑merge is enabled.

- If `allow_auto_merge` is already `True` on the repo, status is `alreadyEnabled`.
- Otherwise, it attempts to set `allow_auto_merge=True` using the GitHub API.

In the table:

- **Enable Auto‑Merge** shows `SUCCESS` if auto‑merge is enabled or already on.
- Shows `FAILED` if the API call fails (for example, lack of admin rights or org‑level restriction).

The header links to **manual-enable-auto-merge** for manual steps in GitHub settings.

### 4.4. Workflow code step

Finally, the utility syncs the cascade workflow files.

1. Identifies the repo’s **default branch** (usually `main` or `master`).
2. Creates a timestamped **feature branch** from that default branch, such as:
    - `feature/cascade-workflows-08_05_2026_01_10_23`.
3. For each template file in `templates/workflows/`:
    - `cascade-next-pr.yml`
    - `cascade-conflict-check.yml`
it reads the local file content and compares it with the file at `.github/workflows/...` on the feature branch.
    - If the file does not exist on the branch, it is **created**.
    - If it exists but content differs, it is **updated**.
4. If any file was created or updated, the utility opens a **pull request** from the feature branch into the default branch with a commit message like:
    - `CWS-1234 - Cascade workflow configuration`.
5. It polls the PR’s mergeability and, if the PR is clean and mergeable, attempts to **auto‑merge** it.

In the table:

- **Workflow code** column can show:
    - `PR [OPEN] = <url>` – PR exists and is still open.
    - `PR [CLOSED] = <url>` – PR was auto‑merged or otherwise closed.
    - `FAILED` – workflow sync failed (e.g., template read error, API failure).
    - `NA` – no changes were needed (files already match templates, so no PR was created).

The header links to **manual-setup-workflows**, which explains how to create or update workflow files manually if needed.

***

## 5. Reading the results table

After a run, the **Results** table gives a compact summary for each repository.

Columns:

- **Repository**: The `owner/name` value from your config JSON.
- **Labels**: Multi‑line summary of created/existing/failed labels. Use the header link to the labels doc if `failed` appears.
- **Repository secret**: `SUCCESS` or `FAILED`. Use the header link if you need to add the secret manually.
- **Enable Auto‑Merge**: `SUCCESS` or `FAILED`. Use the header link to adjust settings if needed.
- **Workflow code**: PR status (`PR [OPEN]` or `PR [CLOSED]` plus URL), `FAILED`, or `NA`.

The headers themselves include a second line with a **clickable manual‑doc link**, e.g.:

- `Labels`
`(manual-create-labels)`
so that anyone who sees a `FAILED` cell knows exactly where to go to fix it by hand.

***

## 6. How to verify what the utility did

A new developer can verify each step directly in GitHub:

1. **Labels**
    - Open the repo.
    - Go to **Issues > Labels** or **Pull requests > Labels**.
    - Confirm that `cascade-pr`, `cascade-merge-conflicts`, and `cascade-manual-review` exist with the expected colors/descriptions.
2. **Repository secret**
    - Go to **Settings > Secrets and variables > Actions**.
    - Confirm there is a secret named `CASCADE_GITHUB_TOKEN`.
    - Verify that its last updated time matches the utility run if it was just created.
3. **Auto‑merge**
    - Go to **Settings > General > Pull Requests** (or repo settings where auto‑merge is configured).
    - Confirm auto‑merge is enabled at repository level.
    - Optionally, open any PR and check that auto‑merge options are available.
4. **Workflow files**
    - In the repository, open the **Code** tab.
    - Browse to `.github/workflows/` and open `cascade-next-pr.yml` and `cascade-conflict-check.yml`.
    - Confirm the content matches your expected templates and that `secrets.CASCADE_GITHUB_TOKEN` is referenced where needed.
5. **Workflow PR**
    - Click the link in the **Workflow code** column (`PR [OPEN] = ...` or `PR [CLOSED] = ...`).
    - Verify:
        - The PR title and commit message refer to cascade workflow configuration.
        - The changed files tab shows only the workflow YAMLs.
        - If auto‑merged, that the default branch now includes the workflow changes.

***

## 7. How to test the cascade after setup

Once a repository is bootstrapped:

1. **Prepare branches**
    - Ensure release branches (for example, `release/1.0`, `release/1.1`, `release/1.2`) already exist and are configured with your ruleset, as described in your broader cascade setup guide.
2. **Create a test PR**
    - Make a small, safe change on the earliest release branch in your cascade.
    - Open a normal PR into that branch and merge it as your team normally would.
3. **Observe Actions**
    - Go to the repo’s **Actions** tab.
    - Confirm the cascade workflows are triggered and run without errors.
    - Inspect job logs if anything fails.
4. **Check downstream PRs**
    - For the next release branch in the chain, confirm that the cascade workflow:
        - Opened a PR.
        - Applied the expected labels (for conflicts, manual review, etc.).
        - Auto‑merged clean PRs when rules allow.
5. **Repeat as needed**
    - Walk through the full branch chain until you hit the final target branch, verifying behavior at each step.
    - Resolve any labels/secret/workflow issues by using the manual docs linked from the Results table headers.

***

## 8. Troubleshooting patterns

Some common scenarios a new developer might see:

- **`FAILED` in Labels column**
    - Typically caused by insufficient permissions on the PAT or label name conflicts.
    - Use `(manual-create-labels)` link in the header to add labels directly in GitHub, then re-run if desired.
- **`FAILED` in Repository secret column**
    - Usually due to missing `secrets` permission or org‑level restrictions on Actions.
    - Use `(manual-create-secret)` guide to create `CASCADE_GITHUB_TOKEN` manually.
- **`FAILED` in Enable Auto‑Merge column**
    - Indicates the PAT user cannot change auto‑merge settings or auto‑merge is disabled at org level.
    - Use `(manual-enable-auto-merge)` guide and coordinate with repo/org admins.
- **`FAILED` or `NA` in Workflow code column**
    - `FAILED`: check file paths in the local `templates/workflows` directory or the repo’s branch protection rules; fix manually using `(manual-setup-workflows)` guide.
    - `NA`: no change was needed because the repo already has up‑to‑date workflow files; this is usually fine.

***

If you share this guide with a new developer, they should be able to configure the JSON, run the utility safely, understand each status in the Results table, and verify/repair any steps directly in GitHub.

What part of this guide would you most like to refine next—input JSON examples, the explanation of each column in the results table, or the testing flow after setup?

<div align="center">⁂</div>

: setup-guide-for-cascade-merge.md

: propagator.py

: cascade-next-pr.yml

: app.py

