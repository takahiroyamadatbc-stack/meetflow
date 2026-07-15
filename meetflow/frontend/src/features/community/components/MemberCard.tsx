import { useState } from "react";
import { MoreVertical } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { RoleBadge } from "@/features/community/components/RoleBadge";
import type { CommunityMember } from "@/features/community/types";

type MemberCardProps = {
  member: CommunityMember;
  canManage: boolean;
  onChangeRole: (role: "ADMIN" | "MEMBER") => void;
  onChangeStatus: (status: "ACTIVE" | "SUSPENDED") => void;
  onRemove: () => void;
};

/** S-08 メンバー管理画面のカード。破壊的操作（退会）は二段階確認する */
export function MemberCard({
  member,
  canManage,
  onChangeRole,
  onChangeStatus,
  onRemove,
}: MemberCardProps) {
  const [confirmRemoveOpen, setConfirmRemoveOpen] = useState(false);
  const isOwner = member.role === "OWNER";

  return (
    <Card>
      <CardContent className="flex items-center gap-3">
        <Avatar>
          <AvatarFallback>{member.nickname.slice(0, 1)}</AvatarFallback>
        </Avatar>
        <div className="flex flex-1 flex-col">
          <p className="text-sm font-medium">{member.nickname}</p>
          <div className="mt-1 flex items-center gap-1">
            <RoleBadge role={member.role} />
            {member.status === "SUSPENDED" && <Badge variant="destructive">一時停止中</Badge>}
          </div>
        </div>

        {canManage && !isOwner && (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant="ghost" size="icon" aria-label="メンバー操作">
                  <MoreVertical className="size-4" />
                </Button>
              }
            />
            <DropdownMenuContent align="end">
              {member.role === "MEMBER" ? (
                <DropdownMenuItem onClick={() => onChangeRole("ADMIN")}>
                  管理者にする
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem onClick={() => onChangeRole("MEMBER")}>
                  メンバーに戻す
                </DropdownMenuItem>
              )}
              {member.status === "ACTIVE" ? (
                <DropdownMenuItem onClick={() => onChangeStatus("SUSPENDED")}>
                  一時停止する
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem onClick={() => onChangeStatus("ACTIVE")}>
                  一時停止を解除する
                </DropdownMenuItem>
              )}
              <DropdownMenuItem
                variant="destructive"
                onClick={() => setConfirmRemoveOpen(true)}
              >
                退会させる
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </CardContent>

      <AlertDialog open={confirmRemoveOpen} onOpenChange={setConfirmRemoveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{member.nickname}さんを退会させますか？</AlertDialogTitle>
            <AlertDialogDescription>この操作は取り消せません。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={onRemove}>退会させる</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
