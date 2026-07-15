# MeetFlow API設計書 v1.8

> v1.0→v1.1は **[v1.1修正]**、v1.1→v1.2は **[v1.2新規/修正]**、v1.2→v1.3は **[v1.2修正]** として明記（表記ゆれのため今回分も[v1.2]タグのまま記載）。v1.3→v1.4は **[v1.4新規/修正]**、v1.4→v1.5は **[v1.5新規]**、v1.5→v1.6は **[v1.6新規]**、v1.6→v1.7は **[v1.7新規/修正]** として明記。

---

## 1. API基本設計

### 1.1 通信方式

| 項目 | 内容 |
|---|---|
| 方式 | REST API |
| Protocol | HTTPS |
| Format | JSON |
| 認証 | Amazon Cognito JWT |
| Backend | AWS Lambda |

---

## 2. API共通仕様

### Request Header

```
Authorization: Bearer {JWT Token}
```

### Response形式

成功：

```json
{
  "success": true,
  "data": {}
}
```

エラー：

```json
{
  "success": false,
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "入力値が不正です"
  }
}
```

---

## 3. User API

### 3.1 プロフィール取得

`GET /users/me`

処理：ログインユーザー情報取得。

Response

```json
{
  "userId": "USER001",
  "nickname": "たか",
  "profile": "麻雀好き"
}
```

### 3.2 プロフィール更新

`PUT /users/me`

Request

```json
{
  "nickname": "たか",
  "profile": "麻雀好き"
}
```

---

## 4. Community API

### 4.1 コミュニティ作成

`POST /communities`

Request

```json
{
  "name": "群馬麻雀会",
  "description": "麻雀仲間",
  "memberApprovalRequired": false
}
```

> **[v1.1修正]** `memberApprovalRequired` を追加。要件定義書10.1「メンバー承認（設定による）」に対応し、コミュニティごとに参加リクエスト制／即時参加制を選択可能にする。

処理：
- Community作成
- 作成者をOWNER登録
- OperationLog登録

### 4.2 コミュニティ一覧取得

`GET /communities`

取得：所属コミュニティ一覧

### 4.2b コミュニティ詳細取得 **[v1.6新規]**

`GET /communities/{communityId}`

Response

```json
{
  "communityId": "COMMUNITY001",
  "name": "群馬麻雀会",
  "description": "麻雀仲間",
  "genre": "麻雀",
  "memberApprovalRequired": false,
  "role": "OWNER"
}
```

処理：呼び出し元がメンバーであるコミュニティの詳細を1件取得する。所属していないコミュニティを指定した場合は`FORBIDDEN`を返す。

> **[v1.6追加]** フロントエンド実装時、コミュニティ詳細画面が単体取得手段を持たず一覧取得（4.2）に依存する回避策を取らざるを得なかったため追加。4.2の一覧レスポンスには含まれない`memberApprovalRequired`・呼び出し元の`role`の両方を含む。

### 4.3 招待URL発行

`POST /communities/{communityId}/invite`

Response

```json
{
  "url": "https://meetflow.jp/invite/xxxxx"
}
```

### 4.3b 招待URL無効化 **[v1.8新規]**

`POST /invites/{token}/revoke`

Response

```json
{
  "token": "xxxxx",
  "communityId": "COMMUNITY001",
  "revoked": true
}
```

処理：
- OWNER/ADMINが発行済み招待URLを無効化する（Invite.revoked=trueに更新）
- OperationLog登録（`REVOKE_INVITE`）

> **[v1.8追加]** 画面設計書v1.4 S-06は「URL無効化ボタン」を要素として既に定義していたが、対応するAPIが未実装だったため招待画面は発行・コピーのみに留まっていた（食い違い#3）。既に無効化済みの招待に対する再実行はエラーにせず冪等に成功として扱う（`DELETE /users/me/push-subscriptions`と同じ方針）。

### 4.4 招待参加

`POST /invites/{token}/join`

Request **[v1.2追加]**

```json
{
  "message": "たかしさんの紹介で来ました（任意）"
}
```

処理：

> **[v1.1修正]** コミュニティの `memberApprovalRequired` 設定に応じて処理を分岐。
> **[v1.2追加]** `message`は承認制コミュニティの場合のみ意味を持つ任意項目。管理者の審査材料として利用する（即時参加モードでは無視してよい）。

- `memberApprovalRequired = false` の場合：Membership作成（即時MEMBER登録）
- `memberApprovalRequired = true` の場合：JoinRequest作成（PENDING状態、`message`を保存）、管理者へ通知

