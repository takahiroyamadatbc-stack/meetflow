# MeetFlow API設計書 v1.26

> v1.0→v1.1は **[v1.1修正]**、v1.1→v1.2は **[v1.2新規/修正]**、v1.2→v1.3は **[v1.2修正]** として明記（表記ゆれのため今回分も[v1.2]タグのまま記載）。v1.3→v1.4は **[v1.4新規/修正]**、v1.4→v1.5は **[v1.5新規]**、v1.5→v1.6は **[v1.6新規]**、v1.6→v1.7は **[v1.7新規/修正]**、v1.8→v1.9は **[v1.9新規]**、v1.9→v1.10は **[v1.10新規/修正]**、v1.11→v1.12は **[v1.12新規/修正]**、v1.12→v1.13は **[v1.13新規/修正]**、v1.13→v1.14は **[v1.14新規]**、v1.14→v1.15は **[v1.15新規]**、v1.15→v1.16は **[v1.16新規]**、v1.16→v1.17は **[v1.17新規]**、v1.17→v1.18は **[v1.18新規/修正]**、v1.18→v1.19は **[v1.19新規/修正]**、v1.19→v1.20は **[v1.20修正]**、v1.20→v1.21は **[v1.21新規/修正]**、v1.21→v1.22は **[v1.22修正]**、v1.22→v1.23は **[v1.23修正]**、v1.23→v1.24は **[v1.24修正]**、v1.24→v1.25は **[v1.25新規]**、v1.25→v1.26は **[v1.26新規]** として明記。

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

### 3.2 プロフィール更新 **[v1.11修正、v1.12修正]**

`PUT /users/me`

Request

```json
{
  "nickname": "たか",
  "profile": "麻雀好き",
  "frequencyLimitCount": 1,
  "frequencyLimitPeriod": "WEEK",
  "autoApprove": true
}
```

> **[v1.11追加]** `frequencyLimitCount`/`frequencyLimitPeriod`（ゲームジャンル単位の参加頻度上限、機能要件書v1.7 F-003）は任意項目。`frequencyLimitPeriod`は`WEEK`/`MONTH`のいずれか。両方セットで送るか、両方nullで上限を解除する（片方のみの指定は`PROFILE_VALIDATION_ERROR`）。コミュニティ単位の上書きは4.5cを参照。
>
> **[v1.12追加]** `autoApprove`（イベント仮確定後の参加承認を以降自動で行うかどうかの全体デフォルト、機能要件書v1.8 F-003）は任意項目のboolean。既定値はfalse。コミュニティ単位の上書きは4.5dを参照。レスポンス（3.1）にも同フィールドが含まれる。

---

## 4. Community API

### 4.1 コミュニティ作成

`POST /communities`

Request

```json
{
  "name": "群馬麻雀会",
  "description": "麻雀仲間",
  "memberApprovalRequired": false,
  "themeColor": "#6366F1"
}
```

> **[v1.1修正]** `memberApprovalRequired` を追加。要件定義書10.1「メンバー承認（設定による）」に対応し、コミュニティごとに参加リクエスト制／即時参加制を選択可能にする。
>
> **[v1.9追加]** `themeColor`を追加（任意、`#RRGGBB`形式）。未指定時は`null`（アプリの既定色にフォールバック）で作成する。バリデーション・変更方法は4.2cを参照。

処理：
- Community作成
- 作成者をOWNER登録
- OperationLog登録

### 4.2 コミュニティ一覧取得 **[v1.10修正]**

`GET /communities`

取得：所属コミュニティ一覧

Response

```json
{
  "communities": [
    {
      "communityId": "COMMUNITY001",
      "name": "群馬麻雀会",
      "description": "麻雀仲間",
      "genre": "麻雀",
      "role": "OWNER",
      "themeColor": "#6366F1"
    }
  ]
}
```

> **[v1.10追加]** `themeColor`（未設定は`null`）を追加し、一覧画面のカード表示にも反映できるようにした。返却順はMembership.sortOrder昇順（4.2dで並び替え可能）とし、未設定（新規参加直後等）のコミュニティは末尾に回る。

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
  "themeColor": "#6366F1",
  "role": "OWNER",
  "pendingRequestCount": 0,
  "rankingDefaultGameType": "MAHJONG4",
  "rankingDefaultPeriodType": "MONTH",
  "rankingDefaultMetric": "AVERAGE_RANK",
  "rankingDefaultMinGames": 0
}
```

処理：呼び出し元がメンバーであるコミュニティの詳細を1件取得する。所属していないコミュニティを指定した場合は`FORBIDDEN`を返す。

> **[v1.6追加]** フロントエンド実装時、コミュニティ詳細画面が単体取得手段を持たず一覧取得（4.2）に依存する回避策を取らざるを得なかったため追加。4.2の一覧レスポンスには含まれない`memberApprovalRequired`・呼び出し元の`role`の両方を含む。
>
> **[v1.9追加]** `themeColor`を追加。未設定のコミュニティは`null`を返す。
>
> **[v1.15追加]** `pendingRequestCount`：コミュニティの未処理（PENDING）JoinRequest件数（Issue #29）。ロールを問わず返却するが、UI上は管理者向けバッジ表示にのみ使う。
>
> **[v1.25追加]** `rankingDefaultGameType`/`rankingDefaultPeriodType`/`rankingDefaultMetric`/`rankingDefaultMinGames`（4.2eで設定するランキングのデフォルト表示条件）を追加。未設定のコミュニティはシステムデフォルト値（`MAHJONG4`/`MONTH`/`AVERAGE_RANK`/`0`）を返す。

### 4.2c コミュニティテーマカラー設定 **[v1.9新規]**

`PUT /communities/{communityId}/theme-color`

Request

```json
{
  "themeColor": "#6366F1"
}
```

Response

```json
{
  "communityId": "COMMUNITY001",
  "themeColor": "#6366F1"
}
```

処理：
- OWNER/ADMINがコミュニティのテーマカラーを設定・変更する（Community.themeColorを更新）
- `themeColor`は`#RRGGBB`形式（7文字hexカラーコード）でなければならず、形式が不正な場合は`400 INVALID_PARAMETER`
- 空文字列または`null`を送ると設定を解除し、アプリの既定色へのフォールバック表示に戻す（4.5bのコミュニティ表示名解除と同じパターン）
- OperationLog登録（`UPDATE_THEME_COLOR`）

> **[v1.9追加]** コミュニティごとのテーマカラー設定に対応する専用エンドポイント。作成時（4.1）にも指定できるが、作成後にOWNER/ADMINが変更する手段として本APIを追加した。アイコン画像のカスタマイズはS3/CloudFront等の追加インフラを要するためPhase2以降とし、まずは軽量なカラーコード設定のみ先行導入する。名称変更・説明文変更等、他のコミュニティ基本情報の編集APIはまだ存在しないため、汎用的な`PUT /communities/{communityId}`ではなく4.5bと同様の単機能エンドポイントとして追加した。

