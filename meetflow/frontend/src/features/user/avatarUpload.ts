import { uploadAvatarImage } from "@/features/user/api";

/** Issue #47: 画像リサイズはLambda側(Sharp/Pillow等)を挟まずクライアント側
 * (canvas)のみで行う方針（コールドスタート・実装コスト増を避けるため）。
 */
const AVATAR_MAX_SIZE = 256;
const AVATAR_OUTPUT_CONTENT_TYPE = "image/webp";
const AVATAR_OUTPUT_QUALITY = 0.85;

async function resizeAvatarImage(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, AVATAR_MAX_SIZE / Math.max(bitmap.width, bitmap.height));
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("画像の処理に失敗しました");
    }
    ctx.drawImage(bitmap, 0, 0, width, height);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, AVATAR_OUTPUT_CONTENT_TYPE, AVATAR_OUTPUT_QUALITY),
    );
    if (!blob) {
      throw new Error("画像の処理に失敗しました");
    }
    return blob;
  } finally {
    bitmap.close();
  }
}

/** 選択された画像ファイルをリサイズしてアップロードし、確定用の公開URLを返す */
export async function resizeAndUploadAvatar(file: File): Promise<string> {
  const blob = await resizeAvatarImage(file);
  return uploadAvatarImage(blob, AVATAR_OUTPUT_CONTENT_TYPE);
}
