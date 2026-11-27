import { useEffect, useState, type FormEvent } from "react";
import { completeAccountLink, requestAccountEmail } from "../api";
import AppLink from "../components/AppLink";
import "./AccountSecurityPage.css";

function MailIcon({ complete = false }: { complete?: boolean }) {
  return <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    {complete ? <path d="m5 12 4 4L19 6" /> : <><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m4 7 8 6 8-6" /></>}
  </svg>;
}

function MailArtwork() {
  return <div className="account-mail-art" aria-hidden="true">
    <div className="account-art-orbit account-art-orbit-one" />
    <div className="account-art-orbit account-art-orbit-two" />
    <span className="account-art-spark">✦</span>
    <div className="account-art-letter"><span className="account-art-home">⌂</span><i /><i /><i /></div>
    <div className="account-art-envelope"><span /><span /></div>
    <div className="account-art-seal"><svg viewBox="0 0 24 24" fill="none"><path d="m6 12 4 4 8-8" /></svg></div>
    <span className="account-art-caption">A little help. A fresh start.</span>
  </div>;
}

export default function AccountSecurityPage({ path, initialEmail, onNavigate, onPasswordReset }: {
  path: "/verify-email" | "/forgot-password" | "/reset-password";
  initialEmail: string; onNavigate: (path: string) => void; onPasswordReset: () => void;
}) {
  const [token, setToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "");
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reset = path === "/reset-password";
  const verify = path === "/verify-email";
  const returnTo = new URLSearchParams(window.location.search).get("returnTo");
  const loginPath = returnTo && /^\/listings\/\d+\/?$/.test(returnTo)
    ? `/login?returnTo=${encodeURIComponent(returnTo)}` : "/login";

  useEffect(() => {
    // Fragments never reach the web server; remove them from browser history too.
    function captureLink() {
      const incoming = new URLSearchParams(window.location.hash.slice(1)).get("token");
      if (incoming) {
        setToken(incoming); setDone(false); setError(null); setNotice(null);
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    }
    captureLink();
    window.addEventListener("hashchange", captureLink);
    const meta = document.querySelector<HTMLMetaElement>('meta[name="referrer"]');
    const previous = meta?.content;
    if (meta) meta.content = "no-referrer";
    return () => {
      window.removeEventListener("hashchange", captureLink);
      if (meta && previous) meta.content = previous;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null); setNotice(null);
    if (reset && password !== confirmation) { setError("The passwords do not match."); return; }
    setBusy(true);
    try {
      const result = reset ? await completeAccountLink(token, password)
        : verify && token ? await completeAccountLink(token)
          : await requestAccountEmail(email, verify ? "verification" : "reset");
      setNotice(result.message);
      if (reset) { setPassword(""); setConfirmation(""); onPasswordReset(); }
      else if (verify && token) setDone(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Please try again."); }
    finally { setBusy(false); }
  }

  const steps = verify ? ["Create your account", "Verify your email", "Make yourself at home"]
    : ["Request your link", "Check your inbox", "Choose a new password"];
  const activeStep = done ? 2 : reset ? 2 : verify ? 1 : notice ? 1 : 0;

  return <main className="account-security">
    <header className="account-security-header">
      <AppLink className="modern-brand" href="/" onNavigate={onNavigate}><span>R</span> Room Rentals</AppLink>
      <span className="account-security-header-note">Your search. Your space. Your next chapter.</span>
    </header>
    <div className="account-security-layout">
      <aside className="account-security-story" aria-label="Your next step">
        <span className="account-story-tag"><span />{verify ? "ONE STEP CLOSER" : "LET’S GET YOU BACK"}</span>
        <h2>{verify ? <>Your next chapter<br />starts here.</> : reset ? <>A new password.<br />A fresh start.</> : <>Let’s get you<br /><em>back home.</em></>}</h2>
        <p>{verify ? "One quick confirmation, then you’re ready to find your space or welcome your next tenant."
          : "Your next room, your saved favourites, your conversations. Pick up right where you left off."}</p>
        <MailArtwork />
        <ol className="account-security-steps">{steps.map((step, index) => <li key={step}
          aria-current={index === activeStep ? "step" : undefined} data-complete={index < activeStep}>
          <span>{index < activeStep ? "✓" : `0${index + 1}`}</span><span>{step}</span>
        </li>)}</ol>
      </aside>
      <div className="account-security-form-column">
      <section className="account-security-card" aria-labelledby="account-security-title">
    <div className="account-security-icon"><MailIcon complete={done || notice !== null} /></div>
    <p className="account-security-eyebrow">{reset ? "A FRESH START" : verify ? "CHECK YOUR INBOX" : "ACCOUNT RECOVERY"}</p>
    <h1 id="account-security-title">{reset ? "Choose a new password" : verify ? "Verify your email" : "Forgot your password?"}</h1>
    <p className="account-security-description">{reset ? "Set a new password for your account. Your other signed-in sessions will end."
      : verify ? token ? "Confirm your email address to finish setting up your account."
        : "Check your inbox for your verification link. You can request another email below."
        : "Enter your account email and we’ll send you a password reset link."}</p>
    {notice && <p className="account-security-notice" role="status">{notice}</p>}
    {error && <p className="account-security-error" role="alert">{error}</p>}
    {reset && !token ? <p className="account-security-error" role="alert">This reset link is missing or invalid. Request a new one.</p>
      : !done && <form className="auth-form account-security-form" onSubmit={submit}>
        {reset ? <>
          <label>New password<input autoComplete="new-password" type="password" minLength={8} maxLength={128} required value={password} onChange={e => setPassword(e.target.value)} /></label>
          <label>Confirm new password<input autoComplete="new-password" type="password" minLength={8} maxLength={128} required value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
          <p className="account-security-field-hint">Use at least 8 characters. A longer, unique passphrase is best.</p>
        </> : !(verify && token) && <label>Email<div className="account-security-email"><MailIcon /><input autoComplete="email" type="email" placeholder="you@example.com" required value={email} onChange={e => setEmail(e.target.value)} /></div></label>}
        <button className="account-security-submit" type="submit" disabled={busy}>{busy ? "Please wait…" : reset ? "Reset password" : verify && token ? "Verify email" : verify ? "Send verification email" : "Send reset link"}<span aria-hidden="true">{busy ? "· · ·" : "→"}</span></button>
      </form>}
    <AppLink className="account-security-back" href={loginPath} onNavigate={onNavigate}><span aria-hidden="true">←</span> Back to sign in</AppLink>
    {((verify && token && !done) || reset) && <p className="account-security-resend"><AppLink href={reset ? "/forgot-password" : "/verify-email?resend=1"} onNavigate={onNavigate}>Request a new link</AppLink></p>}
    {!done && <div className="account-security-help"><span aria-hidden="true">✧</span><p><strong>A quick inbox check</strong>Look in your spam or junk folder if you don’t see our email.</p></div>}
  </section>
      <p className="account-security-footer">A place to belong. A simpler way to find it.</p>
      </div>
    </div>
  </main>;
}
