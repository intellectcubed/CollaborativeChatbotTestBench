import { addDays, dayLabel, weekLabel, weeksAway } from "./dates.js";

// One day: the date on top, then the shift lines: `start–end` and up to three squads. A squad with no crew is red.
// No highlighting: after a refresh the lines simply show the new state.
function DayCell({ iso, day }) {
  let body;
  if (!day) {
    body = <div className="dayempty">…</div>;
  } else if (day.error) {
    body = <div className="dayempty err" title={day.error}>could not read</div>;
  } else if (day.lines === null) {
    body = <div className="dayraw" title="this day's answer could not be read as shifts">{day.raw}</div>;
  } else if (!day.lines.length) {
    body = <div className="dayempty">no shifts</div>;
  } else {
    body = (
      <div className="shifts">
        {day.lines.map((ln, i) => (
          <div className="shift" key={i}>
            <span className="time">{ln.start}–{ln.end}</span>
            <span className="squads">
              {ln.squads.length ? ln.squads.slice(0, 3).map((s, j) => (
                <span key={j} className={s.no_crew ? "nocrew" : ""}>{s.id}{s.no_crew ? " (No Crew)" : ""}</span>
              )) : "—"}
            </span>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="day">
      <div className="dayhead">{dayLabel(iso)}</div>
      {body}
    </div>
  );
}

// The calendar strip at the top of the tab: week navigation, the seven days, and the notices under them.
export default function WeekCalendar({ week, open, setOpen, live, messageWeek }) {
  const byDate = Object.fromEntries(week.days.map(d => [d.date, d]));
  const dates = Array.from({ length: 7 }, (_, i) => addDays(week.start, i));
  return (
    <section className="calendar">
      <div className="calbar">
        <button onClick={() => week.setStart(addDays(week.start, -7))} aria-label="Previous week" title="Previous week">‹</button>
        <label className="weekof">Week of
          <input type="date" value={week.start} onChange={e => e.target.value && week.setStart(e.target.value)} />
        </label>
        <button onClick={() => week.setStart(addDays(week.start, 7))} aria-label="Next week" title="Next week">›</button>
        <b className="weeklabel">{weekLabel(week.start)}</b>
        <button onClick={messageWeek} title="Show the week of the next message">Message week</button>
        {week.loading && <span className="status">reading…</span>}
        {week.error && <span className="err">{week.error}</span>}
        <span className="grow" />
        <button className="chev" onClick={() => setOpen(!open)} aria-expanded={open}
          title={open ? "Hide the calendar" : "Show the calendar"}>{open ? "▾" : "▸"}</button>
      </div>
      {open && <div className="week">{dates.map(iso => <DayCell key={iso} iso={iso} day={byDate[iso]} />)}</div>}
      {(!live || week.outside.length > 0) && (
        <div className="calnotice">
          {!live && <span>Live Calendar is off: the calendar does not change.</span>}
          {week.outside.length > 0 && (
            <span>
              Changed: {week.outside.map(c => `${dayLabel(c.date)} (${weeksAway(week.start, c.date)})`).join(", ")}
              {" · "}
              <button className="link" onClick={() => week.setStart(week.outside[0].date)}>Show</button>
              <button className="link" onClick={week.dismissOutside} aria-label="Dismiss">✕</button>
            </span>
          )}
        </div>
      )}
    </section>
  );
}
