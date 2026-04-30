# Manual: Set up cascade workflows via PR

If workflow setup fails for a repository:

1. Determine the default branch (usually `main` or `master`).
2. Create a new branch from the default branch named like `feature/cascade-workflows-DD_MM_YYYY_HH_MM_SS`.
3. In that branch, create the directory `.github/workflows/` if it does not exist.
4. Add the `cascade-next-pr.yml` and `cascade-conflict-check.yml` files from this project under `.github/workflows/`.
5. Commit with a message that starts with your Jira ID, for example:
   `ABC-123 Update cascade workflow configuration`.
6. Push the branch and open a pull request into the default branch.
7. Once satisfied, merge the PR according to your process.
