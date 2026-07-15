import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ApiError } from "@/api/errors";

/** モーダル表示が必要なエラーコード（UNAUTHORIZED/FORBIDDEN/PARTICIPANT_SCHEDULE_CONFLICT）向けの見出し */
function titleForCode(code: string): string {
  switch (code) {
    case "UNAUTHORIZED":
      return "ログインの有効期限が切れました";
    case "FORBIDDEN":
      return "権限がありません";
    case "PARTICIPANT_SCHEDULE_CONFLICT":
      return "参加者の予定が重複しています";
    default:
      return "エラーが発生しました";
  }
}

type ErrorModalContextValue = {
  showErrorModal: (error: ApiError) => void;
};

const ErrorModalContext = createContext<ErrorModalContextValue | null>(null);

export function ErrorModalProvider({ children }: { children: ReactNode }) {
  const [error, setError] = useState<ApiError | null>(null);

  const showErrorModal = useCallback((err: ApiError) => setError(err), []);
  const value = useMemo(() => ({ showErrorModal }), [showErrorModal]);

  return (
    <ErrorModalContext.Provider value={value}>
      {children}
      <AlertDialog open={error !== null} onOpenChange={(open) => !open && setError(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{error ? titleForCode(error.code) : ""}</AlertDialogTitle>
            <AlertDialogDescription>{error?.message}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction onClick={() => setError(null)}>閉じる</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ErrorModalContext.Provider>
  );
}

export function useErrorModal() {
  const ctx = useContext(ErrorModalContext);
  if (!ctx) {
    throw new Error("useErrorModal must be used within <ErrorModalProvider>");
  }
  return ctx;
}
