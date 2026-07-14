# MeetFlow DynamoDB 物理テーブル設計書 v1.5

> 要件定義書v1.1・機能要件書v1.1・API設計書v1.1・操作ログ設計書v1.0・AWSシステム構成設計書v1.0を踏まえて設計。
> v1.0→v1.1、v1.1→v1.2、v1.2→v1.3、v1.3→v1.4、v1.4→v1.5の変更点はそれぞれ本文中と末尾の変更点サマリを参照。

---

## 1. 設計方針

- **単一テーブル設計（Single Table Design）** を採用する。理由：
  - コミュニティ規模が10〜30人程度と小さく、JOINを多用するRDB的なアクセスよりも、事前に洗い出したアクセスパターンに対してPK/SK一発で応答できる設計の方がLambdaの実行時間・コストの両面で有利
  - サーバーレス構成（Lambda + DynamoDB）との相性が良く、AWS Developer Associateで問われる典型パターンでもある
- テーブル名：`MeetFlowTable`
- キャパシティモード：**オンデマンド**（個人開発規模で負荷予測が立てにくいため。将来トラフィックが安定したらプロビジョンド+Auto Scalingへの切替を検討）
- GSIは最小限（2本）に抑え、オーバーロードGSI（1つのGSIを複数エンティティで使い回す）パターンを採用
- 暗号化：AWS所有キーではなくKMS（要件定義書24章に準拠）
- バックアップ：PITR有効化（要件定義書24章に準拠）

---

## 2. キー設計の全体像

| GSI名 | パーティションキー | ソートキー | 主な用途 |
|---|---|---|---|
| （プライマリ） | PK | SK | エンティティ本体・親子関係の取得 |
| GSI1（ByUser） | GSI1PK | GSI1SK | 「あるユーザーの○○一覧」を横断的に取得 |
| GSI2（ByAltId） | GSI2PK | GSI2SK | コミュニティIDを介さない直接ID検索（候補詳細など） |

---

## 3. エンティティ一覧とキー設計

### 3.1 User

```
PK:   USER#{userId}
SK:   PROFILE
```

| 属性 | 型 | 説明 |
|---|---|---|
| userId | S | Cognito sub |
| nickname | S | ニックネーム |
| icon | S | アイコンURL |
| bio | S | 自己紹介 |
| gameTypes | SS(String Set) | 対応可能ゲーム |
| beginnerOk | BOOL | 初心者対応可否 |
| createdAt | S | ISO8601 |

> F-001/F-002/F-003 に対応。Cognito自体にはメール・パスワードのみ持たせ、プロフィールはDynamoDB側で管理する。

---

### 3.2 Community

```
PK:   COMMUNITY#{communityId}
SK:   METADATA
```

| 属性 | 型 | 説明 |
|---|---|---|
| name | S | コミュニティ名 |
| description | S | 説明 |
| genre | S | ジャンル |
| memberApprovalRequired | BOOL | 参加承認制フラグ [v1.1] |
| **communityType** | **S** | **PERSONAL / STORE / OFFICIAL（デフォルト PERSONAL）[v1.1新規]** |
| ownerId | S | 現在のOWNER userId |
| createdAt | S | ISO8601 |

> F-101 に対応。
>
> **[v1.1追加]** 将来の店舗展開（フリー雀荘・公式コミュニティ等）を見据え、`communityType`属性を追加。MVPでは全件`PERSONAL`固定で保存する。値を文字列として持つだけでキー構造への影響はなく、将来STORE/OFFICIAL向けの機能分岐（公開ディレクトリ掲載、決済連携等）をアプリ層で追加する際の起点にする。
>
> **権限（Membership.role）については、スキーマ変更は不要**。`role`は元々文字列（S型）であり、将来`STORE_ADMIN`や`STAFF`のような値を追加してもテーブル構造上の制約はない。店舗展開が具体化した段階でアプリケーション層のバリデーション・権限マッピングを設計すれば十分なため、本書ではスキーマ上の対応のみ記載し、権限マトリクスの詳細設計は見送る。

---

### 3.3 Membership（コミュニティ所属・権限）

```
PK:      COMMUNITY#{communityId}
SK:      MEMBER#{userId}
GSI1PK:  USER#{userId}
GSI1SK:  COMMUNITY#{communityId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| role | S | OWNER / ADMIN / MEMBER |
| status | S | ACTIVE / SUSPENDED |
| joinedAt | S | ISO8601 |
| **priorityWeight** | **N** | **（Phase3予約属性・未使用）複数コミュニティ横断比較用の優先度。値は0〜100等を想定 [v1.3追加]** |
| **desiredFrequency** | **N** | **（Phase3予約属性・未使用）月あたりの希望参加頻度 [v1.3追加]** |

**アクセスパターン**
- コミュニティのメンバー一覧：`PK=COMMUNITY#{id}, SK begins_with MEMBER#`
- ユーザーの所属コミュニティ一覧：`GSI1PK=USER#{userId}, GSI1SK begins_with COMMUNITY#`

