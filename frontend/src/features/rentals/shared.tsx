import { useState, type ReactNode } from "react";
import { useResource } from "../../queries/resources";
import { useMutation } from "@tanstack/react-query";
import "./rentals.css";

export function useRentalData<T>(path: string, token: string | null) {
  const query = useResource<T>(path, token);
  return { data: query.data ?? null, error: query.error ? message(query.error) : null,
    loading: query.isPending, reload: () => { void query.refetch({ cancelRefetch: false }); } };
}
export function message(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "This request could not be completed. Please try again.";
}
export function useRentalAction() {
  const mutation = useMutation({ mutationFn: (action: () => Promise<unknown>) => action() });
  const busy = mutation.isPending;
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(
    action: () => Promise<unknown>,
    success: string,
    after?: () => void,
  ): Promise<boolean> {
    setError(null);
    setNotice(null);
    try {
      await mutation.mutateAsync(action);
      setNotice(success);
      after?.();
      return true;
    } catch (reason: unknown) {
      setError(message(reason));
      return false;
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
