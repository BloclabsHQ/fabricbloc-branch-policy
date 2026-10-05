# Reviewer routing and App auto-approve (PR-C)

Canon: `rulesets/reviewers.json` (loaded from `fabricbloc-branch-policy` @ `main` at runtime).

## Trust model (verdict markers)

Only **`madgeniusblink`** and **`cursoragent`** may post a PASS verdict comment:

```html
<!-- fb-verdict: PASS reviewer=sentinel sha=<40-char PR head SHA> -->
```

The marker must match the **current PR head**. On match, **fabricbloc-reviewer** (App **5185203**, bot **337673700**) submits an APPROVE when `REVIEWER_APP_TOKEN` is available. Without the App private key secret, the gate **skips** App approval and logs a clear notice (no fail solely for missing key).

**`cris_required`** routes (prod/IAM/secrets classes) never receive App auto-approval.

Human GOV-0022 PRs still skip agent gates (F6-D2/D3).

## Agent merge flow

After gates and CI pass, enable GitHub auto-merge when opening the PR:

```bash
gh pr merge --auto --squash
```

Requires repo **Allow auto-merge** (Cris / MadAgentPM).
