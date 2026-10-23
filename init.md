# catan/init.md

## プロジェクト概要

Catan（カタン）ボードゲームのフル版をスマホ向けに開発するプロジェクト。

## 開発方針

1. **Phase 1**: ゲームロジックをPythonで実装（GUIなし、CLIで動作確認）
2. **Phase 2**: Web UIを追加（HTML/CSS/JS + Canvas）
3. **Phase 3**: モバイル化（PWA or Capacitor）

## 現在のフェーズ

Phase 2（Web UI）進行中 — Pythonバックエンド + Canvas フロントエンド

## Web UI

- `server.py` — http.server ベースのバックエンド（外部依存なし）、REST API
- `web/` — プレイヤー用 `client.html` / 監視用 `index.html` / 共通 `game.js` / `style.css`（旧 `app.js` は未使用）
- 起動: `python3 server.py` → クライアント http://localhost:8000/ ／ 監視 http://localhost:8000/monitor
- 主なエンドポイント: GET `/room`（ロビー）, GET `/state?token=`（自分の視点／無指定は監視の全表示）, POST `/action`（`join`/`room_roll`/`room_pick`/`room_start`/`room_reset`/`room_init`/`monitor_new` と roll, end_turn, build_*, buy_dev, play_dev, move_robber, trade_*, discard, give_resources, auto_setup）
- ヘックス座標は中心対称レイアウト（radius-2 axial hexagon）に修正済み

## ルール検証メモ（公式 CN3081 準拠）

- 発展カードはロール前 or アクションフェーズで使用可（1ターン1枚、購入ターン不可）
- 勝利点カードは購入ターンでも複数公開して勝利可能（実装では購入時に hidden_vp 加算）
- 7出目: **第1巡目は振り直し**、第2巡目以降は「①半分捨て（切り捨て・捨てる札は選択式）→ ②盗賊移動 → ③隣接プレイヤーから1枚強奪」
- 6と8を隣接させない数字配置
- 港: 4:1（港なし）/ 3:1（汎用港）/ 2:1（該当資源の専用港）。港は海岸の**エッジ**上にあり、両端どちらかの頂点に建築すれば利用可能
- 港は**開拓地を建てた同じターンから使える**（公式 Combined Trade/Build Phase: "You can even use a harbor on the same turn you build a settlement there."）。「建てたターンは使えない」はハウスルールであり、本実装は公式準拠で**同ターン可**（`player_port_ratio` は建物の有無のみで判定）。
- 街道は相手建築の向こう側に伸ばせない

## 順番ドラフト（v15）

サイコロは「**何番目に選ぶか**」の優先順位を決めるだけ。ロール後、ダイスの大きい順（同点は席順）に、各プレイヤーが盤面を見ながら **第1〜Nターン目の番号を指名** する（ドラフト式）。指名する順番と、実際に手番が回ってくる順番は別物。

### 盤面プレビュー（v16）

指名は **実際に使う盤面を見ながら** 行う。

- 盤面は 2人以上がロビーにいるときに生成し（`_ensure_board()`）、`room_start` は **その同じ Game を再利用** する（`ROOM["g"]` の盤面は不変、プレイヤー名だけ選択順に付け替え）。→ 見た盤面＝遊ぶ盤面。
- `serialize_room` の `board`（`board_data()` = 地形・数字・港・頂点・辺。建物や手札は含まない）を、`phase=='lobby'` かつ盤面が存在するときだけ返す。
- 席数が変わったら（途中入室）盤面の前提が崩れるので、`_sync_board()` が **盤面とダイス・`slots` を破棄** し、全員が振り直して新しい盤面で指名し直す（古い盤面への指名が残らない）。
- 盤面を出すために lobby 中も `Game` が存在するため、**ゲーム操作は `phase=='playing'` でガード**（`handle_action` と GET `/state`）。ロビー中の `/state` は従来どおり `{"phase":"lobby","started":false}`。
- クライアント: `game.js` の `previewBoard()` が読み取り専用の合成 state（`players:[]`, `valid:[]`）で盤面を描画。`client.html` は `body.preview` で **盤面を上・ロビーパネルを下** に並べる（スマホ縦持ちで両方見える）。監視画面も `/room` の `board` を拾って同じ盤面を表示する。

指名そのものの仕様:

- サーバー: `ROOM["slots"]`（seat → 選んだ番号）を保持。
  - `_pick_queue()` = ダイス降順（同点は seat 昇順）、`_current_picker()`、`_draft_state()`。
  - `serialize_room` に `draft`（`queue`/`slots`/`current_picker`/`ready`）と `can_start`（全員ロール済み **かつ** 全員選択済み）を追加。
- `room_pick`（アクション）: 現在の指名者（`_current_picker`）だけが空き番号を選べる。選択済みの本人は**空き番号へ選び直し可**（ロビー中）。他人が選んだ番号・範囲外（1..人数）は拒否。
- `room_start`: 全員が番号を選ぶまで開始不可（未選択なら `順番が未確定です`）。プレイ順は **選んだ番号の昇順**（ダイスの順ではない）。
- `room_init`（監視のみ）: 席とトークンは維持したまま、ダイス・`order`・`slots`・ゲームをクリアして `phase='lobby'` に戻す。
- クライアント（`client.html`）: ロビーに「n番目」ボタン（`.slot`）を描画。
  - 手番の人は空き番号をタップ、選択済みは緑＋自分の名前（`.mine`）、待機中は「待機中…（〇〇の番）」、「▶ あなたの番です」のヒント。
  - 旧「暫定の順番」表示は「選択順（ダイスの大きい順）」に変更。
