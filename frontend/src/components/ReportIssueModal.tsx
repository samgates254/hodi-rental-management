"use client";

import { useState, type FormEvent } from "react";
import { Button } from "./ui/Button";

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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await onSubmit(new FormData(event.currentTarget));
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
          <label>
            Add photos <span className="portal-field-optional">(optional, up to 5)</span>
            <input name="images" type="file" accept="image/*" multiple />
          </label>
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
