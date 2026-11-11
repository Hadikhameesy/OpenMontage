export function parseLastEventId(value: string | null): number {
  if (!value || !/^\d+$/.test(value)) return 0;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 0;
}

export function formatSseEvent(item: Record<string, unknown>): string {
  const sequence = Number(item.sequence);
  if (!Number.isSafeInteger(sequence) || sequence < 1) {
    throw new TypeError("Event sequence must be a positive safe integer");
  }

  const candidate = String(item.event_type ?? "message");
  const eventName = /^[A-Za-z0-9_.-]{1,64}$/.test(candidate) ? candidate : "message";
  return `id: ${sequence}\nevent: ${eventName}\ndata: ${JSON.stringify(item)}\n\n`;
}