### 4.2d コミュニティ表示順の並び替え **[v1.10新規]**

`PUT /communities/order`

Request

```json
{
  "communityIds": ["COMMUNITY002", "COMMUNITY001", "COMMUNITY003"]
}
```

Response

```json
{
  "communityIds": ["COMMUNITY002", "COMMUNITY001", "COMMUNITY003"]
}
```

処理：
- `communityIds`配列の並び順どおりに、呼び出し元のMembership.sortOrderを0,1,2...と書き換える
- 各IDについて呼び出し元がそのコミュニティのメンバーであることを確認し、所属していないIDが含まれる場合は`403 FORBIDDEN`
- `communityIds`が空配列、または文字列以外の要素を含む場合は`400 INVALID_PARAMETER`

> **[v1.10追加]** コミュニティ一覧の表示順を並び替えたいという要望に対応する新規エンドポイント。特定のコミュニティ（communityId）に対する操作ではなく呼び出し元ユーザー個人の表示設定であるため、`/communities/{communityId}/...`ではなく`/communities/order`とした。DynamoDB物理設計書v1.8 §3.3でMembershipに`sortOrder`属性を追加したことに対応。

### 4.2e コミュニティ内ランキング設定 **[v1.25新規]**

`PUT /communities/{communityId}/ranking-settings`

Request

```json
{
  "gameType": "MAHJONG4",
  "periodType": "MONTH",
  "metric": "AVERAGE_RANK",
  "minGames": 0
}
```

Response

```json
{
  "communityId": "COMMUNITY001",
  "gameType": "MAHJONG4",
  "periodType": "MONTH",
  "metric": "AVERAGE_RANK",
  "minGames": 0
}
```

処理：
- OWNER/ADMINが、コミュニティ内ランキング（10.3）のデフォルト表示条件（種目・集計期間プリセット・指標・足切り閾値）を設定する
- 4項目は常にまとめて1リクエストで更新する（テーマカラー等と異なり、個別のON/OFFや部分更新は設けない）
- `gameType`は`MAHJONG4`/`MAHJONG3`、`periodType`は`MONTH`/`QUARTER`/`HALF_YEAR`/`YEAR`/`ALL_TIME`、`metric`は10.3で定義する10指標のいずれか、`minGames`は0以上の整数。いずれかが不正な場合は`400 INVALID_PARAMETER`
- `null`または未指定でシステムデフォルト（`gameType=MAHJONG4`, `periodType=MONTH`, `metric=AVERAGE_RANK`, `minGames=0`）への解除も可能（4.2cのテーマカラー解除と同じパターン）
- OperationLog登録（`UPDATE_RANKING_SETTINGS`）

> **[v1.25新規]** Issue #40：コミュニティ内ランキング機能（F-806、機能要件書v1.11）に対応。4.2cコミュニティテーマカラー設定と同一の「単機能PUTエンドポイント、OWNER/ADMIN限定」パターンを踏襲する。設定値は4.2bコミュニティ詳細取得のレスポンスにも含める。

### 4.3 招待URL発行

`POST /communities/{communityId}/invite`

Response

```json
{
  "url": "https://meetflow.jp/invite/xxxxx"
}
```

処理：
- **[v1.13修正]** コミュニティの全メンバーが発行できる（従来はOWNER/ADMIN限定だったが、Issue #22で開放）
- 発行時点の発行者ロール（OWNER/ADMIN/MEMBER）をInvite.createdByRoleとして保存する。MEMBERが発行した招待は、4.4の参加処理でコミュニティ設定に関わらず強制的に承認制になる

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
- **[v1.13修正]** OWNER/ADMIN、または発行者本人（Invite.createdBy == 呼び出し元userId）が発行済み招待URLを無効化する（Invite.revoked=trueに更新）。従来はOWNER/ADMIN限定だったが、Issue #22でメンバー発行が可能になったことに伴い、自分が発行したURLは自分で無効化できるよう開放した
- OperationLog登録（`REVOKE_INVITE`）

> **[v1.8追加]** 画面設計書v1.4 S-06は「URL無効化ボタン」を要素として既に定義していたが、対応するAPIが未実装だったため招待画面は発行・コピーのみに留まっていた（食い違い#3）。既に無効化済みの招待に対する再実行はエラーにせず冪等に成功として扱う（`DELETE /users/me/push-subscriptions`と同じ方針）。

### 4.3c 招待プレビュー取得 **[v1.14新規、v1.22修正]**

`GET /invites/{token}`

Response

```json
{
  "communityId": "COMMUNITY001",
  "communityName": "群馬麻雀会",
  "communityDescription": "毎週末集まって打ってます",
  "communityGenre": "麻雀",
  "communityIcon": null,
  "approvalRequired": false,
  "invitedByDisplayName": "たかし",
  "alreadyMember": false,
  "joinRequestPending": false
}
```

処理：
- 招待受諾画面（InviteAcceptPage）が「〇〇さんから招待されています」カードを表示するためのプレビューAPI（Issue #23、v1.22でレスポンスを拡張しIssue #70に対応）
- `approvalRequired`は、4.4と同じ条件（`Community.memberApprovalRequired`、またはInvite.createdByRoleが`MEMBER`）のいずれかがtrueなら`true`
- `communityDescription`/`communityGenre`/`communityIcon`は、Community METADATAの該当項目をそのまま返す（コミュニティ紹介カードの補足情報として使う） **[v1.22追加]**
- `invitedByDisplayName`は招待発行者（`Invite.createdBy`）のコミュニティ内表示名（`Membership.displayName`、未設定時は`User.nickname`にフォールバック）**[v1.22追加]**。招待発行者が既にそのコミュニティのメンバーでない（退会済み等でMembershipが存在しない）場合は、グローバルのニックネームへはフォールバックせず`null`を返す（このカードは「コミュニティ内で通っている名前」を出す目的のため）
- `alreadyMember`/`joinRequestPending`は、呼び出し元（招待URLを踏んだ本人）が対象コミュニティに対して既に「メンバーである」「PENDINGな参加リクエストを持っている」状態かどうかを返す **[v1.22追加]**。フロント側はこれを見て「参加する」ボタンの代わりに詰み画面（既に参加済み/承認待ち）を出し分ける
- 認証は必要（API Gatewayで未認証呼び出しは弾かれる）だが、対象コミュニティへの所属（Membership）は要求しない。招待未受諾の呼び出し元が使うAPIのため
- エラーは4.3bと共通で`INVITE_NOT_FOUND`（404）・`INVITE_REVOKED`（410）

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
> **[v1.13追加]** `memberApprovalRequired = false`のコミュニティでも、Invite.createdByRoleが`MEMBER`の場合（=一般メンバーが発行した招待）は強制的にJoinRequest経由の承認制になる。

- `memberApprovalRequired = false` かつ招待の発行者がOWNER/ADMINの場合：Membership作成（即時MEMBER登録）
- `memberApprovalRequired = true`、または招待の発行者がMEMBERの場合：JoinRequest作成（PENDING状態、`message`を保存）、管理者へ通知

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

