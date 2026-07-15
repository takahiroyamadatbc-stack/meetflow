import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { THEME_COLOR_PRESETS } from "@/features/community/theme-colors";

type ThemeColorPickerProps = {
  value: string | null;
  onChange: (color: string | null) => void;
};

/**
 * S-04（コミュニティ作成）・S-05c（テーマカラー変更）で使うプリセット
 * カラーパレット選択UI。選択中の色を再タップすると選択解除する。
 */
export function ThemeColorPicker({ value, onChange }: ThemeColorPickerProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {THEME_COLOR_PRESETS.map((color) => (
        <button
          key={color}
          type="button"
          aria-label={color}
          onClick={() => onChange(value === color ? null : color)}
          className={cn(
            "flex size-9 items-center justify-center rounded-full border-2 transition-colors",
            value === color ? "border-foreground" : "border-transparent",
          )}
          style={{ backgroundColor: color }}
        >
          {value === color && <Check className="size-4 text-white drop-shadow" />}
        </button>
      ))}
    </div>
  );
}
