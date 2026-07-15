import { Amplify } from "aws-amplify";

/**
 * Cognito UserPoolClientはHosted UI未設定・SRP認証のみ許可
 * （infra/meetflow_infra/meetflow_auth_stack.py: generate_secret=False,
 * auth_flows=cognito.AuthFlow(user_srp=True)）のため、OAuth関連の設定は不要。
 * signIn()はデフォルトでUSER_SRP_AUTHフローを使う。
 */
export function configureAmplify() {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
        userPoolClientId: import.meta.env.VITE_COGNITO_USER_POOL_CLIENT_ID,
        signUpVerificationMethod: "code",
      },
    },
  });
}
