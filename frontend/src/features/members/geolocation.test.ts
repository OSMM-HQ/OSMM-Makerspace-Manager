import { describe, expect, it, vi } from "vitest";

import { geolocationErrorMessage, presenceStartLocation, requestGeolocation } from "./geolocation";

describe("presence geolocation", () => {
  it("returns browser coordinates for an enabled geofence", async () => {
    const getCurrentPosition = vi.fn((success) => success({ coords: { latitude: 12.9, longitude: 77.5, accuracy: 8 } }));
    await expect(requestGeolocation({ geolocation: { getCurrentPosition } } as unknown as Navigator)).resolves.toEqual({ latitude: 12.9, longitude: 77.5, accuracy: 8 });
    expect(getCurrentPosition).toHaveBeenCalledOnce();
  });

  it.each([[1, "denied"], [2, "unavailable"], [3, "timed out"]])("explains geolocation error %s", (code, wording) => {
    expect(geolocationErrorMessage(code)).toContain(wording);
  });

  it("does not request location for a dormant makerspace", async () => {
    const getCurrentPosition = vi.fn();
    await expect(presenceStartLocation(false, { geolocation: { getCurrentPosition } } as unknown as Navigator)).resolves.toEqual({});
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it("does not block presence start when enabled geolocation fails", async () => {
    const getCurrentPosition = vi.fn((_success, error) => error({ code: 1 }));
    await expect(presenceStartLocation(true, { geolocation: { getCurrentPosition } } as unknown as Navigator)).resolves.toEqual({});
  });

  it("explains a browser without geolocation", async () => {
    await expect(requestGeolocation(undefined)).rejects.toThrow("unavailable");
  });
});
