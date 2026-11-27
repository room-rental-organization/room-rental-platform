import type { AnchorHTMLAttributes, MouseEvent } from "react";

type AppLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
  onNavigate: (path: string) => void;
  variant?: "text" | "action" | "plain";
};

export default function AppLink({
  href,
  onNavigate,
  onClick,
  className,
  variant,
  ...anchorProps
}: AppLinkProps) {
  // Unstyled content links share one treatment; navigation, brands and cards
  // retain their existing classes. Explicit variants cover stronger actions.
  const appearance = variant ?? (className?.trim() ? "plain" : "text");
  const linkClassName = [appearance === "plain" ? "" : appearance === "action" ? "action-link" : "text-link", className]
    .filter(Boolean).join(" ") || undefined;
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      anchorProps.target === "_blank" ||
      anchorProps.download !== undefined
    ) {
      return;
    }

    const destination = new URL(href, window.location.href);
    if (destination.origin !== window.location.origin) {
      return;
    }

    event.preventDefault();
    onNavigate(
      `${destination.pathname}${destination.search}${destination.hash}`,
    );
  }

  return (
    <a {...anchorProps} className={linkClassName} href={href} onClick={handleClick}>
      {appearance === "action" ? <><span>{anchorProps.children}</span><svg className="action-link-icon" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 10h12m-5-5 5 5-5 5" /></svg></> : anchorProps.children}
    </a>
  );
}
