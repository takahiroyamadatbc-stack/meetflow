import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { format, formatDistanceToNow, parseISO } from "date-fns";
import { ja } from "date-fns/locale";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import {
  communityKeys,
  createPlace,
  deletePlace,
  getCommunity,
  listPlaces,
  updatePlace,
} from "@/features/community/api";
import type { Place } from "@/features/community/types";
import { getCandidateDetail, matchingKeys } from "@/features/matching/api";
import { createEvent } from "@/features/event/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

type Step = "review" | "place" | "confirm";

const placeSchema = z.object({
  name: z.string().min(1, "会場名を入力してください").max(50, "50文字以内で入力してください"),
  address: z.string().max(200, "200文字以内で入力してください"),
  note: z.string().max(200, "200文字以内で入力してください"),
});
type PlaceFormValues = z.infer<typeof placeSchema>;

/** S-13〜S-15：マッチング候補詳細→会場選択→イベント作成確認 */
export function MatchingCandidateDetailPage() {
  const { communityId, candidateId } = useParams<{ communityId: string; candidateId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const [step, setStep] = useState<Step>("review");
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null);
  const [locationNote, setLocationNote] = useState("");
  const [showNewPlaceForm, setShowNewPlaceForm] = useState(false);
  const [editingPlace, setEditingPlace] = useState<Place | null>(null);
  const [deleteTargetPlaceId, setDeleteTargetPlaceId] = useState<string | null>(null);

  const { data: candidate, isLoading } = useQuery({
    queryKey: matchingKeys.candidateDetail(candidateId!),
    queryFn: () => getCandidateDetail(candidateId!),
    enabled: !!candidateId,
  });

  const { data: community } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });
  const isAdmin = community?.role === "OWNER" || community?.role === "ADMIN";

  const { data: places } = useQuery({
    queryKey: communityKeys.places(communityId!),
    queryFn: () => listPlaces(communityId!),
    enabled: !!communityId && step === "place",
  });

  const placeForm = useForm<PlaceFormValues>({
    resolver: zodResolver(placeSchema),
    defaultValues: { name: "", address: "", note: "" },
  });

  const editPlaceForm = useForm<PlaceFormValues>({
    resolver: zodResolver(placeSchema),
    defaultValues: { name: "", address: "", note: "" },
  });

  const createPlaceMutation = useMutation({
    mutationFn: (values: PlaceFormValues) => createPlace(communityId!, values),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: communityKeys.places(communityId!) });
      setSelectedPlaceId(created.placeId);
      setShowNewPlaceForm(false);
      toast.success("会場を登録しました");
    },
    onError: handleApiError,
  });

  const updatePlaceMutation = useMutation({
    mutationFn: (values: PlaceFormValues) =>
      updatePlace(communityId!, editingPlace!.placeId, values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communityKeys.places(communityId!) });
      setEditingPlace(null);
      toast.success("会場を更新しました");
    },
    onError: handleApiError,
  });

  const deletePlaceMutation = useMutation({
    mutationFn: (placeId: string) => deletePlace(communityId!, placeId),
    onSuccess: (_, placeId) => {
      queryClient.invalidateQueries({ queryKey: communityKeys.places(communityId!) });
      if (selectedPlaceId === placeId) {
        setSelectedPlaceId(null);
      }
      toast.success("会場を削除しました");
    },
    onError: handleApiError,
    onSettled: () => setDeleteTargetPlaceId(null),
  });

  const createEventMutation = useMutation({
    mutationFn: () =>
      createEvent({
        candidateId: candidateId!,
        locationId: selectedPlaceId ?? undefined,
        locationNote: locationNote || undefined,
      }),
    onSuccess: (created) => {
      toast.success("イベントを作成しました");
      navigate(paths.eventDetail(created.eventId), { replace: true });
    },
    onError: handleApiError,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!candidate) {
    return <EmptyState message="候補が見つかりません" />;
  }

  if (step === "review") {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Card>
          <CardContent className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-lg font-semibold">
                {candidate.score !== null ? `${candidate.score}点` : "手動作成"}
              </span>
              {candidate.startTime && (
                <span className="text-muted-foreground text-sm">
                  {format(parseISO(candidate.startTime), "M月d日 HH:mm")} 〜
                  {candidate.endTime && format(parseISO(candidate.endTime), "HH:mm")}
                </span>
              )}
            </div>
            <span className="text-muted-foreground text-xs">
              {formatDistanceToNow(parseISO(candidate.createdAt), {
                addSuffix: true,
                locale: ja,
              })}
              に生成
            </span>
            <div className="flex flex-col gap-1">
              {candidate.members.map((member) => (
                <div key={member.userId} className="flex items-center justify-between text-sm">
                  <span>{member.nickname}</span>
                  <div className="flex gap-1">
                    {member.conflictWarning && <Badge variant="destructive">重複の可能性</Badge>}
                    {member.fairnessCount > 0 && (
                      <Badge variant="outline">候補止まり{member.fairnessCount}回</Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-1">
              {candidate.reasons.map((reason) => (
                <Badge key={reason} variant="secondary">
                  {reason}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
        {candidate.status === "PENDING" ? (
          <Button onClick={() => setStep("place")}>この候補で作成する</Button>
        ) : (
          <p className="text-muted-foreground text-center text-sm">
            この候補は既にイベント化されています
          </p>
        )}
      </div>
    );
  }

  if (step === "place") {
    return (
      <div className="flex flex-col gap-4 p-4">
        <p className="text-sm font-medium">会場を選択してください</p>
        <div className="flex flex-col gap-2">
          {(places ?? []).map((place) =>
            editingPlace?.placeId === place.placeId ? (
              <Card key={place.placeId}>
                <CardContent>
                  <Form {...editPlaceForm}>
                    <form
                      onSubmit={editPlaceForm.handleSubmit((values) =>
                        updatePlaceMutation.mutate(values)
                      )}
                      className="grid gap-3"
                    >
                      <FormField
                        control={editPlaceForm.control}
                        name="name"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>会場名</FormLabel>
                            <FormControl>
                              <Input {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={editPlaceForm.control}
                        name="address"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>住所（任意）</FormLabel>
                            <FormControl>
                              <Input {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={editPlaceForm.control}
                        name="note"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>補足（任意）</FormLabel>
                            <FormControl>
                              <Input {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <div className="flex gap-2">
                        <Button type="submit" size="sm" disabled={updatePlaceMutation.isPending}>
                          保存する
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setEditingPlace(null)}
                        >
                          キャンセル
                        </Button>
                      </div>
                    </form>
                  </Form>
                </CardContent>
              </Card>
            ) : (
              <Card
                key={place.placeId}
                className={selectedPlaceId === place.placeId ? "border-primary" : undefined}
                onClick={() => setSelectedPlaceId(place.placeId)}
              >
                <CardContent className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium">{place.name}</p>
                    {place.note && <p className="text-muted-foreground text-xs">{place.note}</p>}
                  </div>
                  {isAdmin && (
                    <div className="flex shrink-0 gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingPlace(place);
                          editPlaceForm.reset({
                            name: place.name,
                            address: place.address,
                            note: place.note,
                          });
                        }}
                      >
                        編集
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteTargetPlaceId(place.placeId);
                        }}
                      >
                        削除
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            )
          )}
        </div>

        <AlertDialog
          open={deleteTargetPlaceId !== null}
          onOpenChange={(open) => !open && setDeleteTargetPlaceId(null)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>この会場を削除しますか？</AlertDialogTitle>
            </AlertDialogHeader>
            <div className="flex justify-end gap-2 px-4 pb-4">
              <AlertDialogCancel>キャンセル</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => deleteTargetPlaceId && deletePlaceMutation.mutate(deleteTargetPlaceId)}
              >
                削除する
              </AlertDialogAction>
            </div>
          </AlertDialogContent>
        </AlertDialog>

        {showNewPlaceForm ? (
          <Form {...placeForm}>
            <form
              onSubmit={placeForm.handleSubmit((values) => createPlaceMutation.mutate(values))}
              className="grid gap-3"
            >
              <FormField
                control={placeForm.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>会場名</FormLabel>
                    <FormControl>
                      <Input placeholder="例：たかし宅" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={placeForm.control}
                name="note"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>補足（任意）</FormLabel>
                    <FormControl>
                      <Input placeholder="例：全自動卓あり" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" disabled={createPlaceMutation.isPending}>
                会場を登録する
              </Button>
            </form>
          </Form>
        ) : (
          <Button variant="outline" onClick={() => setShowNewPlaceForm(true)}>
            ＋新しい会場を登録する
          </Button>
        )}

        <div className="grid gap-2">
          <label className="text-sm font-medium" htmlFor="location-note">
            会場自由記述（任意）
          </label>
          <Input
            id="location-note"
            value={locationNote}
            onChange={(e) => setLocationNote(e.target.value)}
            placeholder="例：現地集合、駐車場は近隣コインパーキング"
          />
        </div>

        <Button onClick={() => setStep("confirm")}>次へ</Button>
      </div>
    );
  }

  const selectedPlace = (places ?? []).find((p) => p.placeId === selectedPlaceId);

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardContent className="flex flex-col gap-2">
          {candidate.startTime && (
            <p className="text-sm">
              日時：{format(parseISO(candidate.startTime), "M月d日 HH:mm")}
            </p>
          )}
          <p className="text-sm">
            会場：{selectedPlace?.name ?? (locationNote || "未定")}
          </p>
          <p className="text-sm">参加者：{candidate.members.map((m) => m.nickname).join("、")}</p>
        </CardContent>
      </Card>
      <Button onClick={() => createEventMutation.mutate()} disabled={createEventMutation.isPending}>
        このイベントを作成する
      </Button>
      <Button variant="outline" onClick={() => setStep("place")}>
        戻る
      </Button>
    </div>
  );
}
