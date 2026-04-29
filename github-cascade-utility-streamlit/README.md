# GitHub Cascade Workflow Propagation Utility

This utility provides a local Streamlit UI to propagate workflow files into multiple GitHub repositories.

## Features
- JSON input for multiple repositories
- PAT token and Raise PR at repository level
- Detects target repository default branch automatically
- Creates a feature branch from the default branch latest commit SHA
- Pushes workflow files to `.github/workflows/`
- Optionally raises PR to the default branch
- Shows results in the UI

## Project structure
- `app.py` - Streamlit UI
- `propagator.py` - core GitHub propagation logic
- `requirements.txt` - dependencies
- `templates/workflows/` - workflow templates to copy into target repositories

## JSON input format
```json
{
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
```

## Setup
```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run
```bash
streamlit run app.py
```

## Important
Replace the placeholder template files with your actual final workflow YAML content:
- `templates/workflows/cascade-next-pr.yml`
- `templates/workflows/cascade-conflict-check.yml`
