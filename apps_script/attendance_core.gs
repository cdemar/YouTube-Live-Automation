/**
 * SJCAC ATTENDANCE TRACKER — CORE LOGIC
 * =====================================
 * This file contains:
 *   1. Configuration (sheet name, congregation list, column layout)
 *   2. Raw log setup (run once to create the tab + headers)
 *   3. Week-bucketing logic (getWeekStart)
 *   4. logAttendance() — the single function everything writes through
 *   5. onFormSubmit() — wires the Google Form to logAttendance()
 *
 * NOT included yet (next phase):
 *   - Lambda → doPost() web app endpoint
 *   - Summary tab formulas + conditional formatting
 *   - Reminder / missing-data email triggers
 */

// ══════════════════════════════════════════════════════════════════════════
// CONFIG — edit this section as your setup changes
// ══════════════════════════════════════════════════════════════════════════

const RAW_LOG_SHEET_NAME = "Raw Log";

// Column order in the Raw Log tab. If you ever add a column, add it here
// AND in the header row created by setupRawLog() below — keep them in sync.
const RAW_LOG_COLUMNS = [
  "week_start_date",   // Sunday date this row belongs to (Date object)
  "congregation",      // e.g. "SJ English", "WG Arabic", "SJ Joint"
  "metric",            // "IP" or "YT"
  "value",             // the number reported
  "source",            // "form" | "lambda" | "manual"
  "submitted_at",      // raw timestamp of the submission/POST
  "submitter_email",   // email address, if available (blank for Lambda)
  "flag",              // "" | "duplicate" | "non_numeric"
  "notes",              // free-text notes carried over from the form, if any
];

// Every congregation the form can report for. Used for validation and
// for building the list of "who needs to report YT" below.
const CONGREGATIONS = [
  "SJ English",
  "SJ Cantonese",
  "SJ Mandarin",
  "SJ Joint",
  "SJ Children Ministry",
  "WG English",
  "WG Mandarin (New Spring)",
  "WG Spanish (Nueva Vida)",
  "WG Arabic",
  "WG Joint",
  "WG Children Ministry",
];

// Congregations that report their OWN YT number on the form (because Lambda
// either can't reach them, or doesn't cover that stream at all).
// Everyone else either gets YT from Lambda, or has no YT metric at all.
const MANUAL_YT_CONGREGATIONS = ["SJ Cantonese", "SJ Joint", "WG Joint"];

// Congregations with no livestream at all — YT metric simply never applies.
const NO_YT_CONGREGATIONS = [
  "SJ Children Ministry",
  "WG Children Ministry",
  "WG Mandarin (New Spring)",
  "WG Arabic",
];


// ══════════════════════════════════════════════════════════════════════════
// SETUP — run setupRawLog() ONCE from the Apps Script editor to create the tab
// ══════════════════════════════════════════════════════════════════════════

function setupRawLog() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(RAW_LOG_SHEET_NAME);

  if (!sheet) {
    sheet = ss.insertSheet(RAW_LOG_SHEET_NAME);
  }

  sheet.clear();
  sheet.getRange(1, 1, 1, RAW_LOG_COLUMNS.length).setValues([RAW_LOG_COLUMNS]);
  sheet.setFrozenRows(1);

  const headerRange = sheet.getRange(1, 1, 1, RAW_LOG_COLUMNS.length);
  headerRange.setFontWeight("bold").setBackground("#4a4a4a").setFontColor("#ffffff");

  sheet.autoResizeColumns(1, RAW_LOG_COLUMNS.length);

  Logger.log("Raw Log tab created with headers: " + RAW_LOG_COLUMNS.join(", "));
}


// ══════════════════════════════════════════════════════════════════════════
// DATE LOGIC — bucket any timestamp to the Sunday it belongs to
// ══════════════════════════════════════════════════════════════════════════

