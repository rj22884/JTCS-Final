/** Collect files from a paste / clipboard event (images, PDFs, Office docs, etc.). */

const EXT_BY_MIME: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
  "image/gif": "gif",
  "application/pdf": "pdf",
  "text/plain": "txt",
  "application/msword": "doc",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
  "application/vnd.ms-excel": "xls",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
  "application/vnd.ms-powerpoint": "ppt",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
  "audio/mpeg": "mp3",
  "audio/ogg": "ogg",
  "audio/mp4": "m4a",
  "video/mp4": "mp4",
  "video/3gpp": "3gp",
};

const MIME_BY_EXT: Record<string, string> = Object.fromEntries(
  Object.entries(EXT_BY_MIME).map(([mime, ext]) => [ext, mime]),
);

function extensionOf(name: string) {
  const match = name.trim().toLowerCase().match(/\.([a-z0-9]{1,8})$/);
  return match?.[1] || "";
}

/** Ensure pasted clipboard blobs have a usable name + MIME for WhatsApp upload. */
export function normalizeAttachmentFile(file: File, index = 0): File {
  let mime = (file.type || "").trim().toLowerCase();
  let name = (file.name || "").trim();
  const extFromName = extensionOf(name);

  if (!mime && extFromName && MIME_BY_EXT[extFromName]) {
    mime = MIME_BY_EXT[extFromName];
  }
  if (!mime && file.type === "" && name === "") {
    // Screenshot / image copy often arrives as an unnamed image blob.
    mime = "image/png";
  }
  if (!mime) mime = "application/octet-stream";

  if (!name || name === "image" || name === "blob" || name === "untitled") {
    const ext = EXT_BY_MIME[mime] || extFromName || "bin";
    name = `paste-${index + 1}.${ext}`;
  } else if (!extensionOf(name) && EXT_BY_MIME[mime]) {
    name = `${name}.${EXT_BY_MIME[mime]}`;
  }

  if (file.name === name && (file.type || "") === mime) return file;
  return new File([file], name, { type: mime, lastModified: file.lastModified });
}

export function filesFromClipboardData(data: DataTransfer | null): File[] {
  if (!data) return [];
  const collected: File[] = [];
  const seen = new Set<string>();

  if (data.files?.length) {
    for (let i = 0; i < data.files.length; i += 1) {
      const file = data.files.item(i);
      if (!file || file.size <= 0) continue;
      const key = `${file.name}:${file.size}:${file.type}:${file.lastModified}`;
      if (seen.has(key)) continue;
      seen.add(key);
      collected.push(normalizeAttachmentFile(file, collected.length));
    }
  }

  if (data.items?.length) {
    for (let i = 0; i < data.items.length; i += 1) {
      const item = data.items[i];
      if (!item || item.kind !== "file") continue;
      const file = item.getAsFile();
      if (!file || file.size <= 0) continue;
      const key = `${file.name}:${file.size}:${file.type}:${file.lastModified}`;
      if (seen.has(key)) continue;
      seen.add(key);
      collected.push(normalizeAttachmentFile(file, collected.length));
    }
  }

  return collected;
}

export async function filesFromClipboardRead(): Promise<File[]> {
  if (typeof navigator === "undefined" || !navigator.clipboard?.read) return [];
  try {
    const items = await navigator.clipboard.read();
    const files: File[] = [];
    for (const item of items) {
      for (const type of item.types) {
        if (!type.startsWith("image/") && !type.startsWith("application/") && type !== "text/plain") {
          continue;
        }
        if (type === "text/plain" || type === "text/html") continue;
        try {
          const blob = await item.getType(type);
          if (!blob.size) continue;
          const file = new File([blob], "", { type: blob.type || type });
          files.push(normalizeAttachmentFile(file, files.length));
        } catch {
          /* type unavailable */
        }
      }
    }
    return files;
  } catch {
    return [];
  }
}
