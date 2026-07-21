# MeetFlow エラーコード一覧 v1.11

> 機能要件書v1.1 6章（共通エラー4種）を土台に、API設計書v1.2の各エンドポイントで発生しうるドメイン固有エラーを洗い出したもの。v1.1→v1.2はAPI設計書v1.5で追加された空き予定提出リクエスト・プッシュ通知購読のエンドポイントを踏まえて更新。v1.2→v1.3はAPI設計書v1.7で追加されたコミュニティ表示名設定のエンドポイントを踏まえて更新。v1.3→v1.4はAPI設計書v1.8で追加された招待URL無効化のエンドポイントを踏まえて更新。v1.4→v1.5はAPI設計書v1.11で追加された参加頻度上限設定のエンドポイントを踏まえて更新。v1.5→v1.6はAPI設計書v1.12で追加された参加承認・辞退のエンドポイントを踏まえて更新。v1.6→v1.7はAPI設計書v1.13で招待URL発行・無効化の権限が変更されたこと（Issue #22）を踏まえて更新。v1.7→v1.8はAPI設計書v1.16で追加されたメンバー自主退会のエンドポイントを踏まえて更新。v1.8→v1.9はAPI設計書v1.17で追加されたFeedback/Announcement APIを踏まえて更新。v1.9→v1.10はAPI設計書v1.18で追加された「本日の対局を終了する」エンドポイントを踏まえて更新。v1.10→v1.11はAPI設計書v1.25で追加されたコミュニティ内ランキング関連エンドポイントを踏まえて更新（新規コード追加なし、既存コードの流用方針を明記）。
> レスポンス形式はAPI設計書v1.2 2章に準拠：

```json
{
  "success": false,
  "error": {
    "code": "XXXX",
    "message": "日本語メッセージ"
  }
}
```

---

## 1. 共通エラー（全ドメイン共通）

| コード | HTTPステータス | 内容 |
|---|---|---|
| `USER_NOT_FOUND` | 404 | ユーザー不存在 |
| `COMMUNITY_NOT_FOUND` | 404 | コミュニティ不存在 |
| `FORBIDDEN` | 403 | 権限不足（ログイン済みだが操作権限なし） |
| `UNAUTHORIZED` | 401 | 未ログイン・トークン無効（機能要件書v1.1では明記されていなかったため本書で追加） |
| `INVALID_PARAMETER` | 400 | 入力不正 |
| `INTERNAL_ERROR` | 500 | 予期しないサーバーエラー（本書で追加。フロントエンドのトースト表示のデフォルト受け皿） |

---

## 2. User ドメイン

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `PROFILE_VALIDATION_ERROR` | 400 | ニックネーム未入力・文字数超過等（コミュニティ表示名の文字数超過を含む **[v1.3修正]**。参加頻度上限の`frequencyLimitCount`/`frequencyLimitPeriod`の片方のみ指定等の不正も含む **[v1.5修正]**） | `PUT /users/me`, `PUT /communities/{id}/members/me/display-name` |

---

## 3. Community ドメイン

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `INVITE_NOT_FOUND` | 404 | 招待URLのトークンが存在しない | `POST /invites/{token}/join`, **`POST /invites/{token}/revoke`（[v1.4追加]）** |
| `INVITE_REVOKED` | 410 | 招待URLが無効化済み | `POST /invites/{token}/join` |
| `INVITE_EXPIRED` | 410 | 招待URLの有効期限切れ（将来の有効期限付きURL対応時） | 同上 |
| `ALREADY_MEMBER` | 409 | 既にコミュニティのメンバーである（重複参加） | `POST /invites/{token}/join` |
| `JOIN_REQUEST_ALREADY_PENDING` | 409 | 既に参加リクエスト submitted 済み（二重申請） | `POST /invites/{token}/join`（承認制の場合） |
| `JOIN_REQUEST_NOT_FOUND` | 404 | 参加リクエストが存在しない | `.../join-requests/{requestId}/approve`, `.../reject` |
| `JOIN_REQUEST_ALREADY_PROCESSED` | 409 | 既に承認/却下済みの参加リクエストを再処理しようとした（二重承認防止） | 同上 |
| `LAST_OWNER_CANNOT_LEAVE` | 409 | コミュニティに1人しかいないOWNERが退出・降格しようとした | `PUT /communities/{id}/members/{userId}`, `POST .../owner-transfer` |
| `MEMBER_SUSPENDED` | 403 | 一時停止中のメンバーによる操作 | 全メンバー操作系API |
| `LOCATION_NOT_FOUND` | 404 | 指定した会場（Place）が存在しない | `POST /events`（locationId指定時）, `GET/POST /communities/{id}/locations` |
| `DISPLAY_NAME_ALREADY_TAKEN` **[v1.3新規]** | 409 | 同一コミュニティ内で実効表示名（設定済みdisplayName、または未設定メンバーのUser.nickname）が重複している | `PUT /communities/{id}/members/me/display-name` |
| `FREQUENCY_LIMIT_VALIDATION_ERROR` **[v1.5新規]** | 400 | 参加頻度上限のコミュニティ単位上書き設定で、`frequencyLimitCount`/`frequencyLimitPeriod`の片方のみを指定した等の不正 | `PUT /communities/{id}/members/me/frequency-limit` |
| `MEMBER_HAS_UPCOMING_EVENTS` **[v1.8新規]** | 409 | 対象メンバーが、そのコミュニティ発のイベントで開催日時が未来のCONFIRMED（または仮確定＝AWAITING_APPROVAL）な参加を1件以上持っている | `POST /communities/{id}/members/me/leave`, `PUT /communities/{id}/members/{userId}`（remove指定時） |

