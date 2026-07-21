import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import {
  createEventTemplate,
  listEventTemplates,
  matchingKeys,
  updateEventTemplate,
} from "@/features/matching/api";
import { gameTypeLabel, type EventTemplate } from "@/features/matching/types";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";
import { communityKeys, getCommunity } from "@/features/community/api";
import type { CommunityGenre } from "@/features/community/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { getErrorDisplay, ApiError } from "@/api/errors";
import { paths } from "@/routes/paths";

const MAHJONG_GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];

const templateSchema = z
  .object({
    gameType: z.string().min(1, "ゲーム種別を選択してください"),
    minPlayers: z.coerce.number().int().min(2, "2以上を指定してください"),
    maxPlayers: z.coerce.number().int().min(2, "2以上を指定してください"),
    priority: z.coerce.number().int().min(0).max(100),
    beginnerOk: z.boolean(),
  })
  .refine((v) => v.minPlayers <= v.maxPlayers, {
    message: "最低人数は最大人数以下にしてください",
    path: ["minPlayers"],
  });

type TemplateFormInput = z.input<typeof templateSchema>;
type TemplateFormValues = z.output<typeof templateSchema>;

/** S-11 開催条件 作成・編集画面 */
export function EventTemplateFormPage() {
  const { communityId, templateId } = useParams<{ communityId: string; templateId?: string }>();
  const { data: community, isLoading: isCommunityLoading } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });
  const { data: templates, isLoading: isTemplatesLoading } = useQuery({
    queryKey: matchingKeys.templates(communityId!),
    queryFn: () => listEventTemplates(communityId!),
    enabled: !!communityId && !!templateId,
  });

  if (isCommunityLoading || (templateId && isTemplatesLoading)) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  const existing = templateId ? templates?.find((t) => t.templateId === templateId) : undefined;

  return (
    <TemplateForm
      communityId={communityId!}
      templateId={templateId}
      existing={existing}
      genre={community?.genre ?? "麻雀"}
    />
  );
}

function TemplateForm({
  communityId,
  templateId,
  existing,
  genre,
}: {
  communityId: string;
  templateId?: string;
  existing?: EventTemplate;
  /** Issue #92: 麻雀以外のジャンルではEventTemplate.gameTypeはコミュニティの
   * ジャンルと同じ固定値1つのみ（細分類は設けない）。 */
  genre: CommunityGenre;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const isMahjongCommunity = genre === "麻雀";

  const form = useForm<TemplateFormInput, unknown, TemplateFormValues>({
    resolver: zodResolver(templateSchema),
    defaultValues: {
      gameType: existing?.gameType ?? (isMahjongCommunity ? "MAHJONG4" : genre),
      minPlayers: existing?.minPlayers ?? 4,
      maxPlayers: existing?.maxPlayers ?? 4,
      priority: existing?.priority ?? 50,
      beginnerOk: existing?.conditions.beginnerOk ?? false,
    },
  });

  const mutation = useMutation({
    mutationFn: (values: TemplateFormValues) => {
      const input = {
        gameType: values.gameType,
        minPlayers: values.minPlayers,
        maxPlayers: values.maxPlayers,
        priority: values.priority,
        conditions: { beginnerOk: values.beginnerOk },
      };
      return templateId
        ? updateEventTemplate(communityId, templateId, input)
        : createEventTemplate(communityId, input);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: matchingKeys.templates(communityId) });
      toast.success(templateId ? "開催条件を更新しました" : "開催条件を作成しました");
      navigate(paths.eventTemplateList(communityId), { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError && getErrorDisplay(err.code) === "inline") {
        form.setError("minPlayers", { message: err.message });
        return;
      }
      handleApiError(err);
    },
  });

  function onSubmit(values: TemplateFormValues) {
    mutation.mutate(values);
  }

  return (
    <div className="p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
          <FormField
            control={form.control}
            name="gameType"
            render={({ field }) => (
              <FormItem>
                <FormLabel>ゲーム種別</FormLabel>
                {isMahjongCommunity ? (
                  <div className="flex gap-2">
                    {MAHJONG_GAME_TYPES.map((gameType) => (
                      <Button
                        key={gameType}
                        type="button"
                        variant={field.value === gameType ? "default" : "outline"}
                        onClick={() => field.onChange(gameType)}
                      >
                        {GAME_TYPE_LABELS[gameType]}
                      </Button>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    {gameTypeLabel(field.value)}（コミュニティのジャンルに固定）
                  </p>
                )}
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="flex gap-4">
            <FormField
              control={form.control}
              name="minPlayers"
              render={({ field }) => (
                <FormItem className="flex-1">
                  <FormLabel>最低人数</FormLabel>
                  <FormControl>
                    <Input type="number" min={2} {...field} value={field.value as number} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="maxPlayers"
              render={({ field }) => (
                <FormItem className="flex-1">
                  <FormLabel>最大人数</FormLabel>
                  <FormControl>
                    <Input type="number" min={2} {...field} value={field.value as number} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
          <FormField
            control={form.control}
            name="priority"
            render={({ field }) => (
              <FormItem>
                <FormLabel>優先度（0〜100）</FormLabel>
                <FormControl>
                  <Input type="number" min={0} max={100} {...field} value={field.value as number} />
                </FormControl>
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
            {templateId ? "更新する" : "作成する"}
          </Button>
        </form>
      </Form>
    </div>
  );
}
