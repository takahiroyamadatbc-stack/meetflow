import { useCallback } from "react";
import { toast } from "sonner";
import { ApiError, getErrorDisplay } from "@/api/errors";
import { useErrorModal } from "@/components/feedback/ErrorModalContext";

/**
 * APIエラーをエラーコード一覧v1.2 §10の表示方針に沿って処理するフック。
 * トースト/モーダル対象のコードはここで表示まで完結させる。
 * インライン（フォームエラー）・空状態は呼び出し側で個別に扱うため、
 * ここでは何もしない（形式が "inline" | "empty" の場合は無視する）。
 */
export function useApiErrorToast() {
  const { showErrorModal } = useErrorModal();

  return useCallback(
    (error: unknown) => {
      if (!(error instanceof ApiError)) {
        toast.error("予期しないエラーが発生しました");
        return;
      }

      const display = getErrorDisplay(error.code);
      if (display === "toast") {
        toast.error(error.message);
      } else if (display === "modal") {
        showErrorModal(error);
      }
    },
    [showErrorModal],
  );
}
