export const MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"];
export const SETTINGS = ["wait", "thread", "none", "sync"];

export function defaultGoal(pseudonyms = []) {
  return {
    name: "", goal: "", stop_condition: "", expected_results: [], my_squad: pseudonyms[0] || "",
    personas: pseudonyms[0] ? [pseudonyms[0]] : [], window: { start: "", end: "" }, gate_date: "",
    noise: "none", posting_allowed: SETTINGS.slice(), setup_allowed: false,
    models: { tester: "claude-sonnet-5-5", judge: "claude-opus-5-5" },
    temperature: { tester: 0.7, judge: 0 },
    limits: { max_messages: 12, max_turns: 30, reply_timeout_s: 120, max_cost_usd: 0.5 },
    time_between_min: 5,
  };
}
