/**
 * SUMMARY TAB BUILDER — formulas + Fibonacci trend color coding (v2)
 * =====================================================================
 * Three functions, run in order via rebuildSummaryTab():
 *
 *   1. buildSummaryFormulas(sheetName)
 *      Fills every week row (5–57) with formulas pulling from Raw Log:
 *      per-congregation IP/YT, campus totals, and column C's weekly
 *      grand total (Total columns per congregation are still computed
 *      as IP+YT, but no longer get their own trend color).
 *
 *   2. buildTrendHelperSheet(sheetName)
 *      Creates/rebuilds a HIDDEN helper sheet that pre-computes each
 *      week's trailing 4-week average for every IP/YT column. For weeks
 *      1–4 of the year (which don't have 4 prior weeks in the current
 *      year), it blends in the tail end of the PREVIOUS year's tab —
 *      so week 1 of 2027 compares against late 2026, not against nothing.
 *
 *   3. applyTrendFormatting(sheetName)
 *      Colors each cell based on the helper sheet's value: blue if up,
 *      orange if down, gray if missing, uncolored if flat or if no
 *      baseline exists at all (only happens for week 1 of the very
 *      first year ever tracked, with no prior year to blend from).
 *
 * All three are safe to re-run any time — full rebuild, no duplication.
 * RECOMMENDATION: test on a duplicate of your sheet first.
 */

// ══════════════════════════════════════════════════════════════════════════
// CONFIG
// ══════════════════════════════════════════════════════════════════════════

const SUMMARY_WEEK_START_ROW = 5;
const SUMMARY_WEEK_END_ROW = 57; // Week 53
const SUMMARY_AVERAGE_ROW = 4;
const SUMMARY_TOTAL_AVERAGE_ROW = 58; // "Total Average" row below the 53 weeks, column C only
const SUMMARY_DATE_COL = "B";
const SUMMARY_WEEKLY_TOTAL_COL = "C";

const CONGREGATION_LAYOUT = {
  "SJ English": { ip: "D", yt: "E", total: "F" },
  "SJ Cantonese": { ip: "G", yt: "H", total: "I" },
  "SJ Mandarin": { ip: "J", yt: "K", total: "L" },
  "SJ Joint": { ip: "M", yt: "N", total: "O" },
  "SJ Children Ministry": { ip: "P", yt: null, total: null },
  "WG English": { ip: "T", yt: "U", total: "V" },
  "WG Mandarin (New Spring)": { ip: "W", yt: null, total: null },
  "WG Spanish (Nueva Vida)": { ip: "X", yt: "Y", total: "Z" },
  "WG Arabic": { ip: "AA", yt: null, total: null },
  "WG Joint": { ip: "AB", yt: "AC", total: "AD" },
  "WG Children Ministry": { ip: "AE", yt: null, total: null },
};

const SJ_CAMPUS = { ip: "Q", yt: "R", total: "S" };
const WG_CAMPUS = { ip: "AF", yt: "AG", total: "AH" };

const SJ_IP_COLS = ["D", "G", "J", "M", "P"];
const SJ_YT_COLS = ["E", "H", "K", "N"];
const WG_IP_COLS = ["T", "W", "X", "AA", "AB", "AE"];
const WG_YT_COLS = ["U", "Y", "AC"];

// TREND-COLORED COLUMNS — IP and YT only, Total columns removed per request.
const TREND_COLUMNS = [
  "D", "E", "G", "H", "J", "K", "M", "N", "P",
  "T", "U", "W", "X", "Y", "AA", "AB", "AC", "AE",
];

const FIB_BANDS = [
  { lo: 1, hi: 2 },
  { lo: 3, hi: 5 },
  { lo: 8, hi: 13 },
  { lo: 20, hi: null },
];

const BLUE_SHADES = ["#EAF2FB", "#BFD9F2", "#6FA8DC", "#1155CC"];
const ORANGE_SHADES = ["#FFF3E0", "#FFCC80", "#FFA726", "#FF6F00"];
const MISSING_COLOR = "#D9D9D9";

