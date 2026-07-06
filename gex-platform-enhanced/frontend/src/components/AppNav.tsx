/**
 * AppNav — Slim header strip rendered by individual pages.
 *
 * The primary navigation lives in the left rail (AppSidebar). This header
 * keeps only the project switcher and any contextual right-side content.
 */

import ProjectSwitcher from "@/components/ProjectSwitcher";

interface AppNavProps {
  rightContent?: React.ReactNode;
}

const AppNav = ({ rightContent }: AppNavProps) => {
  return (
    <header
      className="border-b border-white/10 px-3 sm:px-5 py-2 flex-shrink-0 z-30 relative"
      style={{ background: "linear-gradient(135deg, hsl(200 25% 10%), hsl(174 45% 18%))" }}
    >
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0 flex-shrink-0">
          <ProjectSwitcher />
        </div>

        {rightContent && (
          <div className="flex items-center gap-2 sm:gap-4 min-w-0 flex-shrink">
            {rightContent}
          </div>
        )}
      </div>
    </header>
  );
};

export default AppNav;
