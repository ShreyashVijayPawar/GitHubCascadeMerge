import json
from pathlib import Path

import streamlit as st

from propagator import parse_config, validate_config, run_all, resolve_flags, FLAG_KEYS


def load_default_config_text() -> str:
    example_path = Path("examples/input.json")
    if example_path.exists():
        return example_path.read_text(encoding="utf-8")
    return ""


def main() -> None:
    st.set_page_config(page_title="Cascade Workflow Bootstrapper", layout="wide")
    st.title("Cascade Workflow Bootstrapper")

    st.markdown("""This utility bootstraps repositories for the cascade merge workflow by:

- Ensuring standard cascade labels exist.
- Creating the `CASCADE_GITHUB_TOKEN` secret if missing.
- Enabling repository-level auto-merge.
- Creating a feature branch, updating workflow files, and opening a PR (optional, per flags).
""")

    st.subheader("1. Configuration JSON")

    default_config_text = load_default_config_text()
    config_text = st.text_area(
        "Paste configuration JSON here",
        value=default_config_text,
        height=260,
        help="Configuration includes defaultSetupFlags and repositories list.",
    )

    if st.button("Validate configuration"):
        if not config_text.strip():
            st.error("Configuration JSON is required.")
            st.stop()
        try:
            config = parse_config(config_text)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to parse JSON: {exc}")
            st.stop()

        errors = validate_config(config)
        if errors:
            st.error("Configuration has validation errors:")
            for err in errors:
                repo = err.get("repository") or "(global)"
                st.write(f"- **{repo}**: {err['message']}")
            st.stop()

        st.success("Configuration is valid.")

        # Preview effective flags per repository
        st.subheader("Effective flags per repository")
        default_flags = config.get("defaultSetupFlags", {})
        rows = []
        for repo_cfg in config.get("repositories", []):
            repo_name = repo_cfg.get("repository")
            repo_flags = repo_cfg.get("setupFlags", {})
            effective = resolve_flags(default_flags, repo_flags)
            row = {"repository": repo_name}
            row.update({k: effective[k] for k in FLAG_KEYS})
            rows.append(row)
        st.dataframe(rows, use_container_width=True)

        if st.button("Run setup & propagate"):
            with st.spinner("Running setup across repositories..."):
                results = run_all(config)

            st.subheader("Results")
            for res in results:
                st.markdown(f"### Repository: `{res['repository']}`")
                steps = res.get("steps", {})
                for step_name in ["labels", "secret", "enableAutoMerge", "workflows"]:
                    step = steps.get(step_name, {})
                    status = step.get("status")
                    st.write(f"**{step_name}**: `{status}`")
                    failed = step.get("failed")
                    manual_doc = step.get("manualDoc")
                    if step_name == "workflows" and step.get("pullRequestUrl"):
                        st.write(f"PR: {step['pullRequestUrl']}")
                    if failed:
                        st.warning(f"  - Error: {failed}")
                    if manual_doc and status == "failed":
                        st.info(f"  - See `{manual_doc}` for manual steps.")


if __name__ == "__main__":
    main()