### 4.5c 参加頻度上限のコミュニティ単位の上書き **[v1.11新規]**

`PUT /communities/{communityId}/members/me/frequency-limit`

自分自身のMembership.frequencyLimitCount/frequencyLimitPeriodを設定・変更する（機能要件書v1.7 F-109）。両方nullまたは省略で設定を解除し、プロフィール（3.2）側の全体設定へのフォールバック表示に戻す。4.5b（表示名）と同じフォールバック構造。

Request

```json
{
  "frequencyLimitCount": 2,
  "frequencyLimitPeriod": "MONTH"
}
```

Response

```json
{
  "communityId": "COMMUNITY001",
  "userId": "USER010",
  "frequencyLimitCount": 2,
  "frequencyLimitPeriod": "MONTH"
}
```

> `frequencyLimitCount`と`frequencyLimitPeriod`は同時に設定・解除する。片方のみの指定は`400 FREQUENCY_LIMIT_VALIDATION_ERROR`を返す（エラーコード一覧v1.5 §3）。この上限はマッチング処理（6章）のスコアリングに反映される（候補からの機械的除外はしない。要件定義書v1.6 30章）。

### 4.5d 自動承認のコミュニティ単位の上書き **[v1.12新規]**

`PUT /communities/{communityId}/members/me/auto-approve`

自分自身のMembership.autoApproveを設定・変更する（機能要件書v1.8 F-109b）。nullで設定を解除し、プロフィール（3.2）側の全体設定へのフォールバックに戻す。4.5b（表示名）・4.5c（参加頻度上限）と同じフォールバック構造。

Request

```json
{
  "autoApprove": true
}
```

Response

```json
{
  "communityId": "COMMUNITY001",
  "userId": "USER010",
  "autoApprove": true
}
```

> `autoApprove`は必須項目（省略は`400 INVALID_PARAMETER`）。boolean以外の値も同エラーコードを返す。設定解除は`null`を送る。このコミュニティで仮確定されたイベントについて、以降の参加承認（9.4参照）を自動化する（要件定義書v1.7 §17参照。イベントの自動確定そのものを意味するわけではない）。

### 4.5e メンバー自主退会 **[v1.16新規]**

`POST /communities/{communityId}/members/me/leave`

メンバー自身の意思でコミュニティを退会する（機能要件書v1.9 F-104d）。4.5b〜4.5dと同じ「自分専用サブリソース」の命名パターンを踏襲する。リクエストボディは無し。

Response

```json
{
  "communityId": "COMMUNITY001",
  "userId": "USER010",
  "left": true
}
```

> 唯一のOWNERは退会できない（`409 LAST_OWNER_CANNOT_LEAVE`。先に`POST /communities/{communityId}/owner-transfer`でのオーナー移譲が必要）。そのコミュニティ発のイベントで開催日時が未来のCONFIRMED（または仮確定時点で予約済み扱いとなるAWAITING_APPROVAL）な参加を1件でも持つ場合も`409 MEMBER_HAS_UPCOMING_EVENTS`でブロックする（エラーコード一覧v1.8 §3）。管理者による強制退会（`PUT /communities/{communityId}/members/{userId}`のremove指定）にも同じチェックが入る（Issue #26）。
>
> 画面設計書v1.12 S-05に対応。

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
4. スコア計算（人数条件は**範囲内判定**。信頼度は対象外＝Phase2。参加頻度上限に達しているメンバーがいれば減点し理由に明記 [v1.11追加]）
5. Candidate保存

> **[v1.1補足]** MVPでは本APIによる手動実行のみを有効化する。ただし内部処理は「テンプレートID単位の実行」を最小単位として抽象化しており、将来のEventBridge Scheduler定期実行や空き予定登録時の自動トリガーからも同一ロジック（内部関数／同一Lambda）を呼び出せる構成とする。API自体の追加は不要。
>
> **[v1.11追加]** 参加頻度上限超過は候補からの機械的除外には使わない（要件定義書v1.6 30章）。スコアを下げた上で、6.2候補一覧の成立理由（reasons相当）にその旨を明記する。

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

`minPlayers`は2以上を指定すること（1を指定すると`400 INVALID_PLAYER_RANGE`）。**[v1.20修正]** 1人だけの空き予定でも候補化できてしまい、相互非公開型マッチングの前提が管理者側から破れる抜け道になっていたための制約（Issue #57）。

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

### 8.3 イベント仮確定 **[v1.4修正、v1.12修正：「イベント承認」から改称]**

`POST /events/{eventId}/confirm`

管理者（OWNER/ADMIN）による仮確定。**[v1.12修正]** 以前は承認と同時にイベントが`CONFIRMED`（本確定）になっていたが、Issue #10「イベント確定フローに全員承認ステップを追加」により、この呼び出しは仮確定（候補メンバー全員の実効自動承認設定に応じて`AWAITING_MEMBER_APPROVAL`または`CONFIRMED`への遷移）のみを行う。本確定は9.3（参加承認）で行われる。

処理：
- **候補メンバー全員のダブルブッキング事前チェック（Participant GSI1を時間範囲でQuery、判定対象statusを`CONFIRMED`/`AWAITING_APPROVAL`に拡張 [v1.12修正]）。重複があれば`409 PARTICIPANT_SCHEDULE_CONFLICT`を返却し中断 [v1.4新規]**
- 候補メンバーごとに実効自動承認設定（4.5d/3.2参照）を解決
- 状態変更（`PENDING_APPROVAL` → `AWAITING_MEMBER_APPROVAL`、全員自動承認ONの場合のみ直接`CONFIRMED`）**[v1.12修正]**
- Participant作成（自動承認ONのメンバーは`CONFIRMED`、それ以外は`AWAITING_APPROVAL`）**[v1.12修正]**
- 通知イベント発行（`AWAITING_MEMBER_APPROVAL`遷移時は承認待ちメンバーへの承認依頼通知、`CONFIRMED`遷移時は確定通知）
- OperationLog保存

Response

```json
{
  "eventId": "EVENT001",
  "status": "AWAITING_MEMBER_APPROVAL"
}
```

> **[v1.4新規]** 前回会話の「候補3：確定時ハードチェック」に対応。Lambda設計書v1.1 7.2b、DynamoDB物理設計書v1.3 5章に準拠。
>
> **[v1.12追加]** レスポンスの`status`は`AWAITING_MEMBER_APPROVAL`または`CONFIRMED`（全員自動承認ONの場合）のいずれか。エンドポイントのパス・メソッド・管理者権限のみ実行可能という点は変更していない（既存クライアントへの破壊的変更を避けるため）。

### 8.4 イベント中止 **[v1.1: 名称・説明を明確化、v1.10修正]**

`POST /events/{eventId}/cancel`

