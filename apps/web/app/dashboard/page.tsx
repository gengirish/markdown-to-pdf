import { OrganizationList } from "@clerk/nextjs";
import { auth, clerkClient } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

export const metadata = { title: "Dashboard" };

/**
 * Where signing in lands. The Studio lives at `/org/{slug}/dashboard`, so a
 * fixed post-sign-in URL cannot name it directly — this page resolves the
 * slug and forwards.
 *
 * Active org first, then the only org the user belongs to. Anyone with none,
 * or several and none active, picks here rather than being dropped back on
 * the landing page, which is the thing this route exists to stop.
 */
export default async function DashboardPage() {
  const { userId, orgSlug, redirectToSignIn } = await auth();
  if (!userId) return redirectToSignIn();

  if (orgSlug) redirect(`/org/${orgSlug}/dashboard`);

  const client = await clerkClient();
  const { data: memberships } = await client.users.getOrganizationMembershipList({
    userId,
    limit: 2,
  });
  const onlySlug = memberships.length === 1 ? memberships[0].organization.slug : null;
  if (onlySlug) redirect(`/org/${onlySlug}/dashboard`);

  return (
    <div className="flex min-h-screen items-center justify-center bg-ground p-6">
      <OrganizationList
        hidePersonal
        afterSelectOrganizationUrl="/org/:slug/dashboard"
        afterCreateOrganizationUrl="/org/:slug/dashboard"
      />
    </div>
  );
}
