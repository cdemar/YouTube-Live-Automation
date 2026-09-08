/**
 * AUTO-DATE POPULATION — fills in Week dates automatically from the Year cell
 * =============================================================================
 * Whenever someone types or changes the year in cell A1 of a summary tab
 * (e.g. typing "2027" when duplicating the sheet for a new year), this
 * automatically fills column B with each week's actual Sunday date —
 * Week 1 = the year's first Sunday, counting forward to the year's last
 * Sunday (52 or 53 rows depending on the year).
 *
 * This is a "simple trigger" — named exactly onEdit — so it runs
 * automatically with NO manual trigger setup required. Just paste this
 * file in and it works immediately.
 */

const WEEK_DATE_START_ROW = 5; // Row where "Week 1" lives (adjust if your layout differs)
const MAX_WEEK_ROWS = 53;      // Covers years with 53 Sundays; extra rows are cleared for 52-week years

/**
 * Fires automatically whenever ANY cell is edited in the spreadsheet.
 * Only acts if the edit was to cell A1 (the Year cell) and the new
 * value looks like a real year — everything else is ignored.
 */
function onEdit(e) {
  const range = e.range;
  const sheet = range.getSheet();

  if (range.getRow() !== 1 || range.getColumn() !== 1) {
    return; // not the Year cell — ignore
  }

  const year = parseInt(range.getValue());
  if (isNaN(year) || year < 2000 || year > 2100) {
    return; // not a plausible year — ignore (avoids misfiring on unrelated tabs)
  }

  populateWeekDates(sheet, year);
}

/**
 * Fills column B with every Sunday of the given year, starting at
 * WEEK_DATE_START_ROW. Clears the full range first so a year with only
 * 52 Sundays doesn't leave a stale 53rd date behind from a prior year.
 */
function populateWeekDates(sheet, year) {
  const sundays = getSundaysForYear(year);

  sheet.getRange(WEEK_DATE_START_ROW, 2, MAX_WEEK_ROWS, 1).clearContent();

  const values = sundays.map(d => [d]);
  sheet.getRange(WEEK_DATE_START_ROW, 2, values.length, 1).setValues(values);
}

/**
 * Returns every Sunday in the given year, in order — the year's first
 * Sunday through its last Sunday (matches the "week keyed by Sunday
 * start-date" logic used everywhere else in this project).
 */
function getSundaysForYear(year) {
  const sundays = [];
  let d = new Date(year, 0, 1);

  while (d.getDay() !== 0) {
    d.setDate(d.getDate() + 1);
  }

  while (d.getFullYear() === year) {
    sundays.push(new Date(d));
    d.setDate(d.getDate() + 7);
  }

  return sundays;
}

/**
 * Run this manually ONCE on your existing "2026" tab to backfill dates
 * for the weeks that already passed — onEdit only fires on FUTURE edits
 * to A1, so it won't retroactively fill a tab that already has "2026" sitting
 * in A1 without ever being re-typed.
 */
function backfillCurrentYearTab() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("2026");
  if (!sheet) {
    throw new Error('Tab named "2026" not found — check the tab name and adjust this function.');
  }
  const year = parseInt(sheet.getRange("A1").getValue());
  populateWeekDates(sheet, year);
  Logger.log(`Backfilled dates for ${year} on tab "${sheet.getName()}"`);
}
