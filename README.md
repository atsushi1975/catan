# カタン（フル版）— スマホ対応 Web 版

> 作者: atsushi1975(Atsushi Sakamoto) / © 2026 All rights reserved([LICENSE](LICENSE))

Python のゲームロジック（フル版カタン）と、ブラウザで遊べる Web UI。
サーバーは **単一プロセス・メモリ内に状態を持つ** シンプルな構成です（DB なし）。

- プレイヤー画面: `/`（自分の手札だけ見える）
- 監視画面: `/monitor`（全情報・閲覧のみ。`?debug=1` で操作可だが `CATAN_HOTSEAT=1` 起動時のみ）

## 必要なもの

- Python 3.10 以上（標準ライブラリのみ。追加インストール不要）

## 動かし方（ローカル）

```bash
cd catan
python3 server.py          # 通常起動（監視画面は閲覧のみ）
./run.sh --hotseat        # ローカルで監視画面から操作する場合（CATAN_HOTSEAT=1）
```

起動したら、同じ PC のブラウザで次を開きます。

- プレイヤー: <http://localhost:8000/>
- 監視: <http://localhost:8000/monitor>
- 監視から操作: <http://localhost:8000/monitor?debug=1>（`CATAN_HOTSEAT=1` 起動時のみ）

### 同じ Wi-Fi に集まって遊ぶ場合

1. 1 人が「ホスト」になり `python3 server.py` を起動
2. ホストの LAN IP を確認（例: `192.168.0.13`）
3. 他の人は同じ Wi-Fi から `http://192.168.0.13:8000/` を開く

> ホストの PC が起動している間だけ遊べます。**インターネットには公開しないでください。**

## 動かし方（GitHub Codespaces：検証用）

PC を起動しなくても、クラウド上で動かして URL を配れます（無料枠あり）。

1. GitHub でこのリポジトリを開く → **Code** → **Codespaces** → **Create codespace**
2. ターミナルで:
   ```bash
   ./run.sh --codespace
   ```
3. **PORTS** タブで `8000` の行の地球アイコン（Open in Browser）を押すと公開 URL が開きます
4. その URL を遊ぶ人に共有（`/` がプレイヤー画面）
   - 監視画面は `<URL>/monitor`
5. **遊び終わったら Codespace を Stop**（無料枠の消費を止める）

> Codespaces は一定時間で自動停止します。進行中のゲームはメモリ上にあるため、
> 停止・再起動で消えます。**1 セッション内で遊び切る**使い方になります。

## 動かし方（PythonAnywhere：常時公開・無料）

無操作でスリープしないので「URL を開けばいつでも遊べる」構成にできます（無料枠）。
常駐プロセスは持てないため、**WSGI アプリ**として動かします
（`wsgi.py`。追加ライブラリ不要、標準ライブラリのみ）。

### 手順

1. **コードを配置**
   - PythonAnywhere のコンソール（Bash）で:
     ```bash
     git clone https://github.com/<あなた>/catan.git
     ```
     （Private の場合は `https://<token>@github.com/<あなた>/catan.git` など）
   - 配置先の例: `/home/<user>/catan`
2. **Web アプリを作成**
   - ダッシュボード → **Web** タブ → **Add a new web app**
   - **Manual configuration** を選ぶ → Python 3.10 以上
3. **パスを設定**（Web タブの設定欄）
   - **Source code**: `/home/<user>/catan`
   - **Working directory**: `/home/<user>/catan`
4. **WSGI 設定ファイルを編集**
   - Web タブの **WSGI configuration file**（`/var/www/<user>_pythonanywhere_com_wsgi.py`）を開き、
     中身を次で置き換えます:
     ```python
     import sys
     sys.path.insert(0, "/home/<user>/catan")
     from wsgi import application
     ```
5. **Reload** を押す → `https://<user>.pythonanywhere.com/` で遊べます
   - プレイヤー画面: `/`
   - 監視画面: `/monitor`

### 重要（無料枠の注意）

- **必ず 1 ワーカー（単一プロセス）で動かしてください。** 状態はメモリ上にあるため、
  ワーカーが複数あると「入室したのに次の操作で別人扱い」等が起きます。
  `https://<user>.pythonanywhere.com/env` を開くと `pid` と `owner_pid` を返すので、
  複数ワーカーになっていれば値が食い違って見えます（＝その場合はワーカー数を 1 に）。
- **1 日 1 回の強制再起動**があります（無料枠の仕様）。その時、進行中のゲームは消えます。
  **遊ぶ直前からセッション内で遊び切る**運用が安全です。
- `?debug=1`（監視画面を操作可能にするスイッチ）は**公開デプロイでは無効**です。
  有効になるのは `CATAN_HOTSEAT=1` を明示したときだけです（既定は無効）。
  監視専用の強力な操作も同じ条件でのみ許可されます。
- ロビーに戻す `初期化` などは、`CATAN_HOTSEAT=1` で起動したローカル環境で使ってください。

## 遊び方（概要）