> **[v1.1修正]** イベント**全体**の開催中止（9.2の個人キャンセル申請とは別物）。管理者のみ実行可能。状態をCANCELLEDへ遷移し、全参加者へ通知。
>
> **[v1.10追加]** 状態遷移とあわせて、元となったMatchCandidate（および各CandidateMember）の`status`を`CONFIRMED`（イベント化済みの意）から`PENDING`へ戻す。これを行わないと、同一候補から再度イベントを作成しようとした際に`409 CANDIDATE_ALREADY_USED`で永久にブロックされ、「キャンセルしても確定イベントが残ったまま再登録できない」状態になっていた（DynamoDB物理設計書v1.8 §3.8参照）。
>
> **[v1.23追加]** イベント確定（8.3）時に削除された候補メンバーのAvailability（5章）を、確定前の登録内容のまま復元する（Issue #68）。復元はイベント時間帯だけでなく、Event.deletedAvailabilitySnapshot（DynamoDB物理設計書v1.17 §3.10）に保持した削除前スナップショットをそのまま書き戻すため、本人が元々登録していたイベント時間帯より広い範囲・gameTypes・commentも失われずに再現される。

### 8.4b 本日の対局を終了する **[v1.18新規]**

`POST /events/{eventId}/complete`

管理者（OWNER/ADMIN）のみ実行可能。`CONFIRMED`（または`IN_PROGRESS`）状態のイベントを`COMPLETED`へ遷移させる。

処理：
- `CONFIRMED`/`IN_PROGRESS`以外の状態からの呼び出しは`409 INVALID_STATUS_TRANSITION`
- 状態変更（`COMPLETED`）、`EventStatusHistory`記録、OperationLog保存
- `EventStatusChanged`イベント発行（EventBridge）

Response

```json
{
  "eventId": "EVENT001",
  "status": "COMPLETED"
}
```

> **[v1.18追加]** 要件定義書・DynamoDB物理設計書・画面設計書はいずれも`COMPLETED`をライフサイクルの一部として定義済みだったが、実際にこの状態へ遷移させる処理が存在しなかった（Issue #20）。10.2の成績集計（`_aggregate`）は、この遷移が起きた対局のみをコミュニティの通算成績（実質的なランキングの原資）に算入する。10.1の成績登録自体は、この遷移の前後を問わず引き続き可能（未確定運用の考慮。エラーコード一覧 §16 未決事項2参照）。

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

### 8.6b 会場更新 **[v1.26新規]**

`PUT /communities/{communityId}/locations/{placeId}`

権限はOWNER/ADMIN限定（登録と同様）。

Request

```json
{
  "name": "たかし宅",
  "address": "非公開（任意）",
  "note": "全自動卓あり"
}
```

### 8.6c 会場削除 **[v1.26新規]**

`DELETE /communities/{communityId}/locations/{placeId}`

権限はOWNER/ADMIN限定。中止・完了以外のステータスのイベントで使用中の会場は`409 LOCATION_IN_USE`で削除を拒否する（過去の利用履歴＝中止・完了済みイベントでの参照は削除の妨げにしない）。

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

### 8.7b 自分の確定イベント一覧取得 **[v1.10新規]**

`GET /users/me/events`

Response

```json
{
  "events": [
    {
      "eventId": "EVENT001",
      "communityId": "COMMUNITY001",
      "startTime": "2026-07-20T19:00:00.000Z",
      "endTime": "2026-07-20T23:00:00.000Z"
    }
  ]
}
```

処理：呼び出し元自身が参加者となっている確定（`CONFIRMED`）イベントを、コミュニティ横断で取得する。8.7と異なりコミュニティを跨いだ自分自身の確定予定のみを対象とする。

> **[v1.10追加]** 予定タブのカレンダー表示（画面設計書v1.6 S-10）で、複数コミュニティの確定予定を横断して表示するために追加。ParticipantのGSI1（DynamoDB物理設計書v1.8 §3.11）をそのまま利用し新規GSIは追加していない。取得対象は自分自身の確定予定のみであり、他メンバーの空き予定を返すものではないため、相互非公開型マッチング（要件定義書v1.5 29章）の原則には抵触しない。

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

### 9.4 参加承認 **[v1.12新規]**

`POST /events/{eventId}/participants/me/approve`

参加者本人が、仮確定（8.3）後に承認待ち（`AWAITING_APPROVAL`）となっている自分の参加を承認する（機能要件書v1.8 F-502b）。候補メンバー全員の承認が完了した時点で、イベント自体も本確定（`AWAITING_MEMBER_APPROVAL` → `CONFIRMED`）される。

Response

```json
{
  "eventId": "EVENT001",
  "userId": "USER010",
  "status": "CONFIRMED",
  "eventStatus": "AWAITING_MEMBER_APPROVAL"
}
```

> `eventStatus`は`AWAITING_MEMBER_APPROVAL`（自分以外にまだ未承認のメンバーがいる）または`CONFIRMED`（自分の承認で全員承認が完了し本確定した）のいずれか。既に応答済み（承認・拒否のいずれか）の場合は`409 PARTICIPANT_ALREADY_RESPONDED`、参加者でない場合は`403 NOT_A_PARTICIPANT`を返す。承認待ち中に管理者がイベント全体を中止（8.4）していた場合、この呼び出し自体は200で成功するが`eventStatus`は`CANCELLED`のまま変化しない（自分の承認自体は事実として記録される）。

### 9.5 参加辞退 **[v1.12新規]**

`POST /events/{eventId}/participants/me/reject`

参加者本人が、仮確定（8.3）後に承認待ち（`AWAITING_APPROVAL`）となっている自分の参加を明示的に辞退する（機能要件書v1.8 F-502c）。9.2の個人キャンセル申請とは異なり承認待ち状態専用で、管理者の承認を待たず即座に`REJECTED`が確定する。

Request

```json
{
  "reason": "その日は都合が悪くなりました"
}
```

Response

```json
{
  "eventId": "EVENT001",
  "userId": "USER010",
  "status": "REJECTED"
}
```

> `reason`は任意項目。イベント自体は自動では中止されない（要件定義書v1.7 §17/§19のヒューマン・イン・ザ・ループ原則）。辞退が発生すると管理者へ通知が送られ、イベントを継続するか中止（8.4）するかは管理者の判断に委ねられる。エラーコードは9.4と同様（`PARTICIPANT_ALREADY_RESPONDED`/`NOT_A_PARTICIPANT`）。

---

## 10. Game Result API

### 10.1 結果登録 **[v1.21修正]**

`POST /events/{eventId}/sessions`

Request

```json
{
  "gameType": "MAHJONG4",
  "calcMode": "AUTO",
  "results": [
    { "userId": "USER001", "score": 35000 }
  ],
  "chips": [
    { "userId": "USER001", "chipCount": 2 }
  ],
  "startingPoints": 25000,
  "returnPoints": 30000,
  "umaByRank": [20, 10, -10, -20],
  "boxUnderSettlement": true,
  "tobiPoints": 10,
  "tobiAssignments": [
    { "bustedUserId": "USER004", "receiverUserId": "USER001" }
  ]
}
```

