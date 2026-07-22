import { setupServer } from "msw/node";
import { handlers } from "./handlers";

/** vitest実行環境(Node)向けのMSWサーバー。ブラウザ用Service Workerは使わない。 */
export const server = setupServer(...handlers);
