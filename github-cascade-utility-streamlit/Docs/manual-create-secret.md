# Manual: Create CASCADE_GITHUB_TOKEN secret

If the tool cannot create the `CASCADE_GITHUB_TOKEN` secret automatically:

1. In GitHub, open the repository.
2. Go to **Settings > Secrets and variables > Actions**.
3. Click **New repository secret**.
4. Set **Name** to `CASCADE_GITHUB_TOKEN`.
5. Paste the PAT you want the workflows to use for cascade PR merge.
6. Click **Add secret**, then rerun the utility.
