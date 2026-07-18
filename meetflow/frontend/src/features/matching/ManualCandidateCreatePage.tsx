import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { communityKeys, listMembers } from "@/features/community/api";
import { createManualCandidate } from "@/features/matching/api";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { getErrorDisplay, ApiError } from "@/api/errors";
import { paths } from "@/routes/paths";

const GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];
const UNSPECIFIED_GAME_TYPE = "UNSPECIFIED";

const manualCandidateSchema = z
  .object({
    memberIds: z.array(z.string()).min(1, "メンバーを1人以上選択してください"),
    startTime: z.string().min(1, "開始日時を指定してください"),
    endTime: z.string().min(1, "終了日時を指定してください"),
    gameType: z.string(),
  })
  .refine((v) => v.endTime > v.startTime, {
    message: "終了日時は開始日時より後にしてください",
    path: ["endTime"],
  });

type ManualCandidateFormValues = z.infer<typeof manualCandidateSchema>;

/**
 * S-12b 手動候補作成画面（Issue #56）。「急遽今から麻雀やろう」等、通常の
 * マッチングフロー（開催条件登録→空き予定収集→候補生成）を経ずに、管理者が
 * その場でメンバー・日時を直接指定する。作成後は既存の候補詳細画面（S-13）
 * に遷移し、以降は通常の候補と同じ「会場選択→イベント作成」フローに乗る。
 */
export function ManualCandidateCreatePage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const handleApiError = useApiErrorToast();

  const { data: members, isLoading } = useQuery({
    queryKey: communityKeys.members(communityId!),
    queryFn: () => listMembers(communityId!),
    enabled: !!communityId,
  });
  const activeMembers = (members ?? []).filter((m) => m.status === "ACTIVE");

  const form = useForm<ManualCandidateFormValues>({
    resolver: zodResolver(manualCandidateSchema),
    defaultValues: {
      memberIds: [],
      startTime: "",
      endTime: "",
      gameType: UNSPECIFIED_GAME_TYPE,
    },
  });

  const mutation = useMutation({
    mutationFn: (values: ManualCandidateFormValues) =>
      createManualCandidate(communityId!, {
        memberIds: values.memberIds,
        startTime: values.startTime,
        endTime: values.endTime,
        gameType: values.gameType === UNSPECIFIED_GAME_TYPE ? undefined : (values.gameType as GameType),
      }),
    onSuccess: (created) => {
      navigate(paths.matchingCandidateDetail(communityId!, created.candidateId), {
        replace: true,
      });
    },
    onError: (err) => {
      if (err instanceof ApiError && getErrorDisplay(err.code) === "inline") {
        form.setError("endTime", { message: err.message });
        return;
      }
      handleApiError(err);
    },
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  return (
    <div className="p-4">
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
          className="grid gap-4"
        >
          <FormField
            control={form.control}
            name="memberIds"
            render={({ field }) => (
              <FormItem>
                <FormLabel>参加メンバー</FormLabel>
                <FormDescription>
                  承認フローを経ずに全員即確定させます。招集済みのメンバーのみ選択してください
                </FormDescription>
                <div className="flex flex-col gap-2">
                  {activeMembers.map((member) => (
                    <div key={member.userId} className="flex items-center gap-2">
                      <Checkbox
                        id={`manual-member-${member.userId}`}
                        checked={field.value.includes(member.userId)}
                        onCheckedChange={(checked) =>
                          field.onChange(
                            checked
                              ? [...field.value, member.userId]
                              : field.value.filter((id) => id !== member.userId),
                          )
                        }
                      />
                      <Label htmlFor={`manual-member-${member.userId}`} className="font-normal">
                        {member.nickname}
                      </Label>
                    </div>
                  ))}
                </div>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="flex gap-2">
            <FormField
              control={form.control}
              name="startTime"
              render={({ field }) => (
                <FormItem className="flex-1">
                  <FormLabel>開始日時</FormLabel>
                  <FormControl>
                    <Input type="datetime-local" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="endTime"
              render={({ field }) => (
                <FormItem className="flex-1">
                  <FormLabel>終了日時</FormLabel>
                  <FormControl>
                    <Input type="datetime-local" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="gameType"
            render={({ field }) => (
              <FormItem>
                <FormLabel>ゲーム種別（任意）</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value={UNSPECIFIED_GAME_TYPE}>未指定</SelectItem>
                    {GAME_TYPES.map((gameType) => (
                      <SelectItem key={gameType} value={gameType}>
                        {GAME_TYPE_LABELS[gameType]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit" disabled={mutation.isPending}>
            この内容でイベントを作成する
          </Button>
        </form>
      </Form>
    </div>
  );
}
