import { configuredApiUrl } from "./runtimeConfig";

export const API_URL = configuredApiUrl();

export const API_V1_URL = API_URL.replace(/\/api$/, "/api/v1");
const PUBLIC_CLIENT_ID = import.meta.env.VITE_PUBLIC_CLIENT_ID ?? "";
const ACCESS_TOKEN_KEY = "makerspace.access";
const REFRESH_CSRF_HEADER = "X-Refresh-CSRF";
let runtimePublishableKey = import.meta.env.VITE_PUBLIC_API_KEY ?? "";
let accessToken = "";
let accessRefreshPromise: Promise<boolean> | null = null;
const tenantPublishableKeys = new Map<string, string>();
const authExpiredListeners = new Set<() => void>();

export type TenantBootstrap = {
  makerspace: {
    id: number;
    name: string;
    slug: string;
    public_code: string;
    location: string;
    map_url?: string;
    logo_url?: string | null;
    cover_image_url?: string | null;
    public_stats_enabled?: boolean;
  };
  frontend: {
    type: string;
    hostname: string;
    allowed_origins: string[];
  };
  modules: string[];
  workflows: string[];
  theme: Record<string, string>;
  branding: Record<string, string>;
  email_enabled: boolean;
  public_api: {
    base_url: string;
    publishable_key: string;
    inventory_path: string;
  };
};

export type StaffAuthUser = {
  username: string;
  role: string;
  is_superuser: boolean;
  must_change_password: boolean;
  makerspaces: { id: number; slug: string; role: string }[];
};

function messageForStatus(status: number): string {
  if (status === 401) {
    return "Inventory client is not authorized";
  }

  if (status === 404) {
    return "Makerspace not found";
  }

  if (status >= 500) {
    return "Inventory service is unavailable";
  }

  return "Unable to load inventory";
}

async function publicHeaders(publishableKey?: string): Promise<HeadersInit> {
  if (PUBLIC_CLIENT_ID) {
    return { "X-Client-Id": PUBLIC_CLIENT_ID };
  }
  const key = publishableKey || runtimePublishableKey;
  return key ? { "X-Publishable-Key": key } : {};
}

export function setRuntimePublishableKey(key: string) {
  runtimePublishableKey = key;
}

export function cacheTenantPublishableKey(slug: string, key: string) {
  const normalized = slug.trim();
  if (normalized && key) {
    tenantPublishableKeys.set(normalized, key);
  }
}

export function getAccessToken() {
  return accessToken;
}

export function cleanupLegacyAccessToken() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function authHeaders(): HeadersInit {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

export function addAuthExpiredListener(listener: () => void) {
  authExpiredListeners.add(listener);
  return () => {
    authExpiredListeners.delete(listener);
  };
}

export function expireStaffAuthSession() {
  clearAccessToken();
  authExpiredListeners.forEach((listener) => listener());
}

function canRefreshAfterUnauthorized(path: string) {
  return !["/auth/login", "/auth/refresh", "/auth/logout"].includes(path);
}

export async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: await publicHeaders(),
  });

  if (!response.ok) {
    throw new Error(`${messageForStatus(response.status)} (${response.status})`);
  }

  return (await response.json()) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  return fetchJson<T>(`${API_URL}${path}`);
}

export async function publicV1Request<T>(
  path: string,
  options: RequestInit = {},
  publishableKey?: string,
): Promise<T> {
  const response = await fetch(`${API_V1_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(await publicHeaders(publishableKey)),
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      body.detail ??
        Object.values(body).flat().join(" ") ??
        `Request failed (${response.status})`,
    );
  }

  return (await response.json()) as T;
}

export async function bootstrapTenant(params: { tenant?: string; slug?: string }) {
  const search = new URLSearchParams();
  if (params.tenant) search.set("tenant", params.tenant);
  if (params.slug) search.set("slug", params.slug);
  const bootstrap = await publicV1Request<TenantBootstrap>(
    `/bootstrap?${search.toString()}`,
  );
  cacheTenantPublishableKey(
    bootstrap.makerspace.slug,
    bootstrap.public_api.publishable_key,
  );
  return bootstrap;
}

export async function tenantPublicRequest<T>(
  slug: string,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const normalized = slug.trim();
  let publishableKey = tenantPublishableKeys.get(normalized);
  if (!publishableKey) {
    const bootstrap = await bootstrapTenant({ slug: normalized });
    publishableKey = bootstrap.public_api.publishable_key;
  }
  return publicV1Request<T>(path, options, publishableKey);
}

export function setAccessToken(token: string) {
  accessToken = token;
  cleanupLegacyAccessToken();
}

export function clearAccessToken() {
  accessToken = "";
  cleanupLegacyAccessToken();
}

export async function refreshAccessToken(): Promise<boolean> {
  if (!accessRefreshPromise) {
    accessRefreshPromise = (async () => {
      const response = await fetch(`${API_V1_URL}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: {
          [REFRESH_CSRF_HEADER]: "1",
        },
      }).catch(() => null);

      if (!response?.ok) {
        return false;
      }

      const body = (await response.json().catch(() => ({}))) as { access?: string };
      if (!body.access) {
        return false;
      }

      setAccessToken(body.access);
      return true;
    })().finally(() => {
      accessRefreshPromise = null;
    });
  }

  return accessRefreshPromise;
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${API_V1_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: {
        [REFRESH_CSRF_HEADER]: "1",
      },
    });
  } finally {
    clearAccessToken();
  }
}

export async function fetchMe(): Promise<StaffAuthUser> {
  return staffRequest<StaffAuthUser>("/auth/me");
}

export async function staffRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const makeRequest = () =>
    fetch(`${API_V1_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(options.headers ?? {}),
      },
    });

  let response = await makeRequest();

  if (response.status === 401 && canRefreshAfterUnauthorized(path)) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await makeRequest();
      if (response.status === 401) {
        expireStaffAuthSession();
      }
    } else {
      expireStaffAuthSession();
    }
  }

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => ({}));
    const flattenMessages = (value: unknown): string[] => {
      if (typeof value === "string") {
        const message = value.trim();
        return message ? [message] : [];
      }
      if (Array.isArray(value)) {
        return value.flatMap(flattenMessages);
      }
      if (value && typeof value === "object") {
        return Object.values(value).flatMap(flattenMessages);
      }
      return [];
    };
    const detail =
      body && typeof body === "object" && !Array.isArray(body)
        ? (body as { detail?: unknown }).detail
        : undefined;
    const message =
      (typeof detail === "string" ? detail.trim() : "") ||
      (body && typeof body === "object" && !Array.isArray(body)
        ? Object.values(body).flatMap(flattenMessages).join(" ")
        : "") ||
      `Request failed (${response.status})`;
    throw new Error(message);
  }
  // 204 No Content (e.g. DRF destroy) has an empty body — parsing it as JSON
  // would throw and surface a successful mutation as a failure.
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function downloadStaffFile(path: string, filename: string) {
  const response = await fetch(`${API_V1_URL}${path}`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`Download failed (${response.status})`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
