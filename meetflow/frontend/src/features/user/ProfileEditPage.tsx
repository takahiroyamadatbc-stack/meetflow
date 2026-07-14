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

  function onSubmit(values: ProfileFormValues) {
    mutation.mutate(values);
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
          <Button type="submit" disabled={mutation.isPending}>
            保存する
          </Button>
        </form>
      </Form>
    </div>
  );
}
