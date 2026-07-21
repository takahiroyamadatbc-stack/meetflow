import {
  autoSignIn,
  confirmResetPassword,
  confirmSignUp,
  fetchAuthSession,
  getCurrentUser,
  resendSignUpCode,
  resetPassword,
  signIn,
  signOut,
  signUp,
  updatePassword,
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

/**
 * 未確認ユーザーへの確認コード再送信（Issue #61）。
 * サインアップ済み・未確認（Cognito側でUNCONFIRMED）のユーザーが確認コードを
 * 消費せず離脱した後、同じメールアドレスで再度signUp()を呼ぶと
 * UsernameExistsExceptionになるため、その場合の再送信に使う。
 * 対象ユーザーが既にCONFIRMED済みの場合はCognito側が
 * InvalidParameterException等を返す（呼び出し元でハンドリングする）。
 */
export async function resendSignUpConfirmationCode(email: string) {
  return resendSignUpCode({ username: email });
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
 * パスワードリセット申請（Issue #81）。UserPoolClientは
 * prevent_user_existence_errors=trueのため、未登録のメールアドレスでも
 * Cognitoは確認コード送信済みであるかのような応答を返す（ユーザー
 * 列挙攻撃対策、MeetFlowAuthStack側の既存設定）。呼び出し元はエラー時
 * のみ特別扱いすればよい。
 */
export async function requestPasswordReset(email: string) {
  return resetPassword({ username: email });
}

/** パスワードリセットの確認コード検証と新パスワードの設定（Issue #81） */
export async function confirmPasswordReset(
  email: string,
  confirmationCode: string,
  newPassword: string,
) {
  return confirmResetPassword({ username: email, confirmationCode, newPassword });
}

/** ログイン中のパスワード変更（Issue #81） */
export async function changePassword(oldPassword: string, newPassword: string) {
  return updatePassword({ oldPassword, newPassword });
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