### 4.4b 参加リクエスト承認 **[v1.1新規]**

`POST /communities/{communityId}/join-requests/{requestId}/approve`

処理：
- JoinRequestを承認済みに変更
- Membership作成
- OperationLog登録（`ADD_MEMBER`）

### 4.4c 参加リクエスト却下 **[v1.1新規]**

`POST /communities/{communityId}/join-requests/{requestId}/reject`

### 4.5 メンバー一覧

`GET /communities/{communityId}/members`

> **[v1.7修正]** レスポンスの`nickname`フィールドは、Membership.displayNameが設定されているメンバーについてはその値を、未設定の場合はUser.nicknameを返す（機能要件書v1.5 F-108のフォールバック仕様）。フィールド名・型は変更しない。

### 4.5b コミュニティ表示名の設定・変更 **[v1.7新規]**

`PUT /communities/{communityId}/members/me/display-name`

自分自身のMembership.displayNameを設定・変更する（機能要件書v1.5 F-108）。空文字列またはnullを送ると設定を解除し、User.nickname（プロフィール画面のニックネーム）へのフォールバック表示に戻す。

Request

```json
{
  "displayName": "たか（麻雀部）"
}
```

Response

```json
{
  "communityId": "COMMUNITY001",
  "userId": "USER010",
  "displayName": "たか（麻雀部）"
}
```

> 同一コミュニティ内の他メンバーの実効表示名（設定済みdisplayName、または未設定メンバーのUser.nickname）と重複する場合は`409 DISPLAY_NAME_ALREADY_TAKEN`を返す（エラーコード一覧v1.3 §3）。文字数超過等の基本バリデーションは`PROFILE_VALIDATION_ERROR`（400）を流用する。
>
> 画面設計書v1.4 S-05bに対応。

### 4.6 参加リクエスト一覧 **[v1.2新規]**

`GET /communities/{communityId}/join-requests`

コミュニティ管理者（OWNER/ADMIN）が未処理の参加リクエストを確認するための一覧取得API。

Response

```json
{
  "requests": [
    {
      "requestId": "REQ001",
      "userId": "USER010",
      "nickname": "たかし",
      "bio": "麻雀好きです、よろしくお願いします",
      "gameTypes": ["MAHJONG4", "MAHJONG3"],
      "beginnerOk": true,
      "message": "たかしさんの紹介で来ました",
      "status": "PENDING",
      "requestedAt": "2026-07-08T10:00:00.000Z"
    }
  ]
}
```

> **[v1.2修正]** v1.0/v1.1ではニックネームのみの返却だったが、承認判断の材料として不十分なため、Userエンティティの`bio`/`gameTypes`/`beginnerOk`とJoinRequestの`message`を合わせて返却する形に修正。画面設計書のS-07（参加リクエスト一覧）に対応。
>
> 画面設計書v1.0 S-07（参加リクエスト一覧）に対応。デフォルトは`status=PENDING`のみ返却し、クエリパラメータ`status`で絞り込み可能とする。

---

## 5. Availability API

空き予定管理。

### 5.1 空き予定登録

`POST /communities/{communityId}/availability`

Request

```json
{
  "startTime": "2026-07-20T19:00",
  "endTime": "2026-07-20T23:00",
  "gameTypes": ["MAHJONG4"],
  "comment": "初心者OK"
}
```

処理：
- Availability保存

> **[v1.2修正]** v1.0/v1.1の「Matching候補再計算トリガー」を削除。MVPのマッチング実行は管理者による手動実行のみ（6.1参照）のため、空き予定登録時の自動トリガーは行わない。

### 5.2 空き予定一覧

`GET /communities/{communityId}/availability`

取得：**呼び出したユーザー自身が登録した分のみ**。他メンバーの空き予定を取得できる公開APIは存在しない。

> **[v1.6追加]** 要件定義書v1.4 29章「相互非公開型マッチング」を実装レベルで担保するAPI。個人の入力（空き予定）は本人以外に公開せず、システムが導き出した候補（6.2参照）のみを関係者に提示するという非対称性のない構造を、本APIのレスポンス範囲によって保証する。コミュニティ内の空き予定を横断的に参照するのはマッチング処理（6.1）の内部専用であり、その結果を返す公開APIは提供しない（DynamoDB物理設計書 3.6, 4章参照）。

### 5.3 空き予定変更

`PUT /availability/{availabilityId}`

### 5.4 空き予定削除

