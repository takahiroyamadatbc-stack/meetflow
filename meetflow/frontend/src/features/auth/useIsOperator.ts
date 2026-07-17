import { useQuery } from "@tanstack/react-query";
import { getIsOperator } from "@/features/auth/api";

/** 運営者ロール（フィードバック管理・アップデート予告投稿）を持つかどうか */
export function useIsOperator(): boolean {
  const { data } = useQuery({
    queryKey: ["auth", "isOperator"] as const,
    queryFn: getIsOperator,
    staleTime: Infinity,
  });
  return data ?? false;
}
