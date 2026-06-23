import type React from "react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Modal } from "../../../components/ui/Modal";
import { downloadStaffFile, staffRequest } from "../../../lib/api";
import { Panel, type Makerspace, type Product, useStaffGet } from "./shared";
import { QrImage } from "./QrImage";
import { invalidateContainerViews, invalidateInventoryViews, invalidateQrViews } from "../queryInvalidation";

type ListResponse<T> = { results: T[] };
type Container = { id: number; code: string; label: string; location: string; qr_code_id: number | null };
type QrCode = { id: number; payload: string; target_type: string; target_id: number };
type Batch = { id: number; title: string; status: string; created_at: string };
type BatchItem = { id: number; qr_code: QrCode; label_text: string; target_type: string; target_id: number };
type BatchDetail = Batch & { items: BatchItem[] };
export function QrTools({ makerspace }: { makerspace: Makerspace }) {
  const queryClient = useQueryClient();
  const [batchId, setBatchId] = useState("");
  const [batchTitle, setBatchTitle] = useState("QR labels");
  const [boxId, setBoxId] = useState("");
  const [boxLabel, setBoxLabel] = useState("");
  const [boxLocation, setBoxLocation] = useState("");
  const [productId, setProductId] = useState("");
  const [assetProductId, setAssetProductId] = useState("");
  const [assetCount, setAssetCount] = useState("50");
  const [assetPrefix, setAssetPrefix] = useState("");
  const [batchModalOpen, setBatchModalOpen] = useState(false);
  const [boxModalOpen, setBoxModalOpen] = useState(false);
  const batches = useStaffGet<ListResponse<Batch>>(["qr-batches", makerspace.id], `/admin/makerspace/${makerspace.id}/qr-print-batches`);
  const products = useStaffGet<ListResponse<Product>>(["inventory", makerspace.id], `/admin/makerspace/${makerspace.id}/inventory?page_size=1000`);
  const containers = useStaffGet<ListResponse<Container>>(["containers", makerspace.id], `/admin/makerspace/${makerspace.id}/containers?page_size=1000`);
  const activeBatchId = Number(batchId) || 0;
  const batch = useStaffGet<BatchDetail>(["qr-batch", activeBatchId], `/admin/qr-print-batches/${activeBatchId}`, Boolean(activeBatchId));
  useEffect(() => {
    if (!batchId && batches.data?.results?.length) {
      setBatchId(String(batches.data.results[0].id));
    }
  }, [batchId, batches.data?.results]);

  const selectedAssetProduct = useMemo(
    () => products.data?.results?.find((product) => product.id === Number(assetProductId)),
    [assetProductId, products.data?.results],
  );
  const refreshBatch = () => {
    queryClient.invalidateQueries({ queryKey: ["qr-batches", makerspace.id] });
    if (activeBatchId) queryClient.invalidateQueries({ queryKey: ["qr-batch", activeBatchId] });
  };
  const createBatch = useMutation({
    mutationFn: () =>
      staffRequest<Batch>(`/admin/makerspace/${makerspace.id}/qr-print-batches`, {
        method: "POST",
        body: JSON.stringify({ title: batchTitle.trim() }),
      }),
    onSuccess: (created) => {
      setBatchId(String(created.id));
      setBatchModalOpen(false);
      refreshBatch();
    },
  });
  const addItem = async (qrCodeId: number, labelText: string) => {
    await staffRequest(`/admin/qr-print-batches/${activeBatchId}/items`, {
      method: "POST",
      body: JSON.stringify({ qr_code_id: qrCodeId, label_text: labelText }),
    });
  };
  const addExistingBox = useMutation({
    mutationFn: async () => {
      const box = containers.data?.results?.find((item) => item.id === Number(boxId));
      if (!box) throw new Error("Choose a box to add.");
      if (!box.qr_code_id) throw new Error("This box has no QR code.");
      await addItem(box.qr_code_id, box.label);
      return box;
    },
    onSuccess: refreshBatch,
  });
  const createBox = useMutation({
    mutationFn: async () => {
      const box = await staffRequest<Container>("/admin/qr/containers", {
        method: "POST",
        body: JSON.stringify({ makerspace_id: makerspace.id, label: boxLabel.trim(), location: boxLocation.trim() }),
      });
      if (!box.qr_code_id) throw new Error("Box created without a QR code.");
      await addItem(box.qr_code_id, box.label);
      return box;
    },
    onSuccess: (box) => {
      setBoxLabel("");
      setBoxLocation("");
      setBoxModalOpen(false);
      invalidateContainerViews(queryClient, makerspace.id, box.id);
      refreshBatch();
    },
  });
  const addProduct = useMutation({
    mutationFn: async () => {
      const product = products.data?.results?.find((item) => item.id === Number(productId));
      if (!product) throw new Error("Choose a product to add.");
      const qr = await staffRequest<QrCode>("/admin/qr/tools", {
        method: "POST",
        body: JSON.stringify({ makerspace_id: makerspace.id, product_id: product.id }),
      });
      await addItem(qr.id, product.name);
    },
    onSuccess: refreshBatch,
  });
  const generateAssets = useMutation({
    mutationFn: () =>
      staffRequest(`/admin/products/${Number(assetProductId)}/assets/generate`, {
        method: "POST",
        body: JSON.stringify({
          count: Number(assetCount),
          name_prefix: assetPrefix.trim() || selectedAssetProduct?.name,
          print_batch_id: activeBatchId,
        }),
      }),
    onSuccess: () => {
      invalidateInventoryViews(queryClient, makerspace.id);
      invalidateQrViews(queryClient, makerspace.id);
      refreshBatch();
    },
  });
  const downloadZip = useMutation({
    mutationFn: () =>
      downloadStaffFile(
        `/admin/qr-print-batches/${activeBatchId}/download`,
        `qr-batch-${activeBatchId}.zip`,
      ),
  });
  const hasBatch = Boolean(activeBatchId);
  const batchItems = batch.data?.items ?? [];
  const count = Number(assetCount);
  const canGenerateAssets = hasBatch && Boolean(assetProductId) && Number.isInteger(count) && count > 0 && count <= 200;
  const selectAssetProduct = (nextId: string) => {
    setAssetProductId(nextId);
    setAssetPrefix(products.data?.results?.find((product) => product.id === Number(nextId))?.name ?? "");
  };

  return (
    <Panel title="QR tools">
      <div className="grid gap-4">
        <div className="rounded-md border border-line bg-surface p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Makerspace</p>
              <p className="font-semibold text-ink">{makerspace.name}</p>
            </div>
            <button className="desk-button-primary" type="button" onClick={() => setBatchModalOpen(true)}>
              New batch
            </button>
          </div>
          <select className="desk-input mt-3 w-full" value={batchId} disabled={batches.isLoading} onChange={(event) => setBatchId(event.target.value)}>
            <option value="">Select a print batch</option>
            {batches.data?.results?.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
          {batches.isError ? <ErrorText text={batches.error.message} /> : null}
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          <ActionBox title="Box QR">
            <select className="desk-input w-full" value={boxId} disabled={!hasBatch || containers.isLoading} onChange={(event) => setBoxId(event.target.value)}>
              <option value="">Existing box</option>
              {containers.data?.results?.map((box) => <option key={box.id} value={box.id}>{box.label}</option>)}
            </select>
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="desk-button" type="button" disabled={!hasBatch || !boxId || addExistingBox.isPending} onClick={() => addExistingBox.mutate()}>
                {addExistingBox.isPending ? "Adding..." : "Add box"}
              </button>
              <button className="desk-button" type="button" disabled={!hasBatch} onClick={() => setBoxModalOpen(true)}>
                Create box
              </button>
            </div>
            {addExistingBox.isError ? <ErrorText text={addExistingBox.error.message} /> : null}
          </ActionBox>

          <ActionBox title="Product QR">
            <select className="desk-input w-full" value={productId} disabled={!hasBatch || products.isLoading} onChange={(event) => setProductId(event.target.value)}>
              <option value="">Product</option>
              {products.data?.results?.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
            </select>
            <button className="desk-button mt-2" type="button" disabled={!hasBatch || !productId || addProduct.isPending} onClick={() => addProduct.mutate()}>
              {addProduct.isPending ? "Adding..." : "Add product"}
            </button>
            {addProduct.isError ? <ErrorText text={addProduct.error.message} /> : null}
          </ActionBox>

          <ActionBox title="Individual asset units">
            <select className="desk-input w-full" value={assetProductId} disabled={!hasBatch || products.isLoading} onChange={(event) => selectAssetProduct(event.target.value)}>
              <option value="">Product</option>
              {products.data?.results?.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
            </select>
            <div className="mt-2 grid grid-cols-[90px_1fr] gap-2">
              <input className="desk-input" inputMode="numeric" value={assetCount} onChange={(event) => setAssetCount(event.target.value)} />
              <input className="desk-input" value={assetPrefix} placeholder="Label prefix" onChange={(event) => setAssetPrefix(event.target.value)} />
            </div>
            <button className="desk-button mt-2" type="button" disabled={!canGenerateAssets || generateAssets.isPending} onClick={() => generateAssets.mutate()}>
              {generateAssets.isPending ? "Generating..." : "Generate unit QRs"}
            </button>
            {generateAssets.isError ? <ErrorText text={generateAssets.error.message} /> : null}
          </ActionBox>
        </div>

        <div className="rounded-md border border-line bg-surface p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-ink">{batch.data?.title ?? "Working batch"}</h3>
              <p className="text-sm text-muted">{batchItems.length} QR labels accumulated</p>
            </div>
            <button className="desk-button-primary" type="button" disabled={!batchItems.length || downloadZip.isPending} onClick={() => downloadZip.mutate()}>
              {downloadZip.isPending ? "Preparing..." : "Download all (ZIP)"}
            </button>
          </div>
          {batch.isLoading ? <p className="mt-3 text-sm text-muted">Loading batch...</p> : null}
          {batch.isError ? <ErrorText text={batch.error.message} /> : null}
          {!batch.isLoading && !batchItems.length ? <p className="mt-3 text-sm text-muted">Add box, product, or individual asset unit QR codes to this batch.</p> : null}
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {batchItems.map((item) => (
              <article key={item.id} className="rounded-md border border-line bg-bg p-3 text-center">
                <QrImage qrId={item.qr_code.id} label={item.label_text} />
                <p className="mt-2 text-sm font-semibold text-ink">{item.label_text}</p>
                <p className="text-xs text-muted">{item.target_type} #{item.target_id}</p>
              </article>
            ))}
          </div>
          {downloadZip.isError ? <ErrorText text={(downloadZip.error as Error).message} /> : null}
        </div>
      </div>

      <Modal open={batchModalOpen} onClose={() => setBatchModalOpen(false)} title="Create QR print batch" footer={<ModalActions pending={createBatch.isPending} onCancel={() => setBatchModalOpen(false)} onSubmit={() => createBatch.mutate()} submitLabel="Create batch" disabled={!batchTitle.trim()} />}>
        <input className="desk-input w-full" value={batchTitle} onChange={(event) => setBatchTitle(event.target.value)} />
        {createBatch.isError ? <ErrorText text={createBatch.error.message} /> : null}
      </Modal>

      <Modal open={boxModalOpen} onClose={() => setBoxModalOpen(false)} title="Create box QR" footer={<ModalActions pending={createBox.isPending} onCancel={() => setBoxModalOpen(false)} onSubmit={() => createBox.mutate()} submitLabel="Create and add" disabled={!boxLabel.trim()} />}>
        <div className="grid gap-2">
          <input className="desk-input" value={boxLabel} placeholder="Box label" onChange={(event) => setBoxLabel(event.target.value)} />
          <input className="desk-input" value={boxLocation} placeholder="Location" onChange={(event) => setBoxLocation(event.target.value)} />
        </div>
        {createBox.isError ? <ErrorText text={createBox.error.message} /> : null}
      </Modal>

    </Panel>
  );
}

function ActionBox({ children, title }: { children: React.ReactNode; title: string }) {
  return <section className="rounded-md border border-line bg-surface p-3"><h3 className="mb-2 font-semibold text-ink">{title}</h3>{children}</section>;
}

function ErrorText({ text }: { text: string }) {
  return <p className="mt-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{text}</p>;
}

function ModalActions(props: { pending: boolean; disabled: boolean; submitLabel: string; onCancel: () => void; onSubmit: () => void }) {
  return (
    <div className="flex flex-wrap justify-end gap-2">
      <button className="desk-button" type="button" disabled={props.pending} onClick={props.onCancel}>Cancel</button>
      <button className="desk-button-primary" type="button" disabled={props.pending || props.disabled} onClick={props.onSubmit}>
        {props.pending ? "Saving..." : props.submitLabel}
      </button>
    </div>
  );
}


