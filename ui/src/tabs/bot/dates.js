// Calendar dates are plain "YYYY-MM-DD" strings, worked on in UTC so the browser's own time zone never shifts a day.
// Message times are shown in New York time, the chatbot's time zone.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const toUtc = iso => { const [y, m, d] = iso.split("-").map(Number); return new Date(Date.UTC(y, m - 1, d)); };
const fromUtc = dt => dt.toISOString().slice(0, 10);

export function addDays(iso, n) {
  const dt = toUtc(iso);
  dt.setUTCDate(dt.getUTCDate() + n);
  return fromUtc(dt);
}

export const sundayOf = iso => addDays(iso, -toUtc(iso).getUTCDay());

export function dayLabel(iso) {
  const dt = toUtc(iso);
  return `${DAYS[dt.getUTCDay()]} ${dt.getUTCDate()} ${MONTHS[dt.getUTCMonth()]}`;
}

// "8–14 Mar 2026", or "29 Mar – 4 Apr 2026" across a month
export function weekLabel(sunday) {
  const a = toUtc(sunday), b = toUtc(addDays(sunday, 6));
  const am = MONTHS[a.getUTCMonth()], bm = MONTHS[b.getUTCMonth()];
  if (am === bm) return `${a.getUTCDate()}–${b.getUTCDate()} ${bm} ${b.getUTCFullYear()}`;
  return `${a.getUTCDate()} ${am} – ${b.getUTCDate()} ${bm} ${b.getUTCFullYear()}`;
}

// How far another week is from the one shown: "next week", "last week", "in 3 weeks", "2 weeks ago"
export function weeksAway(sundayShown, iso) {
  const n = Math.round((toUtc(sundayOf(iso)) - toUtc(sundayShown)) / (7 * 86400000));
  if (n === 1) return "next week";
  if (n === -1) return "last week";
  return n > 0 ? `in ${n} weeks` : `${-n} weeks ago`;
}

// Today's date in New York.
export function todayNY() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
}

// A date and an HH:MM time, moved on by some minutes. Returns { date, time }.
export function addMinutes(iso, hhmm, minutes) {
  const [h, m] = hhmm.split(":").map(Number);
  const total = h * 60 + m + Math.round(minutes);
  const days = Math.floor(total / 1440);
  const rest = ((total % 1440) + 1440) % 1440;
  const pad = n => String(n).padStart(2, "0");
  return { date: addDays(iso, days), time: `${pad(Math.floor(rest / 60))}:${pad(rest % 60)}` };
}

const NY_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "America/New_York", weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  hour12: false,
});

// "Tue 10 Mar 09:05" from an ISO time with an offset.
export function messageTime(isoTime) {
  if (!isoTime) return "";
  const dt = new Date(isoTime);
  if (Number.isNaN(dt.getTime())) return isoTime;
  const p = Object.fromEntries(NY_TIME.formatToParts(dt).map(x => [x.type, x.value]));
  return `${p.weekday} ${p.day} ${p.month} ${p.hour}:${p.minute}`;
}
