// PWA用アイコンセット・OGP画像を元SVG(src/assets/brand/)から生成するスクリプト
// 実行: npm run generate-icons
import sharp from "sharp";
import { readFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");
const brandDir = path.join(rootDir, "src", "assets", "brand");
const publicDir = path.join(rootDir, "public");

const ICON_SVG = path.join(brandDir, "meetflow-icon-v2.svg");
const LOGO_SVG = path.join(brandDir, "meetflow-logo-v3-gorgeous.svg");
const ICON_SOURCE_SIZE = 200;
const LOGO_SOURCE_WIDTH = 680;
const LOGO_SOURCE_HEIGHT = 210;

// meetflow-icon-v2.svgの背景色(rect fill)と同一。マスカブルアイコン・OGP画像の余白埋めに使う
const BRAND_BACKGROUND = "#FBF8F3";

// SVGを指定サイズの正方形PNGバッファへラスタライズする
// density(DPI)を目標サイズに応じて引き上げてからresizeすることで、拡大時のボケを防ぐ
async function rasterizeSquareSvg(svgPath, sourceSize, targetSize) {
  const svgBuffer = await readFile(svgPath);
  const density = Math.ceil(96 * (targetSize / sourceSize));
  return sharp(svgBuffer, { density }).resize(targetSize, targetSize).png().toBuffer();
}

async function writeSquareIcon(svgPath, sourceSize, targetSize, filename) {
  const buffer = await rasterizeSquareSvg(svgPath, sourceSize, targetSize);
  await sharp(buffer).toFile(path.join(publicDir, filename));
  console.log(`generated: ${filename}`);
}

// マスカブルアイコン: 中央80%セーフゾーンにアイコン全体を収め、周囲を背景色で埋める
// (OS側で円形/角丸マスクをかけられても、タイル部分が欠けないようにするため)
async function writeMaskableIcon(svgPath, sourceSize, canvasSize, filename) {
  const safeZoneSize = Math.round(canvasSize * 0.8);
  const iconBuffer = await rasterizeSquareSvg(svgPath, sourceSize, safeZoneSize);
  await sharp({
    create: { width: canvasSize, height: canvasSize, channels: 4, background: BRAND_BACKGROUND },
  })
    .composite([{ input: iconBuffer, gravity: "center" }])
    .png()
    .toFile(path.join(publicDir, filename));
  console.log(`generated: ${filename}`);
}

// OGP画像: ロゴ(アイコン+ワードマーク+タグライン)を横長キャンバスの中央に配置する
async function writeOgImage(svgPath, sourceWidth, sourceHeight, canvasWidth, canvasHeight, filename) {
  const svgBuffer = await readFile(svgPath);
  const targetWidth = Math.round(canvasWidth * 0.75);
  const targetHeight = Math.round((sourceHeight / sourceWidth) * targetWidth);
  const density = Math.ceil(96 * (targetWidth / sourceWidth));

  const logoBuffer = await sharp(svgBuffer, { density }).resize(targetWidth, targetHeight).png().toBuffer();

  await sharp({
    create: { width: canvasWidth, height: canvasHeight, channels: 4, background: BRAND_BACKGROUND },
  })
    .composite([{ input: logoBuffer, gravity: "center" }])
    .png()
    .toFile(path.join(publicDir, filename));
  console.log(`generated: ${filename}`);
}

async function main() {
  await mkdir(publicDir, { recursive: true });

  // favicon
  await writeSquareIcon(ICON_SVG, ICON_SOURCE_SIZE, 16, "favicon-16x16.png");
  await writeSquareIcon(ICON_SVG, ICON_SOURCE_SIZE, 32, "favicon-32x32.png");
  await writeSquareIcon(ICON_SVG, ICON_SOURCE_SIZE, 48, "favicon-48x48.png");

  // apple-touch-icon
  await writeSquareIcon(ICON_SVG, ICON_SOURCE_SIZE, 180, "apple-touch-icon.png");

  // PWAマニフェスト用
  await writeSquareIcon(ICON_SVG, ICON_SOURCE_SIZE, 192, "icon-192x192.png");
  await writeSquareIcon(ICON_SVG, ICON_SOURCE_SIZE, 512, "icon-512x512.png");

  // マスカブルアイコン
  await writeMaskableIcon(ICON_SVG, ICON_SOURCE_SIZE, 512, "maskable-icon-512x512.png");

  // OGP画像
  await writeOgImage(LOGO_SVG, LOGO_SOURCE_WIDTH, LOGO_SOURCE_HEIGHT, 1200, 630, "og-image.png");

  console.log("すべてのアイコン・OGP画像の生成が完了しました");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
