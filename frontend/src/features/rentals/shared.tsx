import { useEffect, useState, type ReactNode } from "react";
import { rentalRequest } from "./api";
import "./rentals.css";

export function useRentalData<T>(path: string, token: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setData(null);
    rentalRequest<T>(path, token, "GET", undefined, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(message(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, token, revision]);
  return {
    data,
    error,
    loading,
    reload: () => setRevision((value) => value + 1),
  };
}
export function message(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "This request could not be completed. Please try again.";
}
export function useRentalAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(
    action: () => Promise<unknown>,
    success: string,
    after?: () => void,
  ): Promise<boolean> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      after?.();
      return true;
    } catch (reason: unknown) {
      setError(message(reason));
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, notice, run };
}
export function ActionMessages({
  error,
  notice,
}: {
  error: string | null;
  notice?: string | null;
}) {
  return (
    <>
      {error && (
        <p className="message message-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="message message-success" role="status">
          {notice}
        </p>
      )}
    </>
  );
}
export function DataPanel({
  title,
  resource,
  children,
}: {
  title: string;
  resource: { loading: boolean; error: string | null; reload: () => void };
  children: ReactNode;
}) {
  return (
    <section className="rental-feature-panel" aria-label={title}>
      <header className="rental-section-heading">
        <h2>{title}</h2>
        <button
          className="secondary-button"
          type="button"
          disabled={resource.loading}
          onClick={resource.reload}
        >
          Refresh {title.toLowerCase()}
        </button>
      </header>
      {resource.loading && <p role="status">Loading {title.toLowerCase()}…</p>}
      <ActionMessages error={resource.error} />
      {children}
    </section>
  );
}