> F-104, F-105, F-106（OWNER変更時は該当Membershipのroleを書き換え。元OWNERはrole=MEMBERに更新 [v1.1]）に対応。
>
> **[v1.3追加]** `priorityWeight`/`desiredFrequency`はPhase3（複数コミュニティ横断の優先度・満足度比較機能）向けの予約属性。今は値を使わないが、後からの一括マイグレーションを避けるため属性だけ先に確保しておく。

---

### 3.4 Invite（招待URL）

```
PK:   INVITE#{token}
SK:   METADATA
```

| 属性 | 型 | 説明 |
|---|---|---|
| communityId | S | 対象コミュニティ |
| createdBy | S | 発行者userId |
| revoked | BOOL | 無効化フラグ |
| expiresAt | S | 有効期限（将来対応、MVPではnull可） |
| createdAt | S | ISO8601 |

> トークン自体がPKなので、招待URLアクセス時は1回のGetItemで完結する。F-102に対応。

---

### 3.5 JoinRequest（参加リクエスト）**[v1.1新規]**

```
PK:      COMMUNITY#{communityId}
SK:      JOINREQ#{userId}
GSI1PK:  USER#{userId}
GSI1SK:  JOINREQ#{communityId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| status | S | PENDING / APPROVED / REJECTED |
| **message** | **S** | **申請時の一言メッセージ（任意、例：「〇〇さんの紹介で来ました」）[v1.2追加]** |
| requestedAt | S | ISO8601 |
| processedAt | S | 承認/却下日時 |
| processedBy | S | 処理した管理者userId |

**アクセスパターン**
- コミュニティの未処理リクエスト一覧：`PK=COMMUNITY#{id}, SK begins_with JOINREQ#` + `status=PENDING`でフィルタ
- ユーザー自身のリクエスト状況確認：GSI1

> F-103／F-104b／F-104cに対応。承認時はTransactWriteItemsで「JoinRequestのstatus更新」と「Membership新規作成」を同時にコミットし、承認処理の途中失敗（片方だけ成功）を防ぐ。
>
> **[v1.2追加]** 管理者が承認判断をする際、ニックネームだけでは材料不足なため、一覧取得時にUserエンティティ（`bio`, `gameTypes`, `beginnerOk`）を`GetItem`で合わせて取得し、申請メッセージと共に返却する（API設計書側で対応）。招待URLはコミュニティ単位のまま維持し、個人ごとの招待URL発行は行わない（管理コストとのバランスを優先）。

---

### 3.6 Availability（空き予定）

```
PK:      COMMUNITY#{communityId}
SK:      AVAIL#{startTime}#{availabilityId}
GSI1PK:  USER#{userId}
GSI1SK:  AVAIL#{startTime}
```

| 属性 | 型 | 説明 |
|---|---|---|
| userId | S | 登録者 |
| endTime | S | ISO8601 |
| gameTypes | SS | 対応可能ゲーム種別 |
| comment | S | コメント |
| createdAt | S | ISO8601 |

**アクセスパターン**
- マッチング処理時「コミュニティ内の指定期間の空き予定を横断取得」：`PK=COMMUNITY#{id}, SK between AVAIL#{from} and AVAIL#{to}` **※マッチング処理（F-401）内部専用。他メンバーの空き予定を返す公開APIは提供しない**
- ユーザー自身の空き予定一覧：GSI1（`GET /communities/{id}/availability`が返すのはこのGSI1ベースの呼び出し元自身の分のみ）

> F-201〜F-204に対応。SKの先頭がstartTimeなので、マッチング処理（F-401）が期間指定でRangeクエリを投げやすい。
>
> **[v1.5追加]** 上記2つのアクセスパターンの非対称性（PKベースの横断取得＝マッチング内部専用、GSI1ベースの自分専用取得＝公開API）は偶然ではなく、要件定義書v1.4 29章「相互非公開型マッチング」（個人の入力は非公開、システムが導き出した出力＝候補のみ公開）をデータ構造レベルで担保する設計である。将来コミュニティ横断の空き予定取得APIを追加検討する場合も、この非対称性を崩さないことを設計上の制約とする。

---

### 3.7 EventTemplate（開催条件）

