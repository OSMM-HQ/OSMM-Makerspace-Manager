type ImageThumbnailProps = {
  src?: string | null;
  alt: string;
  className?: string;
};

export function ImageThumbnail({ src, alt, className = "h-12 w-12" }: ImageThumbnailProps) {
  return (
    <div className={`${className} shrink-0 overflow-hidden rounded-md border border-line bg-surface`}>
      {src ? (
        <img src={src} alt={alt} className="h-full w-full object-cover" />
      ) : (
        <div className="blueprint-bg h-full w-full" aria-hidden="true" />
      )}
    </div>
  );
}
