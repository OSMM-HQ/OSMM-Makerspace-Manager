import { useState } from "react";

import { publicV1Request } from "../../lib/api";

const RESET_SENT_MESSAGE =
  "If an account exists for that email, a reset link has been sent. Check your inbox.";

export function LoginPanel({
  error,
  guestOnly,
  isPending,
  onSubmit,
}: {
  error?: string;
  guestOnly: boolean;
  isPending: boolean;
  onSubmit: (payload: { username: string; password: string }) => void;
}) {
  const [mode, setMode] = useState<"login" | "forgot">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [forgotPending, setForgotPending] = useState(false);
  const [forgotMessage, setForgotMessage] = useState("");

  if (mode === "forgot") {
    return (
      <main className="desk-shell grid place-items-center px-5">
        <form
          className="desk-panel w-full max-w-md p-6"
          onSubmit={async (event) => {
            event.preventDefault();
            setForgotPending(true);
            setForgotMessage("");
            try {
              await publicV1Request("/auth/forgot-password", {
                method: "POST",
                body: JSON.stringify({ email }),
              });
            } catch {
              // Keep the forgot-password flow enumeration-safe even if the
              // endpoint or network fails unexpectedly.
            } finally {
              setForgotMessage(RESET_SENT_MESSAGE);
              setForgotPending(false);
            }
          }}
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            Account access
          </p>
          <h1 className="mt-2 text-2xl font-bold text-ink">Reset password</h1>
          <p className="mt-2 text-sm text-muted">
            Enter your staff email and we will send a reset link if the account exists.
          </p>
          <label className="mt-5 block text-sm font-semibold">Email</label>
          <input
            className="desk-input mt-1 w-full"
            name="email"
            autoComplete="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {forgotMessage ? <p className="mt-3 text-sm text-muted">{forgotMessage}</p> : null}
          <button
            className="desk-button-primary mt-5 flex w-full items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-50"
            type="submit"
            disabled={forgotPending}
          >
            {forgotPending ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-bg/40 border-t-bg" />
            ) : null}
            {forgotPending ? "Sending..." : "Send reset link"}
          </button>
          <button
            className="mt-3 w-full text-sm font-semibold text-accent hover:text-accent/80"
            type="button"
            onClick={() => setMode("login")}
          >
            Back to sign in
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="desk-shell grid place-items-center px-5">
      <form
        className="desk-panel w-full max-w-md p-6"
        onSubmit={(event) => {
          event.preventDefault();
          if (isPending) return;
          onSubmit({ username, password });
        }}
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-accent">
          {guestOnly ? "Guest admin desk" : "Space Manager desk"}
        </p>
        <h1 className="mt-2 text-2xl font-bold text-ink">Sign in</h1>
        <p className="mt-2 text-sm text-muted">
          Use your staff account to manage requests, inventory, and handovers.
        </p>
        <label className="mt-5 block text-sm font-semibold">Username</label>
        <input
          className="desk-input mt-1 w-full"
          name="username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <label className="mt-3 block text-sm font-semibold">Password</label>
        <input
          className="desk-input mt-1 w-full"
          name="password"
          autoComplete="current-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
        <button
          className="desk-button-primary mt-5 flex w-full items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-50"
          type="submit"
          disabled={isPending}
        >
          {isPending ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-bg/40 border-t-bg" />
          ) : null}
          {isPending ? "Signing in..." : "Sign in"}
        </button>
        <button
          className="mt-3 w-full text-sm font-semibold text-accent hover:text-accent/80"
          type="button"
          onClick={() => setMode("forgot")}
        >
          Forgot password?
        </button>
      </form>
    </main>
  );
}
