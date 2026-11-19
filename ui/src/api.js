// One place for every request to the driver. Errors come back as a readable message.
export async function call(path, method = "GET", body) {
  const r = await fetch(path, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = data.detail;
    const text = Array.isArray(d) ? d.map(x => x.msg ?? String(x)).join("; ") : (typeof d === "string" ? d : String(r.status));
    throw new Error(text);
  }
  return data;
}
