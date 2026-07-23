import { publicV1Request } from "../../lib/api";

export type SocialProvider = "google" | "apple";
export type SocialSurface = "member" | "staff";
export type SocialLoginResult = {
  access: string;
  user: Record<string, unknown>;
  outcome: "created" | "existing" | "auto_linked";
};
export type SocialConfig = {
  google?: { enabled: boolean; web_client_id: string };
  apple?: { enabled: boolean; service_id: string };
};

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(options: Record<string, unknown>): void;
          renderButton(element: HTMLElement, options: Record<string, unknown>): void;
        };
      };
    };
    AppleID?: {
      auth: {
        init(options: Record<string, unknown>): void;
        signIn(): Promise<{ authorization: { id_token: string }; user?: { name?: { firstName?: string; lastName?: string } } }>;
      };
    };
  }
}

const scripts = new Map<string, Promise<void>>();

function loadScript(src: string) {
  const existing = scripts.get(src);
  if (existing) return existing;
  const pending = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Unable to load the identity provider."));
    document.head.appendChild(script);
  });
  scripts.set(src, pending);
  return pending;
}

async function requestNonce(provider: SocialProvider, surface: SocialSurface) {
  return publicV1Request<{ nonce: string }>("/auth/social/nonce", {
    method: "POST",
    body: JSON.stringify({
      provider,
      surface,
      delivery: "web",
      client_platform: "web",
    }),
  });
}

async function complete(provider: SocialProvider, surface: SocialSurface, idToken: string, nonce: string, appleName = "") {
  return publicV1Request<SocialLoginResult>(`/auth/social/${provider}`, {
    method: "POST",
    credentials: "include",
    body: JSON.stringify({
      id_token: idToken,
      nonce,
      surface,
      delivery: "web",
      client_platform: "web",
      ...(appleName ? { apple_name: appleName } : {}),
    }),
  });
}

export async function mountGoogleButton(
  element: HTMLElement,
  clientId: string,
  surface: SocialSurface,
  onSuccess: (result: SocialLoginResult) => void,
  onError: (error: Error) => void,
) {
  const { nonce } = await requestNonce("google", surface);
  await loadScript("https://accounts.google.com/gsi/client");
  if (!window.google) throw new Error("Google sign-in is unavailable.");
  window.google.accounts.id.initialize({
    client_id: clientId,
    nonce,
    callback: async ({ credential }: { credential?: string }) => {
      if (!credential) return onError(new Error("Google sign-in was cancelled."));
      try {
        onSuccess(await complete("google", surface, credential, nonce));
      } catch (error) {
        onError(error instanceof Error ? error : new Error("Google sign-in failed."));
      }
    },
  });
  window.google.accounts.id.renderButton(element, {
    type: "standard",
    theme: "outline",
    size: "large",
    width: Math.min(360, Math.max(240, element.clientWidth || 320)),
  });
}

export async function signInWithApple(serviceId: string, surface: SocialSurface) {
  const { nonce } = await requestNonce("apple", surface);
  await loadScript("https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js");
  if (!window.AppleID) throw new Error("Apple sign-in is unavailable.");
  window.AppleID.auth.init({
    clientId: serviceId,
    scope: "name email",
    redirectURI: window.location.origin,
    usePopup: true,
    nonce,
  });
  const result = await window.AppleID.auth.signIn();
  const name = [result.user?.name?.firstName, result.user?.name?.lastName].filter(Boolean).join(" ");
  return complete("apple", surface, result.authorization.id_token, nonce, name);
}