```
PK:   COMMUNITY#{communityId}
SK:   TEMPLATE#{templateId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| gameType | S | ゲーム種別 |
| minPlayers | N | 最低人数 |
| maxPlayers | N | 最大人数 |
| priority | N | 優先度 |
| conditions | M(Map) | 初心者歓迎等の条件 |
| createdAt | S | ISO8601 |

> F-301〜F-304に対応。人数条件は`minPlayers`〜`maxPlayers`の範囲判定（要件定義書v1.1 12章）。

---

### 3.8 MatchCandidate（マッチング候補）

```
PK:      COMMUNITY#{communityId}
SK:      CANDIDATE#{createdAt}#{candidateId}
GSI2PK:  CANDIDATE#{candidateId}
GSI2SK:  METADATA
```

| 属性 | 型 | 説明 |
|---|---|---|
| templateId | S | 参照元テンプレート |
| score | N | スコア |
| members | SS | メンバーuserId一覧 |
| reasons | SS | スコア理由（例：全員予定一致 等） |
| status | S | PENDING / CONFIRMED / DISCARDED |
| createdAt | S | ISO8601 |

**アクセスパターン**
- コミュニティの候補一覧：`PK=COMMUNITY#{id}, SK begins_with CANDIDATE#`
- 候補詳細（communityId不明の状態でcandidateIdのみ既知）：GSI2

> F-401〜F-404、API設計書6.1〜6.3に対応。
>
> **[v1.3補足]** 候補生成時、メンバー1人ごとに3.11bの`CandidateMember`レコードも同時に書き込む（ダブルブッキング検知・公平性指標用）。

---

### 3.9 Place（会場）**[v1.1: Locationから改称・グローバルエンティティ化]**

```
PK:      PLACE#{placeId}
SK:      METADATA
GSI1PK:  COMMUNITY#{communityId}   ※ownerType=COMMUNITYの場合のみセット
GSI1SK:  PLACE#{placeId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| name | S | 会場名 |
| address | S | 住所（任意） |
| ownerType | S | COMMUNITY / STORE / OFFICIAL |
| ownerId | S | 持ち主のID（communityId または将来のstoreId） |
| note | S | 補足（例：全自動卓あり） |
| createdAt | S | ISO8601 |

**アクセスパターン**
- 会場詳細取得：`PK=PLACE#{placeId}`（Eventからの参照時はこちらを直接取得）
- コミュニティに紐づく会場一覧（MVPの主用途）：`GSI1PK=COMMUNITY#{communityId}, SK begins_with PLACE#`

> F-107、要件定義書v1.1 18章に対応。
>
> **[v1.1修正]** v1.0では`PK=COMMUNITY#{communityId}, SK=LOCATION#{locationId}`としてコミュニティに閉じた設計だったが、店舗展開時に「1つの店舗が複数コミュニティから会場として使われる」多対多の関係を表現できないため、`PLACE#{placeId}`を主キーとするグローバルエンティティに変更。
>
> - MVP運用（個人宅・フリー雀荘等）では`ownerType=COMMUNITY, ownerId={communityId}`として登録すれば、GSI1経由で今まで通り「コミュニティに紐づく会場一覧」として取得できるため、UI・API側の挙動は変わらない。
> - 将来、店舗（STORE型）が登場した場合は`ownerType=STORE, ownerId={storeId}`として同じPlaceテーブルに追加するだけで良く、複数コミュニティから同一店舗を参照できるようになる。店舗情報（住所変更等）の更新も1箇所で完結する。
> - `Event.locationId`は引き続き`placeId`を指す形で変更不要。

---

### 3.10 Event（イベント）

```
PK:      EVENT#{eventId}
SK:      METADATA
GSI1PK:  COMMUNITY#{communityId}
GSI1SK:  EVENT#{startTime}#{eventId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| templateId | S | 元テンプレート |
| candidateId | S | 元候補 |
| locationId | S | 会場ID（Place参照、null可）[v1.1: 参照先をPlaceに変更] |
| locationNote | S | 会場自由記述 |
| status | S | DRAFT/OPEN/MATCHING/PENDING_APPROVAL/CONFIRMED/IN_PROGRESS/COMPLETED/CANCELLED |
| startTime / endTime | S | ISO8601 |
| createdAt | S | ISO8601 |

**アクセスパターン**
- イベント詳細取得：PK直接（`GetItem`）
- コミュニティのイベント一覧（開催日時順）：GSI1

> F-501〜F-504、要件定義書14章のライフサイクルに対応。EventIdをPKにすることで、Participant/CancelRequest/GameSession等の子エンティティを同一PK配下にぶら下げられる（次項参照）。

---

### 3.11 Participant（参加者）**[v1.3: GSI1SKを修正]**

```
PK:      EVENT#{eventId}
SK:      PARTICIPANT#{userId}
GSI1PK:  USER#{userId}
GSI1SK:  PARTICIPANT#{startTime}#{eventId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| status | S | CONFIRMED / CANCEL_REQUESTED / CANCELLED |
| startTime / endTime | S | ISO8601（Eventの日時をコピー。ダブルブッキング検知の時間範囲クエリ用） |
| joinedAt | S | ISO8601 |

