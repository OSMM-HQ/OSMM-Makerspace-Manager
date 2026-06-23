export type PublicPrintUploadItem = {
  file: File;
  kind: "stl" | "screenshot";
};

type UploadProgress = (message: string) => void;
type UploadOne = (item: PublicPrintUploadItem) => Promise<number>;

export async function uploadPrintFilesBounded(
  items: PublicPrintUploadItem[],
  uploadOne: UploadOne,
  setProgress: UploadProgress,
  concurrency = 3,
) {
  if (!items.length) return [];
  const fileIds: number[] = [];
  let nextIndex = 0;
  let completed = 0;

  async function worker() {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      setProgress(`Uploading ${completed + 1}/${items.length}`);
      fileIds[index] = await uploadOne(items[index]);
      completed += 1;
      setProgress(`Uploaded ${completed}/${items.length}`);
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(concurrency, items.length) }, () => worker()),
  );
  return fileIds;
}
