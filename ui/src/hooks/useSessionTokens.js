import { useCallback, useRef, useState } from "react";

// The chatbot's model use for this page session, added up from the token counts the status answers carry
// (Bot tab replies and Batch tab rows). Each trace is counted once, whichever event or row brings its count.
// Reset sets the totals to zero; traces already counted are not counted again.
export function useSessionTokens() {
  const [totals, setTotals] = useState({ input: 0, output: 0, messages: 0 });
  const counted = useRef(new Set());

  const add = useCallback(items => {
    let input = 0, output = 0, messages = 0;
    for (const { trace_id: id, tokens } of items) {
      if (!id || !tokens || counted.current.has(id)) continue;
      counted.current.add(id);
      input += Number(tokens.input) || 0;
      output += Number(tokens.output) || 0;
      messages += 1;
    }
    if (messages) setTotals(t => ({ input: t.input + input, output: t.output + output, messages: t.messages + messages }));
  }, []);

  const reset = useCallback(() => setTotals({ input: 0, output: 0, messages: 0 }), []);

  return { totals, add, reset };
}
