import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useLocation, useNavigate } from "react-router-dom";
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
import { signInUser } from "@/features/auth/api";
import { paths } from "@/routes/paths";
import { BrandLogo } from "@/components/brand/BrandLogo";

const loginSchema = z.object({
  email: z.string().min(1, "メールアドレスを入力してください").email("メールアドレスの形式が正しくありません"),
  password: z.string().min(1, "パスワードを入力してください"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

/** S-01 ログイン画面 */
export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  async function onSubmit(values: LoginFormValues) {
    setSubmitError(null);
    try {
      await signInUser(values.email, values.password);
      const from = (location.state as { from?: Location } | null)?.from;
      navigate(from ? `${from.pathname}${from.search}` : paths.home, { replace: true });
    } catch (err) {
      const name = err instanceof Error ? err.name : "";
      if (name === "UserNotConfirmedException") {
        navigate(paths.signupConfirm, { state: { email: values.email } });
        return;
      }
      if (name === "NotAuthorizedException") {
        setSubmitError("メールアドレスまたはパスワードが違います");
        return;
      }
      setSubmitError(err instanceof Error ? err.message : "ログインに失敗しました");
    }
  }

  return (
    <div className="flex flex-1 flex-col justify-center px-6 py-10">
      <BrandLogo />
      <Card>
        <CardHeader>
          <CardTitle>ログイン</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
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
                      <Input type="password" autoComplete="current-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {submitError && <p className="text-destructive text-sm">{submitError}</p>}
              <Button type="submit" disabled={form.formState.isSubmitting}>
                ログイン
              </Button>
            </form>
          </Form>
          <p className="text-muted-foreground mt-4 text-center text-sm">
            アカウントをお持ちでない方は
            <Link to={paths.signup} className="text-primary underline underline-offset-4">
              新規登録
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
