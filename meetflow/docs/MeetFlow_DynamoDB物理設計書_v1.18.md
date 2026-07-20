# MeetFlow DynamoDB 物理テーブル設計書 v1.18

> 要件定義書v1.1・機能要件書v1.1・API設計書v1.1・操作ログ設計書v1.0・AWSシステム構成設計書v1.0を踏まえて設計。
> v1.0→v1.1、v1.1→v1.2、v1.2→v1.3、v1.3→v1.4、v1.4→v1.5、…、v1.10→v1.11の変更点はそれぞれ本文中と末尾の変更点サマリを参照。

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
| GSI2（ByAltId） | GSI2PK | GSI2SK | コミュニティIDを介さない直接ID検索（候補詳細など）。**[v1.12追加]** 種別横断の一覧化（例：全フィードバック一覧）にも、GSI2PKへ種別を表す固定文字列を入れる形で流用する（3.19/3.20参照） |

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
| **frequencyLimitCount** | **N** | **（任意）ゲームジャンル単位の参加頻度上限回数。`frequencyLimitPeriod`とセットで設定・解除する [v1.9追加]** |
| **frequencyLimitPeriod** | **S** | **（任意）上限回数の集計期間。`WEEK` / `MONTH` [v1.9追加]** |
| **autoApprove** | **BOOL** | **（任意、既定false）イベント仮確定後の参加承認を以降自動で行うかどうかの全体デフォルト [v1.10追加]** |
| createdAt | S | ISO8601 |

> F-001/F-002/F-003 に対応。Cognito自体にはメール・パスワードのみ持たせ、プロフィールはDynamoDB側で管理する。
>
> **[v1.9追加]** `frequencyLimitCount`/`frequencyLimitPeriod`は要件定義書v1.6 30章「参加頻度上限」に対応する全体デフォルト設定。3.3 Membershipの同名属性（コミュニティ単位の任意上書き）が優先され、未設定の場合にこちらへフォールバックする（`displayName`と同じ解決順）。Phase3予約属性の`desiredFrequency`（3.3参照）とは別物で、あちらは複数コミュニティ横断の優先度比較・ランキング表示専用（マッチングのスコア計算には使わない）なのに対し、こちらは実際にF-403のスコアリングに反映される。
>
> **[v1.10追加]** `autoApprove`はF-502b「イベント確定フローの全員承認」（要件定義書v1.7 §17、Issue #10）に対応する全体デフォルト設定。3.3 Membershipの同名属性（コミュニティ単位の任意上書き）が優先され、未設定の場合にこちらへフォールバックする（`frequencyLimitCount`/`displayName`と同じ解決順）。自動承認は本人が事前に与えた明示的な同意を都度操作なしに反映するだけであり、システムが自律的にイベントを確定するわけではない（要件定義書v1.7 §17/§19参照）。

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
| **themeColor** | **S** | **（任意）コミュニティのテーマカラー。`#RRGGBB`形式の7文字hexカラーコード（例："#6366F1"）。未設定時はアプリの既定色にフォールバックする [v1.7追加]** |
| createdAt | S | ISO8601 |

> F-101 に対応。
>
> **[v1.1追加]** 将来の店舗展開（フリー雀荘・公式コミュニティ等）を見据え、`communityType`属性を追加。MVPでは全件`PERSONAL`固定で保存する。値を文字列として持つだけでキー構造への影響はなく、将来STORE/OFFICIAL向けの機能分岐（公開ディレクトリ掲載、決済連携等）をアプリ層で追加する際の起点にする。
>
> **権限（Membership.role）については、スキーマ変更は不要**。`role`は元々文字列（S型）であり、将来`STORE_ADMIN`や`STAFF`のような値を追加してもテーブル構造上の制約はない。店舗展開が具体化した段階でアプリケーション層のバリデーション・権限マッピングを設計すれば十分なため、本書ではスキーマ上の対応のみ記載し、権限マトリクスの詳細設計は見送る。
>
> **[v1.7追加]** コミュニティごとの見た目カスタマイズ（アイコン・テーマ設定）のうち、まずテーマカラーのみを対応する。アイコン画像のアップロードはS3/CloudFront等の追加インフラを要するためPhase2以降で別途検討し、本バージョンでは既存の`Community`METADATAアイテムへの属性追加のみで完結する軽量な実装（カラーコードの文字列1つ）に留める。キー構造（PK/SK/GSI）への影響はない。

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
| **displayName** | **S** | **（任意）コミュニティごとの表示名。未設定時はUser.nicknameにフォールバックして表示する [v1.6追加]** |
| **sortOrder** | **N** | **（任意）コミュニティ一覧の表示順。ユーザーごとに並び替えAPIが0始まりの連番で書き込む。未設定（新規参加直後等）は一覧取得時に末尾へ回す [v1.8追加]** |
| **frequencyLimitCount** | **N** | **（任意）このコミュニティにおける参加頻度上限回数。未設定時はUser側の全体デフォルトにフォールバック。`frequencyLimitPeriod`とセットで設定・解除する [v1.9追加]** |
| **frequencyLimitPeriod** | **S** | **（任意）上限回数の集計期間。`WEEK` / `MONTH` [v1.9追加]** |
| **autoApprove** | **BOOL** | **（任意）このコミュニティにおける自動承認設定。未設定時はUser側の全体デフォルトにフォールバック [v1.10追加]** |

