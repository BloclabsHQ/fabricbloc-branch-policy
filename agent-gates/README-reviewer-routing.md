# Reviewer routing and App auto-approve (PR-C)

Canon: `rulesets/reviewers.json` and `rulesets/gate-owners.json` loaded from `fabricbloc-branch-policy` at **`pins.agent_gates_sha`** (never the PR head). See `docs/REVIEWER-IDENTITY.md` and **`docs/owner-approved-agent-gates.md`** (AG-06). **Bots never count as reviewers** except **`fabricbloc-reviewer[bot]`** / **337673700** or a non-author human (`DECISIONS.md` **14**, `docs/GOV-bots-never-count-as-reviewers.md`). **AG-06** owner label is an explicit carve-out (**DECISIONS #16**).

## Auto-approve

**fabricbloc-verdict** posts PR **comments** (Issues API; App needs **Issues** and **Pull requests: Read & write** — PR comment create returns **403** with Issues-only write). **fabricbloc-reviewer** (App **5185203**, bot **337673700**) submits the GitHub **APPROVE** after the gate validates verdicts or deterministic allowlist rules. An **APPROVE** from **fabricbloc-verdict[bot]** never satisfies review-of-record (only PASS comment markers do).

**Two-tier agent-denied-paths**

- **Cris-only** — check **fails** (workflows, engine code/manifests/approval_relay, GOV-* ADRs, rulesets, canon files, floor/manifest entries, unsafe paths).
- **Verdict-eligible** — check **passes** with a notice; **review-of-record** needs PASS markers from **fabricbloc-verdict[bot]** for every required reviewer slug.

**fabricbloc-reviewer** may submit APPROVE when:

- Newest **`agent-denied-paths`** run from GitHub Actions **app id 15368** is **success** on head,
- No **Cris-only** paths in the diff (including `previous_filename` on renames),
- **Verdict path** (`verdict_approval_enabled: true`): every required reviewer has an unedited, unfenced PASS at head from **`verdict_app`** (**fabricbloc-verdict[bot]** / **337980250**; both must match). Any slug FAIL at head blocks approval. **`user_id: 0` fails closed** if ever reintroduced,
- **Deterministic** path (unchanged): pure allowlisted docs/fixtures under pinned extension policy, no routes/exclusions/Cris-only/verdict-eligible paths,
- No **cris_required** route, and
- **`agent-review-of-record`** job (`pull_request`): exact-head APPROVE gate only — no secrets.
- **`reviewer-app-auto-approve`** job (`pull_request_target`, env **`reviewer`**): mint + App APPROVE (missing env PEM → skip with notice; no repo/org fallback). Env deployment rules: **`main` only** — **must not** match `refs/pull/*` (Q14 alone is not enough while cursor[bot] pushes).

### Mint timing and org-required workflows

Org **required workflows** (canon-agent-gates) run only on **`pull_request`**, **`pull_request_target`**, and **`merge_group`**. They do **not** run on **`issue_comment`**, so a **fabricbloc-verdict** PASS comment alone never starts mint on fabricbloc.

On each **`pull_request_target`** mint run, the gate **polls** (shared **240s** job budget) for **agent-denied-paths** success on head, then submits **fabricbloc-reviewer** APPROVE if verdict/deterministic rules pass and the App has not already APPROVED that head.

If verdicts land **after** mint already finished without approving, mint runs again on the next **`pull_request_target`** event (`synchronize`, `reopened`, `edited`, or **`owner-approved`** label). Otherwise re-run the mint job manually (`gh run rerun --job <id>`).

**Follow-up (Cris-gated):** a verdict posted after mint finished still does **not** start mint on fabricbloc today. The **fabricbloc-verdict** App has **Issues** and **Pull requests** write only (no **Actions** / **Checks**). Re-running **`reviewer-app-auto-approve`** from the verdict poster needs **`actions:write`** (or an equivalent workflow-dispatch path) on that App — not added in this change. Until then, use **`pull_request_target`** re-fire or manual mint job re-run.

## Routing (priority)

Highest **`priority`** route wins: cris (prod/IAM/secrets) → sentinel (auth/crypto, `src/auth`, fabric-wallet) → warden (policy/workflows) → aether (iac/infra) → default **madagentpm**.

## Verdict markers

Only **fabricbloc-verdict[bot]** (pinned in **`verdict_app`**) may post markers. Reviewer slug must be one of **`madagentpm`**, **`sentinel`**, **`aether`**, **`warden`**. **`head`** must equal the PR head SHA (40 hex). Edited comments and fenced code blocks are ignored.

```html
<!-- fabricbloc-verdict v1 reviewer=madagentpm verdict=PASS head=<40-char PR head SHA> -->
```

Required slugs: **`madagentpm`** always; route reviewer from `reviewers.json`; plus **`aether`** (+ **`sentinel`** when sensitive) for non-GOV ADRs; **`sentinel`** for verdict-eligible engine tests/docs.

Human GOV-0022 PRs still skip agent gates (F6-D2/D3).

## CI consumer opt-in (AG-03)

An enabled `ci_review` consumer in the pinned `rulesets/reviewers.json` must name
its `repository` and a `required_opt_in_label` (1 to 50 characters, no surrounding
whitespace or control characters). No label or consumer is selected by this change.
An absent or explicitly disabled CI consumer preserves the existing non-CI route;
an enabled consumer only changes the named repository.

For that repository, missing configuration or an absent label selects human review.
The gate checks the live PR before automation, when evaluating verdict evidence,
immediately before App approval, and when deciding whether an existing App approval
still counts. This covers removal at the same head when the gate is evaluated again.
Independent human approval and the existing AG-06 owner path remain available.
The label grants neither task authority nor protected-change or merge permission.

Installation requires merging and pinning the gate revision through the existing
owner procedure, then admitting the CI consumer with the same label as its worker.
The merge controller must call the published `ci_review_opt_in_allowed(config, pr)`
against a freshly read PR before relying on App approval. It must retain the other
current-head, identity and authority checks. Do not enable the consumer until that
merge-time integration and a same-head label-removal drill pass.

A green check is historical evidence. GitHub organization-required workflows ignore
activity-type filters and do not rerun simply because a label changes; adding
`labeled` or `unlabeled` to YAML does not close this gap. See
[GitHub's required-workflow event rules](https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).
This source change does not re-pin rulesets, install the merge controller integration,
dismiss existing reviews, activate a consumer or guarantee revocation between the
last API read and GitHub's merge operation.
