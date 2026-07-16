import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { RoleBadge } from "@/features/community/components/RoleBadge";
import type { CommunitySummary } from "@/features/community/types";
import { paths } from "@/routes/paths";

export function CommunityCard({ community }: { community: CommunitySummary }) {
  return (
    <Link to={paths.communityDetail(community.communityId)}>
      <Card
        className="border-l-4"
        style={community.themeColor ? { borderLeftColor: community.themeColor } : undefined}
      >
        <CardContent className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">{community.name}</p>
            <RoleBadge role={community.role} />
          </div>
          {community.description && (
            <p className="text-muted-foreground line-clamp-2 text-xs">
              {community.description}
            </p>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
