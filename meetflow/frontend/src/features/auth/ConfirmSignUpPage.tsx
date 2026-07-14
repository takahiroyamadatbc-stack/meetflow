import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { confirmSignUpCode } from "@/features/auth/api";
import { paths } from "@/routes/paths";
import { BrandLogo } from "@/components/brand/BrandLogo";

const confirmSchema = z.object({
  code: z.string().min(1, "確認コードを入力してください"),
});

type ConfirmFormValues = z.infer<typeof confirmSchema>;

/** S-01 確認コード入力画面 */
export function ConfirmSignUpPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const email = (location.state as { email?: string } | null)?.email ?? "";
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<ConfirmFormValues>({
    resolver: zodResolver(confirmSchema),
    defaultValues: { code: "" },
  });

  async function onSubmit(values: ConfirmFormValues) {
    setSubmitError(null);
    if (!email) {
      setSubmitError("メールアドレスが取得できませんでした。新規登録からやり直してください");
      return;
    }
    try {
      await confirmSignUpCode(email, values.code);
      // 確認後は自動ログインせず、明示的に再度ログインさせる
      navigate(paths.login);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "確認コードの検証に失敗しました");
    }
  }

  return (
    <div className="flex flex-1 flex-col justify-center px-6 py-10">
      <BrandLogo />
      <Card>
        <CardHeader>
          <CardTitle>確認コード入力</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground mb-4 text-sm">
            {email || "登録したメールアドレス"}宛に届いた確認コードを入力してください。
          </p>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>確認コード</FormLabel>
                    <FormControl>
                      <Input inputMode="numeric" autoComplete="one-time-code" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {submitError && <p className="text-destructive text-sm">{submitError}</p>}
              <Button type="submit" disabled={form.formState.isSubmitting}>
                確認する
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