> **[v1.3新規]** コミュニティごとの表示名（F-108）の文字数超過等の基本バリデーションは、専用コードを新設せず既存の`PROFILE_VALIDATION_ERROR`（Userドメイン、400）を流用する。
>
> **[v1.5新規]** 参加頻度上限のコミュニティ単位上書き（F-109）は、プロフィール側（`PROFILE_VALIDATION_ERROR`を流用）とは別に`FREQUENCY_LIMIT_VALIDATION_ERROR`を新設した。Communityドメインのエンドポイント（`/communities/{id}/members/...`配下）であり、`DISPLAY_NAME_ALREADY_TAKEN`と同様にCommunityLambda側で発生するエラーのため、Userドメインのコードを使い回さずドメインを揃えた。
>
> **[v1.7修正]** 招待URL発行がOWNER/ADMIN限定からコミュニティの全メンバーに開放されたことに伴い（Issue #22）、`POST /invites/{token}/revoke`の権限はOWNER/ADMINまたは発行者本人に拡張された。それ以外のメンバーが無効化を試みた場合は、新規コードを追加せず既存の共通`FORBIDDEN`（1章）をそのまま流用する。
>
> **[v1.8新規]** `MEMBER_HAS_UPCOMING_EVENTS`はメンバー自主退会（Issue #25）・管理者による強制退会（Issue #26）の両方で共通のブロック判定に使う。ダブルブッキング防止（`PARTICIPANT_SCHEDULE_CONFLICT`）と同様、判定対象はCONFIRMEDだけでなくAWAITING_APPROVAL（仮確定時点で時間枠は事実上予約済み）も含める。

---

## 4. Availability ドメイン **[v1.2修正]**

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `INVALID_TIME_RANGE` | 400 | 開始時刻が終了時刻より後になっている等の不正な時間範囲 | `POST /communities/{id}/availability`, `PUT /availability/{id}` |
| `AVAILABILITY_NOT_FOUND` | 404 | 指定した空き予定が存在しない | `PUT/DELETE /availability/{id}` |
| `AVAILABILITY_OVERLAP` | 409 | 同一ユーザー・同一コミュニティで時間帯が重複する予定が既に存在する（画面設計書v1.0 S-09のハイライト表示と連動。エラーとして弾くか警告に留めるかは実装時に確定） | `POST .../availability`, `.../availability/batch` |
| `BATCH_SIZE_EXCEEDED` | 400 | バッチ登録の1回あたり上限（DynamoDB BatchWriteItemの25件制約に対するアプリ側チェック。実際は内部でチャンク分割するため通常発生しないが、極端に大きいリクエストの防御用） | `POST .../availability/batch` |
| `AVAILABILITY_REQUEST_NOT_FOUND` **[v1.2新規]** | 404 | 指定した空き予定提出リクエストが存在しない | `GET /communities/{id}/availability-requests/{requestId}/pending-members` |

