from pathlib import Path

import streamlit as st

from propagator import parse_config, validate_config, run_all


def load_default_config_text() -> str:
    example_path = Path("examples/input.json")
    if example_path.exists():
        return example_path.read_text(encoding="utf-8")
    return ""


def main() -> None:
    st.set_page_config(page_title="Cascade Workflow Bootstrapper", layout="wide")
    st.title("Cascade Workflow Bootstrapper")

    st.markdown(
        """This utility bootstraps repositories for the cascade merge workflow by:

- Ensuring standard cascade labels exist.
- Creating the `CASCADE_GITHUB_TOKEN` secret if missing.
- Enabling repository-level auto-merge.
- Creating a feature branch, updating workflow files, and opening a PR.
"""
    )

    st.subheader("1. Configuration JSON")

    default_config_text = load_default_config_text()
    config_text = st.text_area(
        "Paste configuration JSON here",
        value=default_config_text,
        height=260,
        help="Configuration includes a `repositories` list with `repository` and `patToken` fields.",
    )

    # Single button: validate + run
    run_clicked = st.button("Run setup & propagate")

    if run_clicked:
        # Basic presence check
        if not config_text.strip():
            st.error("Configuration JSON is required.")
            return

        # Parse JSON
        try:
            config = parse_config(config_text)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to parse JSON: {exc}")
            return

        # Validate config
        errors = validate_config(config)
        if errors:
            st.error("Configuration has validation errors:")
            for err in errors:
                repo = err.get("repository") or "(global)"
                st.write(f"- **{repo}**: {err['message']}")
            return

        # If validation passes, run setup
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

                # Extra indentation for labels
                if step_name == "labels":
                    created = step.get("createdLabels") or []
                    existing = step.get("existingLabels") or []
                    missing = step.get("missingLabels") or []

                    if created:
                        st.write(f"  **Created:** {', '.join(created)}")
                    if existing:
                        st.write(f"  **Already existed:** {', '.join(existing)}")
                    if missing:
                        st.write(
                            f"  **Missing (create manually by referring to documentation):** {', '.join(missing)}"
                        )

                # Extra info for workflows PR
                if step_name == "workflows" and step.get("pullRequestUrl"):
                    st.write(f"  PR: {step['pullRequestUrl']}")

                failed = step.get("failed")
                manual_doc = step.get("manualDoc")
                if failed:
                    st.warning(f"- Error: {failed}")
                if manual_doc and status == "failed":
                    st.info(f"- See `{manual_doc}` for manual steps.")


if __name__ == "__main__":
    main()