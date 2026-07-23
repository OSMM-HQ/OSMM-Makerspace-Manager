export type GeolocationReading = { latitude: number; longitude: number; accuracy: number };

type NavigatorLike = Pick<Navigator, "geolocation">;

export async function presenceStartLocation(geofenceEnabled: boolean, browser?: NavigatorLike): Promise<Partial<GeolocationReading>> {
  if (!geofenceEnabled) return {};
  try {
    return await requestGeolocation(browser);
  } catch {
    return {};
  }
}

export function requestGeolocation(browser: NavigatorLike | undefined = typeof navigator === "undefined" ? undefined : navigator): Promise<GeolocationReading> {
  if (!browser?.geolocation) return Promise.reject(new Error("Location is unavailable in this browser. Use a device with location services enabled and retry."));
  return new Promise((resolve, reject) => {
    browser.geolocation.getCurrentPosition(
      (position) => resolve({ latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy }),
      (error) => reject(new Error(geolocationErrorMessage(error.code))),
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 0 },
    );
  });
}

export function geolocationErrorMessage(code: number) {
  if (code === 1) return "Location permission was denied. Allow location access and retry.";
  if (code === 3) return "Location request timed out. Move to an open area and retry.";
  return "Your location is unavailable. Check location services and retry.";
}
