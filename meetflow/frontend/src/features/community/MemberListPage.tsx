import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { MemberCard } from "@/features/community/components/MemberCard";
import { communityKeys, listMembers, updateMember } from "@/features/community/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { useAuthUser } from "@/features/auth/useAuthUser";

/** S-08 メンバー一覧・管理画面 */
export function MemberListPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const { userId: currentUserId } = useAuthUser();

  const { data: members, isLoading } = useQuery({
    queryKey: communityKeys.members(communityId!),
    queryFn: () => listMembers(communityId!),
    enabled: !!communityId,
  });

  const currentMember = members?.find((m) => m.userId === currentUserId);
  const canManage = currentMember?.role === "OWNER" || currentMember?.role === "ADMIN";

  const mutation = useMutation({
    mutationFn: ({
      targetUserId,
      input,
    }: {
      targetUserId: string;
      input: Parameters<typeof updateMember>[2];
    }) => updateMember(communityId!, targetUserId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communityKeys.members(communityId!) });
      toast.success("メンバー情報を更新しました");
    },
    onError: handleApiError,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (!members || members.length === 0) {
    return <EmptyState message="メンバーがいません" />;
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {members.map((member) => (
        <MemberCard
          key={member.userId}
          member={member}
          canManage={canManage}
          onChangeRole={(role) => mutation.mutate({ targetUserId: member.userId, input: { role } })}
          onChangeStatus={(memberStatus) =>
            mutation.mutate({ targetUserId: member.userId, input: { status: memberStatus } })
          }
          onRemove={() => mutation.mutate({ targetUserId: member.userId, input: { remove: true } })}
        />
      ))}
    </div>
  );
}
