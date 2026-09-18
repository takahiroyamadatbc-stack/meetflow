import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/api/errors";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { communityKeys, listMembers } from "@/features/community/api";
import { createDraft, draftKeys } from "@/features/draft/api";
import { paths } from "@/routes/paths";

/**
 * S-33 ドラフト作成画面。
 *
 * DESIGN.md §4.13: 参加者は既存コミュニティのACTIVEメンバーから選ぶ。
 * §4.5: 3〜10人（上限は女性選手数でも抑えられるが、その判定はサーバー側）。
 */
export function DraftCreatePage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [regularSeasonEndDate, setRegularSeasonEndDate] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const { data: members } = useQuery({
    queryKey: communityKeys.members(communityId!),
    queryFn: () => listMembers(communityId!),
    enabled: !!communityId,
  });

  const activeMembers = (members ?? []).filter((member) => member.status === "ACTIVE");

  const createMutation = useMutation({
    mutationFn: () =>
      createDraft(communityId!, {
        name: name.trim(),
        participantUserIds: selected,
        ...(regularSeasonEndDate ? { regularSeasonEndDate } : {}),
      }),
    onSuccess: (draft) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.list(communityId!) });
      toast.success("ドラフトを作成しました");
      navigate(paths.draftRoom(draft.draftId));
    },
    onError: (error) => {
      // 人数・参加者の不備はフォーム直下に出す（他はトースト/モーダル）。
      if (error instanceof ApiError && error.code === "DRAFT_VALIDATION_ERROR") {
        setFormError(error.message);
        return;
      }
      handleApiError(error);
    },
  });

  const toggle = (userId: string) => {
    setFormError(null);
    setSelected((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId],
    );
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="draft-name">ドラフト名</Label>
        <Input
          id="draft-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Mリーグドラフト2026-27"
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label>参加者（{selected.length}人）</Label>
        <Card>
          <CardContent className="flex flex-col gap-1">
            {activeMembers.map((member) => (
              <label
                key={member.userId}
                className="hover:bg-accent flex items-center gap-3 rounded-md px-2 py-2 text-sm"
              >
                <Checkbox
                  checked={selected.includes(member.userId)}
                  onCheckedChange={() => toggle(member.userId)}
                />
                <span>{member.nickname}</span>
              </label>
            ))}
          </CardContent>
        </Card>
        <p className="text-muted-foreground text-xs">
          3〜10人を選んでください。各自4人を指名し、女性選手を必ず1人以上含めます。
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="regular-season-end">レギュラーシーズン終了日（任意）</Label>
        <Input
          id="regular-season-end"
          type="date"
          value={regularSeasonEndDate}
          onChange={(event) => setRegularSeasonEndDate(event.target.value)}
        />
        <p className="text-muted-foreground text-xs">
          {/* DESIGN.md §4.15: 未設定のうちはシーズン全体を集計する。 */}
          未設定の場合はシーズン全体を集計します。公式発表が出たら設定してください。
        </p>
      </div>

      {formError && <p className="text-destructive text-sm">{formError}</p>}

      <Button
        onClick={() => createMutation.mutate()}
        disabled={!name.trim() || selected.length === 0 || createMutation.isPending}
      >
        ドラフトを作成する
      </Button>
    </div>
  );
}
