import {
  confirmSignUp,
  fetchAuthSession,
  getCurrentUser,
  signIn,
  signOut,
  signUp,
} from "aws-amplify/auth";

/**
 * サインアップ。UserLambdaのPost Confirmationトリガー
 * （backend/functions/user_lambda/handler.py: _handle_post_confirmation）が
 * event.request.clientMetadata.nickname を読んでプロフィールを作成するため、
 * ここで必ずニックネームを渡す。未指定だとメールのローカル部が
 * ニックネームとして登録されてしまう。
 */
export async function signUpUser(email: string, password: string, nickname: string) {
  return signUp({
    username: email,
    password,
    options: {
      userAttributes: { email },
      clientMetadata: { nickname },
    },
  });
}

/** サインアップ確認コードの検証 */
export async function confirmSignUpCode(email: string, code: string) {
  return confirmSignUp({ username: email, confirmationCode: code });
}

/** ログイン（UserPoolClientの制約によりSRP認証となる） */
export async function signInUser(email: string, password: string) {
  return signIn({ username: email, password });
}

/** ログアウト */
export async function signOutUser() {
  return signOut();
}

/**
 * APIリクエストのAuthorizationヘッダーに使うIDトークンを取得する。
 * 未ログイン時はundefinedを返す（呼び出し側で401をUNAUTHORIZEDとして扱う）。
 */
export async function getIdToken(): Promise<string | undefined> {
  try {
    const session = await fetchAuthSession();
    return session.tokens?.idToken?.toString();
  } catch {
    return undefined;
  }
}

/** 現在ログイン中かどうかを判定する */
export async function getCurrentAuthUser() {
  return getCurrentUser();
}
