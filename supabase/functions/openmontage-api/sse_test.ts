import { formatSseEvent, parseLastEventId } from "./sse.ts";

Deno.test("parses a valid event cursor", () => {
  if (parseLastEventId("42") !== 42) throw new Error("valid cursor was not parsed");
});

Deno.test("rejects malformed and unsafe event cursors", () => {
  for (const value of [null, "", "-1", "1.5", "1x", "9007199254740992"]) {
    if (parseLastEventId(value) !== 0) throw new Error(`invalid cursor accepted: ${value}`);
  }
});

Deno.test("formats an SSE event with a stable id and JSON data", () => {
  const event = formatSseEvent({ sequence: 7, event_type: "progress", progress: 35 });
  if (event !== 'id: 7\nevent: progress\ndata: {"sequence":7,"event_type":"progress","progress":35}\n\n') {
    throw new Error("SSE frame did not match the expected wire format");
  }
});

Deno.test("falls back to message for an unsafe event name", () => {
  const event = formatSseEvent({ sequence: 1, event_type: "bad\nevent" });
  if (!event.startsWith("id: 1\nevent: message\n")) throw new Error("unsafe event name was not normalized");
});

Deno.test("rejects invalid event sequence numbers", () => {
  let rejected = false;
  try { formatSseEvent({ sequence: 0, event_type: "progress" }); } catch { rejected = true; }
  if (!rejected) throw new Error("invalid sequence was accepted");
});
