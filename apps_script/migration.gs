/**
 * ONE-TIME MIGRATION — pulls 2026 data from the old spreadsheet into Raw Log
 * =============================================================================
 * Run migrateOldData() ONCE from the Apps Script editor. It reads directly
 * from the old spreadsheet by ID (no scraping, no copy-pasting) and writes
 * straight into Raw Log, bypassing the duplicate/non-numeric checks that
 * logAttendance() normally runs — historical data is trusted as-is.
 *
 * ASSUMPTIONS BAKED IN (confirm before running):
 *   - Reads the tab named below (OLD_SHEET_TAB_NAME) in the old spreadsheet.
 *   - Only rows with a 2026 date are migrated.
 *   - "kids" count is folded into the IP number (IP + kids = one combined value).
 *   - "CM" (Children Ministry, undifferentiated by campus in the old sheet)
 *     is migrated as "SJ Children Ministry" with a note flagging that the
 *     campus wasn't distinguished in the source data — so it's findable
 *     and reassignable later, not silently guessed.
 *   - YT numbers are taken as already recorded in the old sheet — NOT
 *     re-fetched from YouTube's API for historical dates.
 */

// ══════════════════════════════════════════════════════════════════════════
// CONFIG — verify these against the actual old sheet before running
// ══════════════════════════════════════════════════════════════════════════

const OLD_SPREADSHEET_ID = "YOUR_OLD_SPREADSHEET_ID_HERE"; // this one-time migration has already been run — real ID redacted
const OLD_SHEET_TAB_NAME = "SUMMARIES 2026";

// The old sheet lists one row per congregation per week, with the date only
// filled in on the first row of each week's block (blank on the rows below
// it, until the next week's date appears). Adjust these column letters/
// numbers if they don't match what you see when you open the old sheet.
const OLD_COL = {
  DATE: 1,      // Column A
  CONGREGATION: 2, // Column B
  YT: 3,        // Column C — "Youtube (peak) concurrent views"
  IP: 4,        // Column D — "In Person"
  KIDS: 5,      // Column E — "kids"
  NOTES: 7,     // Column G — "Note"
};

const OLD_DATA_START_ROW = 5; // confirmed: first data row (week 1) in the old sheet

// Maps the old sheet's short congregation labels to your new full names.
// "CM" intentionally maps to SJ Children Ministry — see note above.
const OLD_LABEL_MAP = {
  "MS": "SJ Mandarin",
  "CS": "SJ Cantonese",
  "ES - SJ": "SJ English",
  "ES-SJ": "SJ English",
  "ES - WG": "WG English",
  "ES-WG": "WG English",
  "NS": "WG Mandarin (New Spring)",
  "Nueva Vida": "WG Spanish (Nueva Vida)",
  "Arabic": "WG Arabic",
  "CM": "SJ Children Ministry",
  "Good Fiday Service": "SJ Joint",
};


// ══════════════════════════════════════════════════════════════════════════
// MIGRATION — run this once
// ══════════════════════════════════════════════════════════════════════════

function migrateOldData() {
  const oldSs = SpreadsheetApp.openById(OLD_SPREADSHEET_ID);
  const oldSheet = oldSs.getSheetByName(OLD_SHEET_TAB_NAME);

  if (!oldSheet) {
    throw new Error(
      `Tab "${OLD_SHEET_TAB_NAME}" not found in old spreadsheet. ` +
      `Available tabs: ${oldSs.getSheets().map(s => s.getName()).join(", ")}`
    );
  }

  const data = oldSheet.getDataRange().getValues();
  const raw = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(RAW_LOG_SHEET_NAME);

  if (!raw) {
    throw new Error("Raw Log sheet not found in this spreadsheet. Run setupRawLog() first.");
  }

  // Build a set of what's already in Raw Log (week + congregation + metric)
  // so this script can be re-run safely without duplicating prior migrations.
  const existingData = raw.getDataRange().getValues();
  const existingKeys = new Set();
  for (let i = 1; i < existingData.length; i++) {
    const wk = new Date(existingData[i][0]).getTime();
    const cong = existingData[i][1];
    const metric = existingData[i][2];
    existingKeys.add(`${wk}|${cong}|${metric}`);
  }

  let currentDate = null;
  let migratedCount = 0;
  let skippedCount = 0;
  const skippedReasons = [];
  const rowsToWrite = [];

  for (let i = OLD_DATA_START_ROW - 1; i < data.length; i++) {
    const row = data[i];
    const dateCell = row[OLD_COL.DATE - 1];
    const congLabel = row[OLD_COL.CONGREGATION - 1];

    // Date only appears on the first row of each week's block — carry it
    // forward until a new one shows up.
    if (dateCell instanceof Date) {
      currentDate = dateCell;
    }

    if (!currentDate || !congLabel) {
      continue; // blank spacer row, or no week established yet
    }

    // Only migrate 2026 data.
    if (currentDate.getFullYear() !== 2026) {
      continue;
    }

    const congregation = OLD_LABEL_MAP[String(congLabel).trim()];
    if (!congregation) {
      skippedCount++;
      skippedReasons.push(`Row ${i + 1}: unrecognized congregation label "${congLabel}"`);
      continue;
    }

    const weekStart = getWeekStart(currentDate);
    const ytValue = row[OLD_COL.YT - 1];
    const ipRaw = row[OLD_COL.IP - 1];
    const kidsRaw = row[OLD_COL.KIDS - 1];
    const notesRaw = row[OLD_COL.NOTES - 1];

    const ipCombined = (Number(ipRaw) || 0) + (Number(kidsRaw) || 0);
    const isCM = congregation === "SJ Children Ministry" && String(congLabel).trim() === "CM";
    const note = (notesRaw ? String(notesRaw) + " " : "") +
      (isCM ? "[migrated — campus not distinguished in source data]" : "[migrated from old sheet]");

    // Write IP if there's a value in EITHER the IP or kids column — a
    // kids-only week (IP blank, kids filled in) should still count,
    // not be silently skipped just because IP itself was empty.
    const hasIp = ipRaw !== "" && ipRaw !== null && ipRaw !== undefined;
    const hasKids = kidsRaw !== "" && kidsRaw !== null && kidsRaw !== undefined;
    const ipKey = `${weekStart.getTime()}|${congregation}|IP`;
    if ((hasIp || hasKids) && !existingKeys.has(ipKey)) {
      rowsToWrite.push([weekStart, congregation, "IP", ipCombined, "migration", new Date(), "", "", note]);
      existingKeys.add(ipKey);
      migratedCount++;
    }

    // Only write YT if there's a real value and it's not already logged.
    const ytKey = `${weekStart.getTime()}|${congregation}|YT`;
    if (ytValue !== "" && ytValue !== null && ytValue !== undefined && !existingKeys.has(ytKey)) {
      rowsToWrite.push([weekStart, congregation, "YT", Number(ytValue) || 0, "migration", new Date(), "", "", note]);
      existingKeys.add(ytKey);
      migratedCount++;
    }
  }

  if (rowsToWrite.length > 0) {
    raw.getRange(raw.getLastRow() + 1, 1, rowsToWrite.length, rowsToWrite[0].length)
      .setValues(rowsToWrite);
  }

  Logger.log(`Migrated ${migratedCount} rows. Skipped ${skippedCount} rows.`);
  if (skippedReasons.length > 0) {
    Logger.log("Skip reasons:\n" + skippedReasons.join("\n"));
  }

  return { migrated: migratedCount, skipped: skippedCount, skipReasons: skippedReasons };
}
