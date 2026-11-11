(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.OpenMontageJobStream = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";
  function createSseParser(onEvent) {
    let buffer = "", data = [], eventName = "", lastEventId = "";
    function dispatch() {
      if (data.length) onEvent({ id: lastEventId, event: eventName || "message", data: data.join("\n") });
      data = []; eventName = "";
    }
    function processLine(line) {
      if (line === "") { dispatch(); return; }
      if (line.charAt(0) === ":") return;
      const separator = line.indexOf(":");
      const field = separator < 0 ? line : line.slice(0, separator);
      let value = separator < 0 ? "" : line.slice(separator + 1);
      if (value.charAt(0) === " ") value = value.slice(1);
      if (field === "data") data.push(value);
      else if (field === "event") eventName = value;
      else if (field === "id" && !value.includes("\0")) lastEventId = value;
    }
    return {
      push(chunk) {
        buffer += String(chunk);
        let newline;
        while ((newline = buffer.indexOf("\n")) >= 0) {
          let line = buffer.slice(0, newline);
          buffer = buffer.slice(newline + 1);
          if (line.endsWith("\r")) line = line.slice(0, -1);
          processLine(line);
        }
      },
      finish() {
        if (buffer.length) {
          let line = buffer; buffer = "";
          if (line.endsWith("\r")) line = line.slice(0, -1);
          processLine(line);
        }
        dispatch();
      }
    };
  }
  function delay(milliseconds) { return new Promise(resolve => setTimeout(resolve, milliseconds)); }
  function start(options) {
    if (!options || !options.url) throw new TypeError("A job event stream URL is required");
    const fetcher = options.fetchImpl || (root.fetch && root.fetch.bind(root));
    if (!fetcher) throw new Error("Fetch is not available in this browser");
    let stopped = false, controller = null, lastEventId = "", backoff = 500;
    const done = (async () => {
      while (!stopped) {
        const token = typeof options.getToken === "function" ? options.getToken() : options.token;
        if (!token) break;
        controller = new AbortController();
        try {
          const headers = new Headers({ Accept: "text/event-stream", Authorization: "Bearer " + token });
          if (lastEventId) headers.set("Last-Event-ID", lastEventId);
          const response = await fetcher(options.url, { method: "GET", headers, cache: "no-store", signal: controller.signal });
          if (!response.ok || !response.body) {
            const error = new Error("Job event stream unavailable (" + response.status + ")");
            error.status = response.status;
            if ([400, 401, 403, 404, 405, 422].includes(response.status)) {
              if (options.onUnavailable) options.onUnavailable(error);
              break;
            }
            throw error;
          }
          const reader = response.body.getReader(), decoder = new TextDecoder();
          const parser = createSseParser(event => {
            if (event.id && /^\d+$/.test(event.id)) lastEventId = event.id;
            if (event.event === "stream_error") {
              if (options.onError) options.onError(new Error("The server reported a stream error"));
              return;
            }
            if (options.onEvent) options.onEvent(event);
          });
          backoff = 500;
          try {
            while (!stopped) {
              const part = await reader.read();
              if (part.done) break;
              parser.push(decoder.decode(part.value, { stream: true }));
            }
            parser.push(decoder.decode());
            parser.finish();
          } finally { try { reader.releaseLock(); } catch (_) {} }
          if (!stopped) await delay(250);
        } catch (error) {
          if (stopped || error.name === "AbortError") break;
          if (options.onError) options.onError(error);
          await delay(backoff);
          backoff = Math.min(backoff * 2, 5000);
        } finally { controller = null; }
      }
    })();
    return {
      stop() { stopped = true; if (controller) controller.abort(); },
      getLastEventId() { return lastEventId; },
      done
    };
  }
  return { createSseParser, start };
});