Response（`calcMode=AUTO`時、`results`内の各行にも同じ計算が反映された`rankPoints`が入る）は、上記Requestの`startingPoints`/`returnPoints`/`umaByRank`/`boxUnderSettlement`/`tobiPoints`/`tobiAssignments`をそのまま返す。

> **[v1.18修正]** 実行権限をOWNER/ADMIN限定からコミュニティのアクティブなメンバー全員に緩和した。対局を打った本人・記録係がその場で登録できないのは不便という要望への対応。登録済みセッションの編集（`PUT /events/{eventId}/sessions/{sessionNo}`）はOWNER/ADMIN限定のまま。
>
> **[v1.19修正]** Requestの例を実装（`result_lambda/handlers/results.py`）に合わせて修正した。`rank`はクライアントからは送らず、サーバーが`score`の降順から機械的に導出する。`calcMode`（`AUTO`/`MANUAL`。省略時`MANUAL`）と、`calcMode=AUTO`時のみ必須の`startingPoints`/`returnPoints`/`umaByRank`、任意項目の`chips`を追記した（従来の記載はいずれも欠落していた）。
>
> **[v1.21修正]** `calcMode=AUTO`時の任意項目として`boxUnderSettlement`（箱下精算あり/なし、省略時true）、`tobiPoints`（飛び賞1件あたりのポイント、省略時0）、`tobiAssignments`（誰が誰をトビにしたかの明示的な指定、`bustedUserId`は実際にscoreがマイナスであることをサーバー側で検証する）を追加した（Issue #66・#67）。`boxUnderSettlement=false`の場合、`base = (max(score, 0) - returnPoints) / 1000`のように基礎点計算のみマイナスの持ち点を0点に切り捨てる。トビ判定自体（`tobiAssignments`の妥当性検証）は常に生の`score`（マイナスのまま）で行う。`tobiAssignments`の各行は受取人に`+tobiPoints`、トビになった本人に`-tobiPoints`を加減点する。

### 10.1b 対局セッション削除 **[v1.19新規]**

`DELETE /events/{eventId}/sessions/{sessionNo}`

Response

```json
{
  "eventId": "EVENT001",
  "sessionNo": "0001"
}
```

> **[v1.19新規]** Issue #42：誤登録した半荘を削除する手段が無かったため新設。実行権限はOWNER/ADMIN限定（10.1のPUTと同じ方針）。GameSession本体・全参加者分のGameResult・GameResultChipをまとめて削除する。対象が存在しない場合は`404 GAME_SESSION_NOT_FOUND`。

### 10.2 成績取得 **[v1.18修正]**

`GET /users/{userId}/results`

Response

```json
{
  "userId": "USER001",
  "communityId": "COMMUNITY001",
  "byGameType": {
    "MAHJONG4": {
      "totalGames": 12,
      "averageRank": 2.33,
      "firstPlaceRate": 0.25,
      "lastPlaceRate": 0.167,
      "totalPoints": 34.5,
      "totalChips": 12
    },
    "MAHJONG3": {
      "totalGames": 0,
      "averageRank": 0,
      "firstPlaceRate": 0,
      "lastPlaceRate": 0,
      "totalPoints": 0,
      "totalChips": 0
    }
  }
}
```

> **[v1.1補足]** 権限チェック方針を明記：閲覧者が対象ユーザーと同一コミュニティに所属している場合のみ、そのコミュニティ内での成績を返却する。コミュニティを跨いだ成績の全体公開は行わない。
>
> **[v1.18修正]** レスポンスをゲーム種別（四麻/三麻）ごとの`byGameType`に分離した（従来は`totalGames`等をトップレベルに混在させて返していた）。四麻と三麻では着順のスケール（1〜4位/1〜3位）が異なり、合算した`averageRank`は指標として意味を持たなくなるため（DynamoDB物理設計書v1.13 §3.13）。
>
> **[v1.18追加]** 各`averageRank`等の統計は、対局が行われたイベントが`COMPLETED`（8.4b「本日の対局を終了する」実行後）になっているものだけを集計対象とする。管理者が終了操作を行うまでは、その日の対局はコミュニティの通算成績に反映されない。

### 10.3 コミュニティ内ランキング取得 **[v1.25新規]**

`GET /communities/{communityId}/rankings`

Query Parameters

| パラメータ | 必須 | 説明 |
|---|---|---|
| `gameType` | ○ | `MAHJONG4` / `MAHJONG3` |
| `periodType` | ○ | `MONTH` / `QUARTER` / `HALF_YEAR` / `YEAR` / `ALL_TIME` |
| `year` | `periodType=ALL_TIME`以外で必須 | 対象年（例：2026） |
| `month` | `periodType=MONTH`で必須 | 1〜12 |
| `quarter` | `periodType=QUARTER`で必須 | 1〜4 |
| `half` | `periodType=HALF_YEAR`で必須 | 1〜2 |

Response

```json
{
  "communityId": "COMMUNITY001",
  "gameType": "MAHJONG4",
  "period": {
    "type": "MONTH",
    "year": 2026,
    "month": 7,
    "startDate": "2026-07-01",
    "endDate": "2026-07-31"
  },
  "members": [
    {
      "userId": "USER001",
      "displayName": "たかし",
      "totalGames": 15,
      "averageRank": 2.13,
      "firstPlaceRate": 0.267,
      "secondPlaceRate": 0.333,
      "topTwoRate": 0.6,
      "nonLastRate": 0.8,
      "totalPoints": 34.5,
      "participatedEvents": 6,
      "totalChips": 12,
      "averageChips": 0.8
    }
  ]
}
```

> **[v1.25新規]** Issue #40：コミュニティ内ランキング表示機能（F-805、機能要件書v1.11）に対応。
>
> **権限**：10.2と同様、コミュニティメンバーであれば誰でも閲覧可能（管理者限定にはしない）。非メンバーは`RESULT_ACCESS_DENIED`（403）。
>
> **`minGames`（足切り）はクエリパラメータに含めない**：`members`配列の各要素に既に`totalGames`が含まれているため、足切り閾値の変更や表示指標の切り替えはフロントエンド側で再取得なしに（レスポンスの再ソート・再フィルタのみで）行う設計とした。`gameType`/`periodType`（期間）の変更のみAPIを叩き直す。
>
> **`members`の並び順**：本APIはソートを行わず、DynamoDBから取得した順のまま返す。指標ごとに昇順/降順の向きが異なる（例：`averageRank`は小さいほど上位、`totalPoints`は大きいほど上位）ため、順位付けはフロントエンド側で選択中の指標に応じて行う。
>
> **集計対象**：10.2と同様、対局が行われたイベントが`COMPLETED`になっているもののみを対象とする。退会済みメンバーも、在籍中に打った成績はランキング集計対象に含める（要件定義書v1.9 §32.5）。
>
> **実装**：DynamoDB物理設計書v1.19 §3.13のGSI2相乗り（`GSI2PK=COMMUNITY#{communityId}#{gameType}`, `GSI2SK between {startDate}~{endDate}`）により、対象コミュニティ・種目・期間の全メンバー分のGameResult/GameResultChipを1回のQueryで取得する（Lambda設計書v1.9 §8.3参照）。

