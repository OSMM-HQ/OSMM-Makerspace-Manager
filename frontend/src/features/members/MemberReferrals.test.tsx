import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MemberReferrals } from "./MemberReferrals";


const invitation = {
  id: 12,
  makerspace: { slug: "community-lab", name: "Community Lab" },
  inviter: "Taylor",
  auto_activates: true,
  role: "Member",
};


describe("MemberReferrals", () => {
  it("shows the referral form only for an enabled delegated member", async () => {
    const refer = vi.fn().mockResolvedValue(undefined);
    const view = render(
      <MemberReferrals
        canRefer={false}
        referralsEnabled
        emailVerified
        invitations={[]}
        invitationsLoading={false}
        onRefer={refer}
        onClaim={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText("Invite email")).not.toBeInTheDocument();

    view.rerender(
      <MemberReferrals
        canRefer
        referralsEnabled
        emailVerified
        invitations={[]}
        invitationsLoading={false}
        onRefer={refer}
        onClaim={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Invite email"), { target: { value: "friend@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Send referral" }));
    await vi.waitFor(() => expect(refer).toHaveBeenCalledWith("friend@example.test"));
  });

  it("guides unverified users without exposing an unmatched invitation", () => {
    render(
      <MemberReferrals
        canRefer={false}
        referralsEnabled={false}
        emailVerified={false}
        invitations={[]}
        invitationsLoading={false}
        onRefer={vi.fn()}
        onClaim={vi.fn()}
      />,
    );
    expect(screen.getByText("Verify your email to discover and claim invitations.")).toBeVisible();
    expect(screen.queryByText("No pending invitations for this makerspace.")).not.toBeInTheDocument();
    expect(screen.queryByText("Taylor")).not.toBeInTheDocument();
  });

  it("renders invitation states and delegates claims", () => {
    const claim = vi.fn();
    const view = render(
      <MemberReferrals
        canRefer={false}
        referralsEnabled={false}
        emailVerified
        invitations={[]}
        invitationsLoading
        onRefer={vi.fn()}
        onClaim={claim}
      />,
    );
    expect(screen.getByText("Checking pending invitations…")).toBeVisible();

    view.rerender(
      <MemberReferrals
        canRefer={false}
        referralsEnabled={false}
        emailVerified
        invitations={[invitation]}
        invitationsLoading={false}
        invitationError={new Error("Invitation lookup failed")}
        onRefer={vi.fn()}
        onClaim={claim}
        claimSuccess="You are now an active member."
      />,
    );
    expect(screen.getByText("Invitation lookup failed")).toBeVisible();
    expect(screen.getByText("You are now an active member.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Claim invitation" }));
    expect(claim).toHaveBeenCalledWith(invitation.id);
  });
});
