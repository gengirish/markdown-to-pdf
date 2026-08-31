/** A small RFC4180 CSV reader/writer.
 *
 *  The wizard needs to parse a cohort file client-side (to report problems
 *  before anything is uploaded) and rebuild one after a person excludes or
 *  edits rows. No dependency is pulled in for this — the format is small
 *  enough to get exactly right, and "exactly right" matters here: the server
 *  parses with Python's `csv.DictReader`, so a naive `split(",")` would parse
 *  a name like `"Rao, Ananya"` into two columns and silently misalign every
 *  column after it.
 */

export interface ParsedCsv {
  /** Header cells, in file order and exact original case — the server's
   *  `csv.DictReader` keys on the literal header text, so `Name` and `name`
   *  are different columns to it even though they read the same to a person. */
  header: string[];
  rows: Record<string, string>[];
}

export function parseCsv(text: string): ParsedCsv {
  const table = parseTable(text);
  if (table.length === 0) return { header: [], rows: [] };

  const [header, ...body] = table;
  const rows = body
    // A trailing blank line parses as one empty cell, not a real row.
    .filter((cells) => !(cells.length === 1 && cells[0] === ""))
    .map((cells) => {
      const row: Record<string, string> = {};
      header.forEach((key, index) => {
        row[key] = cells[index] ?? "";
      });
      return row;
    });

  return { header, rows };
}

/** The state-machine part: quoted fields may contain commas, newlines and a
 *  doubled `""` for a literal quote. Everything else splits on commas and
 *  newlines. */
function parseTable(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char === "\r") {
      // Swallowed; the paired \n (or its absence, on a lone-CR file) drives
      // the row break.
    } else {
      field += char;
    }
  }

  // The last field/row has no trailing newline to close it.
  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

/** The inverse of parseCsv, for rebuilding a file after rows are excluded or
 *  edited in the review step. Quotes a field only when the format requires
 *  it, so an unedited row round-trips byte-for-byte. */
export function buildCsv(header: string[], rows: Record<string, string>[]): string {
  const line = (cells: string[]) => cells.map(quoteCsvField).join(",");
  return [line(header), ...rows.map((row) => line(header.map((key) => row[key] ?? "")))].join(
    "\r\n",
  );
}

function quoteCsvField(value: string): string {
  if (/[",\r\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/** Loose on purpose — this flags a value for a person to glance at, not a
 *  server-side rule. A false negative here just means one more row a person
 *  has to notice is fine; a false positive blocks a real address for no
 *  reason. RFC 5322 has no simple regex, so this checks the one shape that
 *  actually matters: something, an @, something, a dot, something. */
export const LOOSE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
