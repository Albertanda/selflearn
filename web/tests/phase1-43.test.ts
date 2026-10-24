import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import CreateKbModal from "../components/knowledge/CreateKbModal";
import KnowledgeHome from "../components/knowledge/KnowledgeHome";
import { createProviders, linkSourceEnabled } from "../lib/ima-connection";
import type {
  KnowledgeUploadPolicy,
  RagProviderSummary,
} from "../lib/knowledge-api";

const PROVIDERS: RagProviderSummary[] = [
  {
    id: "llamaindex",
    name: "LlamaIndex",
    description: "Build a local index from uploaded documents.",
    configured: true,
    linkable: true,
  },
  {
    id: "pageindex",
    name: "PageIndex",
    description: "Cloud outlines; no local folder to link.",
    configured: true,
    linkable: false,
  },
  {
    id: "lightrag-server",
    name: "LightRAG Server",
    description: "Connect an external LightRAG server.",
    configured: true,
    linkable: true,
  },
  {
    id: "ima",
    name: "IMA",
    description: "Tencent IMA knowledge base (read only).",
    configured: true,
    linkable: true,
  },
];

const POLICY: KnowledgeUploadPolicy = {
  extensions: [".pdf", ".md"],
  accept: ".pdf,.md",
  max_file_size_bytes: 50_000_000,
};

const NOOP = () => undefined;
const NOOP_ASYNC = async () => undefined;

function renderModal(mode: "new" | "link"): string {
  return renderToStaticMarkup(
    createElement(CreateKbModal, {
      isOpen: true,
      onClose: NOOP,
      providers: PROVIDERS,
      uploadPolicy: POLICY,
      onCreate: NOOP_ASYNC,
      onConnectLinkedFolder: NOOP_ASYNC,
      onConnectLightRagServer: NOOP_ASYNC,
      onConnectIma: NOOP_ASYNC,
      initialMode: mode,
      initialSource: mode === "link" ? "llamaindex" : undefined,
    }),
  );
}

test("the link dialog renders no Obsidian option or vault copy", () => {
  const html = renderModal("link");
  assert.ok(!/obsidian/i.test(html), html);
  assert.ok(!/vault/i.test(html), html);
  assert.ok(!html.includes("Connect vault"), html);
  assert.ok(!html.includes("Vault path"), html);
});

test("the still-supported link sources render and keep their affordances", () => {
  const html = renderModal("link");
  assert.match(html, /LlamaIndex/);
  assert.match(html, /PageIndex/);
  assert.match(html, /LightRAG Server/);
  assert.match(html, /IMA/);
  assert.match(html, /Read only/);
  assert.match(html, /Folder path/);
  assert.match(html, /Check folder/);
  assert.match(html, /Source/);
});

test("normal document upload still renders in create mode", () => {
  const html = renderModal("new");
  assert.match(html, /Index engine/);
  assert.match(html, /Choose files/);
  assert.match(html, /LlamaIndex/);
  assert.match(html, /PageIndex/);
  assert.ok(!/obsidian/i.test(html), html);
});

test("new-mode provider choices keep filtering IMA as before", () => {
  const ids = createProviders(PROVIDERS).map((provider) => provider.id);
  assert.deepEqual(ids, ["llamaindex", "pageindex", "lightrag-server"]);
  assert.equal(
    linkSourceEnabled(PROVIDERS.find((p) => p.id === "llamaindex")!),
    true,
  );
  assert.equal(
    linkSourceEnabled(PROVIDERS.find((p) => p.id === "lightrag-server")!),
    true,
  );
  assert.equal(
    linkSourceEnabled(PROVIDERS.find((p) => p.id === "ima")!),
    true,
  );
  assert.equal(
    linkSourceEnabled(PROVIDERS.find((p) => p.id === "pageindex")!),
    false,
  );
});

test("the home has no Obsidian create card while historical KBs stay readable", () => {
  const html = renderToStaticMarkup(
    createElement(KnowledgeHome, {
      kbs: [
        {
          name: "分析笔记",
          is_default: true,
          metadata: { rag_provider: "llamaindex", type: "obsidian" },
        },
      ],
      providers: PROVIDERS,
      onOpenKb: NOOP,
      onOpenEngine: NOOP,
      onCreate: NOOP,
    }),
  );
  assert.ok(!/connect vault/i.test(html), html);
  assert.ok(!/connect your obsidian vault/i.test(html), html);
  assert.ok(!/\{\{count\}\} connected/i.test(html), html);
  assert.match(html, /LlamaIndex/);
  assert.match(html, /PageIndex/);
  // A historical obsidian KB still appears in the ordinary KB list (and keeps
  // its historical type label); only the clickable create entry is gone.
  assert.match(html, /分析笔记/);
  assert.match(html, /Obsidian/);
});

test("the historical 501 Obsidian endpoint and its client stay available read-only", () => {
  const backend = readFileSync(
    path.resolve("../deeptutor/api/routers/knowledge.py"),
    "utf8",
  );
  assert.match(backend, /status_code=501/);
  assert.match(backend, /bsidian/);

  const knowledgeApi = readFileSync(
    path.resolve("lib/knowledge-api.ts"),
    "utf8",
  );
  assert.match(knowledgeApi, /connectObsidianVault/);

  // Historical vault metadata stays recognized for existing KBs, without a
  // create path in the modal.
  const helpers = readFileSync(path.resolve("lib/knowledge-helpers.ts"), "utf8");
  assert.match(helpers, /"obsidian"/);
});

test("no component still requires or passes the Obsidian callback", () => {
  for (const file of [
    "components/knowledge/CreateKbModal.tsx",
    "components/knowledge/KnowledgeHome.tsx",
    "components/knowledge/KnowledgePage.tsx",
  ]) {
    const source = readFileSync(path.resolve(file), "utf8");
    assert.ok(!source.includes("onConnectObsidian"), file);
    assert.ok(!source.includes("openObsidian"), file);
  }
});
