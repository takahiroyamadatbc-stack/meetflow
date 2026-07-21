import { useMutation } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { createInvite, revokeInvite } from "@/features/community/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";

/**
 * S-06 招待URL発行画面（画面設計書v1.4 S-06: URL発行・コピー・無効化）。
 */
export function InvitePage() {
  const { communityId } = useParams<{ communityId: string }>();
  const handleApiError = useApiErrorToast();
  const [copied, setCopied] = useState(false);

  const createMutation = useMutation({
    mutationFn: () => createInvite(communityId!),
    onError: handleApiError,
  });

  // 招待URLは`.../invite/{token}`形式（api.tsのcreateInvite参照）なので、
  // 無効化APIが必要とするtokenは発行済みURLの末尾セグメントから取り出せる
  // （一覧・取得APIを別途持たなくても、直前に発行したURLの無効化だけなら
  // これで完結する）。
  const revokeMutation = useMutation({
    mutationFn: (url: string) => revokeInvite(url.split("/").pop()!),
    onSuccess: () => createMutation.reset(),
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
          {!createMutation.data ? (
            <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
              招待URLを発行する
            </Button>
          ) : (
            <>
              <div className="flex gap-2">
                <Input readOnly value={createMutation.data.url} />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => handleCopy(createMutation.data!.url)}
                  aria-label="URLをコピー"
                >
                  {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                </Button>
              </div>
              <div className="flex flex-col items-center gap-2 py-2">
                <div className="rounded-lg bg-white p-3">
                  <QRCodeSVG value={createMutation.data.url} size={180} bgColor="#ffffff" fgColor="#000000" />
                </div>
                <p className="text-muted-foreground text-xs">QRコードを読み取っても招待URLを開けます</p>
              </div>
              <Button
                variant="destructive"
                onClick={() => revokeMutation.mutate(createMutation.data!.url)}
                disabled={revokeMutation.isPending}
              >
                このURLを無効化する
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