- テスト: `test_draft_api.py`（認可・占有・手番・選び直し・開始順・盤面プレビュー）、`test_ui18.js`（UI操作だけで指名→開始、盤面が描画されることと開始盤面との一致）、`test_ui19.js`（監視画面のロビー盤面）、`test_server_api.py` はロール後に全員 `room_pick` するよう更新。

## スマホ・レイアウト（v17）

狭い画面（`max-width: 860px`）では、盤面を最優先で見せ、操作パネルを **下から開くボトムシート** にした。

- **盤面が主役**: 既定（シート閉）では盤面が画面のほぼ全体を使う（スマホ縦 390×844 実測で盤面 390×790、下に高さ54pxの開閉バーだけ）。以前はサイドバー固定320pxのため盤面が幅46pxしかなく「盤面が見えない」状態だった。
- **開閉バー**（`#m-bar`、`game.js` の `sidebarHTML()` が生成）: 「▲ 操作パネルを開く / ▼ 盤面を広く見る」でトグル（`setBar()`、`body.bar-open`）。バーには現在の状況（ターン数・手番・次にすべき操作）を出す（`updateMobileToggle()`）。
- **必要なときだけ自動で開く**（`autoOpenBar()`）: 捨て札（7）・盗賊移動・初期配置の手番になったら自動で開く。配置操作中は開いたまま（`barHeld`）にして開閉がチカチカしないようにする。
- **折りたたみ**（`.m-fold`）: 交易・発展カードなどは既定で隠し、「▽ 交易・発展カードなども表示」（`#toggle-all`、`body.show-all`）で展開。スマホでも基本操作はワンタップ。
- **描画**: `resize()` は CSS サイズ×DPR（上限2）でバッキングストアを合わせて精細化。`fitCanvas()` をポーリング毎に呼び、シート開閉・回転・DPR変化でもズームやズレが出ないようにする。クリック座標は `rect`→バッキングストアにスケール変換。`#board-wrap` に `ResizeObserver` を張って自動追従。
- デスクトップ（>860px）は従来どおり（盤面＋右サイドバー320px、`#m-bar` は非表示）。
- テスト: `test_ui20.js`（盤面が閉時に横幅いっぱい・十分な高さ、バッキングストアが CSS×DPR、開閉トグル、折りたたみ展開、JS例外0）。デスクトップ回帰は `test_ui10/12/13` で確認。

### ロビーのスクロール（v23）

- スマホでロビーが**スクロールできず操作できない**不具合の修正。`style.css` は狭い画面で `body { overflow: hidden; }`（ゲーム画面では正しい）にしていたが、**ロビープレビューでも効いて**いたため、盤面の下にあるロビーパネル（ダイス・番号選択・ハウスルール）が画面外に出ると触れなかった。
- `body.preview`（ロビー中のみ付与）に `overflow-y: auto` を指定し、`@media (max-width:860px)` では `body.preview { overflow-y: auto; height: auto; }`・`#layout { height: auto; }`・盤面は `min(100%, 86vw)` と上書き。**ゲーム画面は従来どおり `overflow: hidden`**（`preview` クラスが外れるため）で回帰なし。
- テスト: `/tmp/opencode/test_ui27.js`（ロビーで `overflow` が hidden でない、コンテンツが画面を超える、実際にスクロールする、ハウスルール/ボタン/行が画面内に到達可能）。ゲーム画面が `hidden` のままであることも確認。

### ロビー盤面プレビューのポーリング不具合修正（v17）

- `previewBoard()` の「同一盤面ならスキップ」最適化が、`getState()` が毎回 `state` を「ゲーム未開始」ペイロードで上書きした後に走ると、**盤面が state から消えたまま**になっていた（監視画面で顕著。クライアントは `location.reload()` でロビーに戻るため目立たなかった）。同一キー時も `state.board` が無ければ合成 state を作り直すよう修正。

### ロビーの「入り直す」→「退出する」（v17）

- 旧「入り直す」ボタンはトークンを消してリロードするだけだったため、**サーバー側の席が残ったまま**になり、抜けたつもりが生き残っていた。
- `leave` アクションを追加し、ボタンを **「退出する」**（`confirm` 付き）に変更。押すとサーバーで席を削除してからトークンを消してリロードするので、ロビーには自分の席が残らない。再入室は名前欄が空の状態からやり直す。
- テスト: `test_leave_api.py`（20項目）、`test_ui21.js`（11項目）。

## WSGI 化とデプロイ（v18）

常時公開（PC 起動不要・無操作で止まらない）を狙って、**HTTP 層を差し替え可能**にした。

