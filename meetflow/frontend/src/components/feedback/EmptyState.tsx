import type { ReactNode } from "react";

type EmptyStateProps = {
  message: string;
  description?: string;
  action?: ReactNode;
};

/** 0件・NOT_FOUND系エラー時に表示する空状態画面（エラーコード一覧v1.2 §10） */
export function EmptyState({ message, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      <p className="text-foreground text-sm font-medium">{message}</p>
      {description && <p className="text-muted-foreground text-sm">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