function helperColumnMap() {
  // Assigns each TREND_COLUMNS entry a hidden helper column on the SAME
  // sheet, starting right after column AH (leaving one spacer column).
  const startIndex = letterToColIndex("AJ");
  const map = {};
  TREND_COLUMNS.forEach((col, i) => {
    map[col] = colIndexToLetter(startIndex + i);
  });
  return map;
}

function letterToColIndex(letter) {
  let col = 0;
  for (let i = 0; i < letter.length; i++) {
    col = col * 26 + (letter.charCodeAt(i) - 64);
  }
  return col;
}

function colIndexToLetter(index) {
  let letter = "";
  while (index > 0) {
    const rem = (index - 1) % 26;
    letter = String.fromCharCode(65 + rem) + letter;
    index = Math.floor((index - 1) / 26);
  }
  return letter;
}


// ══════════════════════════════════════════════════════════════════════════
// PART 1 — FORMULAS
// ══════════════════════════════════════════════════════════════════════════

function buildSummaryFormulas(sheetName) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
  if (!sheet) throw new Error(`Tab "${sheetName}" not found.`);

  for (let row = SUMMARY_WEEK_START_ROW; row <= SUMMARY_WEEK_END_ROW; row++) {
    const dateRef = `${SUMMARY_DATE_COL}${row}`;

    for (const [congregation, cols] of Object.entries(CONGREGATION_LAYOUT)) {
      writeMetricFormula(sheet, cols.ip, row, dateRef, congregation, "IP");
      if (cols.yt) writeMetricFormula(sheet, cols.yt, row, dateRef, congregation, "YT");
      if (cols.total) {
        sheet.getRange(`${cols.total}${row}`).setFormula(
          `=IF(AND(${cols.ip}${row}="",${cols.yt}${row}=""),"",N(${cols.ip}${row})+N(${cols.yt}${row}))`
        );
      }
    }

    sheet.getRange(`${SJ_CAMPUS.ip}${row}`).setFormula(
      `=IF(AND(${SJ_IP_COLS.map(c => `${c}${row}=""`).join(",")}),"",` +
      SJ_IP_COLS.map(c => `N(${c}${row})`).join("+") + `)`
    );
    sheet.getRange(`${SJ_CAMPUS.yt}${row}`).setFormula(
      `=IF(AND(${SJ_YT_COLS.map(c => `${c}${row}=""`).join(",")}),"",` +
      SJ_YT_COLS.map(c => `N(${c}${row})`).join("+") + `)`
    );
    sheet.getRange(`${SJ_CAMPUS.total}${row}`).setFormula(
      `=IF(AND(${SJ_CAMPUS.ip}${row}="",${SJ_CAMPUS.yt}${row}=""),"",N(${SJ_CAMPUS.ip}${row})+N(${SJ_CAMPUS.yt}${row}))`
    );

    sheet.getRange(`${WG_CAMPUS.ip}${row}`).setFormula(
      `=IF(AND(${WG_IP_COLS.map(c => `${c}${row}=""`).join(",")}),"",` +
      WG_IP_COLS.map(c => `N(${c}${row})`).join("+") + `)`
    );
    sheet.getRange(`${WG_CAMPUS.yt}${row}`).setFormula(
      `=IF(AND(${WG_YT_COLS.map(c => `${c}${row}=""`).join(",")}),"",` +
      WG_YT_COLS.map(c => `N(${c}${row})`).join("+") + `)`
    );
    sheet.getRange(`${WG_CAMPUS.total}${row}`).setFormula(
      `=IF(AND(${WG_CAMPUS.ip}${row}="",${WG_CAMPUS.yt}${row}=""),"",N(${WG_CAMPUS.ip}${row})+N(${WG_CAMPUS.yt}${row}))`
    );

    sheet.getRange(`${SUMMARY_WEEKLY_TOTAL_COL}${row}`).setFormula(
      `=IF(AND(${SJ_CAMPUS.total}${row}="",${WG_CAMPUS.total}${row}=""),"",N(${SJ_CAMPUS.total}${row})+N(${WG_CAMPUS.total}${row}))`
    );
  }

  const allDataCols = [
    ...Object.values(CONGREGATION_LAYOUT).flatMap(c => [c.ip, c.yt, c.total].filter(Boolean)),
    SJ_CAMPUS.ip, SJ_CAMPUS.yt, SJ_CAMPUS.total,
    WG_CAMPUS.ip, WG_CAMPUS.yt, WG_CAMPUS.total,
    SUMMARY_WEEKLY_TOTAL_COL,
  ];
  for (const col of allDataCols) {
    sheet.getRange(`${col}${SUMMARY_AVERAGE_ROW}`).setFormula(
      `=IFERROR(ROUND(AVERAGE(${col}${SUMMARY_WEEK_START_ROW}:${col}${SUMMARY_WEEK_END_ROW}),0),0)`
    );
  }

  // Row 58 — "Total Average" for column C only, per request: average of
  // just the weeks that have data (AVERAGE already ignores blank cells,
  // which is why this only works correctly now that C shows blank
  // instead of 0 for weeks nobody has reported yet).
  sheet.getRange(`${SUMMARY_WEEKLY_TOTAL_COL}${SUMMARY_TOTAL_AVERAGE_ROW}`).setFormula(
    `=IFERROR(ROUND(AVERAGE(${SUMMARY_WEEKLY_TOTAL_COL}${SUMMARY_WEEK_START_ROW}:${SUMMARY_WEEKLY_TOTAL_COL}${SUMMARY_WEEK_END_ROW}),0),0)`
  );

  Logger.log(`Formulas built for "${sheetName}".`);
}