**アクセスパターン**
- ユーザーの確定済み参加イベントを時間帯で横断検索（ダブルブッキング検知用）：`GSI1PK=USER#{userId}, GSI1SK between PARTICIPANT#{from} and PARTICIPANT#{to}`

> F-502（承認時に一括作成）、9.1に対応。
>
> **[v1.3修正]** GSI1SKを`PARTICIPANT#{eventId}`から`PARTICIPANT#{startTime}#{eventId}`に変更。イベント確定処理（EventLambda）で、確定予定の参加者が既に別の確定済みイベントと時間が重複していないかを、GSI1のレンジクエリ1発でチェックできるようにするため（ダブルブッキング防止、Lambda設計書v1.1 7.2参照）。

---

### 3.11b CandidateMember（候補メンバー横断インデックス）**[v1.3新規]**

```
PK:      COMMUNITY#{communityId}
SK:      CANDIDATE#{candidateId}#MEMBER#{userId}
GSI1PK:  USER#{userId}
GSI1SK:  CANDIDATE#{startTime}#{candidateId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| candidateId | S | 参照元MatchCandidate |
| startTime / endTime | S | ISO8601（候補の日時をコピー） |
| status | S | PENDING / CONFIRMED / DISCARDED（MatchCandidate.statusのミラー） |
| conflictWarning | BOOL | 他の確定イベントと時間重複が検知された場合にtrue |
| createdAt | S | ISO8601 |

**アクセスパターン**
- あるユーザーが含まれる、時間帯が重なるPENDING候補の横断検索（衝突検知用）：`GSI1PK=USER#{userId}, GSI1SK between CANDIDATE#{from} and CANDIDATE#{to}`
- あるユーザーの「候補には入ったが確定しなかった」回数の集計（公平性指標）：GSI1を期間指定でQueryし、`status != CONFIRMED`の件数をカウント

> **[v1.3新規]** MatchingLambdaが候補生成（F-401）のたびに、候補メンバー1人ごとに1レコード書き込む。2つの用途を兼ねる：
> 1. **ダブルブッキング事後検知**：あるイベントが確定した際、同じユーザーを含む他コミュニティのPENDING候補に`conflictWarning=true`を立て、該当コミュニティの管理者へ通知する
> 2. **公平性指標**：候補一覧画面（S-12）で「このメンバーは直近◯回候補に入ったが確定しなかった」を表示するための集計データ
>
> いずれもシステムが自動で除外・優先操作は行わず、**管理者への気づき情報として表示するのみ**（要件定義書17章の設計思想に準拠）。

---

### 3.12 CancelRequest（個人キャンセル申請）**[v1.1: 個人/全体を分離]**

```
PK:   EVENT#{eventId}
SK:   CANCELREQ#{userId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| reason | S | 理由 |
| status | S | PENDING / APPROVED / REJECTED |
| requestedAt | S | ISO8601 |
| approvedBy | S | 承認した管理者userId |
| approvedAt | S | ISO8601 |

**冪等性の担保**：承認処理は `ConditionExpression: status = PENDING` を付けたUpdateItemで実施し、二重承認（連打）を防ぐ（F-602の考慮点）。

> F-601／F-602に対応。イベント全体の中止（F-605）はEventのstatusをCANCELLEDに更新するのみで、CancelRequestとは別テーブル項目である点に注意（v1.0で混同していた箇所）。

---

### 3.13 GameSession / GameResult

```
GameSession
PK:   EVENT#{eventId}
SK:   SESSION#{sessionNo}

GameResult
PK:      EVENT#{eventId}
SK:      SESSION#{sessionNo}#RESULT#{userId}
GSI1PK:  USER#{userId}
GSI1SK:  COMMUNITY#{communityId}#{playedAt}
```

| 属性(GameSession) | 型 | 説明 |
|---|---|---|
| gameType | S | ゲーム種別 |
| playedAt | S | 実施日時 |

| 属性(GameResult) | 型 | 説明 |
|---|---|---|
| rank | N | 着順 |
| score | N | 点数 |
| rankPoints | N | 順位点 |
| playedAt | S | ISO8601（GSI1SKと同期） |

**アクセスパターン**
- イベント内の全セッション・結果取得：`PK=EVENT#{id}, SK begins_with SESSION#`
- ユーザーの特定コミュニティ内の成績一覧：`GSI1PK=USER#{userId}, GSI1SK begins_with COMMUNITY#{communityId}`（API設計書10.2の権限方針「同一コミュニティ内でのみ閲覧可」をキー設計レベルで担保）