- **`app_core.py`** を新設し、ゲーム/ロビー状態（`ROOM`）・シリアライズ・`handle_lobby`/`handle_action`・ルーティング（`route_get`/`route_post`）をここへ集約（HTTP 非依存）。
- **`server.py`** は `http.server` の薄いアダプタに縮小（ローカル/Codespaces 用）。
- **`wsgi.py`** を新設（PythonAnywhere 用）。**標準ライブラリのみ**の WSGI アプリで Flask 不要。`application`/`app` を公開。
- ルーティング: `/`(client.html), `/monitor`(index.html), `/style.css`, `/game.js`, `/assets/*`, `/room`, `/env`, `/state`。パストラバーサルは 404。
- **`/env`** に `pid`/`owner_pid` を追加。PythonAnywhere で複数ワーカーになると値が食い違い、状態分裂を検知できる（**1 ワーカー必須**）。
- `wsgi.py` のクライアント IP は `X-Forwarded-For`（プロキシ経由）を優先。これにより公開 URL 経由では `debug_allowed=false`（`?debug=1` は外部無効のまま）。
- Codespaces/PythonAnywhere の手順と無料枠の注意は `README.md` に記載。
- テスト: `tests/test_wsgi.py`（WSGI 経由の E2E。静的配信・`/env` ゲート・join/roll/pick/start・秘匿情報の絞り込み・405/404）。

## 認可・情報公開の穴を修正（v18）

外部公開を見据えて実測したところ、**トークンなし/不正トークン**で以下ができてしまっていた。

1. `GET /state` が全員の手札・隠し勝利点を返す（`token_to_pid` が `None` を返し、`None` が「監視＝全部見える」の意味だったため）。
2. `POST /action` でトークンなしでも手番プレイヤーの操作が通る（権限チェックが `actor is not None` の内側だけだったため。例: トークンなしの `build_settlement` が成功し残り集落が減った）。

### 修正方針

- `/state` の viewer を **3値**に: `pid`（本人視点）/ `'spectator'`（公開情報のみ）/ `'debug'`（全部見える）。
  - 有効トークン → その `pid`
  - トークンなし・不正 → `'spectator'`（`resources`/`dev_cards`/`new_dev_cards`/`hidden_vp` を出さない）
  - `'debug'` は **`view=monitor` かつ信頼アドレス（既定は loopback）** のときだけ。ローカル監視画面のために `game.js` は `VIEW==='monitor'` のとき `?view=monitor` を付ける。
  - `'debug'` を IP だけで与えない（＝localhost のプレイヤー用ページは昇格しない）。監視の表示は従来どおり全公開。
  - `serialize()` の `you` は pid 以外なら `null`、`role`（`player`/`spectator`/`debug`）を追加。
- `/action` の権限: `handle_action(..., actor=None, local=False)` は**すべてのゲーム操作を拒否**（「この操作は外部からは行えません」）。トークンなしで許すのは信頼アドレスからのホットシート/テスト操作のみ。
- 既存の「外部からの監視専用操作（`room_init`/`monitor_new`/`auto_setup`/`give_resources`）拒否」は維持。

### テスト

- `tests/test_authz.py`: 段階1（トークンなし/不正の `/state` に秘匿キーが無い／ローカル監視は `debug`／IP だけでは昇格しない／`view=monitor` でも外部は `spectator`）と段階2（`roll`/`end_turn`/`buy_dev`/`build_*`/`discard`/`trade_respond` がリモートのトークンなしで拒否され、ゲーム状態が変わらない）。
- `/tmp/opencode/test_ui24.js`: ローカル監視= `debug` で全公開、トークンなしクライアント= `spectator` で秘匿情報なし＋「観戦」表示、有効トークン= `player`。

## 勝敗確定後の発展カード公開（v18）

勝者が決まったら（`winner` 確定＝`phase == "end"`）、**全員の所持発展カードを公開**する。

- `serialize_player(p, viewer, reveal)` を追加し、`reveal=True` のときは誰の視点でも `dev_cards`/`new_dev_cards`/`hidden_vp`/`total_vp` を返す。`serialize()` が `reveal=(g.winner is not None)` を渡す。
- 各プレイヤーに `revealed` フラグを出力。UI（`game.js`）は `p.revealed` のとき **未使用:[...]** を表示（購入直後は `(新規)`）。
- **使用済み（`used_dev_cards`）は従来どおり常時公開**なので、勝敗後は「使用済み」と「未使用」を並べて確認できる。例: `使用済:[騎士] 未使用:[独占]`。
- プレイ中は他人の手札は秘匿のまま（枚数のみ `dev_count`）。
- テスト: `tests/test_dev_reveal.py`（プレイ中の秘匿／勝敗後の公開／使用済みと未使用の区別／空手札）、`tests/test_wsgi.py` に WSGI 経由の公開確認を追加、`/tmp/opencode/test_ui23.js`（UI表示6項目）。

## 盤面右下の 2d6（v24）

ゲーム中の現在の出目を、盤面の右下に**テクスチャ化した 2 個のダイス**で常時表示する（アニメーションなし）。

- `diceTexture(size)`: 象牙色の柔らかい手描き風テクスチャ（地形・海と同系）。角丸・薄い影・**細い濃い輪郭**（駒と同じ細さ）。
- `drawDie(cx, cy, side, value)`: 1 つのダイス。ピップは 1〜6 を正しい配置で。**「1」の目だけ赤**（`#c62828`、日本のサイコロ風）、2〜6 は黒。
- `drawDice()`: 2 個を右下に並べて配置（`dicePlacement()` が位置計算）。**表示条件はプレイ中（`phase` が `roll`/`main`/`end`）かつ出目が有効なときだけ**。
  - ロビー（順番決め）・初期配置（`setup`）・ターン開始直後でまだ振っていない（`dice==[0,0]`）では**描かない**。
