/**
 * AccessRestricted — Shown when a user tries to access a project
 * they don't have permissions for.
 */
import { useNavigate } from "react-router-dom";
import { Lock, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface AccessRestrictedProps {
  projectName?: string;
}

const AccessRestricted = ({ projectName }: AccessRestrictedProps) => {
  const navigate = useNavigate();

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="rounded-xl border border-border bg-card p-10 text-center space-y-4 max-w-md">
        <div className="mx-auto h-14 w-14 rounded-full bg-destructive/10 flex items-center justify-center">
          <Lock className="h-7 w-7 text-destructive" />
        </div>
        <h2 className="text-lg font-bold text-card-foreground">Access Restricted</h2>
        <p className="text-sm text-muted-foreground">
          {projectName
            ? `You don't have permission to access "${projectName}". Contact your project admin to request access.`
            : "You don't have permission to access this project. Contact your project admin to request access."}
        </p>
        <Button variant="outline" onClick={() => navigate("/")} className="gap-2">
          <ArrowLeft className="h-4 w-4" />
          Back to Orchestrator
        </Button>
      </div>
    </div>
  );
};

export default AccessRestricted;
