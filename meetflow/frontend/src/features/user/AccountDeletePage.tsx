import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { deleteMyAccount } from "@/features/user/api";
import { signOutUser } from "@/features/auth/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

const CONFIRM_PHRASE = "削除する";

/**
 * マイページからのアカウント削除（Issue #82）。コミュニティ退会より
 * 強い破壊的操作のため、確認ダイアログ内で固定フレーズの入力を要求する
 * 二段階確認にする（誤操作防止。GitHubのリポジトリ削除等と同じ考え方）。
 */
export function AccountDeletePage() {
  const navigate = useNavigate();
  const handleApiError = useApiErrorToast();
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  const mutation = useMutation({
    mutationFn: deleteMyAccount,
    onSuccess: async () => {
      toast.success("アカウントを削除しました");
      await signOutUser();
      navigate(paths.login, { replace: true });
    },
    onError: (err) => {
      handleApiError(err);
      setShowConfirm(false);
      setConfirmText("");
    },
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardContent className="flex flex-col gap-2">
          <p className="text-sm font-medium">アカウントを削除する</p>
          <p className="text-muted-foreground text-sm">
            アカウントを削除すると、ログインできなくなり元に戻せません。所属している全てのコミュニティから退会します。
          </p>
          <ul className="text-muted-foreground list-disc pl-5 text-sm">
            <li>オーナーを務めているコミュニティがある場合は、先にオーナーを移譲してください</li>
            <li>未来に確定している参加予定がある場合は、先にキャンセル申請してください</li>
          </ul>
        </CardContent>
      </Card>
      <Button variant="destructive" onClick={() => setShowConfirm(true)}>
        アカウントを削除する
      </Button>

      <AlertDialog
        open={showConfirm}
        onOpenChange={(open) => {
          setShowConfirm(open);
          if (!open) setConfirmText("");
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>本当にアカウントを削除しますか？</AlertDialogTitle>
          </AlertDialogHeader>
          <div className="flex flex-col gap-2 px-4">
            <p className="text-muted-foreground text-sm">
              この操作は元に戻せません。よろしければ「{CONFIRM_PHRASE}」と入力してください。
            </p>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={CONFIRM_PHRASE}
            />
          </div>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction
              disabled={confirmText !== CONFIRM_PHRASE || mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              削除する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