- **港ラベルを隠さない**: `_portLabelBoxes()` で港ラベルの矩形を求め、`dicePlacement()` が右下コーナーから「左へ・上へ」候補を最大12通り試し、**港ラベルに触れない最初の位置**に置く（余白4px）。サイズは `scale*0.8`（最小18px）と小さめで視認重視。
- テストフック: `CatanGame.diceTexture` / `_debugDrawDie` / `_debugDrawDice` / `_debugPortLabelBoxes` / `_debugDicePlacement`。
- テスト: `/tmp/opencode/test_ui28.js`（ロビー・初期配置・振る前は出ない／振ると出る／右下配置／サイズ／港ラベル非重複／1は赤・6は黒／テクスチャ）。

## 海のテクスチャとハウスルール（v22）

### 海（シームレスタイル）
- 島の周囲を**海**に。`seaTexture(size)` を追加し、`drawSea()` を `render()` の最初（地形より下）で描画。
- **シームレス**: 3倍のキャンバスに模様を**9回（-1/0/+1 の3×3オフセット）**描き、中央タイルを切り出して端同士が一致するようにした（継ぎ目なし）。ベースは単色（`#84bcd4`）— グラデーションだと端で色がズレて線になるため。
- 見た目は**柔らかさ優先**で地形テクスチャと同系の淡い水色。うねり・波は低コントラスト（白の不透明度 8〜18%）。
- **範囲は全面ではなく角丸の正方形**: `SEA_HALF = 5.6 * scale`（世界座標）で、**港のドック＋港ラベルまで含む**大きさ。縁は薄い白線で背景に馴染ませる。

### ハウスルール: 初期砂漠
- ロビーに**ラジオボックス**（`client.html`）。変更は `room_setting`（`key="desert"`）。
- 3値（`Board.desert_mode` / `Game(desert=)`）
  - `center` … 砂漠は常に中央 `(0,0)`
  - `coast_ng` … 内陸のみ（海岸は砂漠にならない）**＝既定**
  - `none` … 盤面のどこでも（海岸もあり）
- `_assign_terrains` がモードで分岐。他の18地形は従来どおりシャッフル。
- 設定変更で**盤面を作り直す**（`ROOM["g"]=None` → `_ensure_board()`、ダイスは振り直し）。ゲーム中は変更不可。`serialize_room` が `settings` を返す。
- テスト: `tests/test_house_rules.py`（各モードの生成／既定=coast_ng／設定の保存・拒否／プレビュー再生成／ゲーム中の拒否／開始後の盤面反映）、`/tmp/opencode/test_ui26.js`（ロビーのラジオ3つ・既定選択・center切替で中央砂漠・coast_ngに戻す・海タイルがシームレス）。

## 地形ラベルの削除と盗賊の駒化（v21）

- **HEX マスの地形名ラベルを削除**。`TERRAIN_LABEL` を廃止し、`render()` から黒い箱のラベル描画を撤去（テクスチャで種類は判別できる）。`TERRAIN_COLOR` はフォールバックとして残置。
- **盗賊（ロバー）を駒化**。`drawRobber(px, py)` を追加し、黒丸に「R」をやめて**初代カタン風の黒い人物シルエット**（マント＋頭＋顔の白い部分、細い黒い輪郭）に。サイズは `(scale/50) * 0.8 * 1.2 * 1.5`（＝1.44倍）。`h.robber` のマスに描画。
- テスト: `/tmp/opencode/test_ui25.js` に「盗賊は図形で描画＝テキストを出さない」「地形ラベルは撤去済み」を追加。

## 駒と街道のデザイン（v20）

初代カタン（1995）の木製ブロックを 2D で見た形に寄せて、開拓地・都市・街道を描き直した。画像アセットなし・すべてベクター。

- **開拓地**: ホームベースを逆さにした五角形（頂点は上）。`drawSettlement`。
- **都市**: 変形七角形（頂点7つ）。底辺は**高さ:幅 = 1:2** の長方形、その**右半分の上に開拓地と同じ五角形**が乗り、**左半分の上辺を少し下げた段差**（`notch = 4×s`）で「一段高い居城」に見せる。`drawCity`。
- **サイズ**: 両方とも `s = (scale/50) * 0.7`（0.7倍）で控えめに。
- **輪郭**: 開拓地・都市は `pieceStroke()`（`#111`・`lineJoin='miter'`・`miterLimit=2`）で**細い黒線**。`miter` にすることで五角形の**頂点が尖る**（round だと丸まる）。太さは `pieceLineWidth() = max(0.8, scale*0.026)`。
- **街道**: `drawRoadBar` で同じバーを**2回ストローク**（①黒を `width + max(1.6, pieceLineWidth()*2)` で下地、②色を `width` で重ねる）。両側に細い黒フチが出て建物と統一感。両端は辺長の24%（`inset`）内側に縮め、頂点の建物と当たらない。配置候補の黄色バーも同じ形。

## HEX マスのテクスチャ（v19）

盤面にリアリティを出すため、HEX マスを単色塗りから**手続き型テクスチャ**に変更した。画像アセットは使わない（追加ファイルなし・スマホでも軽い）。

