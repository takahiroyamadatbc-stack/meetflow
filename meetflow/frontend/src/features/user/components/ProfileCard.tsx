import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Card, CardContent } from "@/components/ui/card";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";
import { cn } from "@/lib/utils";

type ProfileCardProps = {
  nickname: string;
  icon?: string;
  bio?: string;
  gameTypes?: GameType[];
  /** 自己紹介を2行程度に省略表示するか（Issue #46）。詳細表示用途ではfalseにする */
  bioClamp?: boolean;
  className?: string;
};

/** 表示専用のプロフィールカード（Issue #45）。マイページ・ホームタブ・
 * コミュニティメンバー詳細（Issue #48）で共通利用する。
 */
export function ProfileCard({
  nickname,
  icon,
  bio,
  gameTypes,
  bioClamp = true,
  className,
}: ProfileCardProps) {
  return (
    <Card className={className}>
      <CardContent className="flex items-start gap-4">
        <Avatar size="lg" className="size-14">
          {icon && <AvatarImage src={icon} alt={nickname} />}
          <AvatarFallback>{nickname.slice(0, 1)}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold">{nickname}</p>
          {gameTypes && gameTypes.length > 0 && (
            <p className="text-muted-foreground text-xs">
              {gameTypes.map((g) => GAME_TYPE_LABELS[g]).join(" / ")}
            </p>
          )}
          {bio && (
            <p
              className={cn(
                "mt-2 text-sm whitespace-pre-wrap",
                bioClamp && "line-clamp-2",
              )}
            >
              {bio}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