> **[v1.2新規]** 空き予定提出リクエストの対象範囲・期間・期限の入力不正は、専用コードを新設せず既存の`INVALID_PARAMETER`（400）で扱う（機能要件書v1.3 F-205/F-206に対応するAPI設計書v1.5 5.5〜5.7）。

---

## 5. Matching ドメイン（EventTemplate / MatchCandidate）

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `INVALID_PLAYER_RANGE` | 400 | 最低人数が最大人数を上回っている等の不正な範囲指定 | `POST/PUT .../event-templates` |
| `EVENT_TEMPLATE_NOT_FOUND` | 404 | 指定した開催条件が存在しない | `PUT/DELETE /event-templates/{id}` |
| `NO_CANDIDATES_FOUND` | 200（エラーではなく正常系の空結果として扱う） | 条件に合う候補が0件だった | `POST /communities/{id}/matching` |
| `CANDIDATE_NOT_FOUND` | 404 | 指定したマッチング候補が存在しない | `GET /matching/candidates/{id}`, `POST /events`（candidateId指定時） |
| `CANDIDATE_ALREADY_USED` | 409 | 既にイベント化済みの候補を再度イベント化しようとした | `POST /events` |

> `NO_CANDIDATES_FOUND`はエラーコードとして定義するが、HTTPステータスは200（`success: true, data: {candidates: []}`）とし、フロントエンドは画面設計書v1.2 S-12の空状態表示で対応する。true errorとして扱わない点に注意。
>
> 同様に、候補一覧レスポンスの`conflictWarning`（衝突検知フラグ）・`fairnessCount`（公平性指標）もエラーではなく、レスポンスボディに含まれる参考情報である（API設計書v1.4 6.2参照）。

---

## 6. Event ドメイン（イベント・参加者・キャンセル）

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `EVENT_NOT_FOUND` | 404 | 指定したイベントが存在しない | `GET /events/{id}` 他イベント関連全般 |
| `INVALID_STATUS_TRANSITION` | 409 | イベントのステートマシン上、許可されない状態遷移を試みた（例：COMPLETED状態のイベントを承認しようとした） | `POST /events/{id}/confirm`, `POST /events/{id}/cancel`, `POST /events/{id}/complete`（[v1.10追加]。CONFIRMED/IN_PROGRESS以外からの呼び出し） |
| `EVENT_ALREADY_CONFIRMED` | 409 | 既に承認済みのイベントを再度承認しようとした | `POST /events/{id}/confirm` |
| `EVENT_ALREADY_CANCELLED` | 409 | 既に中止済みのイベントに対する操作 | `POST /events/{id}/cancel`, キャンセル申請系 |
| `PARTICIPANT_NOT_FOUND` | 404 | 指定した参加者がイベントに存在しない | `GET /events/{id}/participants`関連 |
| `CANCEL_REQUEST_ALREADY_PENDING` | 409 | 既に未処理のキャンセル申請が存在する（同一ユーザーによる二重申請） | `POST /events/{id}/cancel-request` |
| `CANCEL_REQUEST_NOT_FOUND` | 404 | 指定したキャンセル申請が存在しない | `POST /events/{id}/cancel-requests/{userId}/approve` |
| `CANCEL_REQUEST_ALREADY_PROCESSED` | 409 | 既に承認/却下済みのキャンセル申請を再処理しようとした（`ConditionExpression: status=PENDING`による二重承認防止、CDK設計書v1.0・DynamoDB物理設計書v1.1の冪等性設計に対応） | `POST /events/{id}/cancel-requests/{userId}/approve` |
| `NOT_A_PARTICIPANT` | 403 | イベント参加者ではないユーザーがキャンセル申請、または参加承認・辞退（[v1.6追加]）しようとした | `POST /events/{id}/cancel-request`, `POST /events/{id}/participants/me/approve`, `POST /events/{id}/participants/me/reject` |
| `PARTICIPANT_SCHEDULE_CONFLICT` | 409 | イベント仮確定時、候補メンバーの誰かが既に別の確定済みまたは承認待ちのイベントと時間が重複している（ダブルブッキング防止。[v1.6修正]判定対象に承認待ちを追加） | `POST /events/{id}/confirm` |
| **`PARTICIPANT_ALREADY_RESPONDED`** [v1.6新規] | 409 | 既に参加承認または辞退が完了している参加者（自動承認済みを含む）が再度応答しようとした（`ConditionExpression: status=AWAITING_APPROVAL`による二重応答防止） | `POST /events/{id}/participants/me/approve`, `POST /events/{id}/participants/me/reject` |