- `web/game.js` に `terrainTexture(terrain, size)` を追加。オフスクリーン Canvas に地形ごとの質感を**1回だけ**生成し、`地形@サイズ` をキーにキャッシュ。描画時は `drawImage` を1回（HEX でクリップ）するだけ。
- 見た目は**やわらかい手描き風**: 上→下の淡いグラデーション＋中心のラジアル光（`rgba(255,255,255,0.16)`〜`rgba(0,0,0,0.10)`）で奥行きを出す。
  - 木: もみの木のシルエットを点在 / 土: なだらかな丘 / 羊: 草の穂先＋白い点 / 麦: 金色の畝（縦ストローク） / 鉄: 岩山＋雪の冠 / 砂漠: 砂丘の曲線＋砂粒。
- **ちらつき防止**: 地形ごとの固定シード（`_rng`）で模様を生成するので、ポーリング再描画でも毎回同一。
- **拡大縮小/DPR 追従**: キャッシュキーに `size` を含むため `scale` 変更時に作り直す。`TERRAIN_COLOR` はフォールバックとして残置。
- 数字チップは**羊皮紙風の円盤**（`#f3ead1`＋茶枠）に変更し、テクスチャ上でも読みやすくした。
- **テスト**: `/tmp/opencode/test_ui25.js`（6地形でテクスチャ生成／19マス以上／キャンバスが多色＝テクスチャ適用済み／開拓地=5頂点・都市=7頂点／街道は2回ストローク／盗賊は図形／JS例外0／リサイズ後も正常）。スクショ `/tmp/opencode/board_textures.png`、`board_textures_phone.png`、`board_pieces.png`/`board_pieces_zoom.png`、`board_roads.png`、`board_robber.png`。

## 最終仕上げ（優先度低・後日）

- **港の画像化**と埋め込み（現在は比率ラベルのみ描画）。

## UI 調整（v15）

- **港**: 比率ラベル（4:1/3:1/2:1）を最前面に描画（`drawPortLabels`）。港バー本体は道路より先（下）に描画し、道路が港で隠れないようにする。
- **共有情報**: プレイヤー一覧から「道／開拓地／都市」の残数表示を削除。
- **独占・収穫**: `prompt()` を廃止して**プルダウン**化（`#dev-params`、`updateDevParams()`）。ポーリングで選択が消えないよう `box.dataset.card` が変わる時だけ再構築。
- **勝利点カード**: プレイ用の選択肢に出さない。サーバーの `play_dev_card` も VP カードを拒否（使用済みに記録されない）。
- **監視画面の init ボタン**: ゲームが存在する間、右下に常時表示（`confirm` 付き、監視専用）。終了後はこれでロビーに戻す。
- **ロビーの盤面プレビュー**: 指名は盤面を見ながら（v16 節参照）。ロビーでは盤面が上、ロビーパネルが下。
- **タブタイトル**: ロビーの再描画ガード**より前**に毎回 `setTitle`（後から入室した人のタイトルが既定のままになる不具合の修正）。
- **プレイヤー間交易**: 対象外のプレイヤーには応答パネルを出さず（「〇〇さんが取引提案中」の注記のみ）、自分の提案フォームは維持。取引中に提案しようとした場合はサーバーが具体的な理由を返す（`既に提案が開いています…`）。

## 初期配置の順序強制（v14）

- 初期配置（セットアップ）は各手番で **開拓地 → 街道の固定順**。`Game.setup_placed_settlement` / `Game.setup_last_vertex` で管理。
  - `place_setup_settlement`: 同一ステップで2つ目の開拓地は不可。成功時に「街道待ち」へ。
  - `place_setup_road`: 開拓地未配置なら拒否。さらに **そのステップで置いた開拓地に接続する街道のみ** 許可。
  - `_advance_setup` で毎ステップのフラグをリセット。
  - → 2巡目でも、1巡目の開拓地に隣接する街道を先に置いて詰む問題を解消。
- クライアントの初期モードはサーバー状態から固定（`serialize` の `setup_settlement_required`）。
  - `true` → 「開拓地を建てる」、`false` → 「街道を建てる」。手動の建設モードボタンはセットアップ中は無効化。
  - `valid.roads` はセットアップ中「そのステップの開拓地に接続する街道」のみを返す（クライアントのハイライトとサーバー受理を一致）。
- `tests/test_rules.py` に `test_setup_order_enforced` を追加。

## UI 調整（v14）

- 「発展カードを購入」ボタンを **街道／開拓地／都市と同じ行** に移動（旧・発展カード節のボタンは削除）。
- ブラウザタブのタイトルを入室後に **`カタン（プレイヤー：<名前>）`** に変更（`client.html` の `setTitle`）。
  - ゲーム開始時・リロードでゲーム中に入り直した場合も維持（`showGame` 側でも設定）。未入室は `カタン（プレイヤー）`。

## 7・盗賊・港・交易の実装（v9）

