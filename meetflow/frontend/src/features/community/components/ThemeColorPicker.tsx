import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { THEME_COLOR_PRESETS } from "@/features/community/theme-colors";

type ThemeColorPickerProps = {
  value: string | null;
  onChange: (color: string | null) => void;
};

const HEX_COLOR_PATTERN = /^#([0-9A-Fa-f]{6})$/;

/**
 * S-04（コミュニティ作成）・S-05c（テーマカラー変更）で使うプリセット
 * カラーパレット選択UI。選択中の色を再タップすると選択解除する。
 * Issue #77: オリジナルカラーはブラウザネイティブのカラーピッカーではなく、
 * カラーコード(hex)を直接テキスト入力・貼り付けする方式に変更した。
 */
export function ThemeColorPicker({ value, onChange }: ThemeColorPickerProps) {
  const isPreset = value !== null && (THEME_COLOR_PRESETS as readonly string[]).includes(value);
  const isCustom = value !== null && !isPreset;
  const [customInput, setCustomInput] = useState(isCustom ? value : "");
  const [customError, setCustomError] = useState(false);

  // プリセット選択やリセットなど、外部からvalueが変化した場合はテキスト入力欄も追従させる
  useEffect(() => {
    if (isCustom) {
      setCustomInput(value);
      setCustomError(false);
    } else if (value === null) {
      setCustomInput("");
      setCustomError(false);
    }
  }, [value, isCustom]);

  const handleCustomInputChange = (raw: string) => {
    setCustomInput(raw);
    const trimmed = raw.trim();
    if (trimmed === "") {
      setCustomError(false);
      return;
    }
    if (HEX_COLOR_PATTERN.test(trimmed)) {
      setCustomError(false);
      onChange(trimmed);
    } else {
      setCustomError(true);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
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

      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
            isCustom ? "border-foreground" : "border-dashed border-muted-foreground",
          )}
          style={isCustom ? { backgroundColor: value } : undefined}
        >
          {isCustom && <Check className="size-4 text-white drop-shadow" />}
        </span>
        <div className="flex flex-col gap-1">
          <Input
            value={customInput}
            onChange={(e) => handleCustomInputChange(e.target.value)}
            placeholder="#6366F1"
            aria-label="オリジナルカラーのカラーコード"
            aria-invalid={customError}
            className="h-9 w-28 font-mono text-sm"
          />
          {customError && (
            <span className="text-destructive text-xs">6桁のカラーコード(例: #6366F1)を入力してください</span>
          )}
        </div>
      </div>
    </div>
  );
}
