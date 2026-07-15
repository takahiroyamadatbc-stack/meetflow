import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { GAME_TYPE_LABELS } from "@/features/user/types";
import type { JoinRequest } from "@/features/community/types";

type JoinRequestCardProps = {
  request: JoinRequest;
  onApprove: () => void;
  onReject: () => void;
  disabled?: boolean;
};

export function JoinRequestCard({ request, onApprove, onReject, disabled }: JoinRequestCardProps) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <Avatar>
            <AvatarFallback>{request.nickname.slice(0, 1)}</AvatarFallback>
          </Avatar>
          <div className="flex-1">
            <p className="text-sm font-medium">{request.nickname}</p>
            {request.gameTypes.length > 0 && (
              <div className="mt-1 flex gap-1">
                {request.gameTypes.map((g) => (
                  <Badge key={g} variant="outline">
                    {GAME_TYPE_LABELS[g]}
                  </Badge>
                ))}
                {request.beginnerOk && <Badge variant="outline">初心者歓迎</Badge>}
              </div>
            )}
          </div>
        </div>
        {request.message && <p className="text-muted-foreground text-sm">{request.message}</p>}
        <div className="flex gap-2">
          <Button className="flex-1" onClick={onApprove} disabled={disabled}>
            承認
          </Button>
          <Button className="flex-1" variant="outline" onClick={onReject} disabled={disabled}>
            却下
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