**アクセスパターン**
- コミュニティのメンバー一覧：`PK=COMMUNITY#{id}, SK begins_with MEMBER#`
- ユーザーの所属コミュニティ一覧：`GSI1PK=USER#{userId}, GSI1SK begins_with COMMUNITY#`
- **[v1.6追加]** 表示名重複チェック：コミュニティのメンバー一覧を取得し（上記と同じクエリ）、各メンバーの実効表示名（`displayName`が未設定のメンバーはUser.nicknameを都度`GetItem`）をアプリケーション側で突き合わせる。コミュニティ規模（10〜30人程度）では軽い処理のため、専用GSIは追加しない。
- **[v1.8追加]** コミュニティ一覧の表示順並び替え：上記のユーザーの所属コミュニティ一覧クエリで取得した各Membership行に対し、`sortOrder`を書き込む（`GetItem`/`UpdateItem`の組み合わせ。専用GSIは追加しない）。
- **[v1.9追加]** 実効参加頻度上限の解決：`GetItem`でMembership行（`frequencyLimitCount`/`frequencyLimitPeriod`）とUser行（同名の全体デフォルト）を取得し、Membership側の値があれば優先、なければUser側にフォールバックする（`displayName`の解決と同じ形）。専用GSIは追加しない。
- **[v1.10追加]** 実効自動承認設定の解決：`GetItem`でMembership行（`autoApprove`）とUser行（同名の全体デフォルト）を取得し、Membership側の値があれば優先、なければUser側にフォールバックする（`frequencyLimitCount`と同じ形）。イベント仮確定処理（EventLambda）が候補メンバーごとに呼ぶ。専用GSIは追加しない。

> F-104, F-105, F-106（OWNER変更時は該当Membershipのroleを書き換え。元OWNERはrole=MEMBERに更新 [v1.1]）、F-108（コミュニティごとの表示名 [v1.6追加]）、F-109（参加頻度上限のコミュニティ単位の上書き [v1.9追加]）、F-109b（自動承認のコミュニティ単位の上書き [v1.10追加]）に対応。
>
> **[v1.3追加]** `priorityWeight`/`desiredFrequency`はPhase3（複数コミュニティ横断の優先度・満足度比較機能）向けの予約属性。今は値を使わないが、後からの一括マイグレーションを避けるため属性だけ先に確保しておく。
>
> **[v1.6追加]** `displayName`はコミュニティ単位のMembershipエンティティへの属性追加のみで、PK/SK/GSI1の構造には一切手を加えていない。表示側の解決ロジック（`displayName`優先、無ければUser.nicknameにフォールバック）はLambda層（`meetflow_common.display_name`）に集約し、DynamoDB設計はシンプルな任意属性として持つのみに留める。
>
> **[v1.8追加]** `sortOrder`も`displayName`と同様、PK/SK/GSI1の構造を変えない任意属性として追加した。並び替えAPI（API設計書v1.10 §4.2d）がユーザーの所属コミュニティ一覧クエリの結果に対し、渡された順序どおり0,1,2...を書き込む。専用GSIを持たないため、並び替え自体のクエリコストは所属コミュニティ数（10〜数十件程度を想定）に比例するのみで軽微。
>
> **[v1.9追加]** `frequencyLimitCount`/`frequencyLimitPeriod`も`displayName`と同じ「Membership優先・User側フォールバック」のパターンを踏襲する任意属性で、PK/SK/GSI1の構造には影響しない。解決ロジックはLambda層（`meetflow_common.frequency_limit`）に集約する。3.1 Userの同名属性の注記も参照。
>
> **[v1.10追加]** `autoApprove`も同じ「Membership優先・User側フォールバック」のパターンを踏襲する任意属性で、PK/SK/GSI1の構造には影響しない。解決ロジックはLambda層（`meetflow_common.auto_approve`）に集約する。3.1 Userの同名属性の注記も参照。

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
| createdByRole | S | 発行時点の発行者ロール（OWNER/ADMIN/MEMBER）**[v1.11追加]** |
| revoked | BOOL | 無効化フラグ |
| expiresAt | S | 有効期限（将来対応、MVPではnull可） |
| createdAt | S | ISO8601 |

> トークン自体がPKなので、招待URLアクセス時は1回のGetItemで完結する。F-102に対応。
>
> **[v1.11]** `createdByRole`は招待URLの発行がOWNER/ADMIN限定からコミュニティの全メンバーに開放されたこと（Issue #22）に伴い追加。発行者がMEMBERロールだった招待は、`join_via_invite`（コミュニティの`memberApprovalRequired`設定に関わらず）強制的にJoinRequest経由の承認制になる。発行後に発行者本人のロールが変わっても、この値は発行時点のまま固定される（スナップショット）。

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
>
> **[v1.8追加]** `status=CONFIRMED`はイベント化（Event作成）による「使用済み」を表す転用であり、イベント全体が中止（API設計書v1.10 §8.4）された場合は`PENDING`へ戻す。これを行わないと、同一候補から再度イベントを作成しようとした際に恒久的に`409 CANDIDATE_ALREADY_USED`となり再利用できない不具合になる。あわせて3.11bの`CandidateMember`各行の`status`も同時に`PENDING`へ戻す。

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
| status | S | DRAFT/OPEN/MATCHING/PENDING_APPROVAL/**AWAITING_MEMBER_APPROVAL[v1.10追加]**/CONFIRMED/IN_PROGRESS/COMPLETED/CANCELLED |
| startTime / endTime | S | ISO8601 |
| createdAt | S | ISO8601 |
| **deletedAvailabilitySnapshot** | **List\<Map\>** | **（任意）confirm_event実行時に削除した候補メンバーのAvailability行の完全なスナップショット（PK/SK/GSI1PK/GSI1SK/userId/endTime/comment/createdAt/gameTypesを保持）。cancel_event実行時にそのまま書き戻して復元し、復元後は本属性自体をREMOVEする（恒久的な保持はしない）[v1.17追加]** |