> F-801〜F-804に対応。ゲーム固有結果（ポーカーのBuy-in等）は`extra`属性（Map型）に格納し、基本キー構造は変えずに拡張する（F-902の設計方針）。

---

### 3.14 Notification

```
PK:   USER#{userId}
SK:   NOTIF#{createdAt}#{notificationId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| type | S | CANDIDATE_GENERATED / APPROVAL_REQUESTED / CONFIRMED / CANCELLED / SUBSTITUTE 等 |
| message | S | 本文 |
| read | BOOL | 既読フラグ |
| relatedEventId | S | 関連イベントID |
| createdAt | S | ISO8601 |

> F-701／F-702に対応。ユーザーが直接の主体なのでPKをUSER#にし、GSI不要。

---

### 3.15 OperationLog（操作ログ）**[操作ログ設計書と統合・GSI追加]**

```
PK:      LOG#{communityId}
SK:      {createdAt}#{logId}
GSI1PK:  USER#{userId}
GSI1SK:  LOG#{createdAt}#{logId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| action | S | CREATE_COMMUNITY等 |
| targetType | S | 対象エンティティ種別 |
| targetId | S | 対象ID |
| before | M | 変更前データ |
| after | M | 変更後データ |
| ttl | N | DynamoDB TTL用UNIXタイムスタンプ [新規] |
| createdAt | S | ISO8601（ミリ秒・UTC固定） |

> **[v1.1修正]** `createdAt`はミリ秒精度＋UTC（例：`2026-07-07T13:30:00.123Z`）に統一し、SK内でのソート順の一貫性を担保する。`logId`はULID等の時系列ソート可能なIDを採用し、同一ミリ秒での衝突を回避する。
>
> **GSI1追加**により「ユーザー単位の操作履歴取得」（API設計書12.2）に対応。
>
> **TTL追加**：運用上重要な操作（イベント承認・キャンセル等）は長期保持したいが、全ログを無期限保持するとコストが増えるため、`ttl`属性を設定し例えば2年経過後に自動削除する。将来の相性分析・信頼スコア分析（12章）に使うデータは、TTLで消える前に**S3へエクスポート**（DynamoDB to S3 Export機能）しAthenaで分析する構成にすることを推奨（17章の分析基盤と接続）。

**ログイン等コミュニティに紐づかない操作の扱い**：`communityId`が存在しない操作（`LOGIN`、`UPDATE_PROFILE`等）は `PK=LOG#GLOBAL#{userId}` とし、コミュニティ単位の集計対象から除外する。

---

### 3.16 EventStatusHistory（イベント状態遷移履歴）

```
PK:   EVENT#{eventId}
SK:   STATUS#{createdAt}
```

| 属性 | 型 | 説明 |
|---|---|---|
| fromStatus | S | 遷移前状態 |
| toStatus | S | 遷移後状態 |
| changedBy | S | SYSTEM または userId |
| createdAt | S | ISO8601 |

> 操作ログ設計書9章で「OperationLogとは別に履歴管理する」とされていた設計を具体化。EventBridgeの状態遷移イベント発火のたびに1レコード追記する。

---

### 3.17 PushSubscription（プッシュ通知購読情報） **[v1.4新規]**

```
PK:   USER#{userId}
SK:   PUSHSUB#{endpointHash}
```

| 属性 | 型 | 説明 |
|---|---|---|
| endpoint | S | ブラウザのPush ServiceエンドポイントURL |
| p256dh | S | 購読者公開鍵（Web Push暗号化用） |
| auth | S | 認証シークレット（Web Push暗号化用） |
| userAgent | S | 端末識別用の参考情報（任意） |
| createdAt | S | ISO8601 |

**アクセスパターン**
- あるユーザーの全端末購読情報取得：`PK=USER#{userId}, SK begins_with PUSHSUB#`
- 特定端末の購読解除：`PK=USER#{userId}, SK=PUSHSUB#{endpointHash}` を直接`DeleteItem`

> **[v1.4新規]** F-703／F-704（機能要件書v1.3）に対応。`endpointHash`はendpoint文字列のハッシュ値（例：SHA-256）とし、同一端末の再登録（購読更新）が自然に`PutItem`で上書きされ、購読解除もクライアントが送る`endpoint`から同じハッシュを計算して`DeleteItem`するだけで完結するようにする（別途Query不要）。GSIは不要（通知送信は常にuserId起点で発生するため、`USER#{userId}`パーティション直下で完結する）。

---

### 3.18 AvailabilityRequest（空き予定提出リクエスト） **[v1.4新規]**