---

## 7. Result ドメイン

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `EVENT_NOT_COMPLETED` | 409 | COMPLETED状態でないイベントに成績を登録しようとした（実装方針次第で許可する場合は不要。要検討） | `POST /events/{id}/sessions` |
| `RESULT_VALIDATION_ERROR` | 400 | 着順の重複（同じ順位が2人）、点数の合計が不正等 | `POST /events/{id}/sessions` |
| `RESULT_ACCESS_DENIED` | 403 | 閲覧者と対象ユーザーが同一コミュニティに所属していないため成績を閲覧できない（API設計書v1.2 10.2の権限方針に対応） | `GET /users/{userId}/results` |

> **[v1.11追加]** コミュニティ内ランキング取得（`GET /communities/{communityId}/rankings`、API設計書v1.25 §10.3）は新規エラーコードを追加しない。閲覧権限エラーは既存の`RESULT_ACCESS_DENIED`をそのまま流用し、`periodType`と`year`/`month`/`quarter`/`half`の組み合わせ不正等のクエリパラメータエラーは共通の`INVALID_PARAMETER`（1章）を流用する。ランキング設定更新（`PUT /communities/{communityId}/ranking-settings`）もOWNER/ADMIN以外からのアクセスは共通の`FORBIDDEN`、設定値の不正は`INVALID_PARAMETER`を流用する（Issue #40）。

---

## 8. Notification ドメイン **[v1.2修正]**

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `NOTIFICATION_NOT_FOUND` | 404 | 指定した通知が存在しない | `PUT /notifications/{id}/read` |

> **[v1.2新規]** プッシュ通知購読解除（`DELETE /users/me/push-subscriptions`）は冪等な操作とし、指定した`endpoint`の購読情報が存在しなくても専用エラーは返さず成功として扱う（ブラウザ側が既に失効した購読を解除しようとするケースを想定）。

---

## 9. OperationLog ドメイン

固有エラーなし（参照系のみのため、共通エラー＝`FORBIDDEN`（自分以外のユーザーのログを見ようとした場合）で対応）

---

## 9b. Feedback / Announcement ドメイン **[v1.9新規]**

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `FEEDBACK_NOT_FOUND` | 404 | 指定したフィードバックが存在しない | `GET /feedback/{id}`, `PATCH /feedback/{id}` |
| `FEEDBACK_VALIDATION_ERROR` | 400 | `kind`と`rating`/`category`の組み合わせ不正（例：`kind=QUICK`なのに`category`を指定）等 | `POST /feedback` |
| `ANNOUNCEMENT_NOT_FOUND` | 404 | 指定したアップデート予告が存在しない | `PUT /announcements/{id}` |

> **[v1.9新規]** 運営者限定エンドポイント（`GET/PATCH /feedback`系、`POST/PUT /announcements`系）で運営者（Operators）でないユーザーがアクセスした場合は、専用コードを新設せず既存の共通`FORBIDDEN`（1章）を流用する。

---

## 10. フロントエンド表示方針との対応

画面設計書v1.2 1章のエラー表示方針に沿って、コードごとの表示形式を分類する。

| 表示形式 | 該当するエラーコードの傾向 |
|---|---|
| インライン（フォーム項目の下） | `INVALID_PARAMETER`, `INVALID_TIME_RANGE`, `INVALID_PLAYER_RANGE`, `RESULT_VALIDATION_ERROR`, `PROFILE_VALIDATION_ERROR`, `DISPLAY_NAME_ALREADY_TAKEN`（**[v1.3追加]**）, `FREQUENCY_LIMIT_VALIDATION_ERROR`（**[v1.5追加]**）, `FEEDBACK_VALIDATION_ERROR`（**[v1.9追加]**） |
| トースト（一時的なエラー） | `INTERNAL_ERROR`, `AVAILABILITY_OVERLAP`, `ALREADY_MEMBER`, `JOIN_REQUEST_ALREADY_PENDING`, `CANCEL_REQUEST_ALREADY_PENDING`, `CANCEL_REQUEST_ALREADY_PROCESSED`, `CANDIDATE_ALREADY_USED`, `EVENT_ALREADY_CONFIRMED`, `EVENT_ALREADY_CANCELLED`, `PARTICIPANT_ALREADY_RESPONDED`（**[v1.6追加]**） |
| モーダル（明示的な操作が必要） | `UNAUTHORIZED`（再ログイン誘導）, `FORBIDDEN`（権限不足の説明）, **`PARTICIPANT_SCHEDULE_CONFLICT`（承認をブロックした理由の明示、[v1.1追加]）**, **`MEMBER_HAS_UPCOMING_EVENTS`（退会をブロックした理由の明示、[v1.8追加]）** |
| 空状態画面 | `NO_CANDIDATES_FOUND`, 各種`*_NOT_FOUND`（削除済みリソースへのアクセス） |

