"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useUser } from "@/providers/UserProvider";
import { checkUserIsNoAuthUser, getUserEmail, logout } from "@/lib/user";
import UserAvatar from "@/refresh-components/avatars/UserAvatar";
import SimplePopover from "@/refresh-components/SimplePopover";
import Text from "@/refresh-components/texts/Text";
import { LineItemButton } from "@opal/components";
import { SvgLogOut, SvgSliders, SvgUser } from "@opal/icons";
import { toast } from "@/hooks/useToast";

/**
 * AIPG fork: a round account/login circle for the top-right header. Logged-in
 * users get their avatar + a small account menu (settings, log out); anonymous
 * users get a "sign in" circle that routes to the login screen. Reuses Onyx's
 * own UserAvatar + user helpers so it stays native to the app.
 */
export default function HeaderUserButton() {
  const { user } = useUser();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const isAnon =
    !user || user.is_anonymous_user || checkUserIsNoAuthUser(user.id ?? "");

  const nextParam = () => {
    const current = `${pathname}${
      searchParams?.toString() ? `?${searchParams.toString()}` : ""
    }`;
    return encodeURIComponent(current);
  };

  if (isAnon) {
    return (
      <button
        onClick={() => router.push(`/auth/login?next=${nextParam()}`)}
        aria-label="sign-in"
        title="Sign in"
        className="flex items-center justify-center w-8 h-8 rounded-full bg-background-neutral-03 text-text-03 hover:bg-background-neutral-04 hover:text-text-02 transition-colors"
      >
        <SvgUser size={16} />
      </button>
    );
  }

  const handleLogout = () => {
    logout()
      .then((response) => {
        if (!response?.ok) {
          toast.error("Failed to log out");
          return;
        }
        router.push(
          `/auth/login?disableAutoRedirect=true&next=${nextParam()}`
        );
      })
      .catch(() => toast.error("Failed to log out"));
  };

  return (
    <SimplePopover
      side="bottom"
      align="end"
      trigger={
        <button
          aria-label="account"
          className="flex items-center justify-center w-8 h-8 rounded-full overflow-hidden hover:opacity-90 transition-opacity"
        >
          <UserAvatar user={user} />
        </button>
      }
    >
      <div className="w-56 p-1 flex flex-col gap-0.5">
        <div className="p-2">
          <Text text03 secondaryBody nowrap className="truncate">
            {getUserEmail(user)}
          </Text>
        </div>
        <LineItemButton
          sizePreset="main-ui"
          variant="section"
          rounding="sm"
          icon={SvgSliders}
          title="Settings"
          href="/app/settings"
        />
        <LineItemButton
          sizePreset="main-ui"
          variant="section"
          rounding="sm"
          color="danger"
          icon={SvgLogOut}
          title="Log out"
          onClick={handleLogout}
        />
      </div>
    </SimplePopover>
  );
}
