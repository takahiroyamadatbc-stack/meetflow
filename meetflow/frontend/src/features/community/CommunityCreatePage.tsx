import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { communityKeys, createCommunity } from "@/features/community/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { getErrorDisplay, ApiError } from "@/api/errors";
import { paths } from "@/routes/paths";

const createCommunitySchema = z.object({
  name: z.string().min(1, "コミュニティ名を入力してください").max(50, "50文字以内で入力してください"),
  description: z.string().max(300, "300文字以内で入力してください"),
  genre: z.string().max(30, "30文字以内で入力してください"),
  memberApprovalRequired: z.boolean(),
});

type CreateCommunityFormValues = z.infer<typeof createCommunitySchema>;

/** S-04 コミュニティ作成画面 */
export function CommunityCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const form = useForm<CreateCommunityFormValues>({
    resolver: zodResolver(createCommunitySchema),
    defaultValues: { name: "", description: "", genre: "", memberApprovalRequired: false },
  });

  const mutation = useMutation({
    mutationFn: createCommunity,
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: communityKeys.all });
      toast.success("コミュニティを作成しました");
      navigate(paths.communityDetail(created.communityId), { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError && getErrorDisplay(err.code) === "inline") {
        form.setError("name", { message: err.message });
        return;
      }
      handleApiError(err);
    },
  });

  function onSubmit(values: CreateCommunityFormValues) {
    mutation.mutate(values);
  }

  return (
    <div className="p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>コミュニティ名</FormLabel>
                <FormControl>
                  <Input placeholder="例：週末麻雀部" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="genre"
            render={({ field }) => (
              <FormItem>
                <FormLabel>ジャンル</FormLabel>
                <FormControl>
                  <Input placeholder="例：麻雀" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="description"
            render={({ field }) => (
              <FormItem>
                <FormLabel>説明</FormLabel>
                <FormControl>
                  <Textarea rows={4} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="memberApprovalRequired"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between">
                <div>
                  <FormLabel>参加に承認を必要とする</FormLabel>
                  <FormDescription>
                    オンにすると、招待URLからの参加が管理者の承認待ちになります
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
          <Button type="submit" disabled={mutation.isPending}>
            作成する
          </Button>
        </form>
      </Form>
    </div>
  );
}