```
PK:   COMMUNITY#{communityId}
SK:   AVAILREQ#{requestId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| targetPeriodStart | S | 提出してほしい空き予定の対象期間（開始）ISO8601 |
| targetPeriodEnd | S | 対象期間（終了）ISO8601 |
| deadline | S | 提出期限 ISO8601 |
| targetScope | S | ALL / SPECIFIED |
| targetUserIds | SS | targetScope=SPECIFIEDの場合の対象userId一覧（ALLの場合は省略） |
| message | S | 任意のメッセージ |
| createdBy | S | 依頼した管理者userId |
| createdAt | S | ISO8601 |

**アクセスパターン**
- コミュニティのリクエスト一覧：`PK=COMMUNITY#{id}, SK begins_with AVAILREQ#`
- リクエスト詳細：`PK=COMMUNITY#{id}, SK=AVAILREQ#{requestId}`（`GetItem`）
- 未提出メンバー確認：対象メンバー一覧（`targetScope=ALL`ならMembership一覧、`SPECIFIED`なら`targetUserIds`）を求めた上で、メンバーごとにAvailabilityの既存GSI1（`GSI1PK=USER#{userId}, GSI1SK between AVAIL#{targetPeriodStart}~{targetPeriodEnd}`）をQueryし、0件のユーザーを「未提出」とする

> **[v1.4新規]** F-205／F-206（機能要件書v1.3）に対応。新規GSIは追加しない。「未提出者確認」は対象メンバー数分のQueryを都度実行する軽量な実装とする（コミュニティ規模10〜30人を前提とすれば許容範囲。将来の事前集計化は8章の未決事項として扱う）。リクエスト作成時の対象メンバーへの通知は、他の通知と同様にEventBridge経由（`AvailabilityRequestCreated`、Lambda設計書v1.2参照）でNotificationLambdaが受け取り作成する。

---

## 4. アクセスパターン一覧（総括）

| No | アクセスパターン | 使用キー |
|---|---|---|
| 1 | ユーザープロフィール取得 | PK=USER#{id}, SK=PROFILE |
| 2 | コミュニティのメンバー一覧 | PK=COMMUNITY#{id}, SK begins_with MEMBER# |
| 3 | ユーザーの所属コミュニティ一覧 | GSI1PK=USER#{id}, SK begins_with COMMUNITY# |
| 4 | 招待URLからコミュニティ特定 | PK=INVITE#{token} |
| 5 | コミュニティの未処理参加リクエスト | PK=COMMUNITY#{id}, SK begins_with JOINREQ#, status=PENDING |
| 6 | コミュニティ内・期間指定の空き予定横断取得（マッチング処理F-401内部専用。相互非公開型マッチングの原則上、公開APIとしては提供しない）[v1.5] | PK=COMMUNITY#{id}, SK between AVAIL#{from}~{to} |
| 7 | ユーザー自身の空き予定一覧 | GSI1PK=USER#{id}, SK begins_with AVAIL# |
| 8 | コミュニティの開催条件一覧 | PK=COMMUNITY#{id}, SK begins_with TEMPLATE# |
| 9 | コミュニティの候補一覧 | PK=COMMUNITY#{id}, SK begins_with CANDIDATE# |
| 10 | 候補詳細（community不明） | GSI2PK=CANDIDATE#{id} |
| 11 | コミュニティの会場一覧（Place） | GSI1PK=COMMUNITY#{id}, SK begins_with PLACE# |
| 11b | 会場詳細取得（Place） | PK=PLACE#{placeId} |
| 12 | イベント詳細 | PK=EVENT#{id}, SK=METADATA |
| 13 | コミュニティのイベント一覧 | GSI1PK=COMMUNITY#{id}, SK begins_with EVENT# |
| 14 | イベントの参加者一覧 | PK=EVENT#{id}, SK begins_with PARTICIPANT# |
| 15 | ユーザーの参加イベント一覧・時間帯検索（ダブルブッキング検知） | GSI1PK=USER#{id}, SK begins_with/between PARTICIPANT#{time} |
| 16 | イベントのキャンセル申請一覧 | PK=EVENT#{id}, SK begins_with CANCELREQ# |
| 17 | イベントのセッション・結果一覧 | PK=EVENT#{id}, SK begins_with SESSION# |
| 18 | ユーザーのコミュニティ内成績 | GSI1PK=USER#{id}, SK begins_with COMMUNITY#{communityId} |
| 19 | ユーザーの通知一覧 | PK=USER#{id}, SK begins_with NOTIF# |
| 20 | コミュニティの操作ログ | PK=LOG#{communityId} |
| 21 | ユーザーの操作ログ | GSI1PK=USER#{id}, SK begins_with LOG# |
| 22 | イベントの状態遷移履歴 | PK=EVENT#{id}, SK begins_with STATUS# |
| 23 | あるユーザーが含まれる時間帯重複PENDING候補の横断検索（衝突検知） [v1.3] | GSI1PK=USER#{id}, SK between CANDIDATE#{from}~{to} |
| 24 | あるユーザーの「候補止まり」回数集計（公平性指標） [v1.3] | GSI1PK=USER#{id}, SK begins_with CANDIDATE#、期間指定＋status絞り込み |
| 25 | ユーザーの全プッシュ通知購読情報 [v1.4] | PK=USER#{id}, SK begins_with PUSHSUB# |
| 26 | コミュニティの空き予定提出リクエスト一覧 [v1.4] | PK=COMMUNITY#{id}, SK begins_with AVAILREQ# |
| 27 | 未提出メンバー確認（対象期間内の空き予定有無判定。アクセスパターン7の応用） [v1.4] | GSI1PK=USER#{id}, SK between AVAIL#{targetPeriodStart}~{targetPeriodEnd} |