`DELETE /availability/{availabilityId}`

### 5.5 空き予定提出リクエスト作成 **[v1.5新規]**

`POST /communities/{communityId}/availability-requests`

Request

```json
{
  "targetPeriodStart": "2026-08-01T00:00",
  "targetPeriodEnd": "2026-08-31T23:59",
  "deadline": "2026-07-25T23:59",
  "targetScope": "ALL",
  "targetUserIds": [],
  "message": "来月の空き予定を教えてください"
}
```

処理：

- AvailabilityRequest保存
- 対象メンバーへ通知作成（EventBridge経由、Lambda設計書v1.2参照）

> **[v1.5新規]** F-205（機能要件書v1.3）に対応。`targetScope`は`ALL`または`SPECIFIED`。`SPECIFIED`の場合のみ`targetUserIds`を指定する。

### 5.6 空き予定提出リクエスト一覧 **[v1.5新規]**

`GET /communities/{communityId}/availability-requests`

### 5.7 未提出メンバー確認 **[v1.5新規]**

`GET /communities/{communityId}/availability-requests/{requestId}/pending-members`

Response

```json
{
  "pendingMembers": [
    { "userId": "USER005", "nickname": "たろう" }
  ]
}
```

> **[v1.5新規]** F-206（機能要件書v1.3）に対応。DynamoDB物理設計書v1.4 3.18の通り、対象メンバーごとにAvailabilityの既存GSI1を対象期間でQueryし、レコードが0件のユーザーのみ返却する（提出済みユーザーは含まれない）。

---

## 6. Matching API

MeetFlowの中心機能。

### 6.1 候補生成

`POST /communities/{communityId}/matching`

Request

```json
{
  "templateId": "TEMPLATE001"
}
```

処理：
1. 条件取得
2. 空き予定検索
3. メンバー組み合わせ生成
4. スコア計算（人数条件は**範囲内判定**。信頼度は対象外＝Phase2）
5. Candidate保存

> **[v1.1補足]** MVPでは本APIによる手動実行のみを有効化する。ただし内部処理は「テンプレートID単位の実行」を最小単位として抽象化しており、将来のEventBridge Scheduler定期実行や空き予定登録時の自動トリガーからも同一ロジック（内部関数／同一Lambda）を呼び出せる構成とする。API自体の追加は不要。

Response

```json
{
  "candidateId": "CAND001",
  "score": 92,
  "members": ["USER001", "USER002"]
}
```

### 6.2 候補一覧取得 **[v1.4修正]**

`GET /communities/{communityId}/matching/candidates`

Response

```json
{
  "candidates": [
    {
      "candidateId": "CAND001",
      "score": 92,
      "conflictWarning": false,
      "members": [
        { "userId": "USER001", "nickname": "たか", "fairnessCount": 0 },
        { "userId": "USER002", "nickname": "けん", "fairnessCount": 3 }
      ]
    }
  ]
}
```

> **[v1.4新規]** `conflictWarning`（他コミュニティで確定した別イベントと時間重複が検知された場合true）、`fairnessCount`（メンバーごとの「直近30〜60日で候補に入ったが確定しなかった回数」）を追加。いずれも参考表示のみで、スコアリング・自動除外には使用しない（Lambda設計書v1.1 6.7/6.8、画面設計書v1.2 S-12に対応）。
>
> **[v1.7修正]** `members[].nickname`は4.5と同様、コミュニティ内の実効表示名（displayName優先、フォールバックでUser.nickname）を返す。

### 6.3 候補詳細取得

`GET /matching/candidates/{candidateId}`

---

## 7. Event Template API

開催条件管理。

### 7.1 条件作成

`POST /communities/{communityId}/event-templates`

Request

```json
{
  "gameType": "MAHJONG4",
  "minPlayers": 5,
  "maxPlayers": 6,
  "priority": 80,
  "conditions": {
    "beginnerOk": true
  }
}
```

### 7.2 条件一覧

`GET /communities/{communityId}/event-templates`

---

## 8. Event API

### 8.1 イベント作成

`POST /events`

Request

```json
{
  "candidateId": "CAND001",
  "locationId": "LOC001",
  "locationNote": "たかし宅（全自動卓あり）"
}
```

> **[v1.1修正]** `locationId` / `locationNote` を追加。前回決定「イベント作成時に管理者が場所を選択」を反映。`locationId` はコミュニティに紐づく会場マスタ（8.5参照）からの選択を想定し、自由記述の補足があれば `locationNote` に入れる。

