import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AssistantActivity } from "../components/chat/home/TracePanels";
import type { StreamEvent } from "../lib/unified-ws";

test("ungrouped RAG sources stay visible in the expandable activity trace", () => {
  const event: StreamEvent = {
    type:"sources", source:"chat", stage:"responding", content:"", timestamp:1,
    metadata:{trace_kind:"sources", sources:[
      {title:"a-marker.txt", source:"raw/a-marker.txt", kb_ref:"subject:a:kb:assignment-kb", chunk_id:"one"},
      {title:"a-marker.txt", source:"raw/a-marker.txt", kb_ref:"subject:a:kb:assignment-kb", chunk_id:"two"},
    ]},
  };
  const html = renderToStaticMarkup(createElement(AssistantActivity, {events:[event],isStreaming:true}));
  assert.match(html, /a-marker\.txt/);
  assert.equal((html.match(/a-marker\.txt/g) || []).length, 1);
  assert.match(html, /aria-expanded="true"/);
  assert.doesNotMatch(html, /href=/);
});
