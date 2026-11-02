export type Source = { file: string; page: number | null; chunk_id?: string; document_id?: string;
  version_id?: string; page_label?: string; excerpt?: string; original_available?: boolean };
export type StreamEvent =
  | { type: "status" | "token" | "error"; data: string }
  | { type: "sources"; data: Source[] }
  | { type: "meta"; data: { conversation_id: string; message_id: string } }
  | { type: "done"; data: null | { conversation_id: string; message_id: string } };

/** Decode SSE frames across arbitrary network and UTF-8 boundaries. */
export async function consumeEvents(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  const dispatch = (frame: string) => {
    const data = frame.split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, "")).join("\n");
    if (!data) return; // Includes keep-alive comments.
    const event = JSON.parse(data) as StreamEvent;
    if (event.type === "error") throw new Error(event.data);
    if (event.type === "done") completed = true;
    onEvent(event);
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, "\n");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        dispatch(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
      }
      if (done) break;
    }
    if (buffer.trim()) dispatch(buffer);
    if (!completed) throw new Error("The response was interrupted. Please try again.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