1. 各自が名前を入れて **入室**
2. **サイコロを振る** → 出目の大きい順に、盤面を見ながら **何番目に手番が回るか** を指名
3. 全員が指名したら **ゲーム開始**
4. 以降は盤面の指示に従って操作（建設・交易・発展カード・盗賊など）
5. 誰かが勝利したら、**全員の所持発展カードが公開**されます（使用済み／未使用が分かる）
6. ロビーに戻したいときは、監視画面（`/monitor`）の **初期化** ボタン（`CATAN_HOTSEAT=1` 起動時のみ）

### スマホでの操作

盤面が主役のレイアウトです。画面下の「▲ 操作パネルを開く」で操作パネルが開きます
（捨て札・盗賊・初期配置のときは自動で開きます）。

### 盤面の見た目

HEX マスは地形ごとの**手続き型テクスチャ**（木・土・羊・麦・鉄・砂漠）で描画します。
画像ファイルは使わず、起動時に一度だけ生成してキャッシュするので追加アセットは不要です。

開拓地・都市・街道もベクターで描いた**初代カタンの木製ブロック風**の駒（細い黒い輪郭付き）です。
島の周囲は**シームレスな海**（角丸の正方形、港のラベルまで含む範囲）で、地形テクスチャと同じ手描き風のトーンです。
ゲーム中は現在の出目を**盤面右下の 2 個のダイス**（テクスチャ付き、1 の目のみ赤）で表示します。港ラベルは隠しません。

### ハウスルール

ロビーで**初期砂漠**の置き方を選べます（`センター固定` / `海岸砂漠NG`（既定）/ `固定なし`）。
変更すると盤面を作り直します（ダイスは振り直しになります）。

## セキュリティ / 公開ポリシー

- **`/state` は3種類の見え方**に分かれます。
  - 有効なトークン付き → そのプレイヤーの**自分の手札だけ**（他人の手札・隠し勝利点は見えない）
  - トークンなし / 不正トークン → **観戦（公開情報のみ）**。誰の手札・隠し勝利点も含まれません
  - **監視画面**（`/monitor`）→ `CATAN_HOTSEAT=1` のときだけ全公開（監視の役割）。
    `view=monitor` を付けても、ホットシートモードが無効なら観戦のままです
- **トークンなしの操作は既定で拒否**されます。`roll` / `end_turn` / `build_*` / `discard` / `trade_respond` などを
  トークンなしで送っても「この操作はホットシートモードでのみ行えます」で弾かれます。
- トークンなし操作を許可するのは、**`CATAN_HOTSEAT=1` を明示したときだけ**です。
  クライアントの IP や `X-Forwarded-For` では判定しません（プロキシ配下でも乗っ取れません）。
  ```bash
  CATAN_HOTSEAT=1 python3 server.py   # ローカルのホットシート専用。公開サーバーでは使わない
  ```
- 監視専用の強力な操作（`初期化` / `新しいゲーム` / `自動配置` / `資源付与`）も、
  `CATAN_HOTSEAT=1` のときだけ許可されます。
- ポートは `CATAN_PORT` で変更できます（既定 8000）。

## テスト

追加依存なし（標準ライブラリのみ）。全テストをまとめて実行します。

```bash
for t in tests/test_*.py; do python3 "$t" || exit 1; done
```

個別に実行する場合:

```bash
python3 tests/test_basic.py
python3 tests/test_build.py
python3 tests/test_rules.py
python3 tests/test_vp.py
python3 tests/test_dev_reveal.py  # 勝敗後の発展カード公開
python3 tests/test_authz.py       # トークンなし/不正アクセスの拒否
python3 tests/test_house_rules.py # ハウスルール（初期砂漠）
python3 tests/test_wsgi.py        # WSGI (PythonAnywhere) 経由の E2E
```

GitHub Actions（`.github/workflows/test.yml`）が pull request と `main` への push で
Python 3.10 / 3.12 の全テストを実行します。`main` への push では、このテストが
通った場合のみ VPS へデプロイされます（`.github/workflows/deploy.yml`）。

## 構成

```
catan/
├── app_core.py      # ゲーム/ロビー状態とルーティング（HTTP 非依存・共通）
├── server.py        # ローカル/Codespaces 用 HTTP サーバー（app_core を使う薄い層）
├── wsgi.py          # PythonAnywhere 用 WSGI アプリ（app_core を使う薄い層）
├── cli.py           # テキストでロジックを試す CLI
├── run.sh           # 起動スクリプト
├── game/            # ゲームロジック（UI 非依存）
│   ├── board.py     # 盤面・頂点/辺・港
│   ├── player.py    # プレイヤー状態・建築
│   ├── resources.py # 資源・地形・コスト
│   ├── cards.py     # 発展カード
│   ├── trade.py     # 銀行/港/プレイヤー間交易
│   └── game.py      # ターン進行・セットアップ・勝利判定
├── web/             # フロントエンド
│   ├── client.html  # プレイヤー画面
│   ├── index.html   # 監視画面
│   ├── game.js      # 盤面描画・操作（共通）
│   └── style.css
└── tests/           # テスト
```

ゲームの状態は `app_core.ROOM`（メモリ上）にあります。`server.py` と `wsgi.py` は
同じ `app_core` を共有する薄いアダプタなので、どちらで動かしても挙動は同じです。
**必ず 1 プロセスで動かしてください**（複数ワーカーだと状態が分裂します）。

詳細な設計・ルール対応は `init.md` を参照。