### 8.2 イベント詳細

`GET /events/{eventId}`

Response に `location`（会場名・住所等）を含む。

### 8.3 イベント承認 **[v1.4修正]**

`POST /events/{eventId}/confirm`

処理：
- **候補メンバー全員のダブルブッキング事前チェック（Participant GSI1を時間範囲でQuery）。重複があれば`409 PARTICIPANT_SCHEDULE_CONFLICT`を返却し中断 [v1.4新規]**
- 状態変更（PENDING_APPROVAL → CONFIRMED）
- Participant作成
- 通知イベント発行
- OperationLog保存

> **[v1.4新規]** 前回会話の「候補3：確定時ハードチェック」に対応。Lambda設計書v1.1 7.2b、DynamoDB物理設計書v1.3 5章に準拠。

### 8.4 イベント中止 **[v1.1: 名称・説明を明確化]**

`POST /events/{eventId}/cancel`

> **[v1.1修正]** イベント**全体**の開催中止（9.2の個人キャンセル申請とは別物）。管理者のみ実行可能。状態をCANCELLEDへ遷移し、全参加者へ通知。

### 8.5 会場一覧取得 **[v1.1新規]**

`GET /communities/{communityId}/locations`

コミュニティに紐づく「よく使う会場」マスタの一覧を取得。

### 8.6 会場登録 **[v1.1新規]**

`POST /communities/{communityId}/locations`

Request

```json
{
  "name": "たかし宅",
  "address": "非公開（任意）",
  "note": "全自動卓あり"
}
```

### 8.7 コミュニティのイベント一覧 **[v1.2新規]**

`GET /communities/{communityId}/events`

コミュニティ内のイベント一覧を取得する。開催予定／過去のタブ切替を想定し、クエリパラメータ`status`（例：`OPEN,MATCHING,PENDING_APPROVAL,CONFIRMED,IN_PROGRESS`＝開催予定、`COMPLETED,CANCELLED`＝過去）で絞り込み可能とする。

Response

```json
{
  "events": [
    {
      "eventId": "EVENT001",
      "startTime": "2026-07-20T19:00:00.000Z",
      "locationName": "たかし宅",
      "status": "CONFIRMED"
    }
  ]
}
```

> 画面設計書v1.0 S-17（イベント一覧）に対応。DynamoDB物理設計書v1.1のGSI1（`GSI1PK=COMMUNITY#{communityId}, GSI1SK begins_with EVENT#`）をそのまま利用する。

---

## 9. Participant API

### 9.1 参加者一覧

`GET /events/{eventId}/participants`

> **[v1.7修正]** レスポンスの`nickname`フィールドは4.5と同様、コミュニティ内の実効表示名（displayName優先、フォールバックでUser.nickname）を返す。

### 9.1b キャンセル申請一覧 **[v1.2新規]**

`GET /events/{eventId}/cancel-requests`

管理者が未処理のキャンセル申請を確認するための一覧取得API。

Response

```json
{
  "cancelRequests": [
    {
      "userId": "USER001",
      "reason": "仕事",
      "status": "PENDING",
      "requestedAt": "2026-07-08T10:00:00.000Z"
    }
  ]
}
```

> 画面設計書v1.0 S-19（キャンセル申請一覧・承認）に対応。デフォルトは`status=PENDING`のみ返却。

### 9.2 キャンセル申請（個人の参加辞退） **[v1.1: 名称を明確化]**

`POST /events/{eventId}/cancel-request`

Request

```json
{
  "reason": "仕事"
}
```

> **[v1.1補足]** イベント**全体**の中止（8.4）とは別物。参加者個人が離脱を申請するAPI。申請のみでは離脱は確定せず、9.3の管理者承認を経て確定する（前回決定：即時離脱にすると既に参加確定している他メンバーへの心理的影響があるため、管理者調整の余地を残す）。MVPでは申請・承認までを実装し、欠員補充（補欠検索・繰り上げ）はPhase2とする。

### 9.3 キャンセル申請承認 **[v1.1: エンドポイント名を修正]**

`POST /events/{eventId}/cancel-requests/{userId}/approve`

> **[v1.1修正]** v1.0の `/events/{eventId}/participants/{userId}/approve` から改名。9.2のキャンセル申請を管理者が承認する処理であることを明示。

処理：
- CancelRequestを承認済みに変更
- Participantから当該ユーザーを除外
- OperationLog登録
- （Phase2）欠員補充フローの起動

