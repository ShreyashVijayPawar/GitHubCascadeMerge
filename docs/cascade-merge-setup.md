# Cascade Merge Setup

## Supported branch pattern
release/{app}_{version}-{anything_optional}

Examples:
- release/test_1.50-01_01_2026_deploy
- release/test_2.00-01_02_2026
- release/sample_3.51-anything

## Rules
- Only branches with version in X.YY format are included.
- Branches are ordered only by version number.
- App names are isolated from each other.
- Only the immediate next cascade PR is created.
- If the cascade PR has conflicts, the cascade stops.
- After that cascade PR is merged, the next downstream PR is created automatically.

## Required labels
- cascade-pr
- cascade-conflict

## Required secret
CASCADE_GITHUB_TOKEN