- **7の処理** (`game.py`): `roll_dice()` は第1巡目 (`turn_number < num_players`) の7を自動振り直し。第2巡目以降は `_handle_seven()` で `pending_discards = {pid: n//2}`（>7枚）と `robber_pending = True` を設定
- **捨て札選択**: `discard_cards(resources, player_id)` で捨てるカードを選択（合計が指定枚数と一致すること）。捨て札がある間は build/trade/buy/end_turn/roll をブロック
- **盗賊移動＋強奪**: `move_robber_and_steal(hex, victim)` は `robber_pending` が必要。victim は `possible_robber_victims()` に含まれる必要あり
- **Knight**: `play_dev_card('knight', hex, victim)` は `robber_pending` を立てる。UIは座標 prompt を廃止し**マスクリック→被害者プルダウン**で操作
- **港の配置** (`board.py:_assign_ports`): 海岸サイクル（30辺）上に9港を等間隔配置。`self.ports`（頂点→型、両端に登録）と `self.port_edges`（描画用）を保持。型は 2:1/3:1 交互（特定港5 + 汎用港4）
- **交易比率** (`game.py:player_port_ratio`): 4:1 既定、汎用港で 3:1、該当資源の専用港で 2:1。**別資源の2:1港では3:1にならない**よう修正。`trade_bank` はサーバ側で比率を再計算（クライアント値を信用しない）
- **server.py**: `serialize()` に `robber_pending`, `pending_discards`, `rerolled`, `robber_victims`, `trade_ratios`, `port_edges` を追加。アクション `discard` を追加
- **web/index.html**: 捨て札パネル、盗賊の被害者プルダウン、Knightフロー、銀行/港交易UI、港ドック描画、7時の自動ロボット操作モード

## プレイヤー間交易（v10）

- **提案→承諾方式**: 手番プレイヤーが `create_trade_offer(give, want, targets)` で「出す資源/欲しい資源」と宛先プレイヤー（複数可）を指定し、`self.trade_offer` に保持
- **承諾/拒否**: `respond_trade(player_id, accept)`。承諾時は資源を原子的に交換して提案をクリア。拒否時はそのプレイヤーを `declined` に追加し、全員拒否で自動クリア
- **取り下げ**: `cancel_trade_offer(player_id)` は提案者のみ可能
- **失効条件**: ターン終了時・Knight 使用時にクリア。7未解決中は提案不可。同時に保持できる提案は1件
- **server.py**: `trade_offer` / `trade_respond` / `trade_cancel` アクションを追加。`serialize()` に `trade_offer` を追加（`player` ID を明示的に受け取るため、将来のクライアント分離に対応しやすい）
- **web/index.html**: サイドバーに Player Trade パネル。Give/Want の数値入力、宛先チェックボックス、提案中は宛先ごとの Accept/Decline と Cancel を表示。従来の銀行/港交易は「Bank / Port Trade」に改称

## 日本語化と盤面生成（v11）

### 日本語化
- **資源名**: 木(wood) / 土(brick) / 羊(sheep) / 麦(wheat) / 鉄(ore)。内部キーは英語のまま、表示のみ日本語（`RES_LABEL`）
- **発展カード**: 騎士 / 街道建設(道x2) / 収穫(資源x2) / 独占 / 勝利点+1（`DEV_LABEL`）
- **プレイヤー名**: `プレイヤー1`〜`プレイヤー4`（`game.py`）
- **その他UI**: ボタン・見出し・凡例・状態表示・捨て札/強奪パネル・交易パネル・アラートを日本語化。発展カードの収穫/独占は日本語入力（木/土/羊/麦/鉄）を `toResKey()` で内部キーに変換

### 盤面生成の乱数性・公式準拠
- **ランダム化**: `/new`（およびロビーのゲーム開始 `room_start`）は `seed=None` で毎回ランダムな盤面を生成（従来は seed=42 固定）
- **地形**: ランダム配置。ただし砂漠は**内陸**（内周リング6 + 中心1 = 7マス）のみ＝海岸砂漠を回避（`board.py:_assign_terrains`）
- **数字チップ**: 公式準拠。`NUMBER_SEQUENCE = [5,2,6,3,8,10,9,12,11,4,8,10,9,4,5,6,3,11]`（裏面A〜R順）を、島の6つの角のいずれかから**反時計回り**に螺旋（外周リング→内周リング→中心）で配置し、砂漠は飛ばす（`board.py:_assign_numbers`, `_ring`, `_spiral`）。角はランダム（6通り）
- 検証: 300枚のランダム盤面で6と8が隣接しないことを確認

## ルール穴の修正（v12）

### 銀行の資源供給上限（各資源19枚）
- `Game.bank` を追加（各資源19枚）。資源の総量は「銀行 + 全プレイヤー手札」で保存される
- **生産は資源ごとにオール・オア・ナッシング**（公式）: その出目で生産される資源の合計が銀行に足りなければ、**誰も受け取らない**（`_distribute_resources`）
- 資源が動く全経路で銀行を増減:
  - 生産: 銀行→プレイヤー（`_distribute_resources`）
  - 銀行/港交易: 渡す資源は銀行へ、受け取る資源は銀行から（`trade_bank`。受け取り先が0枚なら交換不可）
  - 建築/発展カード購入: 支払った資源は銀行へ戻る（`_bank_put_cost`）
  - 収穫(Year of Plenty): 銀行から取得（在庫が無ければ取得不可）
  - 捨て札（7）: 捨てた資源は銀行へ戻る（`discard_cards`）
  - 独占/強奪/プレイヤー間交易: プレイヤー間の移動のみ（銀行は関与しない）
  - ※ `give_resources` はデバッグ用チートで銀行を介さない
