import {
  autoSignIn,
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
 * autoSignIn: trueにより、確認コード検証後に自動ログインまで完了できる
 * （UserPoolClientはSRP認証のみ許可の設定だが、autoSignInの内部実装は
 * 確認完了後に通常のsignIn(SRP)を呼ぶだけなので、この制約下でも動作する）。
 */
export async function signUpUser(email: string, password: string, nickname: string) {
  return signUp({
    username: email,
    password,
    options: {
      userAttributes: { email },
      clientMetadata: { nickname },
      autoSignIn: true,
    },
  });
}

/**
 * サインアップ確認コードの検証。
 * Cognitoの仕様上、SignUp時のclientMetadataはPreSignUpトリガーにしか渡らず、
 * PostConfirmationトリガー（nicknameを読む側）にはConfirmSignUp呼び出し時の
 * clientMetadataが渡る。そのためnicknameはここでも改めて渡す必要がある。
 * nicknameが無い場合（ログイン画面から未確認ユーザーとして遷移してきた場合等）は
 * clientMetadataを渡さず、バックエンド側のフォールバックに委ねる。
 */
export async function confirmSignUpCode(email: string, code: string, nickname?: string) {
  return confirmSignUp({
    username: email,
    confirmationCode: code,
    options: nickname ? { clientMetadata: { nickname } } : undefined,
  });
}

/** ログイン（UserPoolClientの制約によりSRP認証となる） */
export async function signInUser(email: string, password: string) {
  return signIn({ username: email, password });
}

/**
 * confirmSignUpCode()の戻り値がCOMPLETE_AUTO_SIGN_INの場合に呼び出す。
 * signUpUser()でautoSignIn: trueを指定していないケース（ログイン画面から
 * 未確認ユーザーとして遷移してきた場合等）ではAutoSignInExceptionを投げる。
 */
export async function completeAutoSignIn() {
  return autoSignIn();
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

/**
 * ログイン中のユーザーが運営者ロール（CognitoのOperatorsグループ、
 * Lambda設計書v1.7 §9b.4）を持つかどうかを判定する。コミュニティ単位の
 * OWNER/ADMIN判定（Membership.role）とは別軸。IDトークンの`cognito:groups`
 * クレームはJWT自体では文字列配列で入っている（API Gatewayが
 * event.requestContext.authorizer.claims経由でLambdaに渡す際はカンマ区切り
 * 文字列に平坦化されるが、それはサーバー側の話）。
 */
export async function getIsOperator(): Promise<boolean> {
  try {
    const session = await fetchAuthSession();
    const groups = session.tokens?.idToken?.payload["cognito:groups"];
    return Array.isArray(groups) && groups.includes("Operators");
  } catch {
    return false;
  }
}