---

## 11. 未決事項

1. **`AVAILABILITY_OVERLAP`をエラーとして弾くか、警告に留めて登録自体は許可するか**：フリー雀荘のように複数コミュニティで同じ時間帯の予定を持つケースもありうるため、「同一コミュニティ内でのみ重複チェック」とするか、そもそもチェックしないかは実装時に確定
2. ~~**`EVENT_NOT_COMPLETED`の要否**~~：**[v1.10解消]** 対局が終わるたびに都度登録したい実運用を優先し、`EVENT_NOT_COMPLETED`は実装しないことで決着した（イベントの状態を問わず`POST /events/{id}/sessions`を許可する。API設計書v1.18 §10.1）。COMPLETED後の新規登録もブロックしない（管理者が「本日の対局を終了する」を押し忘れて次の対局に入るケースを考慮）。一方でCOMPLETEDへの遷移自体（§8.4b）は新設し、コミュニティの通算成績への算入可否の基準として使うことにした（§7 `RESULT`関連の集計方針を参照）
3. **キャンセル申請の却下（REJECTED）に対応するエラーコード**：現状は承認のみを主眼に置いているが、却下されたキャンセル申請への再申請を許可するかどうかで`CANCEL_REQUEST_ALREADY_PROCESSED`の扱いが変わる可能性がある
4. **`PARTICIPANT_SCHEDULE_CONFLICT`発生時の代替導線**：モーダルで「このメンバーを除いて再承認」のような救済アクションを用意するか、単純にブロックして候補生成からやり直させるかはUX検討が必要 [v1.1追加]

---

## v1.0 → v1.1 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | Eventドメインに`PARTICIPANT_SCHEDULE_CONFLICT`（409）を追加 | イベント承認時のダブルブッキング事前チェック |
| 2 | Matchingドメインの補足に`conflictWarning`/`fairnessCount`がエラーではなく参考情報である旨を追記 | API設計書v1.4 6.2との整合 |
| 3 | フロントエンド表示方針表に`PARTICIPANT_SCHEDULE_CONFLICT`をモーダル表示対象として追加 | 承認ブロックの明示的な伝達が必要なため |

---

## v1.1 → v1.2 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | Availabilityドメインに`AVAILABILITY_REQUEST_NOT_FOUND`（404）を追加 | 要件定義書v1.3 28章：管理者からの空き予定提出リクエスト（F-206） |
| 2 | Notificationドメインにプッシュ通知購読解除の冪等性方針を追記（新規エラーコードなし） | 要件定義書v1.3 27章：PWA化とWebプッシュ通知（F-704） |

---

## v1.2 → v1.3 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | Communityドメインに`DISPLAY_NAME_ALREADY_TAKEN`（409）を追加 | 機能要件書v1.5 F-108：コミュニティごとの表示名の重複チェック |
| 2 | `PROFILE_VALIDATION_ERROR`の発生APIにコミュニティ表示名設定エンドポイントを追加（バリデーションを流用） | 上記と同一の決定事項 |
| 3 | フロントエンド表示方針表のインライン欄に`DISPLAY_NAME_ALREADY_TAKEN`を追加 | 上記と同一の決定事項 |

---

## v1.3 → v1.4 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | `INVITE_NOT_FOUND`の発生APIに`POST /invites/{token}/revoke`を追加（新規エラーコードなし、既存コードを流用） | API設計書v1.8 §4.3b：招待URL無効化。既に無効化済みの招待への再実行は冪等に成功として扱うため専用コードは不要 |

---

