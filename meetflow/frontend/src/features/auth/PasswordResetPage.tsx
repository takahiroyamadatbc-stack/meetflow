import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { confirmPasswordReset, requestPasswordReset } from "@/features/auth/api";
import { passwordSchema } from "@/features/auth/passwordSchema";
import { paths } from "@/routes/paths";
import { BrandLogo } from "@/components/brand/BrandLogo";

const emailSchema = z.object({
  email: z.string().min(1, "メールアドレスを入力してください").email("メールアドレスの形式が正しくありません"),
});
type EmailFormValues = z.infer<typeof emailSchema>;

const resetSchema = z
  .object({
    code: z.string().min(1, "確認コードを入力してください"),
    newPassword: passwordSchema,
    confirmNewPassword: z.string().min(1, "確認用パスワードを入力してください"),
  })
  .refine((data) => data.newPassword === data.confirmNewPassword, {
    message: "パスワードが一致しません",
    path: ["confirmNewPassword"],
  });
type ResetFormValues = z.infer<typeof resetSchema>;

/**
 * パスワードリセット画面（Issue #81）。
 * メールアドレス入力→確認コード＋新パスワード入力の2段階。
 * UserPoolClientはprevent_user_existence_errors=trueのため、未登録の
 * メールアドレスでも申請自体は常に成功したかのように見え、確認コード
 * 入力ステップへ進む（列挙攻撃対策としては意図通りの挙動）。
 */
export function PasswordResetPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const emailForm = useForm<EmailFormValues>({
    resolver: zodResolver(emailSchema),
    defaultValues: { email: "" },
  });

  async function onSubmitEmail(values: EmailFormValues) {
    setSubmitError(null);
    try {
      await requestPasswordReset(values.email);
      setEmail(values.email);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "確認コードの送信に失敗しました");
    }
  }

  const resetForm = useForm<ResetFormValues>({
    resolver: zodResolver(resetSchema),
    defaultValues: { code: "", newPassword: "", confirmNewPassword: "" },
  });

  async function onSubmitReset(values: ResetFormValues) {
    setSubmitError(null);
    if (!email) return;
    try {
      await confirmPasswordReset(email, values.code, values.newPassword);
      navigate(paths.login, {
        replace: true,
        state: { email, infoMessage: "パスワードを再設定しました。ログインしてください" },
      });
    } catch (err) {
      const name = err instanceof Error ? err.name : "";
      if (name === "CodeMismatchException") {
        setSubmitError("確認コードが正しくありません");
        return;
      }
      if (name === "ExpiredCodeException") {
        setSubmitError("確認コードの有効期限が切れています。もう一度最初からやり直してください");
        return;
      }
      setSubmitError(err instanceof Error ? err.message : "パスワードの再設定に失敗しました");
    }
  }

  return (
    <div className="flex flex-1 flex-col justify-center px-6 py-10">
      <BrandLogo />
      <Card>
        <CardHeader>
          <CardTitle>パスワードの再設定</CardTitle>
        </CardHeader>
        <CardContent>
          {!email ? (
            <>
              <p className="text-muted-foreground mb-4 text-sm">
                登録済みのメールアドレスを入力してください。確認コードを送信します。
              </p>
              <Form key="email-step" {...emailForm}>
                <form onSubmit={emailForm.handleSubmit(onSubmitEmail)} className="grid gap-4">
                  <FormField
                    control={emailForm.control}
                    name="email"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>メールアドレス</FormLabel>
                        <FormControl>
                          <Input type="email" autoComplete="email" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  {submitError && <p className="text-destructive text-sm">{submitError}</p>}
                  <Button type="submit" disabled={emailForm.formState.isSubmitting}>
                    確認コードを送信する
                  </Button>
                </form>
              </Form>
            </>
          ) : (
            <>
              <p className="text-muted-foreground mb-4 text-sm">
                {email}宛に届いた確認コードと、新しいパスワードを入力してください。
              </p>
              <Form key="reset-step" {...resetForm}>
                <form onSubmit={resetForm.handleSubmit(onSubmitReset)} className="grid gap-4">
                  <FormField
                    control={resetForm.control}
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
                  <FormField
                    control={resetForm.control}
                    name="newPassword"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>新しいパスワード</FormLabel>
                        <FormControl>
                          <PasswordInput autoComplete="new-password" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={resetForm.control}
                    name="confirmNewPassword"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>新しいパスワード（確認用）</FormLabel>
                        <FormControl>
                          <PasswordInput autoComplete="new-password" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  {submitError && <p className="text-destructive text-sm">{submitError}</p>}
                  <Button type="submit" disabled={resetForm.formState.isSubmitting}>
                    パスワードを再設定する
                  </Button>
                </form>
              </Form>
            </>
          )}
          <p className="text-muted-foreground mt-4 text-center text-sm">
            <Link to={paths.login} className="text-primary underline underline-offset-4">
              ログイン画面に戻る
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
