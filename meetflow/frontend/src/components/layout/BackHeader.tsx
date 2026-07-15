import { ChevronLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

type BackHeaderProps = {
  title: string;
};

/** スタック遷移画面（詳細/作成/編集系）の戻るボタン付きヘッダー */
export function BackHeader({ title }: BackHeaderProps) {
  const navigate = useNavigate();

  return (
    <header className="border-border bg-background sticky top-0 z-10 flex items-center gap-2 border-b px-2 py-3">
      <Button variant="ghost" size="icon" onClick={() => navigate(-1)} aria-label="戻る">
        <ChevronLeft className="size-5" />
      </Button>
      <h1 className="text-base font-semibold">{title}</h1>
    </header>
  );
}