---

## 11. Notification API **[v1.5修正]**

> **[v1.1修正]** 14章のMVP範囲の表現を修正（下記14章参照）。アプリ内通知（一覧・既読）自体はMVP対象。LINE連携などチャネル拡張のみPhase2。
>
> **[v1.5修正]** Push通知（Webプッシュ通知）をMVP対象に前倒し、11.3/11.4を新規追加（要件定義書v1.3 27章）。

### 11.1 通知一覧 **[v1.24修正]**

`GET /notifications`

Response

```json
{
  "notifications": [
    {
      "notificationId": "NOTIF001",
      "type": "AVAILABILITY_REQUEST",
      "message": "空き予定の提出が依頼されました。",
      "read": false,
      "relatedEventId": null,
      "relatedCommunityId": "COMMUNITY001",
      "createdAt": "2026-07-08T10:00:00.000Z"
    }
  ]
}
```

> **[v1.24追加]** `relatedCommunityId`（DynamoDB物理設計書v1.18 §3.14参照）を追加。`AVAILABILITY_REQUEST`（空き予定提出リクエスト）の通知は特定のイベントではなくコミュニティに紐づくため、従来の`relatedEventId`だけでは通知タップ時の遷移先を表現できず、タップしても既読になるだけでどこにも遷移しない導線切れになっていた（Issue #73）。フロントエンドは`type=AVAILABILITY_REQUEST`かつ`relatedCommunityId`がある場合、当該コミュニティの空き予定登録画面（`/communities/{communityId}/availability/new`）へ遷移する。他の通知種別は従来通り`relatedEventId`でイベント詳細へ遷移する。

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

## 12b. Feedback API **[v1.17新規]**

> 運営者限定のエンドポイントは、コミュニティのOWNER/ADMINとは別軸の「運営者」ロール（JWTの`cognito:groups`に`Operators`を含むユーザー）のみ利用できる。Lambda設計書v1.7 §9b.4参照。

### 12b.1 フィードバック投稿

`POST /feedback`

Request

```json
{
  "kind": "QUICK",
  "relatedFeature": "MATCHING_CANDIDATE_LIST",
  "rating": "GOOD",
  "category": null,
  "content": null,
  "attachmentKeys": []
}
```

| フィールド | 必須 | 説明 |
|---|---|---|
| kind | ○ | `QUICK`（1クリック評価）または`DETAILED`（詳細投稿） |
| relatedFeature | ○ | 該当機能（画面・操作を表す識別子） |
| rating | kind=QUICK時必須 | `BAD` / `NEUTRAL` / `GOOD` |
| category | kind=DETAILED時必須 | `BUG` / `FEATURE_REQUEST` / `UX_IMPROVEMENT` |
| content | 任意（kind=DETAILEDのみ） | 詳細内容 |
| attachmentKeys | 任意（kind=DETAILEDのみ） | 12b.2で取得したS3オブジェクトキーの配列 |

処理：投稿者はJWTの`userId`から自動的に紐付ける（連絡先の別入力は求めない）。F-1401/F-1402（機能要件書v1.10）に対応。

### 12b.2 スクリーンショット添付用アップロードURL発行 **[v1.17新規]**

`POST /feedback/attachments/presign`

Request

```json
{
  "contentType": "image/png"
}
```

Response

```json
{
  "uploadUrl": "https://xxxxx.s3.amazonaws.com/feedback/xxxxx.png?X-Amz-...",
  "attachmentKey": "feedback/{userId}/{uuid}.png",
  "expiresIn": 300
}
```

処理：フロントエンドは`uploadUrl`へ画像を直接PUTした後、返却された`attachmentKey`を12b.1のリクエストの`attachmentKeys`に含めて送信する（Lambda設計書v1.7 §9b.3参照）。

### 12b.3 フィードバック一覧取得（運営者限定） **[v1.17新規]**

`GET /feedback?status=UNHANDLED&category=BUG&kind=DETAILED&cursor=...`

処理：`status`/`category`/`kind`はいずれも任意の絞り込みクエリパラメータ。

### 12b.4 フィードバック詳細取得（運営者限定） **[v1.17新規]**

`GET /feedback/{feedbackId}`

処理：`attachmentKeys`に対応する`attachmentUrls`（署名付きGET URL、有効期限5分）を都度発行してレスポンスに含める（Lambda設計書v1.7 §9b.3。バケット自体は非公開のため）。一覧取得（12b.3）では発行しない（絞り込み前の全件に対して署名生成コストがかかるため）。

### 12b.5 フィードバックのステータス・優先度更新／返信（運営者限定） **[v1.17新規]**

`PATCH /feedback/{feedbackId}`

Request

```json
{
  "status": "PLANNED",
  "priority": "HIGH",
  "reply": "対応予定です。次回アップデートで反映します。"
}
```

処理：`status`/`priority`/`reply`はいずれも任意（部分更新）。`reply`を指定した場合、投稿者へアプリ内通知を送るため`FeedbackReplied`イベントをEventBridgeへ発行する。

### 12b.6 フィードバック集計取得（運営者限定） **[v1.17新規]**

`GET /feedback/stats`

Response

```json
{
  "byCategory": { "BUG": 3, "FEATURE_REQUEST": 5, "UX_IMPROVEMENT": 2 },
  "byStatus": { "UNHANDLED": 4, "PLANNED": 3, "DONE": 3 },
  "byPriority": { "LOW": 2, "MEDIUM": 4, "HIGH": 1 }
}
```

---

## 12c. Announcement API **[v1.17新規]**

### 12c.1 アップデート予告一覧取得

`GET /announcements`

処理：一般ユーザーには`status=PUBLISHED`のもののみ返却する。運営者は`?includeAll=true`指定時にDRAFT/ARCHIVEDを含めて取得できる。F-1406（機能要件書v1.10）に対応。

### 12c.2 アップデート予告作成（運営者限定）

`POST /announcements`

Request

```json
{
  "title": "次回アップデート予告",
  "body": "○○機能を追加予定です。"
}
```

処理：`status=DRAFT`で作成する。

### 12c.3 アップデート予告更新・公開状態変更（運営者限定）

`PUT /announcements/{announcementId}`

Request

```json
{
  "title": "次回アップデート予告",
  "body": "○○機能を追加予定です。",
  "status": "PUBLISHED"
}
```

処理：`status`は`DRAFT` / `PUBLISHED` / `ARCHIVED`のいずれか。取り下げは`DELETE`ではなく`status=ARCHIVED`への更新で行う（監査証跡を残すため）。

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
| Feedback / Announcement [v1.17] | FeedbackLambda |