- UI: 資源パネル下に「銀行の残り」を表示（`serialize()` の `bank`）

### 同一資源交換の禁止（明示化）
- `trade_bank` は `give == receive` を明示的に拒否（`trade.py` の `bank_trade` と同じ）。木4→木1 のような手札縮小による7のバースト回避を無効化

### 盗賊は同一ヘックスへ移動できない
- `move_robber_and_steal` は現在の盗賊ヘックスと同じ座標を拒否
- UI: 盗賊選択モードで現在盗賊がいるヘックスをクリックしても無視

### 騎士をロール前に使用した際のデッドロック修正
- `play_dev_card` は `PHASE_ROLL` でも騎士を使用可能だが、`move_robber_and_steal` が `PHASE_MAIN` 限定のため盗賊を動かせず、`roll_dice` も `_seven_unresolved()` でブロックされる詰みが発生していた
- `move_robber_and_steal` を `PHASE_ROLL, PHASE_MAIN` の両方で許可するよう修正

### テスト
- `tests/test_rules.py` を追加（同一資源交換の禁止 / 銀行供給のオール・オア・ナッシング / 建築時の銀行戻し / 捨て札の銀行戻し / 盗賊の同一マス禁止 / ロール前騎士）
- `python3 tests/test_rules.py` で実行（他テストと同様に素のスクリプト形式）

## サーバー／クライアント分離（v13）

### ページ構成
- `web/client.html`（`/`）: **プレイヤー用クライアント**。ロビー（名前入力・ダイス・開始）＋自分の視点の盤面＋**操作（サイコロ／建設／交易／発展／捨て札／盗賊）**。
- `web/index.html`（`/monitor`）: **監視画面（閲覧のみ）**。全情報を表示（トークン無し＝`viewer=None`）するが**操作ボタンは持たない**。ゲーム操作はクライアントから行う。
  - 手番クライアントのみ操作可能（サーバー側で `actor == current` を強制）。
  - ローカルのホットシート検証用に `GET /monitor?debug=1` で操作を一時的に有効化できる（既定は閲覧専用）。
- `web/game.js`: 盤面描画・操作の共通JS。両ページが読み込む。サイドバーHTMLはJSが生成。
- 旧 `web/app.js` は未使用。

### 公開情報 / 秘匿情報の振り分け（`server.serialize(g, viewer)`）
- `viewer=None`（監視）: 全プレイヤーの手札の中身まで表示（従来互換）。
- `viewer=pid`（クライアント）: `serialize_player` が以下を切り替え。
  - **公開**: 手札枚数(`hand_count`)・発展カード枚数(`dev_count`)・使用済み発展カード(`used_dev_cards`)・盤面から見える勝利点(`vp`／`total_vp`＝`vp`のみ)・道/開拓地/都市の残数・最長の道/最大騎士団・銀行残数・盤面全般・交易提案。
  - **秘匿（本人のみ）**: 手札の中身(`resources`)・発展カードの中身(`dev_cards`,`new_dev_cards`)・隠し勝利点(`hidden_vp`)と `total_vp`（隠し込み）。
- レスポンスに `you`（自分のpid、監視は null）を付与。

### ロビーと識別（トークン方式）
- `POST /action {action:"join", name}` → 空席に着席し `token`（16桁hex）を発行。クライアントは **sessionStorage** に保存（同一PCの複数タブでも別プレイヤー）。
- `leave`（退出・**ロビー中のみ**）: 席を**完全に削除**する。席が繰り上がるため、残った人の `slots`（選んだ番号）は詰め直す。席数が変わるので `_sync_board()` が盤面プレビューとロールを破棄する（`join` と同じ整合ルール＝全員振り直し）。1人だけになれば盤面プレビューは出ない。ゲーム進行中（`phase=='playing'`）は拒否し、監視画面の初期化でロビーに戻すよう案内する。
- `room_roll`: 2d6 を振って記録（各自1回）。`GET /room` で参加者・出目・暫定順を取得。
- `room_start`: 出目の合計が大きい順に並べ替えて着席順（`order`）を確定 → `player_id = rank`。名前を反映して `Game` を生成。
- `room_reset`: ロビーを初期化。
- `monitor_new`: 監視用に4人ホットシートの新規ゲームを開始（監視専用）。

### アクション権限
- `token` から `actor`（pid）を解決。クライアントは **自分の手番のみ** 操作可能（`CURRENT_ONLY` 集合）。
- `discard` は自分の捨て札のみ、`trade_respond`/`trade_cancel` は自分のみ。
- `give_resources`・`auto_setup`・`monitor_new` は監視（token無し）専用。
- 監視／ホットシート（token無し）は従来どおり全操作可（自動テスト互換）。

### 実装メモ
- `player.py`: 使用済み発展カードの公開ログ `used_dev_cards` を追加（`play_dev_card` で追記）。
- `game.py`: `Game(num_players, seed, names=None)` でプレイヤー名を指定可能に。
- 将来: 4人未満をAIで穴埋め（優先度低）、切断時の再接続・観戦、`prompt()` のドロップダウン化。

## 実装済みモジュール

