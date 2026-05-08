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

    # Simple description only (no User Guide button)
    st.markdown(
        "Bootstraps repositories for the cascade merge workflow by configuring labels, secrets, auto-merge, and cascade workflow PRs automatically."
    )

    st.subheader("Configuration JSON")

    # Input rules shown above the textbox on page load
    st.markdown(
        """
**Input configuration rules:**

- Must be valid JSON with a top-level `repositories` array.  
- Each item in `repositories` must be a JSON object.  
- Every object must have `repository: "owner/name"` (e.g. `CitInternal/172598.onb-vm-gbl.hnw-services`).  
- Every object must have a non-empty `patToken` string using a GitHub PAT that:
  - Has rights to manage labels, secrets, auto-merge, and PRs, and  
  - Has no expiration, so it can be used continuously by the cascade-merge workflow.
"""
    )

    default_config_text = load_default_config_text()
    config_text = st.text_area(
        "Paste configuration JSON here",
        value=default_config_text,
        height=260,
        help=(
            "Configuration includes a `repositories` list with `repository` and `patToken` fields. "
            "Use a PAT with no expiration and sufficient repo/admin scopes so labels, secrets, "
            "auto-merge, and PRs can be created."
        ),
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

        # Build table rows
        table_rows = []
        for res in results:
            repo_name = res.get("repository")
            steps = res.get("steps", {})

            # ----- Labels column -----
            labels_step = steps.get("labels", {})
            created = labels_step.get("createdLabels") or []
            existing = labels_step.get("existingLabels") or []
            missing = labels_step.get("missingLabels") or []

            label_lines = []

            if created:
                label_lines.append("**created**: " + ", ".join(created))
            if existing:
                label_lines.append("**existed**: " + ", ".join(existing))

            if missing or labels_step.get("status") == "failed":
                failed_values = missing if missing else []
                failed_str = ", ".join(failed_values) if failed_values else "unknown"
                label_lines.append(f"**failed**: {failed_str}")

            labels_cell = "<br>".join(label_lines) if label_lines else "-"

            # ----- Repository secret column -----
            secret_step = steps.get("secret", {})
            secret_status = secret_step.get("status")
            if secret_status == "failed":
                secret_cell = "FAILED"
            else:
                secret_cell = "SUCCESS"

            # ----- Enable Auto-Merge column -----
            auto_step = steps.get("enableAutoMerge", {})
            auto_status = auto_step.get("status")
            if auto_status == "failed":
                auto_cell = "FAILED"
            else:
                auto_cell = "SUCCESS"

            # ----- Workflow code column -----
            workflows_step = steps.get("workflows", {})
            wf_status = workflows_step.get("status")
            wf_url = workflows_step.get("pullRequestUrl")
            wf_state = workflows_step.get("pullRequestState")

            if wf_url and wf_state:
                wf_cell = f"PR [{wf_state}] = {wf_url}"
            elif wf_url:
                wf_cell = f"PR [OPEN] = {wf_url}"
            elif wf_status == "failed":
                wf_cell = "FAILED"
            else:
                wf_cell = "NA"

            table_rows.append(
                {
                    "Repository": repo_name,
                    "Labels": labels_cell,
                    "Repository secret": secret_cell,
                    "Enable Auto-Merge": auto_cell,
                    "Workflow code": wf_cell,
                }
            )

        st.subheader("Results")

        # Make markdown table text a bit smaller
        st.markdown(
            """
<style>
table {
    font-size: 0.9rem;
}
</style>
""",
            unsafe_allow_html=True,
        )

        # Render table as markdown with linked headers
        if table_rows:
            headers = [
                "Repository",
                "Labels Required for Cascading<br>[manual-create-labels](Docs/manual-create-labels.md)",
                "Repository secret for Cascading<br>[manual-create-secret](Docs/manual-create-secret.md)",
                "Enable Auto-Merge for Cascading<br>[manual-enable-auto-merge](Docs/manual-enable-auto-merge.md)",
                "Workflow Enabled for Cascading<br>[manual-setup-workflows](Docs/manual-setup-workflows.md)",
            ]
            header_line = "| " + " | ".join(headers) + " |"
            sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"

            lines = [header_line, sep_line]
            for row in table_rows:
                line_cells = [
                    str(row["Repository"] or ""),
                    str(row["Labels"] or ""),
                    str(row["Repository secret"] or ""),
                    str(row["Enable Auto-Merge"] or ""),
                    str(row["Workflow code"] or ""),
                ]
                lines.append("| " + " | ".join(line_cells) + " |")

            md_table = "\n".join(lines)
            st.markdown(md_table, unsafe_allow_html=True)


if __name__ == "__main__":
    main()