---

## 14. MVP API範囲 **[v1.5修正]**

必須（MVP）

- User
- Community（会場マスタ含む）
- Availability（**空き予定提出リクエスト含む**、[v1.5追加]）
- EventTemplate
- Matching
- Event（会場選択含む。仮確定→全員承認→本確定 [v1.12追加]）
- Participant（キャンセル申請・承認、および参加者本人による承認・辞退 [v1.12追加] まで）
- Notification（アプリ内通知・一覧・既読 + **Webプッシュ通知購読管理**、[v1.5追加]） ※v1.0でPhase2誤記だった箇所を修正
- **Feedback / Announcement**（簡易フィードバック・詳細投稿・運営者レビュー・アップデート予告、[v1.17追加]）

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

---

## v1.8 → v1.9 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.1 コミュニティ作成のRequestに`themeColor`（任意）を追加 | コミュニティごとのテーマカラー設定。まずはアイコン画像より軽量なカラーコード設定のみ先行導入する方針 |
| 2 | 4.2b コミュニティ詳細取得のResponseに`themeColor`を追加 | 上記と同一の決定事項 |
| 3 | 4.2c コミュニティテーマカラー設定（`PUT /communities/{communityId}/theme-color`）を新規追加 | 作成後にOWNER/ADMINがテーマカラーを変更する手段。DynamoDB物理設計書v1.7でCommunityに`themeColor`属性を追加したことに対応 |
| 2 | 12章 OperationLog API（`GET /communities/{communityId}/logs`, `GET /users/{userId}/logs`）をCommunityLambdaに実装・接続 | Lambda設計書v1.3 §2で「現時点で未実装」とされていたAPIの実装。ドキュメント（API設計書v1.7時点）自体は既にエンドポイントを定義済みだったため、本書のAPI仕様に変更はない |

## v1.9 → v1.10 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.2 コミュニティ一覧取得のResponseに`themeColor`を追加し、返却順がMembership.sortOrder昇順であることを明記 | 一覧カードへのテーマカラー反映、表示順並び替えの土台 |
| 2 | 4.2d コミュニティ表示順の並び替え（`PUT /communities/order`）を新規追加 | コミュニティ一覧の表示順を並び替えたいという要望への対応。DynamoDB物理設計書v1.8でMembershipに`sortOrder`属性を追加したことに対応 |
| 3 | 8.4 イベント中止時、元となったMatchCandidateの`status`を`PENDING`へ戻す旨を追記 | キャンセル後に同一候補が`CANDIDATE_ALREADY_USED`で永久に再利用できなくなっていた不具合の修正 |
| 4 | 8.7b 自分の確定イベント一覧取得（`GET /users/me/events`）を新規追加 | 予定タブのカレンダー表示で、複数コミュニティの確定予定を横断表示するため |

---

## v1.10 → v1.11 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 3.2 プロフィール更新のRequestに`frequencyLimitCount`/`frequencyLimitPeriod`（任意）を追加 | 要件定義書v1.6 30章：体力・満足度等の理由による個人ごとの参加頻度上限。機能要件書v1.7 F-003 |
| 2 | 4.5c 参加頻度上限のコミュニティ単位の上書き（`PUT /communities/{communityId}/members/me/frequency-limit`）を新規追加 | 4.5b（表示名）と同じフォールバック構造。機能要件書v1.7 F-109 |
| 3 | 6.1 候補生成のスコア計算ステップに、参加頻度上限超過時の減点・理由明記を追記（候補からの機械的除外はしない） | ヒューマン・イン・ザ・ループ原則（要件定義書19章）に沿った設計判断 |

---

## v1.11 → v1.12 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 3.2 プロフィール更新のRequest/Responseに`autoApprove`（任意）を追加 | Issue #10：イベント確定フローへの「全員承認」ステップ追加。自動承認の全体デフォルト設定（機能要件書v1.8 F-003） |
| 2 | 4.5d 自動承認のコミュニティ単位の上書き（`PUT /communities/{communityId}/members/me/auto-approve`）を新規追加 | 4.5b（表示名）・4.5c（参加頻度上限）と同じフォールバック構造。機能要件書v1.8 F-109b |
| 3 | 8.3を「イベント承認」から「イベント仮確定」に改称し、処理内容を仮確定（`AWAITING_MEMBER_APPROVAL`または全員自動承認時のみ`CONFIRMED`）に修正 | Issue #10：管理者の仮確定だけでなく参加予定者全員の承認を経て本確定する多段階フローへの変更 |
| 4 | 9.4 参加承認（`POST /events/{eventId}/participants/me/approve`）、9.5 参加辞退（`POST /events/{eventId}/participants/me/reject`）を新規追加 | 機能要件書v1.8 F-502b/F-502c。参加者本人による個別承認・明示的な辞退 |
| 5 | 13章Lambda対応表は変更なし（Participant系エンドポイントは引き続きEventLambdaが担当） | 新規ドメインLambdaは追加しない設計判断 |
| 6 | 14章MVP必須リストのEvent/Participant項目に、全員承認フローが含まれる旨を追記 | 上記対応の実装スコープ明記 |

---

## v1.12 → v1.13 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.3 招待URL発行の利用者範囲をOWNER/ADMIN限定からコミュニティの全メンバーに拡大 | Issue #22：一般メンバーが友人・知人を誘えるようにしたいという要望への対応 |
| 2 | 4.3b 招待URL無効化の権限にOWNER/ADMINに加え発行者本人を追加 | 発行者本人が自分の発行したURLを取り消せない不便さの解消（Issue #22） |
| 3 | 4.4 招待参加の分岐条件に「Invite.createdByRoleがMEMBERの場合は強制的に承認制」を追加 | 誰でも招待URLを発行できるようにした結果、管理者の意図しないメンバー流入が起きる懸念への対応。既存のJoinRequest承認機構を流用（Issue #22） |

---

## v1.13 → v1.14 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.3c 招待プレビュー取得（`GET /invites/{token}`）を新規追加 | Issue #23：招待受諾画面が承認要否を事前判定できず、即時参加コミュニティでも一言メッセージ欄を常時表示していた食い違いの解消。承認要否が分かれば、フロント側でメッセージ欄の表示要否を出し分けられる |

---

## v1.14 → v1.15 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.2b コミュニティ詳細取得のResponseに`pendingRequestCount`を追加 | Issue #29：コミュニティ詳細画面で参加リクエスト一覧の導線が奥まった位置にあり、未処理件数にも気づけなかった問題への対応。管理者向けバッジ表示に使う |

---

## v1.15 → v1.16 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.5e メンバー自主退会（`POST /communities/{communityId}/members/me/leave`）を新規追加 | Issue #25：メンバー自身の意思でコミュニティを抜ける導線が存在しなかったための対応。機能要件書v1.9 F-104d |
| 2 | 管理者による強制退会（`PUT .../members/{userId}`のremove指定）にも、自主退会と同じ未来の確定イベント参加チェックが入る旨を4.5eの注記に追記（新規エンドポイントなし） | Issue #26：強制退会後もParticipantレコードだけが残る不整合の解消 |

