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
import { signUpUser } from "@/features/auth/api";
import { paths } from "@/routes/paths";
import { BrandLogo } from "@/components/brand/BrandLogo";

const signUpSchema = z
  .object({
    nickname: z.string().min(1, "ニックネームを入力してください").max(30, "30文字以内で入力してください"),
    email: z.string().min(1, "メールアドレスを入力してください").email("メールアドレスの形式が正しくありません"),
    password: z
      .string()
      .min(8, "8文字以上で入力してください")
      .regex(/[a-z]/, "小文字を含めてください")
      .regex(/[A-Z]/, "大文字を含めてください")
      .regex(/[0-9]/, "数字を含めてください"),
    confirmPassword: z.string().min(1, "確認用パスワードを入力してください"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "パスワードが一致しません",
    path: ["confirmPassword"],
  });

type SignUpFormValues = z.infer<typeof signUpSchema>;

/** S-01 新規登録画面 */
export function SignUpPage() {
  const navigate = useNavigate();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<SignUpFormValues>({
    resolver: zodResolver(signUpSchema),
    defaultValues: { nickname: "", email: "", password: "", confirmPassword: "" },
  });

  async function onSubmit(values: SignUpFormValues) {
    setSubmitError(null);
    try {
      await signUpUser(values.email, values.password, values.nickname);
      navigate(paths.signupConfirm, { state: { email: values.email, nickname: values.nickname } });
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "登録に失敗しました");
    }
  }

  return (
    <div className="flex flex-1 flex-col justify-center px-6 py-10">
      <BrandLogo />
      <Card>
        <CardHeader>
          <CardTitle>新規登録</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
              <FormField
                control={form.control}
                name="nickname"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>ニックネーム</FormLabel>
                    <FormControl>
                      <Input placeholder="例：たろう" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
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
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>パスワード</FormLabel>
                    <FormControl>
                      <PasswordInput autoComplete="new-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="confirmPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>パスワード（確認用）</FormLabel>
                    <FormControl>
                      <PasswordInput autoComplete="new-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {submitError && <p className="text-destructive text-sm">{submitError}</p>}
              <Button type="submit" disabled={form.formState.isSubmitting}>
                登録する
              </Button>
            </form>
          </Form>
          <p className="text-muted-foreground mt-4 text-center text-sm">
            アカウントをお持ちの方は
            <Link to={paths.login} className="text-primary underline underline-offset-4">
              ログイン
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
