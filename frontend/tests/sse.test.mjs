import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";
const source = fs.readFileSync(new URL("../lib/sse.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const exportsObject = {};
new Function("exports", compiled)(exportsObject);
const { consumeEvents } = exportsObject;

function stream(bytes) {
  return new ReadableStream({ start(controller) {
    for (const part of bytes) controller.enqueue(part);
    controller.close();
  }});
}
test("handles byte-by-byte UTF-8, CRLF, multiple frames, and keep-alives", async () => {
  const text = ': keep-alive\r\n\r\ndata: {"type":"token","data":"Hello caf?"}\r\n\r\ndata: {"type":"done","data":null}\r\n\r\n';
  const bytes = new TextEncoder().encode(text);
  const events = [];
  await consumeEvents(stream(Array.from(bytes, byte => new Uint8Array([byte]))), e => events.push(e));
  assert.deepEqual(events, [{ type: "token", data: "Hello caf?" }, { type: "done", data: null }]);
});
test("surfaces server errors", async () => {
  const bytes = new TextEncoder().encode('data: {"type":"error","data":"Model unavailable"}\n\n');
  await assert.rejects(consumeEvents(stream([bytes]), () => {}), /Model unavailable/);
});
test("detects truncated streams instead of silently succeeding", async () => {
  const bytes = new TextEncoder().encode('data: {"type":"token","data":"Partial"}\n\n');
  await assert.rejects(consumeEvents(stream([bytes]), () => {}), /interrupted/);
});
