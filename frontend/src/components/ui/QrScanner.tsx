import { useEffect, useRef, useState } from "react";

type QrScannerProps = {
  onScan: (payload: string) => void;
  onClose: () => void;
};

let zxingReaderPromise: Promise<typeof import("zxing-wasm/reader")> | null = null;

export default function QrScanner({ onScan, onClose }: QrScannerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<number | null>(null);
  const detectorRef = useRef<any>(null);
  const nativeFailedRef = useRef(false);
  const onScanRef = useRef(onScan);
  const lastScanRef = useRef({ value: "", at: 0 });
  const isDetectingRef = useRef(false);
  const [error, setError] = useState("");

  const stopScanner = () => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const emitScan = (value: string) => {
    const payload = value.trim();
    const now = Date.now();
    if (!payload) return;
    if (lastScanRef.current.value === payload && now - lastScanRef.current.at < 1500) return;
    lastScanRef.current = { value: payload, at: now };
    onScanRef.current(payload);
  };

  useEffect(() => {
    onScanRef.current = onScan;
  }, [onScan]);

  useEffect(() => {
    let cancelled = false;

    const detect = async () => {
      const video = videoRef.current;
      if (!video || isDetectingRef.current || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
      isDetectingRef.current = true;
      try {
        if ("BarcodeDetector" in window && !nativeFailedRef.current) {
          try {
            const Detector = (window as any).BarcodeDetector;
            detectorRef.current ??= new Detector({ formats: ["qr_code"] });
            const results = await detectorRef.current.detect(video);
            emitScan(results[0]?.rawValue ?? "");
          } catch {
            // Native BarcodeDetector exists but can't construct/read qr_code on this
            // browser — stop retrying it and fall through to the zxing-wasm reader.
            nativeFailedRef.current = true;
            detectorRef.current = null;
          }
        } else {
          zxingReaderPromise ??= import("zxing-wasm/reader");
          const { readBarcodesFromImageData } = await zxingReaderPromise;
          const width = video.videoWidth;
          const height = video.videoHeight;
          if (!width || !height) return;
          const canvas = document.createElement("canvas");
          canvas.width = width;
          canvas.height = height;
          const context = canvas.getContext("2d");
          if (!context) return;
          context.drawImage(video, 0, 0, width, height);
          const imageData = context.getImageData(0, 0, width, height);
          const results = await readBarcodesFromImageData(imageData, { formats: ["QRCode"] });
          emitScan(results[0]?.text ?? "");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "QR scanner could not start.");
        stopScanner();
      } finally {
        isDetectingRef.current = false;
      }
    };

    const start = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play();
        }
        intervalRef.current = window.setInterval(detect, 400);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Camera access was denied.");
      }
    };

    start();
    return () => {
      cancelled = true;
      stopScanner();
    };
  }, []);

  const close = () => {
    stopScanner();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 sm:p-4">
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col gap-3 overflow-y-auto rounded-lg border border-line bg-panel p-4 shadow-xl">
        {error ? (
          <div className="grid gap-3">
            <p className="text-sm text-danger">{error}</p>
            <button className="desk-button w-full" type="button" onClick={close}>
              Close
            </button>
          </div>
        ) : (
          <div className="grid gap-3">
            <video ref={videoRef} className="aspect-video max-h-[60vh] w-full rounded-md bg-black object-cover" autoPlay muted playsInline />
            <p className="text-center text-sm text-muted">Point the camera at a QR code</p>
            <button className="desk-button-primary w-full" type="button" onClick={close}>
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
