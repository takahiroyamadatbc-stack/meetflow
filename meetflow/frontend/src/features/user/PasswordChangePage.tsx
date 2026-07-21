import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/ui/password-input";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { changePassword } from "@/features/auth/api";
import { passwordSchema } from "@/features/auth/passwordSchema";
import { paths } from "@/routes/paths";

const passwordChangeSchema = z
  .object({
    oldPassword: z.string().min(1, "現在のパスワードを入力してください"),
    newPassword: passwordSchema,
    confirmNewPassword: z.string().min(1, "確認用パスワードを入力してください"),
  })
  .refine((data) => data.newPassword === data.confirmNewPassword, {
    message: "パスワードが一致しません",
    path: ["confirmNewPassword"],
  });
type PasswordChangeFormValues = z.infer<typeof passwordChangeSchema>;

/** マイページからのパスワード変更（Issue #81） */
export function PasswordChangePage() {
  const navigate = useNavigate();

  const form = useForm<PasswordChangeFormValues>({
    resolver: zodResolver(passwordChangeSchema),
    defaultValues: { oldPassword: "", newPassword: "", confirmNewPassword: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: PasswordChangeFormValues) =>
      changePassword(values.oldPassword, values.newPassword),
    onSuccess: () => {
      toast.success("パスワードを変更しました");
      navigate(paths.myPage);
    },
    onError: (err: unknown) => {
      const name = err instanceof Error ? err.name : "";
      if (name === "NotAuthorizedException") {
        form.setError("oldPassword", { message: "現在のパスワードが正しくありません" });
        return;
      }
      toast.error(err instanceof Error ? err.message : "パスワードの変更に失敗しました");
    },
  });

  return (
    <div className="p-4">
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
          className="grid gap-4"
        >
          <FormField
            control={form.control}
            name="oldPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>現在のパスワード</FormLabel>
                <FormControl>
                  <PasswordInput autoComplete="current-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
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
            control={form.control}
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
          <Button type="submit" disabled={mutation.isPending}>
            変更する
          </Button>
        </form>
      </Form>
    </div>
  );
}
