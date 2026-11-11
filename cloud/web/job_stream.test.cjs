const test = require("node:test");
const assert = require("node:assert/strict");
const { createSseParser, start } = require("./job_stream.js");

test("parses split SSE frames, CRLF, comments, and multiline data", () => {
  const events = [];
  const parser = createSseParser(event => events.push(event));
  parser.push(": heartbeat\r\nid: 7\r\nevent: stage.progress\r\ndata: {\"progress\":");
  parser.push("35,\r\ndata: \"stage\":\"rendering\"}\r\n\r\n");
  parser.finish();
  assert.equal(events.length, 1);
  assert.equal(events[0].id, "7");
  assert.equal(events[0].event, "stage.progress");
  assert.equal(events[0].data, "{\"progress\":35,\n\"stage\":\"rendering\"}");
});

test("retains the last event id when a later event omits id", () => {
  const events = [];
  const parser = createSseParser(event => events.push(event));
  parser.push("id: 12\ndata: first\n\ndata: second\n\n");
  assert.deepEqual(events.map(event => event.id), ["12", "12"]);
});

test("ignores an id containing a null character", () => {
  const events = [];
  const parser = createSseParser(event => events.push(event));
  parser.push("id: 5\ndata: first\n\nid: bad\0id\ndata: second\n\n");
  assert.deepEqual(events.map(event => event.id), ["5", "5"]);
});

test("reconnects with the last event id and bearer token", async () => {
  let calls = 0, handle;
  const received = [];
  const fetchImpl = async (_url, init) => {
    calls += 1;
    assert.equal(init.headers.get("Authorization"), "Bearer test-access-token");
    if (calls === 1) {
      assert.equal(init.headers.get("Last-Event-ID"), null);
      const body = new ReadableStream({ start(controller) {
        controller.enqueue(new TextEncoder().encode("id: 21\nevent: stage.progress\ndata: {\"progress\":10}\n\n"));
        controller.close();
      }});
      return new Response(body, { status: 200 });
    }
    assert.equal(init.headers.get("Last-Event-ID"), "21");
    const body = new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode("id: 22\nevent: job.completed\ndata: {\"progress\":100}\n\n"));
      controller.close();
    }});
    return new Response(body, { status: 200 });
  };
  handle = start({
    url: "https://example.test/jobs/1/events/stream",
    token: "test-access-token",
    fetchImpl,
    onEvent(event) { received.push(event); if (event.id === "22") handle.stop(); }
  });
  await handle.done;
  assert.equal(calls, 2);
  assert.deepEqual(received.map(event => event.id), ["21", "22"]);
  assert.equal(handle.getLastEventId(), "22");
});

test("stops cleanly when the endpoint is not deployed", async () => {
  let unavailable = 0, calls = 0;
  const handle = start({
    url: "https://example.test/jobs/1/events/stream",
    token: "test-access-token",
    fetchImpl: async () => { calls += 1; return new Response("not found", { status: 404 }); },
    onUnavailable(error) { unavailable += 1; assert.equal(error.status, 404); }
  });
  await handle.done;
  assert.equal(calls, 1);
  assert.equal(unavailable, 1);
});
