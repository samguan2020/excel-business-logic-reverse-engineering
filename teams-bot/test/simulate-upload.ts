/**
 * Simulates a Teams user sending an .xlsx attachment to the bot, without
 * needing attachment UI in the Agents Playground or a real Teams sideload.
 * This is a manual transport simulator, not an end-to-end assertion suite.
 *
 * What it does:
 *   1. Serves the given .xlsx file over local HTTP so the bot's
 *      `contentUrl` download step has something real to fetch.
 *   2. Starts a minimal mock Bot Framework "connector" endpoint
 *      (POST /v3/conversations/:id/activities) that just logs whatever the
 *      bot replies with (Adaptive Card, file-consent card, etc).
 *   3. POSTs a synthetic `message` Activity — with the xlsx as an
 *      attachment — directly to the bot's /api/messages endpoint.
 *
 * Usage:
 *   npx tsx test\simulate-upload.ts <path-to-xlsx> [botEndpoint]
 *
 * Requires the bot to be running with skipAuth (i.e. CLIENT_ID unset),
 * see ../README.md.
 */
import * as http from "http";
import * as fs from "fs";
import * as path from "path";

const FILE_SERVER_PORT = 5679;
const CONNECTOR_PORT = 5680;
const BOT_ENDPOINT = process.argv[3] ?? "http://localhost:3978/api/messages";

async function main() {
  const xlsxPath = process.argv[2];
  if (!xlsxPath) {
    console.error("Usage: tsx test\\simulate-upload.ts <path-to-xlsx> [botEndpoint]");
    process.exit(1);
  }
  const absPath = path.resolve(xlsxPath);
  const filename = path.basename(absPath);

  // 1. Static file server so the bot can download the attachment content.
  const fileServer = http.createServer((req, res) => {
    if (req.url === `/${filename}`) {
      res.writeHead(200, {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      fs.createReadStream(absPath).pipe(res);
    } else {
      res.writeHead(404);
      res.end();
    }
  });
  await new Promise<void>((resolve) => fileServer.listen(FILE_SERVER_PORT, resolve));
  console.log(`📎 Serving ${filename} at http://localhost:${FILE_SERVER_PORT}/${filename}`);

  // 2. Mock connector endpoint — logs whatever the bot replies with.
  const connector = http.createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      try {
        const activity = JSON.parse(body);
        console.log("\n🤖 Bot replied:");
        console.log(`   type: ${activity.type}`);
        if (activity.text) console.log(`   text: ${activity.text}`);
        if (activity.attachments) {
          for (const a of activity.attachments) {
            console.log(`   attachment: contentType=${a.contentType}${a.name ? `, name=${a.name}` : ""}`);
          }
        }
        console.log("   (full JSON below)");
        console.log(JSON.stringify(activity, null, 2));
      } catch {
        console.log("\n🤖 Bot replied with non-JSON body:", body);
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ id: String(Date.now()) }));
    });
  });
  await new Promise<void>((resolve) => connector.listen(CONNECTOR_PORT, resolve));
  console.log(`🔌 Mock connector listening at http://localhost:${CONNECTOR_PORT}`);

  // 3. Send the synthetic message activity with the xlsx attachment.
  const activity = {
    type: "message",
    id: `sim-${Date.now()}`,
    timestamp: new Date().toISOString(),
    serviceUrl: `http://localhost:${CONNECTOR_PORT}`,
    channelId: "test",
    from: { id: "sim-user-1", name: "Simulated User" },
    conversation: { id: "sim-convo-1", conversationType: "personal" },
    recipient: { id: "sim-bot-1", name: "Workbook Logic Analyst" },
    text: `Please analyze ${filename}`,
    attachments: [
      {
        name: filename,
        contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        contentUrl: `http://localhost:${FILE_SERVER_PORT}/${filename}`,
      },
    ],
  };

  console.log(`\n📨 Sending message with attachment to ${BOT_ENDPOINT} ...`);
  // NOTE: the bot doesn't send its HTTP response for /api/messages until the
  // *entire* handler finishes (including the multi-minute FastAPI analysis
  // call), so we must not block on this fetch with a short client timeout —
  // fire it and let the mock connector above capture replies as they arrive.
  fetch(BOT_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(activity),
  })
    .then((res) => console.log(`   bot endpoint responded HTTP ${res.status}`))
    .catch((err) => console.error("   bot endpoint request error:", err.message ?? err));

  console.log("\n⏳ Waiting for bot replies (this can take a few minutes)... Ctrl+C to stop.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