/**
 * Given any date/timestamp, return the most recent Sunday on or before it,
 * as a Date object set to midnight. This is the single source of truth for
 * "which week does this submission belong to" — used by every write path
 * (form, Lambda, manual entry).
 *
 * Example: a submission on Tuesday Jan 6 for the service on Sunday Jan 4
 * returns Jan 4 — regardless of what day the timestamp itself falls on.
 */
function getWeekStart(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  const dayOfWeek = d.getDay(); // 0 = Sunday, 1 = Monday, ... 6 = Saturday
  d.setDate(d.getDate() - dayOfWeek);
  return d;
}


// ══════════════════════════════════════════════════════════════════════════
// CORE WRITE FUNCTION — every source (form, Lambda, manual) calls this
// ══════════════════════════════════════════════════════════════════════════

/**
 * Writes one row to the Raw Log, or flags a conflict if a row already
 * exists for the same week + congregation + metric.
 *
 * @param {Date}   weekStart   Result of getWeekStart() — the Sunday this belongs to
 * @param {string} congregation  Must match an entry in CONGREGATIONS
 * @param {string} metric       "IP" or "YT"
 * @param {number} value        The reported number
 * @param {string} source       "form" | "lambda" | "manual"
 * @param {string} submitterEmail  Optional — blank for Lambda-sourced rows
 * @param {string} notes        Optional free-text notes
 * @return {Object} { status: "logged" | "flagged_duplicate" | "flagged_non_numeric", row: number }
 */
function logAttendance(weekStart, congregation, metric, value, source, submitterEmail, notes) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(RAW_LOG_SHEET_NAME);

  if (!sheet) {
    throw new Error("Raw Log sheet not found. Run setupRawLog() first.");
  }

  if (CONGREGATIONS.indexOf(congregation) === -1) {
    throw new Error("Unknown congregation: " + congregation);
  }

  // ── Non-numeric check ────────────────────────────────────────────────
  // Belt-and-suspenders behind the form's own "Whole number" validation —
  // catches anything that slips through (API submissions, edited responses).
  const numericValue = Number(value);
  const isNonNumeric = value === "" || value === null || isNaN(numericValue);

  // ── Duplicate check ───────────────────────────────────────────────────
  // Looks for an existing, non-flagged row for the same week + congregation
  // + metric. If found, this new submission gets flagged instead of
  // overwriting or averaging with the old one — a human decides which is right.
  const data = sheet.getDataRange().getValues();
  const weekStartTime = weekStart.getTime();

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const existingWeek = new Date(row[0]).getTime();
    const existingCong = row[1];
    const existingMetric = row[2];
    const existingFlag = row[7];

    if (
      existingWeek === weekStartTime &&
      existingCong === congregation &&
      existingMetric === metric &&
      existingFlag !== "duplicate" // don't chain-flag against an already-flagged row
    ) {
      // Found a prior entry — log this new one as a flagged duplicate,
      // preserving BOTH values so a human can reconcile them.
      const newRow = [
        weekStart,
        congregation,
        metric,
        isNonNumeric ? value : numericValue,
        source,
        new Date(),
        submitterEmail || "",
        "duplicate",
        (notes || "") + ` [conflicts with row ${i + 1}, existing value: ${row[3]}]`,
      ];
      sheet.appendRow(newRow);
      return { status: "flagged_duplicate", row: sheet.getLastRow() };
    }
  }

  // ── Write the row ─────────────────────────────────────────────────────
  const flag = isNonNumeric ? "non_numeric" : "";
  const newRow = [
    weekStart,
    congregation,
    metric,
    isNonNumeric ? value : numericValue, // keep original bad value visible for review
    source,
    new Date(),
    submitterEmail || "",
    flag,
    notes || "",
  ];
  sheet.appendRow(newRow);

  return {
    status: isNonNumeric ? "flagged_non_numeric" : "logged",
    row: sheet.getLastRow(),
  };
}


