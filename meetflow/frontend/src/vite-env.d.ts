/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_COGNITO_USER_POOL_ID: string;
  readonly VITE_COGNITO_USER_POOL_CLIENT_ID: string;
  readonly VITE_COGNITO_REGION: string;
  readonly VITE_VAPID_PUBLIC_KEY: string;
  /** Mリーグドラフト企画のAPI（MeetFlowDraftStackのDraftApi。本体とは別のAPI Gateway） */
  readonly VITE_DRAFT_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
