import { useMutation } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { createInvite } from "@/features/community/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";

/**
 * S-06 招待URL発行画面。
 * invite失効（revoke）APIは未実装のため、Phase1では発行とコピーのみ提供する
 * （Phase1実装計画の食い違い#4）。
 */
export function InvitePage() {
  const { communityId } = useParams<{ communityId: string }>();
  const handleApiError = useApiErrorToast();
  const [copied, setCopied] = useState(false);

  const mutation = useMutation({
    mutationFn: () => createInvite(communityId!),
    onError: handleApiError,
  });

  async function handleCopy(url: string) {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardContent className="flex flex-col gap-4">
          <p className="text-muted-foreground text-sm">
            発行した招待URLを、招待したいメンバーに共有してください。
          </p>
          {!mutation.data ? (
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              招待URLを発行する
            </Button>
          ) : (
            <div className="flex gap-2">
              <Input readOnly value={mutation.data.url} />
              <Button
                variant="outline"
                size="icon"
                onClick={() => handleCopy(mutation.data!.url)}
                aria-label="URLをコピー"
              >
                {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
