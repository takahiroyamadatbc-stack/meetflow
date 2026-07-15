import brandLogo from "@/assets/brand/meetflow-logo-v3-gorgeous.svg";

/** 認証画面上部に表示するフルロゴ（アイコン+ワードマーク+タグライン） */
export function BrandLogo() {
  return <img src={brandLogo} alt="MeetFlow" className="mx-auto mb-6 h-auto w-full max-w-[280px]" />;
}
