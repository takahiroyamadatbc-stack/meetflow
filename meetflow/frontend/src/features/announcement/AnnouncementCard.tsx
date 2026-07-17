import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { announcementKeys, listAnnouncements } from "@/features/announcement/api";
import { paths } from "@/routes/paths";

/**
 * S-02 ホーム画面に埋め込むアップデート予告カード。公開中の最新1件のみ表示し、
 * 0件の場合はカード自体を表示しない（画面設計書v1.13 S-02の方針）。
 */
export function AnnouncementCard() {
  const { data: announcements } = useQuery({
    queryKey: announcementKeys.list(false),
    queryFn: () => listAnnouncements(false),
  });

  const latest = announcements?.[0];
  if (!latest) {
    return null;
  }

  return (
    <Link to={paths.announcementList}>
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="flex flex-col gap-1">
          <p className="text-primary text-xs font-medium">お知らせ</p>
          <p className="text-sm font-semibold">{latest.title}</p>
          <p className="text-muted-foreground line-clamp-2 text-xs">{latest.body}</p>
        </CardContent>
      </Card>
    </Link>
  );
}
