import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { communityKeys, getCommunity, updateCommunity, updateThemeColor } from "@/features/community/api";
import { resizeAndUploadCommunityIcon } from "@/features/community/communityIconUpload";
import { ThemeColorPicker } from "@/features/community/components/ThemeColorPicker";
import type { CommunityDetail } from "@/features/community/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

const profileSchema = z.object({
  description: z.string().max(300, "300文字以内で入力してください"),
  themeColor: z.string().nullable(),
});

type ProfileFormValues = z.infer<typeof profileSchema>;

/**
 * S-05c コミュニティプロフィール編集画面（Issue #52）。従来別ページだった
 * テーマカラー変更（ThemeColorEditPage）に、ひとこと（description）編集と
 * アイコン設定を統合する。OWNER/ADMIN限定（コミュニティ詳細の管理者メニュー
 * から遷移）。
 */
export function CommunityProfileEditPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const { data: community, isLoading } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });

  if (isLoading || !community) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  return <CommunityProfileEditForm communityId={communityId!} community={community} />;
}

function CommunityProfileEditForm({
  communityId,
  community,
}: {
  communityId: string;
  community: CommunityDetail;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [iconUrl, setIconUrl] = useState(community.icon);
  const [isUploadingIcon, setIsUploadingIcon] = useState(false);

  async function handleIconSelected(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setIsUploadingIcon(true);
    try {
      const uploadedUrl = await resizeAndUploadCommunityIcon(communityId, file);
      setIconUrl(uploadedUrl);
    } catch {
      toast.error("アイコン画像のアップロードに失敗しました");
    } finally {
      setIsUploadingIcon(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      description: community.description,
      themeColor: community.themeColor,
    },
  });

  const mutation = useMutation({
    // themeColorは汎用のupdateCommunity()ではなく専用のupdateThemeColor()
    // （PUT /communities/{communityId}/theme-color）が扱う（update_community
    // ハンドラー自体がthemeColorフィールドに対応していないため。空文字送信で
    // 解除する既存の挙動をそのまま踏襲する）。
    mutationFn: (values: ProfileFormValues) =>
      Promise.all([
        updateCommunity(communityId, { description: values.description, icon: iconUrl }),
        updateThemeColor(communityId, values.themeColor ?? ""),
      ]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communityKeys.detail(communityId) });
      queryClient.invalidateQueries({ queryKey: communityKeys.all });
      toast.success("コミュニティプロフィールを更新しました");
      navigate(paths.communityDetail(communityId));
    },
    onError: handleApiError,
  });

  return (
    <div className="p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit((values) => mutation.mutate(values))} className="grid gap-4">
          <div className="flex flex-col items-center gap-2">
            <Avatar size="lg" className="size-20">
              {iconUrl && <AvatarImage src={iconUrl} alt="コミュニティアイコン" />}
              <AvatarFallback>{community.name.slice(0, 1)}</AvatarFallback>
            </Avatar>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={isUploadingIcon}
              onChange={(e) => handleIconSelected(e.target.files)}
              className="text-sm"
            />
            {isUploadingIcon && (
              <p className="text-muted-foreground text-xs">アップロード中...</p>
            )}
          </div>

          <FormField
            control={form.control}
            name="description"
            render={({ field }) => (
              <FormItem>
                <FormLabel>ひとこと</FormLabel>
                <FormControl>
                  <Textarea rows={4} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="themeColor"
            render={({ field }) => (
              <FormItem>
                <FormLabel>テーマカラー</FormLabel>
                <FormControl>
                  <ThemeColorPicker value={field.value} onChange={field.onChange} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit" disabled={mutation.isPending || isUploadingIcon}>
            保存する
          </Button>
        </form>
      </Form>
    </div>
  );
}
