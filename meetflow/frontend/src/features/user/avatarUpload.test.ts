import { beforeEach, describe, expect, it, vi } from "vitest";
import { resizeAndUploadAvatar } from "@/features/user/avatarUpload";
import * as userApi from "@/features/user/api";
import * as imageResize from "@/lib/imageResize";

// resizeImageToWebpはcanvas/createImageBitmap依存でjsdomでは実行できないため、
// リサイズ→アップロードの合成ロジックのみをモックで検証する。
vi.mock("@/lib/imageResize");
vi.mock("@/features/user/api");

describe("resizeAndUploadAvatar", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("256px・webp・quality0.85でリサイズしてからアップロードし、公開URLを返す", async () => {
    const file = new File(["dummy"], "avatar.png", { type: "image/png" });
    const resizedBlob = new Blob(["resized"], { type: "image/webp" });
    vi.mocked(imageResize.resizeImageToWebp).mockResolvedValue(resizedBlob);
    vi.mocked(userApi.uploadAvatarImage).mockResolvedValue("https://example.com/avatar.webp");

    const result = await resizeAndUploadAvatar(file);

    expect(imageResize.resizeImageToWebp).toHaveBeenCalledWith(file, 256, 0.85);
    expect(userApi.uploadAvatarImage).toHaveBeenCalledWith(resizedBlob, "image/webp");
    expect(result).toBe("https://example.com/avatar.webp");
  });

  it("リサイズに失敗した場合はアップロードを呼ばずに例外を伝播する", async () => {
    const file = new File(["dummy"], "avatar.png", { type: "image/png" });
    vi.mocked(imageResize.resizeImageToWebp).mockRejectedValue(new Error("画像の処理に失敗しました"));

    await expect(resizeAndUploadAvatar(file)).rejects.toThrow("画像の処理に失敗しました");
    expect(userApi.uploadAvatarImage).not.toHaveBeenCalled();
  });
});
