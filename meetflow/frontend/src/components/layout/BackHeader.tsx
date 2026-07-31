import { ChevronLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { paths } from "@/routes/paths";

type BackHeaderProps = {
  title: string;
};

/**
 * スタック遷移画面（詳細/作成/編集系）の戻るボタン付きヘッダー。
 * 招待URLのようにアプリの外から直接この画面へ到達した場合、
 * ブラウザ履歴に戻り先（アプリ内のページ）が存在せず`navigate(-1)`が
 * 機能しないため、react-router-domが`history.state`に持つ`idx`
 * （このルーターインスタンスでの遷移回数。外部からの初回到達時は0）
 * を見て、戻り先が無ければホームへフォールバックする。
 */
export function BackHeader({ title }: BackHeaderProps) {
  const navigate = useNavigate();

  const handleBack = () => {
    const idx = (window.history.state as { idx?: number } | null)?.idx;
    if (idx) {
      navigate(-1);
    } else {
      navigate(paths.home);
    }
  };

  return (
    <header className="border-border bg-background sticky top-0 z-10 flex items-center gap-2 border-b px-2 py-3">
      <Button variant="ghost" size="icon" onClick={handleBack} aria-label="戻る">
        <ChevronLeft className="size-5" />
      </Button>
      <h1 className="text-base font-semibold">{title}</h1>
    </header>
  );
}
