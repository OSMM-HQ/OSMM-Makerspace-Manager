import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { publicV1Request } from "../../lib/api";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const uid = searchParams.get("uid") ?? "";
  const token = searchParams.get("token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState(false);
  const passwordsMatch = newPassword === confirmPassword;
  const passwordLongEnough = newPassword.length >= 8;
  const canSubmit = passwordsMatch && passwordLongEnough && !pending && !updated;

  return (
    <main className="desk-shell grid place-items-center px-5">
      <section className="desk-panel w-full max-w-md p-6">
        <p className="text-xs font-semibold tracking-wide text-accent-ink">
          Account access
        </p>
        <h1 className="mt-2 text-2xl font-bold text-ink">Set a new password</h1>

        {!uid || !token ? (
          <>
            <p className="mt-4 text-sm text-danger">
              This reset link is invalid or incomplete.
            </p>
            <Link className="desk-button mt-5 w-full" to="/admin">
              Back to sign in
            </Link>
          </>
        ) : updated ? (
          <>
            <p className="mt-4 text-sm text-muted">
              Your password has been updated. You can now sign in.
            </p>
            <Link className="desk-button-primary mt-5 w-full" to="/admin">
              Go to sign in
            </Link>
          </>
        ) : (
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              if (!canSubmit) return;
              setPending(true);
              setError("");
              try {
                await publicV1Request("/auth/reset-password", {
                  method: "POST",
                  body: JSON.stringify({ uid, token, new_password: newPassword }),
                });
                setUpdated(true);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to update password.");
              } finally {
                setPending(false);
              }
            }}
          >
            <label className="mt-5 block text-sm font-semibold">New password</label>
            <input
              className="desk-input mt-1 w-full"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
            <label className="mt-3 block text-sm font-semibold">Confirm password</label>
            <input
              className="desk-input mt-1 w-full"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
            {!passwordLongEnough && newPassword.length > 0 ? (
              <p className="mt-3 text-sm text-danger">
                Password must be at least 8 characters.
              </p>
            ) : null}
            {!passwordsMatch && confirmPassword.length > 0 ? (
              <p className="mt-3 text-sm text-danger">Passwords do not match.</p>
            ) : null}
            {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
            <button
              className="desk-button-primary mt-5 w-full disabled:cursor-not-allowed disabled:opacity-50"
              type="submit"
              disabled={!canSubmit}
            >
              {pending ? "Updating..." : "Update password"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
