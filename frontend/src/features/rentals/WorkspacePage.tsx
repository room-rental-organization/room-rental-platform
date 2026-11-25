import type { UserProfile } from "../../api";
import {
  WorkspaceShell,
  workspaceLinks,
} from "../../components/WorkspaceChrome";
import { AdminDisputesPanel, LeadPanel } from "./LeadPanel";
import {
  AdminVerificationPanel,
  LandlordVerificationPanel,
} from "./VerificationPanel";
import "./rentals.css";

type Role = "landlord" | "tenant" | "admin";

export default function RentalWorkspacePage({
  profile,
  role,
  path,
  token,
  onNavigate,
  onSignOut,
}: {
  profile: UserProfile;
  role: Role;
  path: string;
  token: string;
  onNavigate: (path: string) => void;
  onSignOut: () => void;
}) {
  const title =
    workspaceLinks[role].find((link) => link.path === path)?.label ??
    "Rental workspace";
  return (
    <WorkspaceShell
      role={role}
      currentPath={path}
      title={title}
      profile={profile}
      onNavigate={onNavigate}
      onSignOut={onSignOut}
    >
      {path.endsWith("/verification") ? (
        role === "admin" ? (
          <AdminVerificationPanel token={token} />
        ) : (
          <LandlordVerificationPanel token={token} />
        )
      ) : path.endsWith("/disputes") ? (
        <AdminDisputesPanel token={token} onNavigate={onNavigate} />
      ) : (
        <>
          <LeadPanel token={token} role={role} onNavigate={onNavigate} />
        </>
      )}
    </WorkspaceShell>
  );
}