- `game/resources.py` — 資源・地形・コスト・VP定数
- `game/board.py` — ヘックス盤面、頂点/辺グラフ、盗賊、港
- `game/player.py` — プレイヤー状態、建築、資源管理
- `game/cards.py` — 発展カードデッキ
- `game/trade.py` — 銀行/港/プレイヤー間交易
- `game/game.py` — ターン進行、セットアップ、建築、勝利判定、最長の道/最大の騎士

## ディレクトリ構成（予定）

```
catan/
├── init.md          # このファイル
├── game/            # ゲームロジック（Python）
│   ├── board.py     # 盤面・ヘックス管理
│   ├── player.py    # プレイヤー状態
│   ├── resources.py # 資源・コスト定義
│   ├── cards.py     # 発展カード
│   ├── trade.py     # 交易
│   └── game.py      # ゲーム進行・ターン管理
├── tests/           # テスト
└── ui/              # Web UI（Phase 2以降）
```

## 規約

- Python 3.x を使用
- テストは pytest で実行
- ゲームロジックはUIに依存しない純粋なPythonコードとして実装

## v25: 放置復帰とイベント通知

### 放置復帰（スマホ）
- スマホがタブを破棄すると `sessionStorage` が消え、復帰時にトークンを失って
  進行中ゲームに戻れなくなっていた。トークンを **`localStorage` ＋ タブID** で保持し、
  タブ破棄・ブラウザ再起動でも同じ席に戻れるようにした（同一PCの2タブは別プレイヤーのまま）。
- それでも席が無い（完全にセッションが切れた等）場合は、盤面に入れず
  **ロビーで「進行中には途中参加できません」と案内**する（途中参加不可はサーバー仕様と同じ）。

### 公開イベントの通知（トースト＋ログ）
- サーバー: `game.py` に公開イベントログ `add_event` を追加。記録対象は
  ダイス（7／出目）、盗賊の移動・強奪、騎士／街道建設／収穫／独占カードの使用、
  最長交易路、最大騎士力、勝利。GET `/state` が `events`（`{id,kind,text}`）を配信する。
  すべて公開情報のみ（手札や隠れVPは含めない）。
- クライアント: 新しいイベントを検知して **画面中央付近のトースト**（約3秒で消える）と
  **操作パネル下部のログ欄**（最新20件・新しいものが上）に表示。
  ダイスの出目は盤面に常時表示されているため**トーストせずログのみ**。
- 初回読み込み時は過去ログを一括トーストしない（ログには残す）。

## v26: ハウスルール追加（勝利点・数字チップ）

### 勝利点
- ロビーのハウスルールで **10点（通常）／7点（短時間）** を選べる。
- `settings.victory` に保存し、`Game(victory_target=...)` に渡す。勝利判定は
  `self.victory_target` を使う（既定 10）。

### 数字チップの配置
- ロビーで **公式準拠／ランダム** を選べる。
- `Board(numbers="official"|"random")`。
  - `official`: ルールブック通りの螺旋配置（従来どおり）。
  - `random`: 同じ18枚をランダムに並べるが、**6 と 8 が隣接しない／2 と 12 が隣接しない**
    配置だけを採用（条件を満たすまで最大400回試行、満たせない場合は公式配置にフォールバック）。
- 盤面に関わる設定を変えると地図を作り直す（ダイスの振り直しになる）。

### 変更箇所
- `game/board.py`: `numbers` モードと `_assign_numbers_random`／`_numbers_ok`
- `game/game.py`: `victory_target` と `numbers` の受け渡し
- `app_core.py`: `settings` に `numbers`／`victory`、`_numbers_mode()`／`_victory_target()`、
  値バリデーション、`room_setting` の許可キー
- `web/client.html`: ロビーに「勝利点」「数字チップ」のラジオ

## v27: スリープ復帰の修正（席の再取得）

### 原因
スマホがバックグラウンドのタブを破棄すると、`sessionStorage` に置いていた
**タブIDも消える**。トークンは `localStorage` にあったが、引くためのキーが
消えるため取り出せず、復帰すると「席を持っていない」状態になっていた。
さらに、復帰直後の1回の通信失敗でも「席が無い」と誤判定して
**トークンを削除**していた（`client.html` のロビー処理 / `game.js` の stale 処理）。

### 修正
- `catan_last_seat`（このブラウザが最後に使った席）を `localStorage` に保存。
  タブIDが消えていても、**ゲーム進行中なら自動で席を再取得**する（`recoverSeat`）。
  - サーバーに問い合わせ、そのトークンがまだ有効な席を指しているときだけ採用。
  - `catan_tab_beats` のハートビート（90秒）で**他タブが生きているか**を判定し、
    生きている席は奪わない（PCの2タブ＝2プレイヤーは従来どおり）。
- `/room` の応答が異常（通信失敗など）のときは何もしない（誤って席を捨てない）。
- `game.js`: 「席なし」が**2回連続**したときだけ切断扱いにする。

### 検証
- `test_wake.js`（単体・14項目）: タブID消失時の再取得、2タブの席を奪わない、
  無効トークンを採用しない、通常時の取得、ロビーでの再取得、後始末。
- `e2e_wake.js`（実ブラウザ・7項目）: 実行中ゲームで `sessionStorage` を消して
  リロード → 自動で盤面に復帰し、トークンが新しいタブIDに付け替わること。
