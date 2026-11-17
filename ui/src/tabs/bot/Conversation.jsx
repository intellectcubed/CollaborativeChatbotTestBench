import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { messageTime } from "./dates.js";
import TraceId from "../../components/TraceId.jsx";

// The chatbot's model use for one message, from its trace: input and output tokens over its model calls.
function Tokens({ t }) {
  const n = v => Number(v || 0).toLocaleString();
  return (
    <span className="tokens" title={`${t.calls} model call${t.calls === 1 ? "" : "s"}`}>
      {" · "}tokens {n(t.input)} in / {n(t.output)} out
    </span>
  );
}

function Verdicts({ ev }) {
  const [open, setOpen] = useState({});
  return ev.verdicts.map(v => (
    <div className="note verdict" key={v.id}>
      <span className={`tag ${v.verdict}`}>{v.verdict}</span> {v.id}
      {" "}<button className="link" onClick={() => setOpen({ ...open, [v.id]: !open[v.id] })}>
        {open[v.id] ? "hide" : "details"}
      </button>
      {open[v.id] && <div className="ev">evidence: {v.evidence}{"\n"}reason: {v.reason}</div>}
    </div>
  ));
}

// One item in the window. Member messages are blue on the left; chatbot replies are green on the right.
// Everything else is a small grey note between them.
function Item({ ev, postFor }) {
  switch (ev.kind) {
    case "post":
      return (
        <div className="bubble mine">
          <div className="meta">
            {messageTime(ev.sent_at)} · {ev.name || ev.persona} · squad {ev.squad}
            {ev.trace_id && <> · <TraceId id={ev.trace_id} /></>}
            {ev.source !== "manual" && <span className="bottag">bot</span>}
          </div>
          <div className="body">{ev.text}</div>
          {ev.warning && <div className="meta warn">{ev.warning}</div>}
        </div>
      );
    case "reply": {
      const post = postFor(ev.trace_id);
      // A finished turn with no message (the chatbot acted, or chose not to) shows the title line alone.
      return (
        <div className={`bubble theirs${ev.no_message ? " titleonly" : ""}`}>
          <div className="meta">
            {messageTime(ev.sent_at || post?.sent_at)} · Chatbot · squad {ev.squad || post?.squad || "?"}
            {ev.trace_id && <> · <TraceId id={ev.trace_id} /></>}
            {ev.tokens && <Tokens t={ev.tokens} />}
            {ev.no_message && <span className="done"> · ✓ done, no message{ev.trace_status ? ` (${ev.trace_status})` : ""}</span>}
          </div>
          {!ev.no_message && <div className="body">{ev.text}</div>}
          {ev.error && <div className="meta err">{ev.error}</div>}
        </div>
      );
    }
    case "calendar": return <div className="note cal">calendar: {ev.text}</div>;
    case "plan": return <div className="note">plan: {ev.text}</div>;
    case "checks": return ev.checks.map(c => <div className="note" key={c.id}>check {c.id}: {c.check}</div>);
    case "verdict": return <><Verdicts ev={ev} />{ev.summary && <div className="note">judge: {ev.summary}</div>}</>;
    case "snapshot": return <div className="note">judge saved the {ev.label} calendar for {(ev.dates || []).join(", ") || "no days"}</div>;
    case "setup": return <div className="note">setup {ev.action} {ev.date} {ev.start}–{ev.end} squad {ev.squad}{ev.live ? "" : " (preview)"}</div>;
    case "finish": return <div className="note stop">tester finished: {ev.passed ? "passed" : "not passed"}. {ev.reason}</div>;
    case "stop": return <div className="note stop">run stopped: {ev.reason}</div>;
    case "note": return <div className="note">{ev.text}</div>;
    default: return null;  // model calls and tool calls are in the run's files, not in the window
  }
}

// The scrolling window. It follows new messages, unless I have scrolled up; then a button takes me back down.
export default function Conversation({ items, waiting, onClear, canClear }) {
  const box = useRef(null);
  const atBottom = useRef(true);
  const [unseen, setUnseen] = useState(false);
  const posts = {};
  for (const ev of items) if (ev.kind === "post" && ev.trace_id) posts[ev.trace_id] = ev;

  const toBottom = () => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
    setUnseen(false);
  };

  useLayoutEffect(() => {
    if (atBottom.current) toBottom();
    else if (items.length) setUnseen(true);
  }, [items.length, waiting]);

  useEffect(() => { if (!items.length) setUnseen(false); }, [items.length]);

  function onScroll() {
    const el = box.current;
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom.current) setUnseen(false);
  }

  return (
    <section className="convowrap">
      <button className="clear" onClick={onClear} disabled={!canClear} title="Clear the conversation">Clear</button>
      <div className="convo" ref={box} onScroll={onScroll}>
        {items.length === 0 && !waiting && (
          <p className="placeholder">Type a message below and press Send, or switch to Automated and press Go.</p>
        )}
        {items.map(ev => <Item key={ev.key} ev={ev} postFor={id => posts[id]} />)}
        {waiting && <div className="bubble theirs pending"><div className="body">…</div></div>}
      </div>
      {unseen && <button className="newmsgs" onClick={toBottom}>New messages ↓</button>}
    </section>
  );
}
