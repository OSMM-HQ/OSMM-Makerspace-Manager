import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import { Card } from "../../components/ui/Card";
import { formatSlug } from "../inventory/PublicInventoryParts";
import { useTenantBootstrap } from "../inventory/usePublicInventory";
import { StatusResult, SubmittedTokenCard } from "./PublicPrintRequestParts";
import {
  PrintDetailsForm,
  initialForm,
  optional,
  type FormState,
} from "./PublicPrintRequestForm";
import {
  fetchPublicSpools,
  fetchPrintStatus,
  presignPrintUpload,
  submitPrintRequest,
  uploadToStorage,
  verifyPrintCheckin,
} from "./publicApi";

export function PublicPrintRequestPage() {
  const { slug } = useParams();
  const makerspaceSlug = slug ?? "";
  const [identifier, setIdentifier] = useState("");
  const [verifiedIdentifier, setVerifiedIdentifier] = useState("");
  const [verifiedName, setVerifiedName] = useState("");
  const [form, setForm] = useState<FormState>(initialForm);
  const [modelFiles, setModelFiles] = useState<File[]>([]);
  const [screenshotFiles, setScreenshotFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState("");
  const [submittedToken, setSubmittedToken] = useState("");
  const statusLinkHandledRef = useRef(false);
  // Anti-spam honeypot: hidden from real users; a bot that autofills it triggers the
  // backend decoy-success (no request created).
  const [website, setWebsite] = useState("");

  const bootstrapQuery = useTenantBootstrap(makerspaceSlug);
  const spoolsQuery = useQuery({
    queryKey: ["public-print-spools", makerspaceSlug],
    queryFn: () => fetchPublicSpools(makerspaceSlug),
    enabled: Boolean(makerspaceSlug),
  });
  const statusMutation = useMutation({
    mutationFn: (token: string) => fetchPrintStatus(token.trim()),
  });
  useEffect(() => {
    if (statusLinkHandledRef.current) {
      return;
    }
    statusLinkHandledRef.current = true;
    const token = new URLSearchParams(window.location.search).get("token")?.trim();
    if (token) {
      statusMutation.mutate(token);
    }
  }, [statusMutation]);
  const verifyMutation = useMutation({
    mutationFn: (id: string) => verifyPrintCheckin(makerspaceSlug, id),
    onSuccess: (data, id) => {
      setVerifiedIdentifier(id);
      setVerifiedName(data.username);
    },
  });
  const verified =
    identifier.trim().length > 0 && identifier.trim() === verifiedIdentifier;
  const displayName =
    bootstrapQuery.data?.branding.display_name ||
    bootstrapQuery.data?.makerspace.name ||
    formatSlug(makerspaceSlug) ||
    "Makerspace";

  const submitMutation = useMutation({
    mutationFn: async () => {
      const fileIds: number[] = [];
      const files = [
        ...modelFiles.map((file) => ({ file, kind: "stl" as const })),
        ...screenshotFiles.map((file) => ({ file, kind: "screenshot" as const })),
      ];

      for (const [index, item] of files.entries()) {
        setUploadProgress(`Uploading ${index + 1}/${files.length}`);
        const presigned = await presignPrintUpload(makerspaceSlug, {
          identifier: identifier.trim(),
          kind: item.kind,
          filename: item.file.name,
          content_type:
            item.kind === "stl"
              ? item.file.type || "application/octet-stream"
              : item.file.type,
        });
        await uploadToStorage(presigned.upload, item.file);
        fileIds.push(presigned.file_id);
      }

      setUploadProgress(files.length ? "Submitting request..." : "");
      // Material/color are no longer free-text fields; the chosen spool is the single
      // source, so derive them from it for staff display (empty when "No preference").
      const chosenSpool = spoolsQuery.data?.find(
        (spool) => String(spool.id) === form.filamentSpoolId,
      );
      return submitPrintRequest(makerspaceSlug, {
        website,
        identifier: identifier.trim(),
        requester_name: optional(form.requesterName),
        title: form.title.trim(),
        project_brief: optional(form.projectBrief),
        preferred_settings: optional(form.preferredSettings),
        material: chosenSpool?.material || undefined,
        color: chosenSpool?.color || undefined,
        filament_spool_id: form.filamentSpoolId
          ? Number(form.filamentSpoolId)
          : null,
        quantity: form.quantity,
        source_link: optional(form.sourceLink),
        contact_email: optional(form.contactEmail),
        contact_phone: optional(form.contactPhone),
        file_ids: fileIds,
      });
    },
    onSuccess: (response) => {
      setUploadProgress("");
      setSubmittedToken(response.public_token);
      statusMutation.mutate(response.public_token);
    },
    onError: () => setUploadProgress(""),
  });

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (verified && form.title.trim()) {
      submitMutation.mutate();
    }
  }

  return (
    <main className="desk-shell">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-screen-xl flex-col gap-4 px-5 py-6 sm:px-8">
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">
            Public 3D Print Request
          </p>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-3xl font-bold text-ink sm:text-4xl">
                {displayName}
              </h1>
              <p className="mt-2 text-sm text-muted">
                Submit print files — we'll email you status updates at every step.
              </p>
            </div>
            <Link className="desk-button" to={`/m/${makerspaceSlug}`}>
              Back to inventory
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-screen-xl gap-5 px-5 py-6 lg:grid-cols-[minmax(0,1fr)_360px] sm:px-8">
        <div className="space-y-4">
          <Card>
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">
              Check-In
            </p>
            <label className="mt-3 block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
                Check-In email or phone
              </span>
              <input
                className="desk-input w-full"
                placeholder="Email or phone used at Check-In"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
              />
            </label>
            <button
              className="desk-button mt-3"
              disabled={!identifier.trim() || verifyMutation.isPending}
              type="button"
              onClick={() => verifyMutation.mutate(identifier.trim())}
            >
              {verifyMutation.isPending ? "Verifying..." : "Verify Check-In"}
            </button>
            {verified ? (
              <p className="mt-3 rounded-md border border-success/40 bg-success/10 px-3 py-2 text-sm text-success">
                Check-In verified{verifiedName ? ` for ${verifiedName}` : ""}
              </p>
            ) : null}
            {verifyMutation.error ? (
              <p className="mt-3 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                {verifyMutation.error.message}
              </p>
            ) : null}
          </Card>

          <PrintDetailsForm
            form={form}
            updateField={updateField}
            spoolsQuery={spoolsQuery}
            modelFiles={modelFiles}
            setModelFiles={setModelFiles}
            screenshotFiles={screenshotFiles}
            setScreenshotFiles={setScreenshotFiles}
            verified={verified}
            submitPending={submitMutation.isPending}
            submitError={submitMutation.error}
            uploadProgress={uploadProgress}
            website={website}
            onWebsiteChange={setWebsite}
            onSubmit={submitForm}
          />
        </div>

        <aside className="space-y-4 lg:sticky lg:top-0 lg:max-h-[100dvh] lg:overflow-y-auto">
          {submittedToken ? <SubmittedTokenCard token={submittedToken} /> : null}
          <Card>
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">
              Status Tracker
            </p>
            <p className="mt-3 text-sm text-muted">
              We email status updates to your contact email at every step
              (received → accepted → printing → ready to collect). Open the link in
              those emails to see the live status here — no token to copy.
            </p>
            <div className="mt-4">
              <StatusResult
                error={statusMutation.error}
                isPending={statusMutation.isPending}
                status={statusMutation.data}
              />
            </div>
          </Card>
        </aside>
      </section>
    </main>
  );
}
