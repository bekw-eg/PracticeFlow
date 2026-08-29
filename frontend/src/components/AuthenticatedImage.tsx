import { useEffect, useState, type ImgHTMLAttributes } from "react";

import { api } from "../lib/api";

interface AuthenticatedImageProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> {
  fileId: string;
}

/**
 * File downloads are tenant-protected API calls. A plain <img src> cannot
 * attach the in-memory bearer token, so retrieve the bytes through the
 * authenticated client and expose only a short-lived object URL to the DOM.
 */
export function AuthenticatedImage({ fileId, alt, ...props }: AuthenticatedImageProps) {
  const [objectUrl, setObjectUrl] = useState<string>();

  useEffect(() => {
    const controller = new AbortController();
    let createdUrl: string | undefined;

    void api
      .get<Blob>(`/files/${fileId}`, { responseType: "blob", signal: controller.signal })
      .then((response) => {
        createdUrl = URL.createObjectURL(response.data);
        setObjectUrl(createdUrl);
      })
      .catch(() => {
        if (!controller.signal.aborted) setObjectUrl(undefined);
      });

    return () => {
      controller.abort();
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [fileId]);

  if (!objectUrl) {
    return <span role="img" aria-label={alt} className="inline-block min-h-16 min-w-16 animate-pulse bg-[var(--color-surface)]" />;
  }
  return <img {...props} src={objectUrl} alt={alt} />;
}
