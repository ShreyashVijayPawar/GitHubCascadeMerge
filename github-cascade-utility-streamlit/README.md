# Cascade Workflow Bootstrapper

This project is a Streamlit-based utility that bootstraps GitHub repositories for the cascade merge workflow.

It can, per repository and per configurable flags:

- Ensure standard cascade labels exist.
- Create the `CASCADE_GITHUB_TOKEN` secret if it does not exist (never overwrites).
- Enable repository-level auto-merge.
- Create a feature branch from the default branch, update cascade workflow files from templates, and open a PR (Jira ID required when this is enabled).

See `Docs/` for manual fallback instructions for each step.
