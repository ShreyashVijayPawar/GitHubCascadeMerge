import json

import streamlit as st

from propagator import propagate_batch

st.set_page_config(page_title="GitHub Cascade Workflow Utility", layout="wide")

st.title("GitHub Cascade Workflow Propagation Utility")
st.write("Paste repository-level JSON input, run propagation, and review results here.")

sample_json = {
    "repositories": [
        {
            "repositoryUrl": "https://github.com/owner/repo-one",
            "patToken": "github_pat_xxx_1",
            "raisePr": "Y"
        },
        {
            "repositoryUrl": "https://github.com/owner/repo-two",
            "patToken": "github_pat_xxx_2",
            "raisePr": "N"
        }
    ]
}

with st.expander("Sample input JSON", expanded=False):
    st.json(sample_json)

branch_prefix = st.text_input("Feature branch prefix", value="feature/add-cascade-workflows")
input_json = st.text_area(
    "Repository input JSON",
    value=json.dumps(sample_json, indent=2),
    height=300,
)

if st.button("Run propagation", type="primary"):
    try:
        payload = json.loads(input_json)
        results = propagate_batch(payload, branch_prefix=branch_prefix)

        st.subheader("Results")
        st.dataframe(results, use_container_width=True)

        st.subheader("Detailed JSON")
        st.json(results)
    except Exception as exc:
        st.error(f"Operation failed: {exc}")
