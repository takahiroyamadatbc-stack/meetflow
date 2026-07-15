/**
 * コミュニティのテーマカラー用プリセットパレット（画面設計書v1.5 S-04, S-05c）。
 * 設計書はプリセットの具体的な色までは規定していないため、視認性の良い
 * 彩度の高い9色をここで定義する。API設計書v1.9の例に合わせ先頭をIndigoにする。
 */
export const THEME_COLOR_PRESETS = [
  "#6366F1", // Indigo
  "#EF4444", // Red
  "#F97316", // Orange
  "#F59E0B", // Amber
  "#22C55E", // Green
  "#14B8A6", // Teal
  "#3B82F6", // Blue
  "#A855F7", // Purple
  "#EC4899", // Pink
] as const;

/** テーマカラー未設定時にフォールバックする、アプリの既定色。 */
export const DEFAULT_THEME_COLOR = "#6366F1";