---

## 5. トランザクション・冪等性の設計方針

| ケース | 対応 |
|---|---|
| 参加リクエスト承認（JoinRequest更新＋Membership作成） | `TransactWriteItems`で同時コミット |
| イベント承認（Event状態更新＋Participant一括作成） | `TransactWriteItems` |
| キャンセル承認の二重実行防止 | `UpdateItem`に`ConditionExpression: status = PENDING`を付与 |
| OWNER変更（Membership.roleの入れ替え） | `TransactWriteItems`で「新OWNERのrole更新」と「元OWNERのrole=MEMBER更新」を同時に行い、途中失敗による権限不整合を防ぐ |
| **イベント承認時のダブルブッキング事前チェック** [v1.3] | Participant一括作成の**前**に、候補メンバー全員分についてGSI1（`PARTICIPANT#{startTime}#{eventId}`）を時間範囲でQueryし、既存の確定済みイベントと重複がないか確認。重複があれば`TransactWriteItems`を実行せず`PARTICIPANT_SCHEDULE_CONFLICT`エラーで中断する |

---

## 6. 容量・コスト設計メモ

- コミュニティ単位でPKが分散するため、ホットパーティション（特定PKへのアクセス集中）は起きにくい規模感（10〜30人×コミュニティ単位）
- オンデマンドモードにより、個人開発フェーズでの過剰プロビジョニングを回避
- OperationLogにTTLを設定することで長期的なストレージコストを抑制
- 将来の分析基盤（AWSシステム構成設計書17章）は、DynamoDBに全データを持たせ続けるのではなく、S3 Data Lake + Athenaへのエクスポートを前提とする

---

## 7. 各設計書との対応関係

| 本書のエンティティ | 対応する機能要件書 | 対応するAPI |
|---|---|---|
| User | F-001〜F-003 | 3.1, 3.2 |
| Community / Membership | F-101, F-104〜F-106 | 4.1, 4.2, 4.5 |
| Invite / JoinRequest | F-102, F-103, F-104b, F-104c | 4.3, 4.4, 4.4b, 4.4c |
| Availability | F-201〜F-204 | 5.1〜5.4 |
| EventTemplate | F-301〜F-304 | 7.1, 7.2 |
| MatchCandidate / CandidateMember | F-401〜F-404 | 6.1〜6.3 |
| Place | F-107 | 8.5, 8.6 |
| Event | F-501〜F-504 | 8.1, 8.2 |
| Participant | F-502, ダブルブッキング防止（Lambda設計書v1.1 7.2） | 9.1, 8.3 |
| CancelRequest | F-601, F-602 | 9.2, 9.3 |
| GameSession / GameResult | F-801〜F-804 | 10.1, 10.2 |
| Notification | F-701, F-702 | 11.1, 11.2 |
| OperationLog | F-1301, F-1302 | 12.1, 12.2 |
| EventStatusHistory | 要件定義書14章 | （内部利用、API非公開） |
| PushSubscription [v1.4] | F-703, F-704 | 11.3, 11.4 |
| AvailabilityRequest [v1.4] | F-205, F-206 | 5.5〜5.7 |

---

## 8. 未決事項・次の検討ポイント

