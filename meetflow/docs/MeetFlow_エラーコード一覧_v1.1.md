# MeetFlow エラーコード一覧 v1.1

> 機能要件書v1.1 6章（共通エラー4種）を土台に、API設計書v1.2の各エンドポイントで発生しうるドメイン固有エラーを洗い出したもの。
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
| `PROFILE_VALIDATION_ERROR` | 400 | ニックネーム未入力・文字数超過等 | `PUT /users/me` |

---

## 3. Community ドメイン

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `INVITE_NOT_FOUND` | 404 | 招待URLのトークンが存在しない | `POST /invites/{token}/join` |
| `INVITE_REVOKED` | 410 | 招待URLが無効化済み | 同上 |
| `INVITE_EXPIRED` | 410 | 招待URLの有効期限切れ（将来の有効期限付きURL対応時） | 同上 |
| `ALREADY_MEMBER` | 409 | 既にコミュニティのメンバーである（重複参加） | `POST /invites/{token}/join` |
| `JOIN_REQUEST_ALREADY_PENDING` | 409 | 既に参加リクエスト submitted 済み（二重申請） | `POST /invites/{token}/join`（承認制の場合） |
| `JOIN_REQUEST_NOT_FOUND` | 404 | 参加リクエストが存在しない | `.../join-requests/{requestId}/approve`, `.../reject` |
| `JOIN_REQUEST_ALREADY_PROCESSED` | 409 | 既に承認/却下済みの参加リクエストを再処理しようとした（二重承認防止） | 同上 |
| `LAST_OWNER_CANNOT_LEAVE` | 409 | コミュニティに1人しかいないOWNERが退出・降格しようとした | `PUT /communities/{id}/members/{userId}`, `POST .../owner-transfer` |
| `MEMBER_SUSPENDED` | 403 | 一時停止中のメンバーによる操作 | 全メンバー操作系API |
| `LOCATION_NOT_FOUND` | 404 | 指定した会場（Place）が存在しない | `POST /events`（locationId指定時）, `GET/POST /communities/{id}/locations` |

---

## 4. Availability ドメイン

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `INVALID_TIME_RANGE` | 400 | 開始時刻が終了時刻より後になっている等の不正な時間範囲 | `POST /communities/{id}/availability`, `PUT /availability/{id}` |
| `AVAILABILITY_NOT_FOUND` | 404 | 指定した空き予定が存在しない | `PUT/DELETE /availability/{id}` |
| `AVAILABILITY_OVERLAP` | 409 | 同一ユーザー・同一コミュニティで時間帯が重複する予定が既に存在する（画面設計書v1.0 S-09のハイライト表示と連動。エラーとして弾くか警告に留めるかは実装時に確定） | `POST .../availability`, `.../availability/batch` |
| `BATCH_SIZE_EXCEEDED` | 400 | バッチ登録の1回あたり上限（DynamoDB BatchWriteItemの25件制約に対するアプリ側チェック。実際は内部でチャンク分割するため通常発生しないが、極端に大きいリクエストの防御用） | `POST .../availability/batch` |

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
| `INVALID_STATUS_TRANSITION` | 409 | イベントのステートマシン上、許可されない状態遷移を試みた（例：COMPLETED状態のイベントを承認しようとした） | `POST /events/{id}/confirm`, `POST /events/{id}/cancel` |
| `EVENT_ALREADY_CONFIRMED` | 409 | 既に承認済みのイベントを再度承認しようとした | `POST /events/{id}/confirm` |
| `EVENT_ALREADY_CANCELLED` | 409 | 既に中止済みのイベントに対する操作 | `POST /events/{id}/cancel`, キャンセル申請系 |
| `PARTICIPANT_NOT_FOUND` | 404 | 指定した参加者がイベントに存在しない | `GET /events/{id}/participants`関連 |
| `CANCEL_REQUEST_ALREADY_PENDING` | 409 | 既に未処理のキャンセル申請が存在する（同一ユーザーによる二重申請） | `POST /events/{id}/cancel-request` |
| `CANCEL_REQUEST_NOT_FOUND` | 404 | 指定したキャンセル申請が存在しない | `POST /events/{id}/cancel-requests/{userId}/approve` |
| `CANCEL_REQUEST_ALREADY_PROCESSED` | 409 | 既に承認/却下済みのキャンセル申請を再処理しようとした（`ConditionExpression: status=PENDING`による二重承認防止、CDK設計書v1.0・DynamoDB物理設計書v1.1の冪等性設計に対応） | `POST /events/{id}/cancel-requests/{userId}/approve` |
| `NOT_A_PARTICIPANT` | 403 | イベント参加者ではないユーザーがキャンセル申請しようとした | `POST /events/{id}/cancel-request` |
| `PARTICIPANT_SCHEDULE_CONFLICT` | 409 | イベント承認時、候補メンバーの誰かが既に別の確定済みイベントと時間が重複している（ダブルブッキング防止） | `POST /events/{id}/confirm` |

