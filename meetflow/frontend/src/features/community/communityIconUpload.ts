import { uploadCommunityIconImage } from "@/features/community/api";
import { resizeImageToWebp } from "@/lib/imageResize";

/** Issue #52: リサイズ方針はユーザーアバター（Issue #47）と揃える */
const ICON_MAX_SIZE = 256;
const ICON_OUTPUT_CONTENT_TYPE = "image/webp";
const ICON_OUTPUT_QUALITY = 0.85;

/** 選択された画像ファイルをリサイズしてアップロードし、確定用の公開URLを返す */
export async function resizeAndUploadCommunityIcon(
  communityId: string,
  file: File,
): Promise<string> {
  const blob = await resizeImageToWebp(file, ICON_MAX_SIZE, ICON_OUTPUT_QUALITY);
  return uploadCommunityIconImage(communityId, blob, ICON_OUTPUT_CONTENT_TYPE);
}