---

## v1.16 → v1.17 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 12b章「Feedback API」を新規追加（フィードバック投稿、スクリーンショット添付URL発行、運営者限定の一覧・詳細・ステータス更新/返信・集計） | Issue #34：フィードバック機能の設計書追加。機能要件書v1.10 F-1401〜F-1405 |
| 2 | 12c章「Announcement API」を新規追加（アップデート予告の一覧・作成・更新） | 同上。機能要件書v1.10 F-1406 |
| 3 | 13章Lambda対応表・14章MVP API範囲に上記を追加 | 整合性維持 |

---

## v1.17 → v1.18 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 8.4b「本日の対局を終了する」（`POST /events/{eventId}/complete`）を新規追加。`CONFIRMED`/`IN_PROGRESS`→`COMPLETED`遷移を実装 | Issue #20：要件定義書・DynamoDB物理設計書・画面設計書はCOMPLETEDを定義済みだったが、実際に遷移させる処理が存在しなかったギャップの解消。管理者が対局終了を明示的に確定する導線として新設 |
| 2 | 10.1 結果登録の実行権限をOWNER/ADMIN限定からコミュニティのアクティブなメンバー全員に緩和 | 対局を打った本人・記録係がその場で確定できないのは不便という要望への対応。編集（10.1のPUT）はOWNER/ADMIN限定のまま据え置き |
| 3 | 10.2 成績取得のレスポンスをゲーム種別（四麻/三麻）ごとの`byGameType`に分離。あわせて統計集計を、対局が行われたイベントが`COMPLETED`のものだけに限定する旨を追記 | 四麻/三麻混在ユーザーの平均着順が意味を持たなくなる問題の解消。および上記No.1の「終了する」操作が、コミュニティの通算成績（実質的なランキング）に反映されるタイミングを明確化するため |

---

## v1.18 → v1.19 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 10.1新規セクション「10.1b 対局セッション削除」（`DELETE /events/{eventId}/sessions/{sessionNo}`）を追加。実行権限はOWNER/ADMIN限定 | Issue #42：登録済み半荘を削除する手段が無かったため新設。GameSession本体・全参加者分のGameResult・GameResultChipをまとめて削除する |

---

## v1.19 → v1.20 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 7.1 条件作成の`minPlayers`下限を1から2に変更（`400 INVALID_PLAYER_RANGE`） | Issue #57：`minPlayers=1`だとメンバー1人だけの空き時間帯もそのまま候補化され、相互非公開型マッチングの前提を管理者側から破れてしまうための制約強化 |
| 2 | 10.1結果登録のRequest例を実装（`result_lambda/handlers/results.py`）に合わせて修正。`rank`をクライアントが送る記載は誤りで、サーバーが`score`降順から導出する。`calcMode`・`calcMode=AUTO`時必須の`startingPoints`/`returnPoints`/`umaByRank`・任意項目の`chips`が例から欠落していたため追記 | ドキュメントと実装の食い違い解消 |

---

## v1.20 → v1.21 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 10.1結果登録に、`calcMode=AUTO`時の任意項目`boxUnderSettlement`（箱下精算あり/なし、既定true）を追加。`false`の場合、基礎点計算のみマイナスの持ち点を0点に切り捨てる | Issue #67：箱下精算なしのルールで対局しているコミュニティの自動計算結果が実際の精算と合わない問題への対応。既定はtrue（既存の挙動を維持し、後方互換） |
| 2 | 同10.1に、`tobiPoints`（飛び賞1件あたりのポイント、既定0）・`tobiAssignments`（誰が誰をトビにしたかの明示的な指定）を追加 | Issue #66：飛び賞の仕組みが無く、飛び賞ありのルールで対局しているコミュニティの自動計算結果が実際の精算と合わない問題への対応。最終スコアだけでは加害者（誰がトビにしたか）を機械的に特定できないため、フロントのUIで管理者に明示的に選んでもらう方式とした。サーバー側は`bustedUserId`のscoreが実際にマイナスであることを検証する |

---

## v1.21 → v1.22 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 4.3c 招待プレビュー取得のレスポンスに`communityDescription`/`communityGenre`/`communityIcon`（コミュニティ補足情報）、`invitedByDisplayName`（招待発行者のコミュニティ内表示名）、`alreadyMember`/`joinRequestPending`（呼び出し元の既存所属状態）を追加 | Issue #70：招待受諾画面を「〇〇さんから招待されています」カードUIに刷新するため、必要な情報を事前取得できるようにした。あわせて参加済み・承認待ちユーザーが招待URLを踏んだ際の詰み画面を解消する |

---

## v1.22 → v1.23 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 8.4 イベント中止に、確定時に削除された候補メンバーのAvailabilityを確定前の登録内容のまま復元する旨を追記 | Issue #68：中止後にマッチングエンジンが新規候補を再生成する材料（Availability）自体が無く、メンバーが空き予定を再登録しないと候補すら出てこない問題への対応。DynamoDB物理設計書v1.17 §3.10で追加したEvent.deletedAvailabilitySnapshotに削除前の完全なスナップショットを保持し、単純なイベント時間帯の復元では失われる「元々登録していたより広い範囲」も再現できるようにした |

---

## v1.23 → v1.24 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 11.1 通知一覧のレスポンスに`relatedCommunityId`を追加 | Issue #73：空き予定提出リクエスト（`AVAILABILITY_REQUEST`）の通知は特定のイベントではなくコミュニティに紐づくため、既存の`relatedEventId`だけでは遷移先を表現できず、通知をタップしても遷移しない導線切れになっていた。DynamoDB物理設計書v1.18 §3.14で追加した`Notification.relatedCommunityId`をそのままレスポンスに含める |

---

## v1.24 → v1.25 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 10.3 コミュニティ内ランキング取得（`GET /communities/{communityId}/rankings`）を新規追加 | Issue #40：コミュニティ内ランキング表示機能の追加（F-805） |
| 2 | 4.2e コミュニティ内ランキング設定（`PUT /communities/{communityId}/ranking-settings`）を新規追加 | 上記と同一の決定事項（F-806） |
| 3 | 4.2b コミュニティ詳細取得のレスポンスに、ランキングのデフォルト設定4項目を追加予定である旨を明記 | 上記と同一の決定事項 |

Issue #40「コミュニティ内ランキング表示機能の追加」に対応。

---

## v1.25 → v1.26 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 8.6b 会場更新（`PUT /communities/{communityId}/locations/{placeId}`）を新規追加 | Issue #86：会場（Place）の編集・削除機能の追加 |
| 2 | 8.6c 会場削除（`DELETE /communities/{communityId}/locations/{placeId}`）を新規追加。中止・完了以外のステータスのイベントで使用中の会場は`409 LOCATION_IN_USE`で削除を拒否する | 上記と同一の決定事項 |
