import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import {
  listNotifications,
  markNotificationRead,
  notificationKeys,
} from "@/features/notification/api";
import type { NotificationItem } from "@/features/notification/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

/** S-23 通知一覧画面 */
export function NotificationListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const { data: notifications, isLoading } = useQuery({
    queryKey: notificationKeys.all,
    queryFn: listNotifications,
  });

  const readMutation = useMutation({
    mutationFn: (notificationId: string) => markNotificationRead(notificationId),
    onMutate: (notificationId: string) => {
      const previous = queryClient.getQueryData<NotificationItem[]>(notificationKeys.all);
      queryClient.setQueryData<NotificationItem[]>(
        notificationKeys.all,
        (old) => old?.map((n) => (n.notificationId === notificationId ? { ...n, read: true } : n)) ?? [],
      );
      return previous;
    },
    onError: (err, _id, previous) => {
      queryClient.setQueryData(notificationKeys.all, previous);
      handleApiError(err);
    },
  });

  function handleTap(notification: NotificationItem) {
    if (!notification.read) {
      readMutation.mutate(notification.notificationId);
    }
    if (notification.relatedEventId) {
      navigate(paths.eventDetail(notification.relatedEventId));
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (!notifications || notifications.length === 0) {
    return <EmptyState message="通知はありません" />;
  }

  return (
    <div className="flex flex-col gap-2 p-4">
      {notifications.map((notification) => (
        <Card
          key={notification.notificationId}
          className="cursor-pointer"
          onClick={() => handleTap(notification)}
        >
          <CardContent className="flex items-start gap-2">
            {!notification.read && (
              <span className="bg-primary mt-1.5 size-2 shrink-0 rounded-full" />
            )}
            <div className="flex flex-col gap-1">
              <p className="text-sm">{notification.message}</p>
              <p className="text-muted-foreground text-xs">
                {format(parseISO(notification.createdAt), "M月d日 HH:mm")}
              </p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
