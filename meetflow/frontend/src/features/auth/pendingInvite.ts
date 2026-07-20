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

/**
 * 保持している招待先パスを、削除せずに読むだけ。
 *
 * LoginPage/ConfirmSignUpPage/RedirectIfAuthenticatedの3箇所はいずれも
 * 「ログイン後にどこへ遷移すべきか」の判定にこの値を使うが、判定が完了する
 * タイミングは screen 間のレースで前後しうる。「読んだら消す」実装だと、
 * 先に読んだ側が値を消費してしまい、後から判定する側はnullを受け取って
 * ホームへフォールバックしてしまう（招待パスの消失、Issue #69）。
 * 読み取りは何度行っても副作用が無いpeekにし、消費（削除）は招待受諾画面
 * （InviteAcceptPage）の到着時にのみ行う。
 */
export function peekPendingInvitePath(): string | null {
  return sessionStorage.getItem(STORAGE_KEY);
}

/** 保持していた招待先パスを削除する。招待受諾画面の到着時・参加処理完了時にのみ呼ぶこと。 */
export function consumePendingInvitePath() {
  sessionStorage.removeItem(STORAGE_KEY);
}