// ══════════════════════════════════════════════════════════════════════════
// FORM TRIGGER — wires the Google Form to logAttendance()
// ══════════════════════════════════════════════════════════════════════════
//
// SETUP REQUIRED (one-time, in the Apps Script editor):
//   Triggers (clock icon in left sidebar) → Add Trigger →
//     Function: onFormSubmit
//     Event source: From spreadsheet
//     Event type: On form submit
//
// This reads directly from the form's response columns in "Form Responses 1".
// Adjust the column letters below to match your actual form layout —
// they're based on the screenshots you shared (Timestamp, Email, Church
// Location, SJ Congregation, SJ IP, SJ YT, SJ Notes, WG Congregation,
// WG IP, WG YT, WG Notes).

function onFormSubmit(e) {
  const responses = e.namedValues; // object: { "Question Title": ["answer"] }

  const timestamp = new Date(e.values[0]);
  const weekStart = getWeekStart(timestamp);
  const submitterEmail = getFirst(responses["Email Address"]);
  const churchLocation = getFirst(responses["What Church Location"]);

  if (churchLocation === "San Jose") {
    logCampus("SJ", responses, weekStart, submitterEmail);
  } else if (churchLocation === "Willow Glen") {
    logCampus("WG", responses, weekStart, submitterEmail);
  } else {
    Logger.log("Unrecognized church location: " + churchLocation);
  }
}

/**
 * Handles one campus's block of form questions (SJ or WG prefix).
 * Maps the radio-button congregation answer to the full congregation name,
 * logs the IP value always, and logs the YT value only if that
 * congregation is one of the manual-YT congregations AND a value was given.
 */
function logCampus(prefix, responses, weekStart, submitterEmail) {
  const congregationShort = getFirst(responses[prefix + " Congregation"]);
  const ipValue = getFirst(responses[prefix + " Number of people (in person)"]);
  const ytValue = getFirst(responses[prefix + " Number of people (online)"]);
  const notes = getFirst(responses[prefix + " Notes"]);

  const congregation = resolveCongregationName(prefix, congregationShort);
  if (!congregation) {
    Logger.log("Could not resolve congregation for prefix=" + prefix + " value=" + congregationShort);
    return;
  }

  // IP is always expected.
  logAttendance(weekStart, congregation, "IP", ipValue, "form", submitterEmail, notes);

  // YT only applies to the manual-YT congregations. Everyone else's YT
  // either comes from Lambda automatically, or doesn't exist at all —
  // in both cases, a value on the form for them would be unexpected,
  // but we still log it if present rather than silently discarding it.
  if (ytValue !== undefined && ytValue !== "") {
    logAttendance(weekStart, congregation, "YT", ytValue, "form", submitterEmail, notes);
  }
}

/**
 * Maps a campus prefix + the form's short congregation label to the full
 * congregation name used everywhere else (CONGREGATIONS list, Raw Log,
 * summary tab). Edit this if your form's radio button labels change.
 */
function resolveCongregationName(prefix, shortLabel) {
  const map = {
    "SJ": {
      "English": "SJ English",
      "Cantonese": "SJ Cantonese",
      "Mandarin": "SJ Mandarin",
      "Joint Services": "SJ Joint",
      "Children Ministry": "SJ Children Ministry",
    },
    "WG": {
      "English": "WG English",
      "Mandarin (New Spring)": "WG Mandarin (New Spring)",
      "Spanish (NUEVA VIDA)": "WG Spanish (Nueva Vida)",
      "ARABIC Church": "WG Arabic",
      "Joint Services": "WG Joint",
      "Children Ministry": "WG Children Ministry",
    },
  };

  return (map[prefix] && map[prefix][shortLabel]) || null;
}

/** Helper — namedValues gives arrays even for single answers. Unwrap safely. */
function getFirst(arr) {
  return arr && arr.length > 0 ? arr[0] : "";
}
