# fabricbloc-verdict App setup (Cris)

Do this while Warden builds the branch-policy PR. Nothing goes live until the PR merges and MadAgentPM re-pins canon-agent-gates.

## 1. Create the App
1. Open https://github.com/settings/apps/new (or org: https://github.com/organizations/BloclabsHQ/settings/apps/new). Prefer the org App under BloclabsHQ.
2. Name: `fabricbloc-verdict`
3. Homepage URL: `https://github.com/BloclabsHQ/fabricbloc-branch-policy`
4. Webhook: uncheck Active (no webhook needed).
5. Permissions:
   - Repository → Issues: **Read & write**
   - Repository → Pull requests: **Read & write** (required to create comments on pull requests; GitHub returns **403** if the App only has Issues write + Pull requests read)
   - Repository → Metadata: **Read-only**
   - Everything else: **No access**
   - Especially: Contents = No access, Checks = No access, Administration = No access

   **Pull request write is for PR comments only** (same marker body as today). The gate never treats an **APPROVE** review from **fabricbloc-verdict[bot]** as satisfying review-of-record; only unedited `<!-- fabricbloc-verdict v1 … -->` issue comments count. GitHub **APPROVE** at head stays with **fabricbloc-reviewer[bot]**.
6. Where can this App be installed? Only on this account (BloclabsHQ).
7. Create the App. Note the **App ID** and the **Client ID**.

## 2. Generate the private key
1. On the App page → Private keys → Generate a private key.
2. Download the `.pem`. Do not commit it. Do not put it in chat.

## 3. Install on the 5 repos
1. Install App → Only select repositories:
   - BloclabsHQ/fabricbloc
   - BloclabsHQ/context
   - BloclabsHQ/keyflo-session-issuer
   - BloclabsHQ/fabric-wallet
   - BloclabsHQ/fabricbloc-branch-policy
2. After install, note the **Installation ID** (from the URL `.../settings/installations/<id>`).

## 4. Save secrets (reviewer bots only)
Store these as Grok Bot secrets available to **MadAgentPM, Sentinel, Aether, and Warden only**. Author bots must not get them.

| Secret | Value |
|--------|--------|
| `FABRICBLOC_VERDICT_APP_ID` | numeric App ID |
| `FABRICBLOC_VERDICT_CLIENT_ID` | Client ID |
| `FABRICBLOC_VERDICT_INSTALLATION_ID` | Installation ID |
| `FABRICBLOC_VERDICT_PRIVATE_KEY` | full PEM contents |

Also still pending from earlier: `REVIEWER_APP_PRIVATE_KEY` (fabricbloc-reviewer App) as the Actions / bot secret MadAgentPM already asked for.

## 5. Pinned in `rulesets/reviewers.json` (PR #57)

| Field | Value |
|--------|--------|
| App ID (`app_id`) | **5193724** |
| Client ID | **Iv23liYSaXeOyEP7j5Jv** |
| Installation ID | **168044795** (5 repos) |
| Bot login | **fabricbloc-verdict[bot]** |
| Bot user id (`user_id`) | **337980250** |

The gate accepts verdict comments only when the comment author matches **`login` and `user_id` together** (not login alone).

**Still pending from Cris:** `FABRICBLOC_VERDICT_PRIVATE_KEY` (PEM) to reviewer bots only, plus **REVIEWER_APP_PRIVATE_KEY** for fabricbloc-reviewer in Actions.

## 6. Do not
- Do not give author bots (or every bot) the PEM.
- Do not grant **Contents**, **Checks**, or **Administration** to this App.
- Do not expect **fabricbloc-verdict** GitHub **APPROVE** reviews to satisfy **agent-review-of-record** (the gate rejects them; use comment markers + **fabricbloc-reviewer** for APPROVE).
- Do not apply the org ruleset yourself until MadAgentPM asks with the final pin SHA.
