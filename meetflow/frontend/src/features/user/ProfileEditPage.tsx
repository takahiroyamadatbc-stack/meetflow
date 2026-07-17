import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
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
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { getMyProfile, updateMyProfile, userKeys } from "@/features/user/api";
import { GAME_TYPE_LABELS, type GameType, type UserProfile } from "@/features/user/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { getErrorDisplay, ApiError } from "@/api/errors";
import { paths } from "@/routes/paths";

const GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];

const profileSchema = z.object({
  nickname: z.string().min(1, "ニックネームを入力してください").max(30, "30文字以内で入力してください"),
  profile: z.string().max(300, "300文字以内で入力してください"),
  gameTypes: z.array(z.enum(["MAHJONG4", "MAHJONG3"])),
  beginnerOk: z.boolean(),
  autoApprove: z.boolean(),
  frequencyLimitEnabled: z.boolean(),
  frequencyLimitCount: z.number().int().min(1).optional(),
  frequencyLimitPeriod: z.enum(["WEEK", "MONTH"]).optional(),
});

type ProfileFormValues = z.infer<typeof profileSchema>;

/** S-24 プロフィール編集画面 */
export function ProfileEditPage() {
  const { data: profile, isLoading } = useQuery({
    queryKey: userKeys.me,
    queryFn: getMyProfile,
  });

  if (isLoading || !profile) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  return <ProfileEditForm profile={profile} />;
}

function ProfileEditForm({ profile }: { profile: UserProfile }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      nickname: profile.nickname,
      profile: profile.profile,
      gameTypes: profile.gameTypes,
      beginnerOk: profile.beginnerOk,
      autoApprove: profile.autoApprove,
      frequencyLimitEnabled: profile.frequencyLimitCount != null,
      frequencyLimitCount: profile.frequencyLimitCount ?? undefined,
      frequencyLimitPeriod: profile.frequencyLimitPeriod ?? "WEEK",
    },
  });

  const mutation = useMutation({
    mutationFn: updateMyProfile,
    onSuccess: (updated) => {
      queryClient.setQueryData(userKeys.me, updated);
      toast.success("プロフィールを更新しました");
      navigate(paths.myPage);
    },
    onError: (err) => {
      if (err instanceof ApiError && getErrorDisplay(err.code) === "inline") {
        form.setError("nickname", { message: err.message });
        return;
      }
      handleApiError(err);
    },
  });

  const frequencyLimitEnabled = form.watch("frequencyLimitEnabled");

  function onSubmit(values: ProfileFormValues) {
    const { frequencyLimitEnabled: enabled, ...rest } = values;
    if (enabled && values.frequencyLimitCount === undefined) {
      form.setError("frequencyLimitCount", { message: "上限回数を入力してください" });
      return;
    }
    mutation.mutate({
      ...rest,
      frequencyLimitCount: enabled ? (values.frequencyLimitCount ?? null) : null,
      frequencyLimitPeriod: enabled ? (values.frequencyLimitPeriod ?? null) : null,
    });
  }

  return (
    <div className="p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
          <FormField
            control={form.control}
            name="nickname"
            render={({ field }) => (
              <FormItem>
                <FormLabel>ニックネーム</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="profile"
            render={({ field }) => (
              <FormItem>
                <FormLabel>自己紹介</FormLabel>
                <FormControl>
                  <Textarea rows={4} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="gameTypes"
            render={() => (
              <FormItem>
                <FormLabel>プレイするゲーム</FormLabel>
                <div className="flex flex-col gap-2">
                  {GAME_TYPES.map((gameType) => (
                    <FormField
                      key={gameType}
                      control={form.control}
                      name="gameTypes"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-center gap-2">
                          <FormControl>
                            <Checkbox
                              checked={field.value.includes(gameType)}
                              onCheckedChange={(checked) => {
                                field.onChange(
                                  checked
                                    ? [...field.value, gameType]
                                    : field.value.filter((v) => v !== gameType),
                                );
                              }}
                            />
                          </FormControl>
                          <FormLabel className="font-normal">
                            {GAME_TYPE_LABELS[gameType]}
                          </FormLabel>
                        </FormItem>
                      )}
                    />
                  ))}
                </div>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="beginnerOk"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between">
                <FormLabel>初心者歓迎</FormLabel>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="autoApprove"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between">
                <div>
                  <FormLabel>参加を自動承認する</FormLabel>
                  <p className="text-muted-foreground text-sm">
                    イベントが仮確定した際、参加承認を都度行わず自動で確定します
                  </p>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="frequencyLimitEnabled"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between">
                <div>
                  <FormLabel>参加頻度に上限を設ける</FormLabel>
                  <p className="text-muted-foreground text-sm">
                    ゲームジャンルごとの参加回数に上限を設け、マッチングのスコアに反映します
                  </p>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
          {frequencyLimitEnabled && (
            <div className="flex flex-row items-center gap-2">
              <FormField
                control={form.control}
                name="frequencyLimitCount"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        placeholder="回数"
                        value={field.value ?? ""}
                        onChange={(e) =>
                          field.onChange(
                            e.target.value === "" ? undefined : Number(e.target.value),
                          )
                        }
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <span className="text-sm">回 /</span>
              <FormField
                control={form.control}
                name="frequencyLimitPeriod"
                render={({ field }) => (
                  <FormItem>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-24">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="WEEK">週</SelectItem>
                        <SelectItem value="MONTH">月</SelectItem>
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
            </div>
          )}
          <Button type="submit" disabled={mutation.isPending}>
            保存する
          </Button>
        </form>
      </Form>
    </div>
  );
}
