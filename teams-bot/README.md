# Workbook Logic Analyst — Teams bot

A TypeScript front-end for the parent project's Excel reverse-engineering
pipeline. In a **personal (1:1) Teams chat**, upload an `.xlsx` workbook to
receive a summary and choose whether to upload its markdown report to your
OneDrive through Teams file consent. This is a prototype, not a production-ready
calculation or migration system.

## What the bot actually does

1. Selects the first attachment whose name ends in `.xlsx` and acknowledges it.
2. Downloads `content.downloadUrl`, falling back to `contentUrl`, into a local
   temporary file.
3. Sends multipart field `file` to `ANALYZE_API_URL` (`POST /analyze`).
   The API responds with HTTP 202 and `{ "job_id": "..." }`, **not** the report.
4. Polls `GET /analyze/{job_id}` every five seconds, with a ten-minute waiting
   ceiling and a thirty-second timeout per API request.
5. On `status: "done"`, reads `result.report_markdown` and `result.summary`
   (`filename`, `sheets`, `cell_count`, `authors`). Sends an Adaptive Card
   summary, followed by a file-consent card for `<workbook-name>-report.md`.
   `status: "error"` produces a failure message.
6. On `file.consent.accept`, uploads the cached report bytes to the
   Teams-provided `uploadUrl` and sends a confirmation. Declining removes the
   cached report. The downloaded workbook is deleted when analysis finishes.

Analysis runs in the separate Python/FastAPI service (`..\api\server.py`),
not in the bot. The bot itself does not call a model.

## SDK and licensing

`package.json` and `package-lock.json` pin **`@microsoft/teams.apps` and
`@microsoft/teams.cards` to 2.0.5**. They use the server-side Microsoft Teams
SDK v2: `App` and typed event routes. This is not the legacy `botbuilder`
Bot Framework SDK and not the browser-side TeamsJS SDK (`@microsoft/teams-js`).
Bot Framework-compatible activities and file-consent schemas remain part of
the Teams transport; using those schemas does not mean this app uses
`botbuilder`.

The JavaScript/TypeScript Teams SDK is open source under the **MIT License**:
see the upstream [version-tagged license](https://github.com/microsoft/teams.ts/blob/v2.0.5/LICENSE)
and published 2.0.5 package metadata for
[`teams.apps`](https://unpkg.com/@microsoft/teams.apps@2.0.5/package.json) and
[`teams.cards`](https://unpkg.com/@microsoft/teams.cards@2.0.5/package.json).
The lockfile also records `license: "MIT"` for both pinned SDK packages.
Retain applicable upstream notices when redistributing dependencies.
This SDK license does **not** make the Microsoft Teams service open source or
grant Teams/Microsoft 365 accounts, tenant access, subscriptions, or cloud usage.
Other dependencies have their own licenses; no license for this project's
application code is asserted here.

## Local setup

Use Node.js **20 or newer** (the pinned SDK requires Node 20+).
Set up the parent project's Python environment and chosen analysis backend
first; see the parent README. From the parent project directory:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn api.server:app --host 127.0.0.1 --port 8000
```

In a separate terminal, from `teams-bot`:

```powershell
Copy-Item .env.example .env
npm ci
npm run build
npx --no-install tsc --noEmit
npm run dev
```

Leave `CLIENT_ID`, `CLIENT_SECRET`, and `TENANT_ID` blank for local simulation.
`ANALYZE_API_URL` defaults to `http://127.0.0.1:8000/analyze`; `PORT` defaults
to `3978`. The bot listens for activities at `/api/messages`.

**Warning:** an unset/empty `CLIENT_ID` automatically enables `skipAuth`.
Keep this mode isolated to local testing; never expose it through a public
tunnel or production endpoint. Credentials belong in a private environment,
not in the manifest, source, logs, or committed `.env` files.

## Local testing versus end-to-end testing

The optional Microsoft 365 Agents Playground can exercise local messages
without a Teams tenant or bot registration, if installed separately:

```powershell
agentsplayground -e http://localhost:3978/api/messages -c msteams
```

Do not assume the Playground reproduces Teams attachment and OneDrive consent
behavior. For attachment transport, the included manual simulator serves a
workbook and mock connector on ports 5679 and 5680:

```powershell
npx --no-install tsx test\simulate-upload.ts ..\sample\business_planning_sample.xlsx
```

Generate that synthetic workbook using the parent README first, or supply
another non-sensitive local `.xlsx` path. Start the bot and analysis API
separately. The simulator sends a synthetic activity, prints bot replies,
and waits until stopped with Ctrl+C. It has **no assertions**, does **not**
simulate file-consent acceptance/upload, and still invokes the real analysis
API (and therefore its configured model). Do not run it when model calls
are unwanted.

Build and type checks are offline code checks after dependencies are installed;
they are not proof of successful Teams authentication, file upload, backend
analysis, or end-to-end deployment. No automatic test suite is configured.

## Real Teams configuration

`appPackage\manifest.json` is an **unresolved template**, not a deployable
manifest and not an existing app registration. Before packaging, supply:

| Placeholder | Required value |
| --- | --- |
| `${{TEAMS_APP_ID}}` | Your Teams application ID |
| `${{BOT_ID}}` | Your registered bot's application/client ID |
| `${{BOT_DOMAIN}}` | Your reachable bot hostname, without a URL scheme or path |
| `${{DEVELOPER_NAME}}` | Your publisher name |
| `${{WEBSITE_URL}}` | Your actual HTTPS website |
| `${{PRIVACY_URL}}` | Your actual HTTPS privacy notice |
| `${{TERMS_OF_USE_URL}}` | Your actual HTTPS terms |

There is no placeholder substitution/provisioning script in this project.
Resolve a **copy** of the template under the ignored `appPackage\build`
directory, validate it, and package the resolved manifest and the two PNG
icons at the root of a ZIP. Do not include credentials. Actual Teams testing
also requires a permitted Microsoft 365/Teams account and tenant, a bot
registration with the Teams channel enabled, an HTTPS messaging endpoint
ending in `/api/messages`, and matching `CLIENT_ID`, `CLIENT_SECRET`, and
`TENANT_ID` configuration. These resources are not included or provisioned.

The template keeps `scopes: ["personal"]` and `supportsFiles: true`.
Microsoft documents file-consent APIs as personal-chat-only; see
[Send and receive files](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/bots-filesv4).
Validate authentication and the complete accept/decline/OneDrive upload flow
in real Teams before claiming end-to-end support.

## Existing limitations

- Reports are cached only in memory, without persistence or expiry cleanup.
  Restarting loses pending reports; multiple instances cannot share them.
- The analysis API is asynchronous, but the bot's activity handler still waits
  for polling to finish. There is no durable background queue, retry policy,
  cancellation, or restart recovery.
- Attachment selection checks only the filename extension. Download size,
  URL restrictions, malware scanning, and production data-access controls
  are not implemented by this bot.
- File-consent byte-size metadata uses JavaScript string length, which can
  differ from UTF-8 byte length for non-ASCII reports.
- The backend URL has no bot-to-API authentication configuration here. Keep
  the backend isolated; production authentication/rate limiting requires
  additional work.
- Bot and simulator logs may contain filenames, report metadata, download
  URLs, or error payloads. Treat them as sensitive; do not publish them.
- Generated analysis needs human verification against workbook formulas and
  business requirements. Use synthetic workbooks until data handling and
  model-service permissions are independently reviewed.

`node_modules`, `dist`, local environments, credentials, logs, runtime data,
and app ZIPs are excluded by the local ignore rules. The supplied icons are
generic letter-X artwork, not a service or publisher endorsement.
