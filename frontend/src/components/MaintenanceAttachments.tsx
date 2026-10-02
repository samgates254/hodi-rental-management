"use client";

import { useEffect, useState } from "react";
import { clientApi } from "@/lib/clientApi";

export type MaintenanceAttachment = {
  id: number | string;
  url: string;
  file_name: string;
  content_type: string;
  media_type: "IMAGE" | "VIDEO";
};

function MaintenanceAttachmentItem({ attachment }: { attachment: MaintenanceAttachment }) {
  const [source, setSource] = useState("");
  const [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";
    setSource("");
    setLoadError("");
    void clientApi.get<Blob>(attachment.url, { responseType: "blob" })
      .then(response => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(response.data);
        setSource(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setLoadError("This attachment couldn’t be loaded.");
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [attachment.url, retry]);

  if (loadError) {
    return (
      <div className="portal-attachment-error" role="alert">
        <span>{loadError}</span>
        <button type="button" onClick={() => setRetry(value => value + 1)}>Retry</button>
      </div>
    );
  }
  if (!source) {
    return <span className="portal-attachment-loading" role="status">Loading {attachment.file_name}…</span>;
  }

  return attachment.media_type === "VIDEO" ? (
    <video
      className="portal-issue-video"
      src={source}
      controls
      preload="metadata"
      aria-label={attachment.file_name}
    />
  ) : (
    <a href={source} target="_blank" rel="noreferrer" aria-label={`Open ${attachment.file_name}`}>
      <img src={source} alt={attachment.file_name} loading="lazy" />
    </a>
  );
}

export default function MaintenanceAttachments({
  attachments,
}: {
  attachments?: MaintenanceAttachment[];
}) {
  if (!attachments?.length) return null;

  return (
    <div className="portal-issue-gallery">
      {attachments.map(attachment => (
        <MaintenanceAttachmentItem key={attachment.id} attachment={attachment} />
      ))}
    </div>
  );
}
