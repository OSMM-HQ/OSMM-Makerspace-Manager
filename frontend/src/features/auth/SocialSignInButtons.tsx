import { useEffect, useRef, useState } from "react";

import { publicV1Request } from "../../lib/api";
import {
  mountGoogleButton,
  signInWithApple,
  type SocialConfig,
  type SocialLoginResult,
  type SocialSurface,
} from "./socialSdk";

export function SocialSignInButtons({
  surface,
  onSuccess,
}: {
  surface: SocialSurface;
  onSuccess: (result: SocialLoginResult) => void;
}) {
  const googleHost = useRef<HTMLDivElement>(null);
  const onSuccessRef = useRef(onSuccess);
  const [config, setConfig] = useState<SocialConfig>();
  const [error, setError] = useState("");
  const [applePending, setApplePending] = useState(false);

  useEffect(() => {
    onSuccessRef.current = onSuccess;
  }, [onSuccess]);

  useEffect(() => {
    publicV1Request<{ social_auth?: SocialConfig }>("/config")
      .then((result) => setConfig(result.social_auth ?? {}))
      .catch(() => setConfig({}));
  }, []);

  useEffect(() => {
    const host = googleHost.current;
    if (!host || !config?.google?.enabled) return;
    host.replaceChildren();
    void mountGoogleButton(
      host,
      config.google.web_client_id,
      surface,
      (result) => onSuccessRef.current(result),
      (nextError) => setError(nextError.message),
    ).catch((nextError: unknown) => {
      setError(nextError instanceof Error ? nextError.message : "Google sign-in failed.");
    });
  }, [config, surface]);

  if (!config?.google?.enabled && !config?.apple?.enabled) return null;

  return (
    <section className="mt-5 border-t border-line pt-5" aria-label="Social sign in">
      <p className="mb-3 text-center text-sm text-muted">Or continue with</p>
      <div className="flex flex-col items-center gap-3">
        {config.google?.enabled ? <div ref={googleHost} className="min-h-10 w-full text-center" /> : null}
        {config.apple?.enabled ? (
          <button
            className="desk-button w-full max-w-[360px] bg-ink text-bg"
            type="button"
            disabled={applePending}
            onClick={async () => {
              setApplePending(true);
              setError("");
              try {
                onSuccessRef.current(await signInWithApple(config.apple!.service_id, surface));
              } catch (nextError) {
                setError(nextError instanceof Error ? nextError.message : "Apple sign-in failed.");
              } finally {
                setApplePending(false);
              }
            }}
          >
            {applePending ? "Connecting to Apple…" : "Continue with Apple"}
          </button>
        ) : null}
      </div>
      {error ? <p className="mt-3 text-sm text-danger" role="alert">{error}</p> : null}
    </section>
  );
}