---

## 10. Game Result API

### 10.1 結果登録

`POST /events/{eventId}/sessions`

Request

```json
{
  "gameType": "MAHJONG4",
  "results": [
    { "userId": "USER001", "rank": 1, "score": 35000 }
  ]
}
```

### 10.2 成績取得

`GET /users/{userId}/results`

> **[v1.1補足]** 権限チェック方針を明記：閲覧者が対象ユーザーと同一コミュニティに所属している場合のみ、そのコミュニティ内での成績を返却する。コミュニティを跨いだ成績の全体公開は行わない。

---

## 11. Notification API **[v1.5修正]**

> **[v1.1修正]** 14章のMVP範囲の表現を修正（下記14章参照）。アプリ内通知（一覧・既読）自体はMVP対象。LINE連携などチャネル拡張のみPhase2。
>
> **[v1.5修正]** Push通知（Webプッシュ通知）をMVP対象に前倒し、11.3/11.4を新規追加（要件定義書v1.3 27章）。

### 11.1 通知一覧

`GET /notifications`

### 11.2 既読更新

`PUT /notifications/{notificationId}/read`

### 11.3 プッシュ通知購読登録 **[v1.5新規]**

`POST /users/me/push-subscriptions`

Request

```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/xxxxx",
  "keys": {
    "p256dh": "xxxxx",
    "auth": "xxxxx"
  },
  "userAgent": "Mozilla/5.0 ..."
}
```

処理：

- PushSubscription保存（同一`endpoint`の場合は上書き）

> **[v1.5新規]** F-703（機能要件書v1.3）に対応。

### 11.4 プッシュ通知購読解除 **[v1.5新規]**

`DELETE /users/me/push-subscriptions`

Request

```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/xxxxx"
}
```

処理：

- 該当PushSubscription削除

> **[v1.5新規]** F-704（機能要件書v1.3）に対応。

---

## 12. OperationLog API

管理者向け。

### 12.1 コミュニティ操作履歴取得

`GET /communities/{communityId}/logs`

### 12.2 ユーザー操作履歴取得 **[v1.1新規]**

`GET /users/{userId}/logs`

> **[v1.1補足]** 操作ログ設計書側でGSI（`PK=USER#{userId}`）を追加する前提のAPI。本人または同一コミュニティのOWNER/ADMINのみ閲覧可能とする。

---

## 13. Lambda対応表

> **[v1.1修正]** EventTemplateの担当を明記。会場（Location）はCommunityLambdaが担当。

| API領域 | Lambda |
|---|---|
| User | UserLambda |
| Community | CommunityLambda |
| Location | CommunityLambda |
| Availability | AvailabilityLambda |
| EventTemplate | MatchingLambda |
| Matching | MatchingLambda |
| Event | EventLambda |
| Participant | EventLambda |
| Result | ResultLambda |
| Notification | NotificationLambda |
| OperationLog | 各Lambda内で共通関数として呼び出し（専用Lambdaは持たない） |

---

## 14. MVP API範囲 **[v1.5修正]**

必須（MVP）

- User
- Community（会場マスタ含む）
- Availability（**空き予定提出リクエスト含む**、[v1.5追加]）
- EventTemplate
- Matching
- Event（会場選択含む）
- Participant（キャンセル申請・承認まで）
- Notification（アプリ内通知・一覧・既読 + **Webプッシュ通知購読管理**、[v1.5追加]） ※v1.0でPhase2誤記だった箇所を修正

Phase2

- 欠員補充（補欠検索・繰り上げ通知）
- LINE連携
- Result詳細（高度な統計）
- TrustScore（信頼度）
- 相性分析・NG設定

> **[v1.5修正]** Push通知は上記の通りMVP対象に前倒しし、本リストから削除する。

---

## 15. API設計方針

MeetFlow APIはCRUD中心ではなく、「ユーザーの行動」を中心に設計する。

例：

```
予定登録 → 候補生成 → イベント確定 → 開催 → 結果蓄積
```

というサービスフローをAPIで表現する。

---