## v1.4 → v1.5 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | Communityドメインに`FREQUENCY_LIMIT_VALIDATION_ERROR`（400）を新規追加 | 要件定義書v1.6 30章：参加頻度上限。機能要件書v1.7 F-109（コミュニティ単位の上書き）のバリデーションエラー |
| 2 | `PROFILE_VALIDATION_ERROR`の内容に、参加頻度上限（プロフィール側、F-003）のバリデーション不正を含める旨を追記（新規コードなし、既存コードを流用） | 上記と同一の決定事項。ユーザー全体デフォルト側はUserドメインの既存コードで対応 |
| 3 | フロントエンド表示方針表のインライン欄に`FREQUENCY_LIMIT_VALIDATION_ERROR`を追加 | 上記と同一の決定事項 |

---

## v1.5 → v1.6 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | Eventドメインに`PARTICIPANT_ALREADY_RESPONDED`（409）を新規追加 | Issue #10：イベント確定フローへの「全員承認」ステップ追加（機能要件書v1.8 F-502b/F-502c）。参加承認・辞退の二重応答防止 |
| 2 | `NOT_A_PARTICIPANT`の発生APIに参加承認・辞退の2エンドポイントを追加（新規コードなし、既存コードを流用） | 上記と同一の決定事項。「候補メンバーではない/Participant行が存在しない」ケースの認可はキャンセル申請と同じ構造 |
| 3 | `PARTICIPANT_SCHEDULE_CONFLICT`の内容を、判定対象が承認待ち（`AWAITING_APPROVAL`）にも拡張された旨に更新 | 仮確定＝承認待ちの時点で参加者の時間枠は事実上予約済みになるため（DynamoDB物理設計書v1.10 5章） |
| 4 | フロントエンド表示方針表のトースト欄に`PARTICIPANT_ALREADY_RESPONDED`を追加 | 上記No.1と同一の決定事項 |

---

## v1.6 → v1.7 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | `POST /invites/{token}/revoke`のFORBIDDEN発生条件を「OWNER/ADMIN以外」から「OWNER/ADMINでも発行者本人でもない場合」に更新（新規コードなし、既存の共通`FORBIDDEN`を流用） | Issue #22：招待URL発行のメンバー開放に伴い、無効化権限も発行者本人に拡張されたため |

---

## v1.7 → v1.8 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | Communityドメインに`MEMBER_HAS_UPCOMING_EVENTS`（409）を新規追加 | Issue #25：メンバー自主退会機能の新設。未来の確定イベント参加が残っている場合のブロック判定 |
| 2 | `MEMBER_HAS_UPCOMING_EVENTS`の発生APIに管理者による強制退会（`PUT .../members/{userId}`のremove指定）を追加（新規コードなし、自主退会と同じコードを流用） | Issue #26：強制退会が同チェックを欠いていた抜け穴の解消 |
| 3 | フロントエンド表示方針表のモーダル欄に`MEMBER_HAS_UPCOMING_EVENTS`を追加 | 上記No.1と同一の決定事項 |

---

## v1.8 → v1.9 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 9b章「Feedback / Announcement ドメイン」を新規追加。`FEEDBACK_NOT_FOUND`（404）・`FEEDBACK_VALIDATION_ERROR`（400）・`ANNOUNCEMENT_NOT_FOUND`（404）を新規追加 | Issue #34：フィードバック機能の設計書追加。API設計書v1.17 §12b/§12c |
| 2 | 運営者限定エンドポイントへの非運営者アクセスは、専用コードを新設せず既存の共通`FORBIDDEN`を流用する旨を明記 | 上記と同一の決定事項 |
| 3 | フロントエンド表示方針表のインライン欄に`FEEDBACK_VALIDATION_ERROR`を追加 | 上記No.1と同一の決定事項 |

---

## v1.9 → v1.10 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | `INVALID_STATUS_TRANSITION`の発生APIに`POST /events/{id}/complete`（新規追加）を追加（新規コードなし、既存コードを流用） | Issue #20：「本日の対局を終了する」エンドポイント新設（API設計書v1.18 §8.4b）。CONFIRMED/IN_PROGRESS以外の状態からの呼び出しをブロックする |

---

## v1.10 → v1.11 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 7章Resultドメインに、コミュニティ内ランキング関連2エンドポイントの発生エラーは新規コードを追加せず`RESULT_ACCESS_DENIED`/`INVALID_PARAMETER`/`FORBIDDEN`を流用する旨を注記 | Issue #40：コミュニティ内ランキング表示機能の追加（API設計書v1.25 §4.2e, §10.3） |

Issue #40「コミュニティ内ランキング表示機能の追加」に対応。
