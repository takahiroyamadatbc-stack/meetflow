/**
 * 画像ファイルを指定した最大辺のサイズにリサイズし、WebP形式のBlobに変換する。
 * リサイズはLambda側(Sharp/Pillow等)を挟まずクライアント側(canvas)のみで行う
 * 方針（コールドスタート・実装コスト増を避けるため、Issue #47）。ユーザー
 * アバター（features/user/avatarUpload.ts）とコミュニティアイコン
 * （features/community/communityIconUpload.ts、Issue #52）の両方が使う。
 */
export async function resizeImageToWebp(
  file: File,
  maxSize: number,
  quality: number,
): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, maxSize / Math.max(bitmap.width, bitmap.height));
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
      canvas.toBlob(resolve, "image/webp", quality),
    );
    if (!blob) {
      throw new Error("画像の処理に失敗しました");
    }
    return blob;
  } finally {
    bitmap.close();
  }
}
