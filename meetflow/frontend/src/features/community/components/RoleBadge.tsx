import { Badge } from "@/components/ui/badge";
import type { MembershipRole } from "@/types/api";

const ROLE_LABELS: Record<MembershipRole, string> = {
  OWNER: "オーナー",
  ADMIN: "管理者",
  MEMBER: "メンバー",
};

export function RoleBadge({ role }: { role: MembershipRole }) {
  return <Badge variant={role === "MEMBER" ? "secondary" : "default"}>{ROLE_LABELS[role]}</Badge>;
}