function writeMetricFormula(sheet, col, row, dateRef, congregation, metric) {
  const countPart =
    `COUNTIFS('Raw Log'!$A:$A,${dateRef},'Raw Log'!$B:$B,"${congregation}",` +
    `'Raw Log'!$C:$C,"${metric}",'Raw Log'!$H:$H,"")`;
  const sumPart =
    `SUMIFS('Raw Log'!$D:$D,'Raw Log'!$A:$A,${dateRef},'Raw Log'!$B:$B,"${congregation}",` +
    `'Raw Log'!$C:$C,"${metric}",'Raw Log'!$H:$H,"")`;

  sheet.getRange(`${col}${row}`).setFormula(`=IF(${countPart}=0,"",${sumPart})`);
}


// ══════════════════════════════════════════════════════════════════════════
// PART 2 — TREND HELPER SHEET (trailing 4-week average, blended across years)
// ══════════════════════════════════════════════════════════════════════════

function buildTrendHelperSheet(sheetName) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const mainSheet = ss.getSheetByName(sheetName);
  if (!mainSheet) throw new Error(`Tab "${sheetName}" not found.`);

  const year = parseInt(mainSheet.getRange("A1").getValue());
  const prevSheetName = String(year - 1);
  const prevWeekCount = getWeekCountForYearTab(prevSheetName); // null if that tab doesn't exist

  const helperMap = helperColumnMap();

  for (const col of TREND_COLUMNS) {
    const helperCol = helperMap[col];

    for (let row = SUMMARY_WEEK_START_ROW; row <= SUMMARY_WEEK_END_ROW; row++) {
      const weekNum = row - (SUMMARY_WEEK_START_ROW - 1); // row 5 = week 1

      let formula;
      if (weekNum > 4) {
        // Fully within the current year — plain trailing 4 weeks.
        formula = `=IFERROR(ROUND(AVERAGE(${col}${row - 4}:${col}${row - 1}),0),"")`;
      } else {
        const neededFromPrev = 4 - weekNum;
        const currentYearPart = weekNum > 1 ? `,${col}${row - (weekNum - 1)}:${col}${row - 1}` : "";

        if (prevWeekCount === null) {
          formula = weekNum > 1
            ? `=IFERROR(ROUND(AVERAGE(${col}${row - (weekNum - 1)}:${col}${row - 1}),0),"")`
            : `=""`;
        } else {
          const prevLastRow = SUMMARY_WEEK_START_ROW - 1 + prevWeekCount;
          const prevFirstRow = prevLastRow - neededFromPrev + 1;
          const prevPart = `'${prevSheetName}'!${col}${prevFirstRow}:${col}${prevLastRow}`;
          formula = `=IFERROR(ROUND(AVERAGE(${prevPart}${currentYearPart}),0),"")`;
        }
      }

      mainSheet.getRange(`${helperCol}${row}`).setFormula(formula);
    }
  }

  // Hide the helper columns — they're plumbing, not something to look at day-to-day.
  const helperCols = Object.values(helperMap).map(letterToColIndex);
  const minCol = Math.min(...helperCols);
  const maxCol = Math.max(...helperCols);
  mainSheet.hideColumns(minCol, maxCol - minCol + 1);

  Logger.log(
    `Trend helper columns built for "${sheetName}" ` +
    (prevWeekCount !== null
      ? `(blending from "${prevSheetName}", ${prevWeekCount} weeks found).`
      : `(no "${prevSheetName}" tab found — weeks 1-4 will use current-year-only data where available).`)
  );
}

