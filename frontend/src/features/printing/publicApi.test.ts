import { afterEach, describe, expect, it, vi } from "vitest";
import { cacheTenantPublishableKey } from "../../lib/api";
import { fetchPrintQueues, fetchPrintStatus, submitPrintRequest } from "./publicApi";

describe("generic public printer service API", () => {
  afterEach(() => vi.restoreAllMocks());
  it("uses machine-service routes for queues, submission, and token status", async () => {
    cacheTenantPublishableKey("forge", "test-key");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify([]), { status: 200 }));
    await fetchPrintQueues("forge");
    await submitPrintRequest("forge", { title: "Bracket", queue_id: 8, consumable_pool_id: 13, file_ids: [] });
    await fetchPrintStatus("private-token");
    const urls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(urls).toEqual(expect.arrayContaining([expect.stringContaining("/public/forge/machine-service/3d-printer/queues"), expect.stringContaining("/public/forge/machine-service/3d-printer/requests"), expect.stringContaining("/public/machine-service/3d-printer/requests/private-token/status")]));
    expect(urls.join(" ")).not.toContain("/printing/");
  });
});
