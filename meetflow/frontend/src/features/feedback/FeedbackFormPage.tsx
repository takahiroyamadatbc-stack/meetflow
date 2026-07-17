import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { createFeedback, uploadFeedbackAttachment } from "@/features/feedback/api";
import {
  FEEDBACK_CATEGORY_LABELS,
  RELATED_FEATURE_OPTIONS,
  type FeedbackCategory,
} from "@/features/feedback/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { getErrorDisplay, ApiError } from "@/api/errors";
import { paths } from "@/routes/paths";

const CATEGORIES: FeedbackCategory[] = ["BUG", "FEATURE_REQUEST", "UX_IMPROVEMENT"];

const feedbackSchema = z.object({
  category: z.enum(["BUG", "FEATURE_REQUEST", "UX_IMPROVEMENT"]),
  relatedFeature: z.string().min(1, "該当機能を選択してください"),
  content: z.string().max(2000, "2000文字以内で入力してください"),
});
type FeedbackFormValues = z.infer<typeof feedbackSchema>;

/** S-28 フィードバック投稿画面 */
export function FeedbackFormPage() {
  const navigate = useNavigate();
  const handleApiError = useApiErrorToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachmentKeys, setAttachmentKeys] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const form = useForm<FeedbackFormValues>({
    resolver: zodResolver(feedbackSchema),
    defaultValues: { category: "BUG", relatedFeature: "", content: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: FeedbackFormValues) =>
      createFeedback({
        kind: "DETAILED",
        relatedFeature: values.relatedFeature,
        category: values.category,
        content: values.content || undefined,
        attachmentKeys: attachmentKeys.length > 0 ? attachmentKeys : undefined,
      }),
    onSuccess: () => {
      toast.success("フィードバックを送信しました。ありがとうございました");
      navigate(paths.myPage, { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError && getErrorDisplay(err.code) === "inline") {
        form.setError("relatedFeature", { message: err.message });
        return;
      }
      handleApiError(err);
    },
  });

  async function handleFilesSelected(files: FileList | null) {
    if (!files || files.length === 0) return;
    setIsUploading(true);
    try {
      const uploaded = await Promise.all(
        Array.from(files).map((file) => uploadFeedbackAttachment(file)),
      );
      setAttachmentKeys((prev) => [...prev, ...uploaded]);
    } catch {
      toast.error("スクリーンショットのアップロードに失敗しました");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function removeAttachment(key: string) {
    setAttachmentKeys((prev) => prev.filter((k) => k !== key));
  }

  function onSubmit(values: FeedbackFormValues) {
    mutation.mutate(values);
  }

  return (
    <div className="p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
          <FormField
            control={form.control}
            name="category"
            render={({ field }) => (
              <FormItem>
                <FormLabel>フィードバック種別</FormLabel>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map((category) => (
                    <Button
                      key={category}
                      type="button"
                      variant={field.value === category ? "default" : "outline"}
                      size="sm"
                      onClick={() => field.onChange(category)}
                    >
                      {FEEDBACK_CATEGORY_LABELS[category]}
                    </Button>
                  ))}
                </div>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="relatedFeature"
            render={({ field }) => (
              <FormItem>
                <FormLabel>該当機能</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="選択してください" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {RELATED_FEATURE_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="content"
            render={({ field }) => (
              <FormItem>
                <FormLabel>詳細内容（任意）</FormLabel>
                <FormControl>
                  <Textarea rows={6} placeholder="気づいたことを教えてください" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid gap-2">
            <span className="text-sm font-medium">スクリーンショット（任意）</span>
            {attachmentKeys.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {attachmentKeys.map((key) => (
                  <div
                    key={key}
                    className="bg-muted flex items-center gap-1 rounded-md px-2 py-1 text-xs"
                  >
                    <span className="max-w-40 truncate">{key.split("/").pop()}</span>
                    <button
                      type="button"
                      aria-label="削除"
                      onClick={() => removeAttachment(key)}
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              multiple
              disabled={isUploading}
              onChange={(e) => handleFilesSelected(e.target.files)}
              className="text-sm"
            />
          </div>

          <Button type="submit" disabled={mutation.isPending || isUploading}>
            送信する
          </Button>
        </form>
      </Form>
    </div>
  );
}