**アクセスパターン**
- イベント詳細取得：PK直接（`GetItem`）
- コミュニティのイベント一覧（開催日時順）：GSI1

> F-501〜F-504、要件定義書14章のライフサイクルに対応。EventIdをPKにすることで、Participant/CancelRequest/GameSession等の子エンティティを同一PK配下にぶら下げられる（次項参照）。
>
> **[v1.10追加]** `AWAITING_MEMBER_APPROVAL`はF-502b「イベント確定フローの全員承認」（Issue #10）で追加した中間状態。管理者による仮確定（F-502、`PENDING_APPROVAL`→`AWAITING_MEMBER_APPROVAL`）と、参加予定者全員の個別承認完了による本確定（`AWAITING_MEMBER_APPROVAL`→`CONFIRMED`）の間に位置する。候補メンバー全員が自動承認（3.1/3.3の`autoApprove`）ONの場合はこの状態を経由せず直接`CONFIRMED`になる。
>
> **[v1.17追加]** `deletedAvailabilitySnapshot`はIssue #68（イベント中止時にAvailabilityを復元する）に対応する属性。confirm_eventは候補元となった参加者のAvailability（3.9参照）のうち確定イベント時間帯と重複するものを削除するが（Issue #14）、単純にイベントの`[startTime, endTime)`と同じ範囲だけをcancel_event時に復元すると、メンバーが元々登録していたより広い範囲（マッチングは複数メンバーの空き予定の交差区間をイベント時間として採用するため、本人の元の登録はイベント時間帯より広いことがある）を正しく復元できない。そのため、削除対象となった各Availability行の全属性をそのままEvent側に一時保持し、cancel_event時に完全に同一の内容で書き戻す方式とした。書き戻し後は本属性を`REMOVE`し、Eventアイテムに恒久的なコピーを残さない（GameSession等と異なりAvailability自体の正本はあくまでAVAIL#側であるため）。

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
| status | S | CONFIRMED / CANCEL_REQUESTED / CANCELLED / **AWAITING_APPROVAL[v1.10追加]** / **REJECTED[v1.10追加]** |
| startTime / endTime | S | ISO8601（Eventの日時をコピー。ダブルブッキング検知の時間範囲クエリ用） |
| joinedAt | S | ISO8601 |
| **communityGenre** | **S** | **確定時点のCommunity.genreを非正規化してコピーしたもの（3.2参照）[v1.9追加]** |
| **approvedAt** | **S** | **（任意）ISO8601。本人が参加承認した日時（自動承認された場合も含む）[v1.10追加]** |
| **autoApproved** | **BOOL** | **（任意）仮確定時に自動承認によってCONFIRMEDになった場合true [v1.10追加]** |
| **rejectedAt** | **S** | **（任意）ISO8601。本人が参加を辞退した日時 [v1.10追加]** |
| **rejectReason** | **S** | **（任意）辞退理由の自由記述 [v1.10追加]** |

**アクセスパターン**
- ユーザーの確定済み参加イベントを時間帯で横断検索（ダブルブッキング検知用）：`GSI1PK=USER#{userId}, GSI1SK between PARTICIPANT#{from} and PARTICIPANT#{to}`
- **[v1.8追加、v1.15修正]** ユーザー自身が参加する確定イベントのコミュニティ横断一覧（予定タブのカレンダー表示用）：`GSI1PK=USER#{userId}, GSI1SK begins_with PARTICIPANT#`（`status=CONFIRMED`の行のみ抽出し、各行のEventも取得してEvent側の`status`もCONFIRMEDであることを確認する。v1.15でイベント全体中止時にParticipant.statusも`CANCELLED`へ更新するようになったが、それ以前に中止されたイベントの残留データに備え、Event側のstatus確認は二重防御として引き続き行う）
- **[v1.9追加]** 参加頻度上限のコミュニティ横断カウント（マッチング処理F-401内部専用）：`GSI1PK=USER#{userId}, GSI1SK between PARTICIPANT#{periodStart} and PARTICIPANT#{periodEnd}`（集計対象期間はF-109/F-003で設定した週/月）で取得した行のうち、`communityGenre`が候補生成対象コミュニティの`genre`と一致するものだけを件数カウントする。ダブルブッキング検知（1つ目のパターン）と同一インデックスの応用で、新規GSIは追加しない。
- **[v1.10追加]** 全員承認済み判定（F-502b、本確定のトリガー）：`PK=EVENT#{eventId}, SK begins_with PARTICIPANT#`（アクセスパターン14と同一クエリ）で取得した全行の`status`が`CONFIRMED`であるかを判定する。1件でも`AWAITING_APPROVAL`/`REJECTED`が残っていれば本確定しない。新規GSIは追加しない。

