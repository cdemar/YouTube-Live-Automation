/**
 * LAMBDA INTEGRATION — receives viewer counts from the YT automation Lambda
 * =========================================================================
 * This file adds a doPost() endpoint. When deployed as a Web App, Lambda
 * can POST its viewer counts here after its existing Wednesday/Tuesday run,
 * and they get logged through the exact same logAttendance() function the
 * form uses — so bucketing and duplicate-detection logic only exists once.
 *
 * Only handles the 4 Lambda-automated congregations. Cantonese, SJ Joint,
 * WG Joint, and the no-YT congregations are NOT touched by this endpoint —
 * those stay on the manual form path, as decided.
 */

// ══════════════════════════════════════════════════════════════════════════
// CONFIG
// ══════════════════════════════════════════════════════════════════════════

// Maps Lambda's internal channel keys (from CHANNELS dict in handler.py)
// to the full congregation names used in the Raw Log / CONGREGATIONS list.
const CHANNEL_TO_CONGREGATION = {
  "ms_channel": "SJ Mandarin",
  "es_channel": "SJ English",
  "es2_channel": "WG English",
  "ss_channel": "WG Spanish (Nueva Vida)",
};

// Shared secret — Lambda must send this in its POST body so random internet
// traffic can't write fake data into your sheet just by finding the URL.
// Generate any random string and put the SAME string in a Lambda env var
// called SHEET_WEBAPP_SECRET. Treat it like a password.
//
// This is a placeholder — the real value lives only in the live Apps Script
// project attached to the Sheet, never committed here. Replace this before
// deploying your own copy.
const WEBAPP_SHARED_SECRET = "REPLACE_WITH_YOUR_OWN_RANDOM_SECRET_STRING";


// ══════════════════════════════════════════════════════════════════════════
// doPost — entry point for the Web App
// ══════════════════════════════════════════════════════════════════════════

/**
 * Expects a POST body shaped like:
 * {
 *   "secret": "the shared secret string",
 *   "results": [
 *     { "channel": "ms_channel", "date": "2026-07-05", "viewers": 42 },
 *     { "channel": "es_channel", "date": "2026-07-05", "viewers": 118 },
 *     ...
 *   ]
 * }
 *
 * "date" should be the Sunday the viewer count is FOR (Lambda already
 * calculates this as last_sunday) — but we still run it through
 * getWeekStart() for safety, in case Lambda ever sends a non-Sunday date.
 */
function doPost(e) {
  let payload;

  try {
    payload = JSON.parse(e.postData.contents);
  } catch (err) {
    return jsonResponse({ status: "error", message: "Invalid JSON body" });
  }

  if (payload.secret !== WEBAPP_SHARED_SECRET) {
    return jsonResponse({ status: "error", message: "Unauthorized" });
  }

  if (!Array.isArray(payload.results)) {
    return jsonResponse({ status: "error", message: "Missing or invalid 'results' array" });
  }

  const outcomes = [];

  for (let i = 0; i < payload.results.length; i++) {
    const item = payload.results[i];
    const congregation = CHANNEL_TO_CONGREGATION[item.channel];

    if (!congregation) {
      outcomes.push({
        channel: item.channel,
        status: "skipped",
        reason: "Unrecognized or unmapped channel key",
      });
      continue;
    }

    if (item.viewers === undefined || item.viewers === null) {
      outcomes.push({
        channel: item.channel,
        status: "skipped",
        reason: "No viewer count provided",
      });
      continue;
    }

    try {
      const weekStart = getWeekStart(new Date(item.date));

      const result = logAttendance(
        weekStart,
        congregation,
        "YT",
        item.viewers,
        "lambda",
        "", // no submitter email for Lambda-sourced rows
        item.notes || ""
      );

      outcomes.push({
        channel: item.channel,
        congregation: congregation,
        status: result.status,
        row: result.row,
      });
    } catch (err) {
      outcomes.push({
        channel: item.channel,
        congregation: congregation,
        status: "error",
        reason: err.message,
      });
    }
  }

  return jsonResponse({ status: "ok", outcomes: outcomes });
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Optional — run this manually from the Apps Script editor to test the
 * endpoint logic without needing Lambda at all. Check the Raw Log tab
 * and the Logger output afterward.
 */
function testDoPost() {
  const fakeEvent = {
    postData: {
      contents: JSON.stringify({
        secret: WEBAPP_SHARED_SECRET,
        results: [
          { channel: "ms_channel", date: "2026-07-05", viewers: 25 },
          { channel: "es_channel", date: "2026-07-05", viewers: 140 },
          { channel: "es2_channel", date: "2026-07-05", viewers: 60 },
          { channel: "ss_channel", date: "2026-07-05", viewers: 15 },
        ],
      }),
    },
  };

  const response = doPost(fakeEvent);
  Logger.log(response.getContent());
}
