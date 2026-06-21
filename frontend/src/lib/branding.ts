import type { TenantBootstrap } from "./api";

function setFavicon(url: string) {
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  link.href = url;
}

export function applyTenantBranding(bootstrap: TenantBootstrap) {
  const name =
    bootstrap.branding.display_name ||
    bootstrap.makerspace.name ||
    "Makerspace Manager";
  document.title = name;
  if (typeof bootstrap.theme.logo_url === "string" && bootstrap.theme.logo_url) {
    setFavicon(bootstrap.theme.logo_url);
  }
}