> F-502（承認時に一括作成）、9.1に対応。
>
> **[v1.3修正]** GSI1SKを`PARTICIPANT#{eventId}`から`PARTICIPANT#{startTime}#{eventId}`に変更。イベント確定処理（EventLambda）で、確定予定の参加者が既に別の確定済みイベントと時間が重複していないかを、GSI1のレンジクエリ1発でチェックできるようにするため（ダブルブッキング防止、Lambda設計書v1.1 7.2参照）。
>
> **[v1.8追加]** 上記のGSI1レンジクエリは元々ダブルブッキング検知専用だったが、同じインデックスがユーザー横断の確定イベント一覧取得（API設計書v1.10 §8.7b）にもそのまま流用できるため、新規GSIは追加していない。この横断取得は自分自身の確定予定のみを対象とし、他メンバーの空き予定を公開するものではないため、相互非公開型マッチング（要件定義書v1.5 29章）の原則には抵触しない。
>
> **[v1.9追加]** `communityGenre`はイベント確定処理（F-502、EventLambda）でCommunity METADATA（3.2）の`genre`を`GetItem`で取得しParticipant作成時にコピーする。これにより参加頻度上限のジャンル横断カウント（要件定義書v1.6 30.4）がGSI1のレンジクエリ1発＋アプリ側フィルタで完結し、確定イベントごとにEventTemplateへ`GetItem`するN+1呼び出しを避けられる。
>
> **[v1.10追加]** F-502b「イベント確定フローの全員承認」（Issue #10）に対応。仮確定（F-502）時点では、候補メンバーの実効自動承認設定（3.1/3.3の`autoApprove`）に応じて`status`を`CONFIRMED`（`autoApproved=true`）または`AWAITING_APPROVAL`のいずれかで作成する。`AWAITING_APPROVAL`の参加者は`POST /events/{eventId}/participants/me/approve`で`CONFIRMED`（本人による個別承認）、`POST /events/{eventId}/participants/me/reject`で`REJECTED`（明示的な辞退）に遷移する。全員が`CONFIRMED`になった時点でEvent側もAWAITING_MEMBER_APPROVAL→CONFIRMEDへ本確定する（上記アクセスパターン参照）。`REJECTED`は自動でイベント全体を中止しない — 管理者への通知（Notification）のみを行い、中止するかどうかの判断は既存のcancel_event（F-605）に委ねる（要件定義書v1.7 §17/§19のヒューマン・イン・ザ・ループ原則）。

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

### 3.13 GameSession / GameResult / GameResultChip **[v1.13修正]**

```
GameSession
PK:   EVENT#{eventId}
SK:   SESSION#{sessionNo}

GameResult
PK:      EVENT#{eventId}
SK:      SESSION#{sessionNo}#RESULT#{userId}
GSI1PK:  USER#{userId}
GSI1SK:  COMMUNITY#{communityId}#{playedAt}

GameResultChip
PK:      EVENT#{eventId}
SK:      SESSION#{sessionNo}#CHIP#{userId}
GSI1PK:  USER#{userId}
GSI1SK:  COMMUNITY#{communityId}#{playedAt}
```

| 属性(GameSession) | 型 | 説明 |
|---|---|---|
| gameType | S | ゲーム種別（`MAHJONG4`/`MAHJONG3`） |
| playedAt | S | 実施日時 |
| calcMode | S | `AUTO`（ウマ・オカ自動計算）/`MANUAL`（点数のみ） **[v1.13追加、実装済みだが未文書化だった属性を反映]** |
| startingPoints | N | 配給原点（calcMode=AUTOの場合のみ） **[v1.13追加]** |
| returnPoints | N | 返し点（calcMode=AUTOの場合のみ） **[v1.13追加]** |
| umaByRank | List\<N\> | 着順ごとのウマ（calcMode=AUTOの場合のみ） **[v1.13追加]** |
| boxUnderSettlement | BOOL | 箱下精算あり/なし（calcMode=AUTOの場合のみ。省略時true扱い） **[v1.16追加]** |
| tobiPoints | N | 飛び賞1件あたりのポイント（calcMode=AUTOの場合のみ。省略時0扱い） **[v1.16追加]** |
| tobiAssignments | List\<Map\> | 飛び賞の受取人指定。各要素は`{bustedUserId, receiverUserId}`（calcMode=AUTOの場合のみ。無ければ空リスト） **[v1.16追加]** |

| 属性(GameResult) | 型 | 説明 |
|---|---|---|
| rank | N | 着順 |
| score | N | 点数 |
| rankPoints | N | 順位点 |
| playedAt | S | ISO8601（GSI1SKと同期） |
| gameType | S | ゲーム種別（GameSessionから書き込み時に非正規化） **[v1.13新規]** |

| 属性(GameResultChip) | 型 | 説明 |
|---|---|---|
| chipCount | N | チップ枚数 |
| playedAt | S | ISO8601（GSI1SKと同期） |
| gameType | S | ゲーム種別（GameSessionから書き込み時に非正規化） **[v1.13新規]** |

**アクセスパターン**
- イベント内の全セッション・結果取得：`PK=EVENT#{id}, SK begins_with SESSION#`
- ユーザーの特定コミュニティ内の成績一覧：`GSI1PK=USER#{userId}, GSI1SK begins_with COMMUNITY#{communityId}`（API設計書10.2の権限方針「同一コミュニティ内でのみ閲覧可」をキー設計レベルで担保）。GameResultとGameResultChipはGSI1PK/GSI1SKのプレフィックスを共有するため、アプリ側はSKの`#RESULT#`/`#CHIP#`で判別する

