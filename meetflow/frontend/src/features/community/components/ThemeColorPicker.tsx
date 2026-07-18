import { useRef } from "react";
import { Check, Pipette } from "lucide-react";
import { cn } from "@/lib/utils";
import { THEME_COLOR_PRESETS } from "@/features/community/theme-colors";

type ThemeColorPickerProps = {
  value: string | null;
  onChange: (color: string | null) => void;
};

/**
 * S-04（コミュニティ作成）・S-05c（テーマカラー変更）で使うプリセット
 * カラーパレット選択UI。選択中の色を再タップすると選択解除する。
 * Issue #30: プリセットに無い任意の色（オリジナルカラー）も、ブラウザ
 * ネイティブのカラーピッカー（`input[type=color]`）経由で選択できる。
 */
export function ThemeColorPicker({ value, onChange }: ThemeColorPickerProps) {
  const customInputRef = useRef<HTMLInputElement>(null);
  const isPreset = value !== null && (THEME_COLOR_PRESETS as readonly string[]).includes(value);
  const isCustom = value !== null && !isPreset;

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

      <button
        type="button"
        aria-label="オリジナルカラーを選択"
        onClick={() => customInputRef.current?.click()}
        className={cn(
          "flex size-9 items-center justify-center rounded-full border-2 transition-colors",
          isCustom ? "border-foreground" : "border-dashed border-muted-foreground",
        )}
        style={isCustom ? { backgroundColor: value } : undefined}
      >
        {isCustom ? (
          <Check className="size-4 text-white drop-shadow" />
        ) : (
          <Pipette className="text-muted-foreground size-4" />
        )}
      </button>
      <input
        ref={customInputRef}
        type="color"
        aria-label="オリジナルカラーのカラーピッカー"
        value={isCustom ? value : "#000000"}
        onChange={(e) => onChange(e.target.value)}
        className="sr-only"
      />
    </div>
  );
}
