const STORAGE_KEY = "meetflow.pendingInvitePath";

/**
 * 未ログインで招待URL(/invite/:token)を踏んだ場合、ログイン→サインアップ
 * →確認コード入力という複数画面をまたぐ導線でも招待先を見失わないよう、
 * sessionStorageに一時保持する。React Routerのlocation.stateは画面遷移
 * のたびに明示的に転送しない限り引き継がれず、この導線には各画面をまたぐ
 * 転送漏れが起きやすいため、ページをまたいでも生き残るsessionStorageを使う。
 */
export function savePendingInvitePath(path: string) {
  sessionStorage.setItem(STORAGE_KEY, path);
}

/** 保持していた招待先パスを取得し、同時に消費（削除）する。 */
export function consumePendingInvitePath(): string | null {
  const path = sessionStorage.getItem(STORAGE_KEY);
  if (path) {
    sessionStorage.removeItem(STORAGE_KEY);
  }
  return path;
}
