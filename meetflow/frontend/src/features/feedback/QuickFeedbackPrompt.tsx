import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { createFeedback } from "@/features/feedback/api";
import type { FeedbackRating } from "@/features/feedback/types";

const RATINGS: { value: FeedbackRating; emoji: string; label: string }[] = [
  { value: "BAD", emoji: "😞", label: "不満" },
  { value: "NEUTRAL", emoji: "😐", label: "ふつう" },
  { value: "GOOD", emoji: "😊", label: "満足" },
];

/**
 * 画面設計書v1.13 4b「簡易フィードバックUI（横断要素）」。主要な操作の
 * 直後に差し込む1クリック評価。一度送信または閉じたら、同じ`storageKey`
 * では再表示しない（localStorageに記録。詳細入力は求めない）。
 */
export function QuickFeedbackPrompt({
  relatedFeature,
  storageKey,
}: {
  relatedFeature: string;
  /** 同じ操作に対して二度出さないためのキー（例：`matching:${communityId}:${templateId}`） */
  storageKey: string;
}) {
  const fullKey = `meetflow.quickFeedback.${storageKey}`;
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(fullKey) === "1");
  const [sent, setSent] = useState(false);

  const mutation = useMutation({
    mutationFn: (rating: FeedbackRating) =>
      createFeedback({ kind: "QUICK", relatedFeature, rating }),
    onSuccess: () => {
      localStorage.setItem(fullKey, "1");
      setSent(true);
    },
  });

  if (dismissed) {
    return null;
  }

  function dismiss() {
    localStorage.setItem(fullKey, "1");
    setDismissed(true);
  }

  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-2">
        {sent ? (
          <p className="text-muted-foreground text-sm">フィードバックありがとうございました</p>
        ) : (
          <>
            <p className="text-sm">この結果は満足ですか？</p>
            <div className="flex items-center gap-1">
              {RATINGS.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  aria-label={r.label}
                  className="text-xl leading-none disabled:opacity-50"
                  disabled={mutation.isPending}
                  onClick={() => mutation.mutate(r.value)}
                >
                  {r.emoji}
                </button>
              ))}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-6"
                aria-label="閉じる"
                onClick={dismiss}
              >
                <X className="size-4" />
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
