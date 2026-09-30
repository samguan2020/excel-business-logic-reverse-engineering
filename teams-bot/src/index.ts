/**
 * Teams bot front-end for finance workbook reverse engineering.
 *
 * Flow:
 *   1. User uploads an .xlsx file to the bot in a Teams 1:1 chat.
 *   2. We ack immediately ("Analyzing...") since the pipeline can take minutes.
 *   3. We download the attachment and POST it to the FastAPI wrapper
 *      (api/server.py) around the existing Python LangGraph pipeline.
 *   4. We reply with an Adaptive Card summary (sheets, cell count, authors).
 *   5. We offer the full markdown report via a Teams "file consent" card so
 *      the user can accept/decline the bot uploading report.md to the chat.
 *
 * NOTE: This is a local-development prototype. The
 * file-consent upload flow uses the Teams file consent
 * card schema (`application/vnd.microsoft.teams.card.file.consent`) plus the
 * `fileConsent/invoke` activity, routed by the Teams SDK to
 * `file.consent.accept` and `file.consent.decline`.
 */
import "dotenv/config";
import { App } from "@microsoft/teams.apps";
import type { IAdaptiveCard } from "@microsoft/teams.cards";
import axios from "axios";
import FormData from "form-data";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

const ANALYZE_API_URL = process.env.ANALYZE_API_URL ?? "http://127.0.0.1:8000/analyze";

// In-memory cache of generated reports, keyed by a random id, so the
// file-consent accept handler can find the bytes to upload. Fine for local
// dev; swap for real storage before any shared/production deployment.
const pendingReports = new Map<string, { filename: string; markdown: string }>();

const app = new App({
  // SDK also auto-reads CLIENT_ID / CLIENT_SECRET / TENANT_ID from env vars.
  clientId: process.env.CLIENT_ID,
  clientSecret: process.env.CLIENT_SECRET,
  tenantId: process.env.TENANT_ID,
  // Only for local testing with the Microsoft 365 Agents Playground, which
  // sends unauthenticated requests (no Bot Framework JWT). Never enable this
  // in production — it disables inbound request authentication. Leave
  // CLIENT_ID unset locally to use the Playground; set it for real Azure
  // Bot / Teams sideload testing.
  skipAuth: !process.env.CLIENT_ID,
});

app.on("install.add", async ({ send }) => {
  await send(
    "👋 Hi! Send me an Excel workbook (.xlsx) and I'll reverse-engineer its " +
      "business logic into a readable report — sheet-by-sheet documentation, " +
      "dependency analysis, and migration recommendations."
  );
});

app.on("message", async ({ activity, send }) => {
  const attachment = (activity.attachments ?? []).find((a) =>
    (a.name ?? "").toLowerCase().endsWith(".xlsx")
  );

  if (!attachment) {
    await send(
      "Please attach an .xlsx workbook and I'll analyze it. " +
        "(Drag & drop or use the paperclip icon in Teams.)"
    );
    return;
  }

  await send(`📊 Got **${attachment.name}** — analyzing now, this can take a few minutes...`);

  let tmpFile: string | undefined;
  try {
    // Prefer the pre-authorized `content.downloadUrl` (no auth needed) over
    // `contentUrl`, which for Teams file uploads is a SharePoint/OneDrive
    // sharing link that requires interactive user auth and returns 403 for
    // a plain anonymous GET.
    const downloadUrl = (attachment.content as { downloadUrl?: string } | undefined)?.downloadUrl ?? attachment.contentUrl!;
    tmpFile = await downloadAttachment(downloadUrl, attachment.name!);

    const form = new FormData();
    form.append("file", fs.createReadStream(tmpFile), attachment.name);

    // The pipeline can take several minutes (multiple sequential LLM calls
    // per sheet), which exceeds Azure Container Apps' hard 240s ingress
    // request timeout. So /analyze returns a job_id immediately and we poll
    // /analyze/{job_id} — each poll is a fast, cheap call that never risks
    // hitting that platform timeout.
    const submitResponse = await axios.post(ANALYZE_API_URL, form, {
      headers: form.getHeaders(),
      maxBodyLength: Infinity,
      maxContentLength: Infinity,
      timeout: 30 * 1000,
    });
    const jobId = (submitResponse.data as { job_id: string }).job_id;

    const statusUrl = `${ANALYZE_API_URL}/${jobId}`;
    const pollIntervalMs = 5 * 1000;
    const maxWaitMs = 10 * 60 * 1000; // 10 min ceiling
    const deadline = Date.now() + maxWaitMs;

    let report_markdown: string;
    let summary: { filename: string; sheets: string[]; cell_count: number; authors: string[] };
    for (;;) {
      const statusResponse = await axios.get(statusUrl, { timeout: 30 * 1000 });
      const job = statusResponse.data as {
        status: "running" | "done" | "error";
        error?: string;
        result?: {
          report_markdown: string;
          summary: { filename: string; sheets: string[]; cell_count: number; authors: string[] };
        };
      };

      if (job.status === "done" && job.result) {
        ({ report_markdown, summary } = job.result);
        break;
      }
      if (job.status === "error") {
        throw new Error(job.error ?? "Analysis job failed.");
      }
      if (Date.now() > deadline) {
        throw new Error("stream timeout");
      }
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }
    const reportMarkdown = report_markdown;

    const reportId = cryptoRandomId();
    pendingReports.set(reportId, {
      filename: `${path.parse(attachment.name!).name}-report.md`,
      markdown: reportMarkdown,
    });

    await send(buildSummaryCard(summary));
    await send(buildFileConsentActivity(reportId, `${path.parse(attachment.name!).name}-report.md`, reportMarkdown.length));
  } catch (err: any) {
    console.error("Analysis failed:", err?.response?.data ?? err);
    await send(
      "❌ Sorry, something went wrong analyzing that workbook. " +
        "Check the bot server logs (and confirm the FastAPI service at " +
        `${ANALYZE_API_URL} is running).`
    );
  } finally {
    if (tmpFile) fs.promises.unlink(tmpFile).catch(() => {});
  }
});

