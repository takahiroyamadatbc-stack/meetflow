import { useEffect } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowDown, ArrowUp } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { listParticipants } from "@/features/event/api";
import { createSession } from "@/features/result/api";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { getErrorDisplay, ApiError } from "@/api/errors";
import { paths } from "@/routes/paths";

const GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];

const sessionSchema = z.object({
  gameType: z.enum(["MAHJONG4", "MAHJONG3"]),
  results: z.array(
    z.object({
      userId: z.string(),
      nickname: z.string(),
      score: z.coerce.number().int(),
      rankPoints: z.coerce.number().int(),
    }),
  ),
});
type SessionFormInput = z.input<typeof sessionSchema>;
type SessionFormValues = z.output<typeof sessionSchema>;

/** S-21 成績登録画面。着順は一覧の並び順（上ほど上位）から自動採番する */
export function ResultSessionCreatePage() {
  const { eventId } = useParams<{ eventId: string }>();
  const navigate = useNavigate();
  const handleApiError = useApiErrorToast();

  const { data: participants, isLoading } = useQuery({
    queryKey: ["events", eventId, "participants"],
    queryFn: () => listParticipants(eventId!),
    enabled: !!eventId,
  });

  const form = useForm<SessionFormInput, unknown, SessionFormValues>({
    resolver: zodResolver(sessionSchema),
    defaultValues: { gameType: "MAHJONG4", results: [] },
  });
  const { fields, move, replace } = useFieldArray({ control: form.control, name: "results" });

  useEffect(() => {
    if (participants) {
      replace(
        participants
          .filter((p) => p.status !== "CANCELLED")
          .map((p) => ({ userId: p.userId, nickname: p.nickname, score: 0, rankPoints: 0 })),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participants]);

  const mutation = useMutation({
    mutationFn: (values: SessionFormValues) =>
      createSession(
        eventId!,
        values.gameType,
        values.results.map((r, index) => ({
          userId: r.userId,
          rank: index + 1,
          score: r.score,
          rankPoints: r.rankPoints,
        })),
      ),
    onSuccess: () => {
      toast.success("成績を登録しました");
      navigate(paths.eventDetail(eventId!), { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError && getErrorDisplay(err.code) === "inline") {
        toast.error(err.message);
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
            name="gameType"
            render={({ field }) => (
              <FormItem>
                <FormLabel>ゲーム種別</FormLabel>
                <div className="flex gap-2">
                  {GAME_TYPES.map((gameType) => (
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
              </FormItem>
            )}
          />

          <p className="text-sm font-medium">着順（上ほど上位。矢印で並び替え）</p>
          <div className="flex flex-col gap-3">
            {fields.map((item, index) => (
              <div key={item.id} className="flex items-center gap-2 rounded-lg border p-3">
                <div className="flex flex-col">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={index === 0}
                    onClick={() => move(index, index - 1)}
                  >
                    <ArrowUp className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={index === fields.length - 1}
                    onClick={() => move(index, index + 1)}
                  >
                    <ArrowDown className="size-4" />
                  </Button>
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">
                    {index + 1}位　{item.nickname}
                  </p>
                  <div className="mt-1 flex gap-2">
                    <FormField
                      control={form.control}
                      name={`results.${index}.score`}
                      render={({ field }) => (
                        <FormItem className="flex-1">
                          <FormLabel className="text-xs">点数</FormLabel>
                          <FormControl>
                            <Input type="number" {...field} value={field.value as number} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name={`results.${index}.rankPoints`}
                      render={({ field }) => (
                        <FormItem className="flex-1">
                          <FormLabel className="text-xs">順位点（任意）</FormLabel>
                          <FormControl>
                            <Input type="number" {...field} value={field.value as number} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          <Button type="submit" disabled={mutation.isPending || fields.length === 0}>
            登録する
          </Button>
        </form>
      </Form>
    </div>
  );
}
