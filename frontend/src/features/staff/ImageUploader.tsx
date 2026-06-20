import { useState } from "react";

import { staffRequest } from "../../lib/api";

type PresignResponse = {
  object_key: string;
  url: string;
  fields?: Record<string, string>;
  method?: string;
  headers?: Record<string, string>;
};

type ImageUploaderProps = {
  /** Admin endpoint base, e.g. `/admin/inventory/12/image` or `/admin/makerspace/3/logo`. */
  endpoint: string;
  /** Current public image URL (preview), or null/empty when none. */
  currentUrl?: string | null;
  label: string;
  /** Called after a successful attach or clear so the parent can refetch. */
  onChanged: () => void;
  disabled?: boolean;
  /** object-contain (logos) vs object-cover (photos). */
  fit?: "cover" | "contain";
  /** square preview (logos/thumbnails) vs wide banner preview (cover images). */
  shape?: "square" | "wide";
};

/**
 * Reusable public-image uploader for staff (item photos, makerspace logo/cover).
 * Drives the Phase-2 flow: POST → presign, upload via the returned method
 * (POST multipart or PUT), then PUT { object_key } to finalize+attach. The
 * storage upload itself is an unauthenticated direct-to-bucket request.
 */
export function ImageUploader({
  endpoint,
  currentUrl,
  label,
  onChanged,
  disabled = false,
  fit = "cover",
  shape = "square",
}: ImageUploaderProps) {
  // Cover images are wide banners — give them a rectangular preview that matches
  // how they render publicly, instead of cropping into an 80×80 square.
  const previewBox = shape === "wide" ? "h-20 w-44" : "h-20 w-20";
  const [status, setStatus] = useState<"idle" | "uploading" | "error">("idle");
  const [error, setError] = useState("");

  async function handleFile(file: File) {
    setStatus("uploading");
    setError("");
    try {
      const presigned = await staffRequest<PresignResponse>(endpoint, {
        method: "POST",
        body: JSON.stringify({
          content_type: file.type || "application/octet-stream",
          filename: file.name,
        }),
      });

      if (presigned.method === "PUT") {
        const res = await fetch(presigned.url, {
          method: "PUT",
          body: file,
          headers: presigned.headers,
        });
        if (!res.ok) throw new Error(`Storage upload failed (${res.status})`);
      } else {
        const formData = new FormData();
        Object.entries(presigned.fields ?? {}).forEach(([k, v]) => formData.append(k, v));
        formData.append("file", file);
        // Direct presigned POST — no auth header, and do NOT set Content-Type so the
        // browser supplies the multipart boundary.
        const res = await fetch(presigned.url, { method: "POST", body: formData });
        if (!res.ok) throw new Error(`Storage upload failed (${res.status})`);
      }

      await staffRequest(endpoint, {
        method: "PUT",
        body: JSON.stringify({ object_key: presigned.object_key }),
      });
      setStatus("idle");
      onChanged();
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Upload failed.");
    }
  }

  async function clearImage() {
    setStatus("uploading");
    setError("");
    try {
      await staffRequest(endpoint, { method: "DELETE" });
      setStatus("idle");
      onChanged();
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Could not remove image.");
    }
  }

  return (
    <div className="space-y-2">
      <p className="font-mono text-xs uppercase tracking-tight text-muted">{label}</p>
      <div className="flex items-center gap-3">
        <div className={`${previewBox} shrink-0 overflow-hidden border-2 border-ink bg-surface`}>
          {currentUrl ? (
            <img
              src={currentUrl}
              alt={label}
              className={`h-full w-full ${fit === "contain" ? "object-contain" : "object-cover"}`}
            />
          ) : (
            <div className="blueprint-bg grid h-full w-full place-items-center font-mono text-[10px] uppercase text-muted">
              none
            </div>
          )}
        </div>
        <div className="space-y-1">
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={disabled || status === "uploading"}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) handleFile(file);
            }}
            className="block w-full text-sm text-muted file:mr-3 file:border-2 file:border-ink file:bg-accent file:px-3 file:py-1.5 file:font-mono file:text-xs file:font-semibold file:uppercase file:text-on-accent"
          />
          {currentUrl ? (
            <button
              type="button"
              className="font-mono text-xs uppercase text-danger hover:underline disabled:opacity-50"
              disabled={disabled || status === "uploading"}
              onClick={clearImage}
            >
              Remove
            </button>
          ) : null}
          {status === "uploading" ? (
            <p className="font-mono text-xs text-muted">Working…</p>
          ) : null}
          {status === "error" ? <p className="text-xs text-danger">{error}</p> : null}
        </div>
      </div>
    </div>
  );
}
