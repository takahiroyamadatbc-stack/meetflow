import { uploadAvatarImage } from "@/features/user/api";
import { resizeImageToWebp } from "@/lib/imageResize";

const AVATAR_MAX_SIZE = 256;
const AVATAR_OUTPUT_CONTENT_TYPE = "image/webp";
const AVATAR_OUTPUT_QUALITY = 0.85;

/** 選択された画像ファイルをリサイズしてアップロードし、確定用の公開URLを返す */
export async function resizeAndUploadAvatar(file: File): Promise<string> {
  const blob = await resizeImageToWebp(file, AVATAR_MAX_SIZE, AVATAR_OUTPUT_QUALITY);
  return uploadAvatarImage(blob, AVATAR_OUTPUT_CONTENT_TYPE);
}
