import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { listMembers } from "@/features/community/api";
import { availabilityKeys, createAvailabilityRequest } from "@/features/availability/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

const createRequestSchema = z
  .object({
    targetPeriodStart: z.string().min(1, "対象期間の開始日を指定してください"),
    targetPeriodEnd: z.string().min(1, "対象期間の終了日を指定してください"),
    deadline: z.string().min(1, "提出期限を指定してください"),
    targetScope: z.enum(["ALL", "SPECIFIED"]),
    targetUserIds: z.array(z.string()),
    message: z.string().max(300, "300文字以内で入力してください"),
  })
  .refine((v) => v.targetScope !== "SPECIFIED" || v.targetUserIds.length > 0, {
    message: "対象メンバーを1人以上選択してください",
    path: ["targetUserIds"],
  });

type CreateRequestFormValues = z.infer<typeof createRequestSchema>;

/** S-26 空き予定提出リクエスト作成画面 */
export function AvailabilityRequestCreatePage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const { data: members } = useQuery({
    queryKey: ["communities", communityId, "members"],
    queryFn: () => listMembers(communityId!),
    enabled: !!communityId,
  });

  const form = useForm<CreateRequestFormValues>({
    resolver: zodResolver(createRequestSchema),
    defaultValues: {
      targetPeriodStart: "",
      targetPeriodEnd: "",
      deadline: "",
      targetScope: "ALL",
      targetUserIds: [],
      message: "",
    },
  });

  const targetScope = form.watch("targetScope");

  const mutation = useMutation({
    mutationFn: (values: CreateRequestFormValues) =>
      createAvailabilityRequest(communityId!, {
        targetPeriodStart: `${values.targetPeriodStart}T00:00:00`,
        targetPeriodEnd: `${values.targetPeriodEnd}T23:59:59`,
        deadline: values.deadline,
        targetScope: values.targetScope,
        targetUserIds: values.targetScope === "SPECIFIED" ? values.targetUserIds : undefined,
        message: values.message || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: availabilityKeys.requests(communityId!) });
      toast.success("提出リクエストを送信しました");
      navigate(paths.availabilityRequestList(communityId!), { replace: true });
    },
    onError: handleApiError,
  });

  function onSubmit(values: CreateRequestFormValues) {
    mutation.mutate(values);
  }

  return (
    <div className="p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
          <div className="flex gap-2">
            <FormField
              control={form.control}
              name="targetPeriodStart"
              render={({ field }) => (
                <FormItem className="flex-1">
                  <FormLabel>対象期間（開始）</FormLabel>
                  <FormControl>
                    <Input type="date" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="targetPeriodEnd"
              render={({ field }) => (
                <FormItem className="flex-1">
                  <FormLabel>対象期間（終了）</FormLabel>
                  <FormControl>
                    <Input type="date" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="deadline"
            render={({ field }) => (
              <FormItem>
                <FormLabel>提出期限</FormLabel>
                <FormControl>
                  <Input type="datetime-local" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="targetScope"
            render={({ field }) => (
              <FormItem>
                <FormLabel>対象範囲</FormLabel>
                <FormControl>
                  <ToggleGroup
                    value={[field.value]}
                    onValueChange={(v) => v[0] && field.onChange(v[0])}
                  >
                    <ToggleGroupItem value="ALL">全員</ToggleGroupItem>
                    <ToggleGroupItem value="SPECIFIED">指名</ToggleGroupItem>
                  </ToggleGroup>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {targetScope === "SPECIFIED" && (
            <FormField
              control={form.control}
              name="targetUserIds"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>対象メンバー</FormLabel>
                  <div className="flex flex-col gap-2">
                    {members?.map((member) => (
                      <div key={member.userId} className="flex items-center gap-2">
                        <Checkbox
                          id={`member-${member.userId}`}
                          checked={field.value.includes(member.userId)}
                          onCheckedChange={(checked) =>
                            field.onChange(
                              checked
                                ? [...field.value, member.userId]
                                : field.value.filter((id) => id !== member.userId),
                            )
                          }
                        />
                        <Label htmlFor={`member-${member.userId}`} className="font-normal">
                          {member.nickname}
                        </Label>
                      </div>
                    ))}
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          <FormField
            control={form.control}
            name="message"
            render={({ field }) => (
              <FormItem>
                <FormLabel>メッセージ（任意）</FormLabel>
                <FormControl>
                  <Textarea rows={3} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit" disabled={mutation.isPending}>
            送信する
          </Button>
        </form>
      </Form>
    </div>
  );
}
