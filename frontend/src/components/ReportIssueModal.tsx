"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "./ui/Button";

const MAX_ATTACHMENTS = 5;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const MAX_VIDEO_BYTES = 50 * 1024 * 1024;

export default function ReportIssueModal({
  onClose,
  onSubmit,
  flatLabel,
}: {
  onClose: () => void;
  onSubmit: (formData: FormData) => Promise<void>;
  flatLabel: string;
}) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [attachments, setAttachments] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);

  useEffect(() => {
    const urls = attachments.map(file => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach(url => URL.revokeObjectURL(url));
  }, [attachments]);

  function addAttachments(fileList: FileList | null) {
    if (!fileList?.length) return;
    const selected = Array.from(fileList);
    if (attachments.length + selected.length > MAX_ATTACHMENTS) {
      setError(`Choose no more than ${MAX_ATTACHMENTS} photos and videos combined.`);
      return;
    }
    const oversized = selected.find(file =>
      file.type.startsWith("image/")
        ? file.size > MAX_IMAGE_BYTES
        : file.type.startsWith("video/")
          ? file.size > MAX_VIDEO_BYTES
          : true,
    );
    if (oversized) {
      setError(
        oversized.type.startsWith("video/")
          ? `${oversized.name} is too large. Videos must be 50 MB or smaller.`
          : oversized.type.startsWith("image/")
            ? `${oversized.name} is too large. Photos must be 10 MB or smaller.`
            : "Only photo and video files can be attached.",
      );
      return;
    }
    setError("");
    setAttachments(current => [...current, ...selected]);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (error) return;
    setError("");
    setIsSubmitting(true);
    try {
      const formData = new FormData(event.currentTarget);
      attachments.forEach(file => formData.append("attachments", file));
      await onSubmit(formData);
    } catch (submitError) {
      setError(submitError instanceof Error
        ? submitError.message
        : "Your maintenance request couldn’t be submitted. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="dashboard-modal-backdrop" role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget && !isSubmitting) onClose();
    }}>
      <section
        className="dashboard-modal portal-issue-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-issue-title"
      >
        <button
          className="dashboard-icon-button portal-payment-close"
          type="button"
          aria-label="Close report issue form"
          onClick={onClose}
          disabled={isSubmitting}
        >
          ×
        </button>
        <p className="portal-modal-eyebrow">MAINTENANCE</p>
        <h2 id="report-issue-title">Report an issue</h2>
        <p className="portal-section-description">{flatLabel}</p>
        <form className="portal-issue-form" onSubmit={submit}>
          <label>
            Issue title
            <input name="title" required maxLength={160} placeholder="e.g. Leaking kitchen tap" />
          </label>
          <label>
            Category
            <select name="category" defaultValue="general">
              <option value="general">General repair</option>
              <option value="plumbing">Plumbing</option>
              <option value="electrical">Electrical</option>
              <option value="appliance">Appliance</option>
              <option value="security">Security</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            Priority
            <select name="priority" defaultValue="normal">
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
              <option value="urgent">Urgent</option>
            </select>
          </label>
          <label>
            Describe the issue
            <textarea name="description" required rows={4} maxLength={3000} />
          </label>
          <fieldset className="portal-issue-media">
            <legend>Photos and videos <span className="portal-field-optional">(optional, up to 5)</span></legend>
            <div className="portal-issue-media-actions">
              <label className="portal-media-button">
                Take photo
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onChange={event => {
                    addAttachments(event.currentTarget.files);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              <label className="portal-media-button">
                Record video
                <input
                  type="file"
                  accept="video/*"
                  capture="environment"
                  onChange={event => {
                    addAttachments(event.currentTarget.files);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              <label className="portal-media-button">
                Choose files
                <input
                  type="file"
                  accept="image/*,video/*"
                  multiple
                  onChange={event => {
                    addAttachments(event.currentTarget.files);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
            </div>
            <small className="portal-field-optional">Photos up to 10 MB each; videos up to 50 MB each.</small>
            {attachments.length > 0 && (
              <div className="portal-issue-media-list">
                {attachments.map((file, index) => (
                  <div className="portal-issue-media-item" key={`${file.name}-${file.lastModified}-${index}`}>
                    {file.type.startsWith("video/")
                      ? <video src={previews[index]} controls preload="metadata" aria-label={`Preview ${file.name}`} />
                      : <img src={previews[index]} alt={`Preview ${file.name}`} />}
                    <span title={file.name}>{file.name}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${file.name}`}
                      onClick={() => {
                        setError("");
                        setAttachments(current => current.filter((_, fileIndex) => fileIndex !== index));
                      }}
                    >×</button>
                  </div>
                ))}
              </div>
            )}
          </fieldset>
          {error && <p className="dashboard-form-error" role="alert">{error}</p>}
          <div className="portal-issue-actions">
            <Button type="button" variant="secondary" onClick={onClose} disabled={isSubmitting}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Submitting…" : "Submit request"}
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}
