import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { useIsOperator } from "@/features/auth/useIsOperator";
import {
  announcementKeys,
  createAnnouncement,
  listAnnouncements,
  updateAnnouncement,
} from "@/features/announcement/api";
import { ANNOUNCEMENT_STATUS_LABELS, type Announcement } from "@/features/announcement/types";

const announcementSchema = z.object({
  title: z.string().min(1, "タイトルを入力してください").max(100, "100文字以内で入力してください"),
  body: z.string().min(1, "本文を入力してください").max(2000, "2000文字以内で入力してください"),
});
type AnnouncementFormValues = z.infer<typeof announcementSchema>;

/** S-30 アップデート予告一覧画面 */
export function AnnouncementListPage() {
  const isOperator = useIsOperator();
  const { data: announcements, isLoading } = useQuery({
    queryKey: announcementKeys.list(isOperator),
    queryFn: () => listAnnouncements(isOperator),
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      {isOperator && <AnnouncementCreateForm />}

      {isLoading && <Skeleton className="h-20 w-full" />}

      {!isLoading && (announcements ?? []).length === 0 && (
        <EmptyState message="まだお知らせはありません" />
      )}

      <div className="flex flex-col gap-2">
        {(announcements ?? []).map((announcement) => (
          <AnnouncementCard
            key={announcement.announcementId}
            announcement={announcement}
            isOperator={isOperator}
          />
        ))}
      </div>
    </div>
  );
}

function AnnouncementCreateForm() {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [open, setOpen] = useState(false);

  const form = useForm<AnnouncementFormValues>({
    resolver: zodResolver(announcementSchema),
    defaultValues: { title: "", body: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: AnnouncementFormValues) => createAnnouncement(values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: announcementKeys.all });
      toast.success("下書きを作成しました");
      form.reset();
      setOpen(false);
    },
    onError: handleApiError,
  });

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        ＋新規作成
      </Button>
    );
  }

  return (
    <Card>
      <CardContent>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
            className="grid gap-3"
          >
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>タイトル</FormLabel>
                  <FormControl>
                    <Input placeholder="例：次回アップデート予告" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="body"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>本文</FormLabel>
                  <FormControl>
                    <Textarea rows={4} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="flex gap-2">
              <Button type="submit" disabled={mutation.isPending}>
                下書きを作成
              </Button>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                キャンセル
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

function AnnouncementCard({
  announcement,
  isOperator,
}: {
  announcement: Announcement;
  isOperator: boolean;
}) {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState(announcement.title);
  const [body, setBody] = useState(announcement.body);

  const mutation = useMutation({
    mutationFn: (input: { title?: string; body?: string; status?: string }) =>
      updateAnnouncement(announcement.announcementId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: announcementKeys.all });
      toast.success("更新しました");
      setIsEditing(false);
    },
    onError: handleApiError,
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium">
            {format(parseISO(announcement.createdAt), "M月d日")}
          </span>
          {isOperator && (
            <Badge variant="outline">{ANNOUNCEMENT_STATUS_LABELS[announcement.status]}</Badge>
          )}
        </div>

        {isEditing ? (
          <div className="flex flex-col gap-2">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            <Textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)} />
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={mutation.isPending}
                onClick={() => mutation.mutate({ title, body })}
              >
                保存
              </Button>
              <Button size="sm" variant="outline" onClick={() => setIsEditing(false)}>
                キャンセル
              </Button>
            </div>
          </div>
        ) : (
          <>
            <p className="text-sm font-semibold">{announcement.title}</p>
            <p className="text-muted-foreground text-sm whitespace-pre-wrap">
              {announcement.body}
            </p>
          </>
        )}

        {isOperator && !isEditing && (
          <div className="flex gap-2">
            {announcement.status !== "PUBLISHED" && (
              <Button
                size="sm"
                disabled={mutation.isPending}
                onClick={() => mutation.mutate({ status: "PUBLISHED" })}
              >
                公開する
              </Button>
            )}
            {announcement.status === "PUBLISHED" && (
              <Button
                size="sm"
                variant="outline"
                disabled={mutation.isPending}
                onClick={() => mutation.mutate({ status: "ARCHIVED" })}
              >
                取り下げる
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setIsEditing(true)}>
              編集
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
