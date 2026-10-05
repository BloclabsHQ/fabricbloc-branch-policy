# fabricbloc-verdict App setup (Cris)

Do this while Warden builds the branch-policy PR. Nothing goes live until the PR merges and MadAgentPM re-pins canon-agent-gates.

## 1. Create the App
1. Open https://github.com/settings/apps/new (or org: https://github.com/organizations/BloclabsHQ/settings/apps/new). Prefer the org App under BloclabsHQ.
2. Name: `fabricbloc-verdict`
3. Homepage URL: `https://github.com/BloclabsHQ/fabricbloc-branch-policy`
4. Webhook: uncheck Active (no webhook needed).
5. Permissions:
   - Repository → Issues: **Read & write** (for PR comments; GitHub uses the Issues API for PR comments)
   - Repository → Pull requests: **Read-only**
   - Repository → Metadata: **Read-only**
   - Everything else: **No access**
   - Especially: Contents = No access, Checks = No access, Administration = No access
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

## 5. Tell Warden
Reply with:
- App ID (number)
- Client ID
- Installation ID
- Bot login that will appear on comments (usually `fabricbloc-verdict[bot]`)
- Numeric bot user id (from `https://api.github.com/users/fabricbloc-verdict%5Bbot%5D` once the App has posted once, or from the App's "Bot user" link)

Warden will pin the bot login + numeric id into `rulesets/reviewers.json` before the PR goes live. If the bot has never posted, create a throwaway comment on a closed PR after install so the user id exists, then delete the comment.

## 6. Do not
- Do not give author bots (or every bot) the PEM.
- Do not grant Contents or Pull request write (approval) to this App. Approvals stay with fabricbloc-reviewer.
- Do not apply the org ruleset yourself until MadAgentPM asks with the final pin SHA.