---

## 7. Result ドメイン

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `EVENT_NOT_COMPLETED` | 409 | COMPLETED状態でないイベントに成績を登録しようとした（実装方針次第で許可する場合は不要。要検討） | `POST /events/{id}/sessions` |
| `RESULT_VALIDATION_ERROR` | 400 | 着順の重複（同じ順位が2人）、点数の合計が不正等 | `POST /events/{id}/sessions` |
| `RESULT_ACCESS_DENIED` | 403 | 閲覧者と対象ユーザーが同一コミュニティに所属していないため成績を閲覧できない（API設計書v1.2 10.2の権限方針に対応） | `GET /users/{userId}/results` |

---

## 8. Notification ドメイン

| コード | HTTPステータス | 内容 | 発生API |
|---|---|---|---|
| `NOTIFICATION_NOT_FOUND` | 404 | 指定した通知が存在しない | `PUT /notifications/{id}/read` |

---

## 9. OperationLog ドメイン

固有エラーなし（参照系のみのため、共通エラー＝`FORBIDDEN`（自分以外のユーザーのログを見ようとした場合）で対応）

---

## 10. フロントエンド表示方針との対応

画面設計書v1.2 1章のエラー表示方針に沿って、コードごとの表示形式を分類する。

| 表示形式 | 該当するエラーコードの傾向 |
|---|---|
| インライン（フォーム項目の下） | `INVALID_PARAMETER`, `INVALID_TIME_RANGE`, `INVALID_PLAYER_RANGE`, `RESULT_VALIDATION_ERROR`, `PROFILE_VALIDATION_ERROR` |
| トースト（一時的なエラー） | `INTERNAL_ERROR`, `AVAILABILITY_OVERLAP`, `ALREADY_MEMBER`, `JOIN_REQUEST_ALREADY_PENDING`, `CANCEL_REQUEST_ALREADY_PENDING`, `CANCEL_REQUEST_ALREADY_PROCESSED`, `CANDIDATE_ALREADY_USED`, `EVENT_ALREADY_CONFIRMED`, `EVENT_ALREADY_CANCELLED` |
| モーダル（明示的な操作が必要） | `UNAUTHORIZED`（再ログイン誘導）, `FORBIDDEN`（権限不足の説明）, **`PARTICIPANT_SCHEDULE_CONFLICT`（承認をブロックした理由の明示、[v1.1追加]）** |
| 空状態画面 | `NO_CANDIDATES_FOUND`, 各種`*_NOT_FOUND`（削除済みリソースへのアクセス） |

---

## 11. 未決事項

1. **`AVAILABILITY_OVERLAP`をエラーとして弾くか、警告に留めて登録自体は許可するか**：フリー雀荘のように複数コミュニティで同じ時間帯の予定を持つケースもありうるため、「同一コミュニティ内でのみ重複チェック」とするか、そもそもチェックしないかは実装時に確定
2. **`EVENT_NOT_COMPLETED`の要否**：COMPLETED前のイベント（IN_PROGRESS中）にも結果登録を許可したい実運用（対局が終わるたびに都度登録したい等）があれば、このエラー自体を撤廃する可能性がある
3. **キャンセル申請の却下（REJECTED）に対応するエラーコード**：現状は承認のみを主眼に置いているが、却下されたキャンセル申請への再申請を許可するかどうかで`CANCEL_REQUEST_ALREADY_PROCESSED`の扱いが変わる可能性がある
4. **`PARTICIPANT_SCHEDULE_CONFLICT`発生時の代替導線**：モーダルで「このメンバーを除いて再承認」のような救済アクションを用意するか、単純にブロックして候補生成からやり直させるかはUX検討が必要 [v1.1追加]

---

## v1.0 → v1.1 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | Eventドメインに`PARTICIPANT_SCHEDULE_CONFLICT`（409）を追加 | イベント承認時のダブルブッキング事前チェック |
| 2 | Matchingドメインの補足に`conflictWarning`/`fairnessCount`がエラーではなく参考情報である旨を追記 | API設計書v1.4 6.2との整合 |
| 3 | フロントエンド表示方針表に`PARTICIPANT_SCHEDULE_CONFLICT`をモーダル表示対象として追加 | 承認ブロックの明示的な伝達が必要なため |