## v1.0 → v1.1 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | Community作成に`memberApprovalRequired`追加、参加リクエスト承認/却下API新規追加 | メンバー承認制の分岐（要件定義書10.1が正） |
| 2 | イベント作成に`locationId`/`locationNote`追加、会場一覧・登録API新規追加 | 会場情報はイベント作成時に選択 |
| 3 | 9.3のエンドポイント名を`cancel-requests/{userId}/approve`に変更 | F-602キャンセル承認の意図明確化 |
| 4 | 8.4を「イベント中止」として9.2「個人キャンセル申請」と役割分離を明記 | 用語の混同防止 |
| 5 | 14章のNotificationをMVP必須に修正 | 要件定義書16章・機能要件書12章との整合 |
| 6 | 12章にユーザー単位ログ取得API追加 | 操作ログ設計書のGSI設計との連動 |
| 7 | 13章Lambda対応表にLocation/EventTemplate/Participantの担当を明記 | 実装時の迷いを解消 |
| 8 | 10.2に成績閲覧の権限方針を明記 | コミュニティスコープでの成績公開 |
| 9 | 6.1に将来の定期実行との関係を補足 | F-401トリガー方式（仕組みは作っておく） |

---

## v1.1 → v1.2 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.6 参加リクエスト一覧取得API新規追加 | 画面設計書S-07 |
| 2 | 8.7 コミュニティのイベント一覧取得API新規追加 | 画面設計書S-17 |
| 3 | 9.1b キャンセル申請一覧取得API新規追加 | 画面設計書S-19 |
| 4 | 5.1の処理から「Matching候補再計算トリガー」を削除 | MVPマッチング実行は手動のみという決定との矛盾解消（Lambda設計書v1.0 5.2で既に反映済みだったが本書側が未修正だった） |

---

## v1.2 → v1.3 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.4 招待参加リクエストに`message`（任意の一言メッセージ）を追加 | F-103参加リクエストの判断材料が不足していた問題への対応 |
| 2 | 4.6 参加リクエスト一覧のレスポンスに`bio`/`gameTypes`/`beginnerOk`/`message`を追加 | 同上。招待URLはコミュニティ単位のまま維持（個人発行URLは見送り） |

---

## v1.3 → v1.4 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 6.2 候補一覧レスポンスに`conflictWarning`（衝突検知）・`fairnessCount`（公平性指標）を追加 | 複数コミュニティ横断の衝突検知・公平な機会分配の可視化 |
| 2 | 8.3 イベント承認にダブルブッキング事前チェック（`PARTICIPANT_SCHEDULE_CONFLICT`）を追加 | 確定時ハードチェックによる実害防止 |

---

## v1.4 → v1.5 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 5.5〜5.7 空き予定提出リクエスト作成・一覧・未提出メンバー確認APIを新規追加 | 要件定義書v1.3 28章：管理者からの空き予定提出リクエスト（F-205/F-206） |
| 2 | 11.3/11.4 プッシュ通知購読登録・解除APIを新規追加 | 要件定義書v1.3 27章：PWA化とWebプッシュ通知（F-703/F-704） |
| 3 | 14章のMVP必須リストに上記2機能を追加、Phase2リストからPush通知を削除 | Push通知のMVP前倒し |

---

## v1.5 → v1.6 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.2b コミュニティ詳細取得（`GET /communities/{communityId}`）を新規追加 | フロントエンド実装時に単体取得手段の欠如が判明したため |
| 2 | 5.2 空き予定一覧が呼び出したユーザー自身の分のみを返す仕様であり、相互非公開型マッチングの原則を実装レベルで担保している旨を明記 | 要件定義書v1.4 29章：相互非公開型マッチング（コア設計原則） |

---

## v1.6 → v1.7 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.5b コミュニティ表示名の設定・変更（`PUT /communities/{communityId}/members/me/display-name`）を新規追加 | 機能要件書v1.5 F-108：コミュニティごとの表示名 |
| 2 | 4.5・6.2・9.1の`nickname`フィールドが、Membership.displayName優先・User.nicknameフォールバックの実効表示名を返す旨を明記 | 上記と同一の決定事項。既存フィールド名・型は変更しないため、フロントエンドの表示コンポーネント側の改修は不要 |

---

## v1.7 → v1.8 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.3b 招待URL無効化（`POST /invites/{token}/revoke`）を新規追加 | 画面設計書v1.4 S-06が定義済みの「URL無効化ボタン」に対応するAPIが無く、招待画面が発行・コピーのみに制限されていた食い違いの解消 |
| 2 | 12章 OperationLog API（`GET /communities/{communityId}/logs`, `GET /users/{userId}/logs`）をCommunityLambdaに実装・接続 | Lambda設計書v1.3 §2で「現時点で未実装」とされていたAPIの実装。ドキュメント（API設計書v1.7時点）自体は既にエンドポイントを定義済みだったため、本書のAPI仕様に変更はない |