// Handle the user's response to the file-consent card (accept/decline).
// NOTE: the SDK routes file-consent invokes to `file.consent.accept` /
// `file.consent.decline` (activity.name === "fileConsent/invoke"), NOT
// "message.submit" — that event never fires for these cards.
app.on("file.consent.accept", async ({ activity, send }) => {
  const value = activity.value as { context?: { reportId?: string }; uploadInfo?: { uploadUrl?: string; contentUrl?: string } };
  const reportId = value.context?.reportId;
  const pending = reportId ? pendingReports.get(reportId) : undefined;

  if (!pending) {
    await send("That report has expired — please re-upload the workbook.");
    return;
  }

  const uploadInfo = value.uploadInfo;
  if (uploadInfo?.uploadUrl) {
    await axios.put(uploadInfo.uploadUrl, Buffer.from(pending.markdown, "utf-8"), {
      headers: {
        "Content-Type": "text/plain",
        "Content-Range": `bytes 0-${Buffer.byteLength(pending.markdown) - 1}/${Buffer.byteLength(
          pending.markdown
        )}`,
      },
    });
    await send(`✅ Uploaded **${pending.filename}**.`);
  }
  if (reportId) pendingReports.delete(reportId);
});

app.on("file.consent.decline", async ({ activity, send }) => {
  const value = activity.value as { context?: { reportId?: string } };
  const reportId = value.context?.reportId;
  await send("No problem — let me know if you'd like the full report later.");
  if (reportId) pendingReports.delete(reportId);
});


async function downloadAttachment(contentUrl: string, filename: string): Promise<string> {
  const response = await axios.get(contentUrl, { responseType: "arraybuffer" });
  const buf = Buffer.from(response.data);
  console.log(
    "downloadAttachment debug:",
    "status=", response.status,
    "content-type=", response.headers["content-type"],
    "bytes=", buf.length,
    "magic=", buf.subarray(0, 4).toString("hex")
  );
  const tmpPath = path.join(os.tmpdir(), `teams-upload-${Date.now()}-${filename}`);
  await fs.promises.writeFile(tmpPath, buf);
  return tmpPath;
}

function buildSummaryCard(summary: {
  filename: string;
  sheets: string[];
  cell_count: number;
  authors: string[];
}): IAdaptiveCard {
  return {
    type: "AdaptiveCard" as const,
    body: [
      { type: "TextBlock", text: "📈 Workbook Analysis Complete", weight: "Bolder", size: "Medium" },
      { type: "TextBlock", text: summary.filename, isSubtle: true, wrap: true },
      {
        type: "FactSet",
        facts: [
          { title: "Sheets", value: summary.sheets.join(", ") },
          { title: "Cells analyzed", value: String(summary.cell_count) },
          { title: "Known authors", value: summary.authors.join(", ") || "None found" },
        ],
      },
      {
        type: "TextBlock",
        text: "Full documentation, dependency analysis, and migration recommendations are in the attached report.",
        wrap: true,
      },
    ],
  } as IAdaptiveCard;
}

function buildFileConsentActivity(reportId: string, filename: string, sizeInBytes: number) {
  return {
    type: "message" as const,
    attachments: [
      {
        contentType: "application/vnd.microsoft.teams.card.file.consent",
        name: filename,
        content: {
          description: "Full markdown analysis report",
          sizeInBytes,
          acceptContext: { type: "fileUpload", reportId },
          declineContext: { type: "fileDecline", reportId },
        },
      },
    ],
  };
}

function cryptoRandomId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

const port = Number(process.env.PORT ?? 3978);
app.start(port).then(() => {
  console.log(`Finance Workbook Analyst Teams bot listening on port ${port} 🚀`);
});
