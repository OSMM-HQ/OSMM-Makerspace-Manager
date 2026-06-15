import { useState } from "react";

export function LoginPanel({
  error,
  guestOnly,
  onSubmit,
}: {
  error?: string;
  guestOnly: boolean;
  onSubmit: (payload: { username: string; password: string }) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  return (
    <main className="desk-shell grid place-items-center px-5">
      <form
        className="desk-panel w-full max-w-md p-6"
        onSubmit={(event) => {
          event.preventDefault();
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
        <button className="desk-button-primary mt-5 w-full" type="submit">
          Sign in
        </button>
      </form>
    </main>
  );
}