1. **F-603欠員補充（Phase2）のデータ構造**：候補検索結果の一時保存が必要になった場合、`SUBSTITUTE#{userId}`のようなSKを追加する形で拡張予定（実装段階で決定）
2. **フロントエンド構成（SPA/SSR）確定後**、S3/CloudFrontのキャッシュ無効化パターンとAPIレスポンスの整合を再確認
3. **信頼スコア・NG設定（Phase2）**：User配下に`TRUST#{communityId}`、`NG#{userId}#{targetUserId}`のような項目追加を想定。マッチング処理（F-403）のスコア計算関数を先に分離しておくと拡張がスムーズ
4. **店舗展開時の権限マトリクス**：`STORE_ADMIN`／`STAFF`ロールの具体的な操作範囲は、STORE型コミュニティの機能要件が固まった段階で別途定義する（スキーマ上は対応済み）
5. **店舗（STORE）自体のエンティティ化**：現状Placeの`ownerId`は`communityId`のみを想定しているが、店舗展開時に「Store」を独立したエンティティ（`PK=STORE#{storeId}`）として持つかどうかは、店舗アカウント機能の要件が固まってから決定する
6. **複数コミュニティ横断の優先度比較（Phase3）**：`priorityWeight`/`desiredFrequency`属性は確保済みだが、実際にどう使うか（単純ソートか、スコアへの重み付けか）は満足度の定義が固まってから設計する
7. **公平性指標（3.11b CandidateMember）の集計をどのLambdaが担うか**：候補一覧取得時にMatchingLambdaが都度計算するか、非同期で事前集計しておくかは、コミュニティ規模が大きくなった際のクエリコストを見て判断する
8. **AvailabilityRequestの未提出者確認のスケーリング** [v1.4]：対象メンバー数分のQueryを都度実行する軽量実装（3.18参照）はコミュニティ規模10〜30人であれば十分だが、規模が大きくなった場合は提出済みユーザーIDのSetをAvailabilityRequest側にキャッシュする等の事前集計化を検討する

---

## 9. v1.0 → v1.1 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | Communityに`communityType`（PERSONAL/STORE/OFFICIAL）属性を追加 | 将来の店舗展開に備えた最小限の布石 |
| 2 | Location（3.9）を廃止し、Place（`PK=PLACE#{placeId}`のグローバルエンティティ、GSI1でコミュニティ紐付け）に置き換え | 1つの会場が複数コミュニティから参照される店舗展開の実態に対応するため |
| 3 | アクセスパターン一覧・対応関係表のLocation関連記述をPlaceに更新 | 整合性維持 |
| 4 | 権限（Membership.role）はスキーマ変更なしと明記 | role列が文字列型のため将来値追加のみで対応可能 |
| 5 | 未決事項に店舗展開関連の検討ポイントを追加 | 権限マトリクス・Storeエンティティ化は別途詳細設計が必要なため |

---

## 10. v1.1 → v1.2 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | JoinRequestに`message`（申請時の一言メッセージ、任意）属性を追加 | F-103参加リクエスト承認時、ニックネームのみでは管理者の判断材料が不足するため |
| 2 | 参加リクエスト一覧取得時、Userエンティティ（bio/gameTypes/beginnerOk）を合わせて返却する方針を明記 | 同上。招待URLは個別発行せずコミュニティ単位のまま維持する判断もあわせて記載 |

---

## 11. v1.2 → v1.3 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | Membershipに`priorityWeight`/`desiredFrequency`予約属性を追加（Phase3未使用） | 複数コミュニティ横断の優先度比較機能に備えた最小限の布石 |
| 2 | ParticipantのGSI1SKを`PARTICIPANT#{eventId}`から`PARTICIPANT#{startTime}#{eventId}`に変更 | イベント確定時のダブルブッキング事前チェックを時間範囲クエリ1発で実現するため |
| 3 | CandidateMember（3.11b）を新規追加 | ①候補確定後の事後衝突検知、②「候補止まり」の公平性指標表示、の2用途を1エンティティで実現 |
| 4 | トランザクション設計方針にイベント承認時のダブルブッキング事前チェックを追加 | 実害の防止を確定処理の直前でハードチェックする方針を明記 |
| 5 | 対応関係表・アクセスパターン一覧を更新 | 整合性維持 |

---

## 12. v1.3 → v1.4 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | PushSubscription（3.17）を新規追加 | 要件定義書v1.3 27章：PWA化とWebプッシュ通知（F-703/F-704） |
| 2 | AvailabilityRequest（3.18）を新規追加 | 要件定義書v1.3 28章：管理者からの空き予定提出リクエスト（F-205/F-206） |
| 3 | アクセスパターン一覧に25〜27を追加 | 上記2エンティティの整合 |
| 4 | 対応関係表に上記2エンティティを追加 | 整合性維持 |
| 5 | 未決事項にAvailabilityRequestの未提出者確認のスケーリングを追加 | 将来のコミュニティ規模拡大時の検討事項として明記 |

---

## 13. v1.4 → v1.5 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.6 Availabilityのアクセスパターンについて、コミュニティ横断クエリがマッチング処理（F-401）内部専用であり公開APIとして提供しないことを明記 | 要件定義書v1.4 29章：相互非公開型マッチング（コア設計原則）をデータ構造レベルで担保する旨の記録 |
| 2 | 4章アクセスパターン一覧No.6に同様の注記を追加 | 上記との整合 |
