import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { createCancelRequest, eventKeys } from "@/features/event/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

const REASON_PRESETS = ["仕事", "体調不良", "家庭都合"] as const;

/** S-18 参加キャンセル申請画面 */
export function CancelRequestCreatePage() {
  const { eventId } = useParams<{ eventId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [selectedReason, setSelectedReason] = useState<string | null>(null);
  const [freeText, setFreeText] = useState("");

  const mutation = useMutation({
    mutationFn: () => createCancelRequest(eventId!, selectedReason === "その他" ? freeText : selectedReason ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: eventKeys.detail(eventId!) });
      toast.success("キャンセル申請を送信しました");
      navigate(paths.eventDetail(eventId!), { replace: true });
    },
    onError: handleApiError,
  });

  const canSubmit =
    selectedReason !== null && (selectedReason !== "その他" || freeText.trim().length > 0);

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="text-sm font-medium">キャンセルの理由を選んでください</p>
      <div className="flex flex-wrap gap-2">
        {[...REASON_PRESETS, "その他"].map((reason) => (
          <Button
            key={reason}
            type="button"
            variant={selectedReason === reason ? "default" : "outline"}
            size="sm"
            onClick={() => setSelectedReason(reason)}
          >
            {reason}
          </Button>
        ))}
      </div>

      {selectedReason === "その他" && (
        <Textarea
          rows={3}
          placeholder="理由を入力してください"
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
        />
      )}

      <p className="text-muted-foreground text-sm">
        申請後は管理者の承認を経てキャンセルが確定します。
      </p>

      <Button disabled={!canSubmit || mutation.isPending} onClick={() => mutation.mutate()}>
        申請する
      </Button>
    </div>
  );
}