/** Returns how many weeks (52 or 53) a given year tab actually has data rows for, or null if the tab doesn't exist. */
function getWeekCountForYearTab(sheetName) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
  if (!sheet) return null;

  for (let row = SUMMARY_WEEK_END_ROW; row >= SUMMARY_WEEK_START_ROW; row--) {
    const dateVal = sheet.getRange(`${SUMMARY_DATE_COL}${row}`).getValue();
    if (dateVal instanceof Date) {
      return row - (SUMMARY_WEEK_START_ROW - 1);
    }
  }
  return null;
}


// ══════════════════════════════════════════════════════════════════════════
// PART 3 — TREND CONDITIONAL FORMATTING (reads from the helper sheet)
// ══════════════════════════════════════════════════════════════════════════

function applyTrendFormatting(sheetName) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
  if (!sheet) throw new Error(`Tab "${sheetName}" not found.`);

  const helperMap = helperColumnMap();
  const rules = [];

  for (const col of TREND_COLUMNS) {
    const range = sheet.getRange(`${col}${SUMMARY_WEEK_START_ROW}:${col}${SUMMARY_WEEK_END_ROW}`);
    const cellRef = `${col}${SUMMARY_WEEK_START_ROW}`;
    const helperRef = `${helperMap[col]}${SUMMARY_WEEK_START_ROW}`; // same sheet — no sheet qualifier

    // Missing data is left at the sheet's default white — no rule applied here.

    FIB_BANDS.forEach((band, i) => {
      const diff = `(${cellRef}-${helperRef})`;
      const upper = band.hi === null ? "" : `,${diff}<=${band.hi}`;
      const formula = `=AND(${cellRef}<>"",${helperRef}<>"",${diff}>=${band.lo}${upper})`;
      const isDeepest = i === FIB_BANDS.length - 1;
      let rule = SpreadsheetApp.newConditionalFormatRule()
        .whenFormulaSatisfied(formula)
        .setBackground(BLUE_SHADES[i]);
      if (isDeepest) rule = rule.setFontColor("#FFFFFF");
      rules.push(rule.setRanges([range]).build());
    });

    FIB_BANDS.forEach((band, i) => {
      const diff = `(${helperRef}-${cellRef})`;
      const upper = band.hi === null ? "" : `,${diff}<=${band.hi}`;
      const formula = `=AND(${cellRef}<>"",${helperRef}<>"",${diff}>=${band.lo}${upper})`;
      const isDeepest = i === FIB_BANDS.length - 1;
      let rule = SpreadsheetApp.newConditionalFormatRule()
        .whenFormulaSatisfied(formula)
        .setBackground(ORANGE_SHADES[i]);
      if (isDeepest) rule = rule.setFontColor("#FFFFFF");
      rules.push(rule.setRanges([range]).build());
    });
  }

  sheet.setConditionalFormatRules(rules);
  Logger.log(`Applied ${rules.length} trend formatting rules to "${sheetName}".`);
}


// ══════════════════════════════════════════════════════════════════════════
// RUN ALL THREE — convenience wrapper
// ══════════════════════════════════════════════════════════════════════════

function rebuildSummaryTab(sheetName) {
  // No name given? Use whichever tab is currently open/active — so you can
  // just open "Template", "2026", "2027", etc. and run this with no arguments.
  sheetName = sheetName || SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();
  buildSummaryFormulas(sheetName);
  buildTrendHelperSheet(sheetName);
  applyTrendFormatting(sheetName);
  Logger.log(`Summary tab fully rebuilt for "${sheetName}".`);
}
