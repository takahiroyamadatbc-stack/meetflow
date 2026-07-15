import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { communityKeys, listMembers, updateMyDisplayName } from "@/features/community/api";
import { useAuthUser } from "@/features/auth/useAuthUser";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { getErrorDisplay, ApiError } from "@/api/errors";
import { paths } from "@/routes/paths";

const displayNameSchema = z.object({
  displayName: z.string().max(30, "30文字以内で入力してください"),
});
type DisplayNameFormValues = z.infer<typeof displayNameSchema>;

/** このコミュニティでの表示名変更（S-05から遷移） */
export function DisplayNameEditPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const { userId } = useAuthUser();

  const { data: members, isLoading } = useQuery({
    queryKey: communityKeys.members(communityId!),
    queryFn: () => listMembers(communityId!),
    enabled: !!communityId,
  });
  const currentName = members?.find((m) => m.userId === userId)?.nickname;

  const form = useForm<DisplayNameFormValues>({
    resolver: zodResolver(displayNameSchema),
    defaultValues: { displayName: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: DisplayNameFormValues) =>
      updateMyDisplayName(communityId!, values.displayName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communityKeys.members(communityId!) });
      toast.success("表示名を変更しました");
      navigate(paths.communityDetail(communityId!));
    },
    onError: (err) => {
      if (err instanceof ApiError && getErrorDisplay(err.code) === "inline") {
        form.setError("displayName", { message: err.message });
        return;
      }
      handleApiError(err);
    },
  });

  if (isLoading) {
    return (
      <div className="p-4">
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  return (
    <div className="p-4">
      {currentName && (
        <p className="text-muted-foreground mb-4 text-sm">現在の表示名：{currentName}</p>
      )}
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
          className="grid gap-4"
        >
          <FormField
            control={form.control}
            name="displayName"
            render={({ field }) => (
              <FormItem>
                <FormLabel>このコミュニティでの表示名</FormLabel>
                <FormControl>
                  <Input
                    placeholder="未入力のままだとプロフィールのニックネームが使われます"
                    {...field}
                  />
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
