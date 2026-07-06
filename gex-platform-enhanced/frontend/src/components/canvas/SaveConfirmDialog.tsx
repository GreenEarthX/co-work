/**
 * SaveConfirmDialog — Prompts user whether to save changes to localStorage.
 */
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { Save, X } from "lucide-react";

interface SaveConfirmDialogProps {
  open: boolean;
  onSave: () => void;
  onDiscard: () => void;
  onCancel: () => void;
  context?: string; // e.g. "canvas changes" or "plant list"
}

const SaveConfirmDialog = ({ open, onSave, onDiscard, onCancel, context = "changes" }: SaveConfirmDialogProps) => (
  <AlertDialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
    <AlertDialogContent className="sm:max-w-sm">
      <AlertDialogHeader>
        <AlertDialogTitle className="text-sm flex items-center gap-2">
          <Save className="h-4 w-4 text-primary" />
          Save {context}?
        </AlertDialogTitle>
        <AlertDialogDescription className="text-xs">
          You have unsaved {context}. Would you like to save them so they persist across sessions, or discard?
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter className="gap-2 sm:gap-2">
        <AlertDialogCancel
          onClick={onDiscard}
          className="text-xs"
        >
          <X className="h-3 w-3 mr-1" />
          Discard
        </AlertDialogCancel>
        <AlertDialogAction
          onClick={onSave}
          className="text-xs"
        >
          <Save className="h-3 w-3 mr-1" />
          Save Changes
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
);

export default SaveConfirmDialog;