> F-801〜F-804に対応。ゲーム固有結果（ポーカーのBuy-in等）は`extra`属性（Map型）に格納し、基本キー構造は変えずに拡張する（F-902の設計方針）。
>
> **[v1.13追加]** `GameResult.gameType`/`GameResultChip.gameType`は、四麻と三麻で平均着順のスケールが異なり合算すると指標として意味を持たなくなる問題（ResultLambda `_aggregate`）に対応するために追加した。GameResultにはイベント/セッションの状態が保持されておらず`GameSession`への都度JOINが必要になるため、GSI1で1回のQueryのまま種別ごとに集計できるよう書き込み時に非正規化した（読み取り時に都度GameSessionを引く方式は、コミュニティの通算成績集計のような多件数アクセスパターンでは高コストになるため採用しない）。
>
> **[v1.16追加]** `boxUnderSettlement`/`tobiPoints`/`tobiAssignments`はIssue #66（飛び賞）・#67（箱下精算）対応で追加した。いずれも新規のPK/SK/GSIは不要（GameSession本体への属性追加のみ）。`tobiAssignments`は「誰が誰をトビにしたか」という最終スコアだけからは導けない情報のため、フロントのUIで管理者に明示的に選んでもらった結果をそのまま保存する（GameResult側には非正規化しない。`rankPoints`は書き込み時にサーバー側で加減点済みの最終値のみを保持する）。

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
| relatedEventId | S | （任意）関連イベントID |
| **relatedCommunityId** | **S** | **（任意）関連コミュニティID。イベント単位ではなくコミュニティ単位でしか遷移先を持たない通知（`AVAILABILITY_REQUEST`等）用 [v1.18追加]** |
| createdAt | S | ISO8601 |

> F-701／F-702に対応。ユーザーが直接の主体なのでPKをUSER#にし、GSI不要。
>
> **[v1.18追加]** `relatedCommunityId`はIssue #73対応。空き予定提出リクエスト（`AVAILABILITY_REQUEST`）の通知は特定のイベントではなくコミュニティに紐づくため、`relatedEventId`だけでは遷移先を表現できず、通知をタップしても画面遷移しない導線切れになっていた。`relatedEventId`と`relatedCommunityId`は排他ではなく通知種別ごとにどちらか一方（または将来的に両方）が設定される想定で、汎用的な`relatedId`+`relatedType`にはせず既存の`relatedEventId`と同じ素直な命名パターンを踏襲した。

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

### 3.19 Feedback（フィードバック） **[v1.12新規]**

```
PK:      FEEDBACK#{feedbackId}
SK:      METADATA
GSI1PK:  USER#{userId}
GSI1SK:  FEEDBACK#{createdAt}#{feedbackId}
GSI2PK:  FEEDBACK
GSI2SK:  {createdAt}#{feedbackId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| userId | S | 投稿者（Cognito sub）。連絡先の別入力は求めず、常にこの値で追跡する |
| kind | S | QUICK（1クリック評価）／ DETAILED（詳細投稿） |
| relatedFeature | S | 該当機能（画面・操作を表す識別子。例：`MATCHING_CANDIDATE_LIST`） |
| rating | S | （kind=QUICKのみ）BAD／NEUTRAL／GOOD |
| category | S | （kind=DETAILEDのみ）BUG／FEATURE_REQUEST／UX_IMPROVEMENT |
| content | S | （kind=DETAILEDのみ、任意）詳細内容 |
| attachmentKeys | SS | （kind=DETAILEDのみ、任意）スクリーンショットのS3オブジェクトキー一覧 |
| status | S | UNHANDLED／PLANNED／DONE（既定UNHANDLED） |
| priority | S | （任意）LOW／MEDIUM／HIGH |
| reply | M | （任意）運営者からの返信。`{ message: S, repliedBy: S(userId), repliedAt: S }` |
| createdAt | S | ISO8601 |
| updatedAt | S | ISO8601 |

**アクセスパターン**
- フィードバック詳細取得：`PK=FEEDBACK#{feedbackId}`（`GetItem`）
- 投稿者自身の投稿履歴：`GSI1PK=USER#{userId}, GSI1SK begins_with FEEDBACK#`
- 運営者向け・全フィードバック一覧（新着順）：`GSI2PK=FEEDBACK`をQuery（`ScanIndexForward=false`で新着順）。種別・ステータスでの絞り込みはFilterExpressionで行う

> **[v1.12新規]** F-1401〜F-1405（機能要件書v1.10）に対応。GSI2PKに固定文字列`FEEDBACK`を用いる「種別横断の一覧化」は、既存のGSI2（直接ID検索専用）の使い方を拡張したものである。フィードバック投稿数はコミュニティ単位のアクセスパターンと異なり全体でも小規模（個人開発のMVP検証規模を想定）なため、ステータス絞り込みを専用のSK設計（例：`{status}#{createdAt}#{feedbackId}`）にせずFilterExpressionに委ねる軽量な実装とした。将来投稿数が増えステータス別の一覧化コストが問題になった場合は、8章の未決事項としてSK設計の見直しを検討する。
>
> 投稿者本人以外（他ユーザー）のフィードバック本文を閲覧できるのは運営者のみであり、権限判定はLambda層（`cognito:groups`にOperatorsが含まれるか）で行う。DynamoDBのキー設計自体には権限分離の仕組みは持たせていない（Lambda設計書v1.7 §12.4参照）。

---

### 3.20 Announcement（アップデート予告） **[v1.12新規]**

```
PK:      ANNOUNCEMENT#{announcementId}
SK:      METADATA
GSI2PK:  ANNOUNCEMENT
GSI2SK:  {createdAt}#{announcementId}
```

| 属性 | 型 | 説明 |
|---|---|---|
| title | S | タイトル |
| body | S | 本文 |
| status | S | DRAFT／PUBLISHED／ARCHIVED |
| createdBy | S | 作成した運営者userId |
| createdAt | S | ISO8601 |
| updatedAt | S | ISO8601 |

**アクセスパターン**
- 一覧取得：`GSI2PK=ANNOUNCEMENT`をQuery（`ScanIndexForward=false`で新着順）。一般ユーザー向けには`status=PUBLISHED`のFilterExpressionを適用し、運営者向けには全件返却する

> **[v1.12新規]** F-1406（機能要件書v1.10）に対応。3.19 Feedbackと同じ「GSI2PKに固定文字列を用いた一覧化」パターンを踏襲する。件数は少数（月1回程度の告知を想定）のためFilterExpressionで十分であり、専用GSIやSK設計の作り込みは行わない。

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
| 28 | コミュニティ表示名の重複チェック（実効表示名の突き合わせ。アクセスパターン2の応用） [v1.6] | PK=COMMUNITY#{id}, SK begins_with MEMBER# |
| 29 | コミュニティ一覧の表示順並び替え（アクセスパターン3の応用。各Membership行にsortOrderを書き込む） [v1.8] | PK=COMMUNITY#{id}, SK=MEMBER#{userId} |
| 30 | ユーザー自身が参加する確定イベントのコミュニティ横断一覧（予定タブのカレンダー表示用。アクセスパターン15の応用） [v1.8] | GSI1PK=USER#{id}, SK begins_with PARTICIPANT# |
| 31 | 参加頻度上限のジャンル横断カウント（マッチング処理F-401内部専用。アクセスパターン15の応用＋communityGenre絞り込み） [v1.9] | GSI1PK=USER#{id}, SK between PARTICIPANT#{periodStart}~{periodEnd} |
| 32 | イベント全員承認済み判定（F-502b、本確定のトリガー。アクセスパターン14と同一クエリ） [v1.10] | PK=EVENT#{id}, SK begins_with PARTICIPANT# |
| 33 | 運営者向け・全フィードバック一覧（種別/ステータス絞り込みはFilterExpression） [v1.12] | GSI2PK=FEEDBACK |
| 34 | 投稿者自身のフィードバック投稿履歴 [v1.12] | GSI1PK=USER#{id}, SK begins_with FEEDBACK# |
| 35 | アップデート予告一覧（一般ユーザーはstatus=PUBLISHEDのみFilterExpressionで絞り込み） [v1.12] | GSI2PK=ANNOUNCEMENT |

---

## 5. トランザクション・冪等性の設計方針

| ケース | 対応 |
|---|---|
| 参加リクエスト承認（JoinRequest更新＋Membership作成） | `TransactWriteItems`で同時コミット |
| イベント仮確定（Event状態更新＋Participant一括作成）[v1.10: 「イベント承認」から名称変更] | `TransactWriteItems` |
| キャンセル承認の二重実行防止 | `UpdateItem`に`ConditionExpression: status = PENDING`を付与 |
| OWNER変更（Membership.roleの入れ替え） | `TransactWriteItems`で「新OWNERのrole更新」と「元OWNERのrole=MEMBER更新」を同時に行い、途中失敗による権限不整合を防ぐ |
| **イベント仮確定時のダブルブッキング事前チェック** [v1.3、v1.10で判定対象statusを拡張] | Participant一括作成の**前**に、候補メンバー全員分についてGSI1（`PARTICIPANT#{startTime}#{eventId}`）を時間範囲でQueryし、`status`が`CONFIRMED`または`AWAITING_APPROVAL`（承認待ち＝事実上予約済み）の既存行と重複がないか確認。重複があれば`TransactWriteItems`を実行せず`PARTICIPANT_SCHEDULE_CONFLICT`エラーで中断する |
| **参加者個別承認の二重実行防止** [v1.10] | `UpdateItem`に`ConditionExpression: status = AWAITING_APPROVAL`を付与（承認・拒否のいずれも同じ形） |
| **イベント本確定（全員承認完了時のAWAITING_MEMBER_APPROVAL→CONFIRMED）** [v1.10] | `UpdateItem`に`ConditionExpression: status = AWAITING_MEMBER_APPROVAL`を付与。競合時（既に本確定済み、または承認待ち中に管理者がイベント全体を中止済み）は現在のstatusを再取得し、`CONFIRMED`以外の場合はEventConfirmedを発行しない |
| **登録済み対局セッションの削除**（GameSession本体＋全参加者分のGameResult＋GameResultChip） [v1.14新規、Issue #42] | `TransactWriteItems`で対象PK/SK配下の全アイテムをまとめて削除し、途中まで削除された不整合状態を防ぐ |

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
| Participant | F-502, F-502b, F-502c [v1.10], ダブルブッキング防止（Lambda設計書v1.6 7.2b） | 9.1, 8.3, 8.3b, 8.3c |
| CancelRequest | F-601, F-602 | 9.2, 9.3 |
| GameSession / GameResult | F-801〜F-804 | 10.1, 10.2 |
| Notification | F-701, F-702 | 11.1, 11.2 |
| OperationLog | F-1301, F-1302 | 12.1, 12.2 |
| EventStatusHistory | 要件定義書14章 | （内部利用、API非公開） |
| PushSubscription [v1.4] | F-703, F-704 | 11.3, 11.4 |
| AvailabilityRequest [v1.4] | F-205, F-206 | 5.5〜5.7 |
| Feedback [v1.12] | F-1401〜F-1405 | 12b.1〜12b.6 |
| Announcement [v1.12] | F-1406 | 12c.1〜12c.3 |

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
9. **Feedback/AnnouncementのGSI2固定パーティション化に伴うスケーリング** [v1.12]：GSI2PK=`FEEDBACK`/`ANNOUNCEMENT`という固定値パーティションは、投稿数が個人開発のMVP検証規模を大きく超えた場合にホットパーティション・肥大化の懸念がある。その場合はステータス別にSKを分ける（例：`{status}#{createdAt}#{feedbackId}`）か、日付でパーティションを分割する等の見直しを検討する

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

---

## 14. v1.5 → v1.6 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.3 Membershipに`displayName`（S、任意）属性を追加 | コミュニティごとに表示名を変えたいという要望への対応（F-108）。未設定時はUser.nicknameにフォールバックする後方互換設計とし、既存ユーザーは無設定で従来通り動作する |
| 2 | 3.3のアクセスパターン節に表示名重複チェックのクエリパターンを追記 | なりすまし・混同防止のため、同一コミュニティ内での実効表示名（displayNameまたはフォールバック後のnickname）の重複を防ぐ必要があるため。10〜30人規模のメンバー一覧取得+アプリケーション側比較で十分軽く、専用GSIは追加しない |

---

## 15. v1.6 → v1.7 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.2 Communityに`themeColor`（S、任意）属性を追加 | コミュニティごとにテーマカラーを設定したいという要望への対応。未設定時はアプリの既定色にフォールバックする後方互換設計とし、既存コミュニティは無設定で従来通り動作する |
| 2 | アイコン画像のカスタマイズはPhase2以降に切り分け、本バージョンではテーマカラー（文字列属性1つ）のみを対象とする旨を明記 | アイコンアップロードにはS3/CloudFront等の追加インフラが必要なため、まず軽量な変更のみを先行させる方針 |
| 3 | 4章アクセスパターン一覧にNo.28を追加 | 上記と同一のアクセスパターンを総括表にも反映 |

## 16. v1.7 → v1.8 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.3 Membershipに`sortOrder`（N、任意）属性を追加 | コミュニティ一覧の表示順を並び替えたいという要望への対応。未設定（新規参加直後等）は一覧取得時に末尾へ回す後方互換設計とし、既存Membershipは無設定で従来通り動作する |
| 2 | 3.8 MatchCandidateに、イベント全体中止時は`status`を`CONFIRMED`から`PENDING`へ戻す旨を追記 | キャンセル後に同一候補が`CANDIDATE_ALREADY_USED`で永久に再利用できなくなっていた不具合の修正 |
| 3 | 3.11 Participantのアクセスパターンに、ユーザー横断の確定イベント一覧取得（既存GSI1の応用、新規GSI追加なし）を追記 | 予定タブのカレンダー表示（確定イベントの表示）に必要なため |
| 4 | 4章アクセスパターン一覧にNo.29, 30を追加 | 上記No.1・No.3のアクセスパターンを総括表にも反映 |

---

## 17. v1.8 → v1.9 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.1 Userに`frequencyLimitCount`(N)/`frequencyLimitPeriod`(S)属性を追加 | 体力・満足度等の理由による個人ごとの参加頻度上限（要件定義書v1.6 30章）の全体デフォルト設定 |
| 2 | 3.3 Membershipに同名属性を任意の上書きとして追加（F-109新規） | `displayName`と同じ「コミュニティ単位で上書き、未設定ならUser側にフォールバック」構造を踏襲 |
| 3 | 3.11 Participantに`communityGenre`(S)属性を追加。イベント確定時にCommunity.genreを非正規化してコピーする | 参加頻度上限のコミュニティ横断・ジャンル単位カウントを、既存GSI1のレンジクエリ1発＋アプリ側フィルタで実現し、EventTemplateへのN+1 GetItemを避けるため |
| 4 | 3.11のアクセスパターンに参加頻度上限のカウントクエリを追記 | ダブルブッキング検知と同一インデックスの応用であることを明記 |
| 5 | 4章アクセスパターン一覧にNo.31を追加 | 上記No.3・No.4のアクセスパターンを総括表にも反映 |

---

## 18. v1.9 → v1.10 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.1 Userに`autoApprove`(BOOL)属性を追加 | イベント確定フローへの「全員承認」ステップ追加（要件定義書v1.7 §17、Issue #10）に伴う、自動承認の全体デフォルト設定 |
| 2 | 3.3 Membershipに同名属性を任意の上書きとして追加（F-109b新規） | `displayName`/`frequencyLimitCount`と同じ「コミュニティ単位で上書き、未設定ならUser側にフォールバック」構造を踏襲 |
| 3 | 3.10 Event.statusに`AWAITING_MEMBER_APPROVAL`を追加 | 管理者による仮確定と、参加予定者全員の承認完了による本確定の間の中間状態 |
| 4 | 3.11 Participant.statusに`AWAITING_APPROVAL`/`REJECTED`を追加。`approvedAt`/`autoApproved`/`rejectedAt`/`rejectReason`属性を追加 | 参加者ごとの個別承認・辞退の状態を保持するため |
| 5 | 3.11のアクセスパターンに「全員承認済み判定」を追記 | 既存のPK直接クエリ（参加者一覧取得）の応用で新規GSIが不要であることを明記 |
| 6 | 4章アクセスパターン一覧にNo.32を追加 | 上記No.5のアクセスパターンを総括表にも反映 |
| 7 | 5章トランザクション設計に「イベント仮確定時のダブルブッキング判定対象の拡張」「参加者個別承認の二重実行防止」「イベント本確定」の3行を追加・修正 | 判定対象statusの拡張と、新規の2段階承認フローにおけるConditionExpression設計を明記 |
| 8 | 7章の対応関係表でParticipant行にF-502b/F-502cを追記 | 新規APIエンドポイント（API設計書v1.12 §8.3b/§8.3c）との対応を明記 |

---

## 19. v1.10 → v1.11 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.4 Inviteに`createdByRole`（S）属性を追加 | 招待URL発行がOWNER/ADMIN限定からコミュニティの全メンバーに開放されたこと（Issue #22）に伴い、発行者ロールをスナップショット保持し参加時の承認要否分岐に使う |

---

## 20. v1.11 → v1.12 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | Feedback（3.19）を新規追加 | 機能要件書v1.10 F-1401〜F-1405：フィードバック機能（簡易フィードバック・詳細投稿・運営者レビュー・返信・集計） |
| 2 | Announcement（3.20）を新規追加 | 機能要件書v1.10 F-1406：アップデート予告 |
| 3 | 2章のGSI2説明に、種別横断の一覧化（固定文字列パーティション）という新しい使い方を追記 | 上記2エンティティが、既存の直接ID検索専用だったGSI2の用途を拡張するため |
| 4 | 4章アクセスパターン一覧にNo.33〜35を追加 | 上記2エンティティのアクセスパターンを総括表にも反映 |
| 5 | 7章の対応関係表に上記2エンティティを追加 | 整合性維持 |
| 6 | 8章未決事項に、GSI2固定パーティション化に伴う将来のスケーリング検討事項を追加 | 投稿数が増えた場合のホットパーティション・肥大化リスクを明記 |

---

## 21. v1.12 → v1.13 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.13 GameSessionの属性表に`calcMode`/`startingPoints`/`returnPoints`/`umaByRank`を追加（新規属性ではなく、既に実装済みだったが本書に未反映だった属性の反映） | 実装（ResultLambda）と設計書の食い違いの解消。自動計算（ウマ・オカ）機能追加時に本書側の更新が漏れていた |
| 2 | 3.13にGameResultChild（`GameResultChip`、SK=`SESSION#{sessionNo}#CHIP#{userId}`）を新規追加 | 同上。チップ集計機能追加時に本書側の更新が漏れていた |
| 3 | 3.13 GameResult/GameResultChipに`gameType`属性を追加（書き込み時にGameSessionから非正規化） | Issue #20派生：四麻/三麻混在ユーザーの平均着順が意味を持たなくなる問題の解消。ResultLambda `_aggregate`をゲーム種別ごとに集計できるようにするため |

---

## 22. v1.13 → v1.14 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | §5トランザクション・冪等性の設計方針に「登録済み対局セッションの削除」を追加。GameSession本体＋全参加者分のGameResult＋GameResultChipを`TransactWriteItems`でまとめて削除する方針を明記 | Issue #42：登録済み半荘の削除機能追加。既存のキー設計（PK/SK）自体は変更せず、削除時の操作方針のみ新規追加 |

---

## 23. v1.14 → v1.15 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.11 Participantのアクセスパターン注記を修正。イベント全体中止（cancel_event）時、CONFIRMEDのParticipant行を`CANCELLED`へ更新するようになった旨を反映（新規属性・キー変更なし） | Issue #63：中止済みイベントのParticipant行がCONFIRMEDのまま残留し、同じメンバー・同じ時間帯の新規イベント確定がPARTICIPANT_SCHEDULE_CONFLICTで誤ってブロックされていたバグの解消。`status`の取り得る値自体（CANCELLED含む）は元々本書が定義済みだったため、値の追加ではなく実装の追従 |

---

## 24. v1.15 → v1.16 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.13 GameSessionに`boxUnderSettlement`（BOOL、既定true相当）を追加 | Issue #67：箱下精算あり/なしの切り替え。既存レコードには属性が無いためアプリ側で既定trueとして読む（マイグレーション不要） |
| 2 | 3.13 GameSessionに`tobiPoints`（N、既定0相当）・`tobiAssignments`（List\<Map\>、既定空リスト相当）を追加 | Issue #66：飛び賞の受取人指定。最終スコアだけでは「誰が誰をトビにしたか」を導けないため、フロントUIでの明示的な選択結果をそのまま保存する方式とした。GameResultへの非正規化は行わない（`rankPoints`側で既に加減点済みのため） |

---

## 25. v1.16 → v1.17 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.10 Eventに`deletedAvailabilitySnapshot`（List\<Map\>、任意）を追加 | Issue #68：confirm_event時に削除される候補メンバーのAvailabilityを、cancel_event時に正確に復元できるようにするため。イベント時間帯だけでの復元だと、メンバーが元々登録していたより広い範囲（複数メンバーの空き予定の交差区間をイベント時間として採用するマッチングの性質上、本人の元の登録はイベント時間帯より広いことがある）を再現できないため、削除前の完全なスナップショットを一時的にEvent側へ保持する方式とした。復元後は本属性をREMOVEし恒久的な保持はしない |

---

## 26. v1.17 → v1.18 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | 3.14 Notificationに`relatedCommunityId`（S、任意）を追加 | Issue #73：空き予定提出リクエスト（`AVAILABILITY_REQUEST`）通知は特定のイベントではなくコミュニティに紐づくため、既存の`relatedEventId`だけでは遷移先を表現できず、通知タップ後に画面遷移しない導線切れになっていた |
