# Blender 基本事項まとめ（4.x 系想定）

> 単位・座標・操作の前提を揃えておくと、後工程（リグ・物理・書き出し）での事故が激減する。

## 1. 画面と前提設定
| 項目 | 推奨 | 理由 |
|---|---|---|
| 単位 | Metric / Unit Scale 1.0（1 BU = 1 m） | Rigify・クロス・物理は実寸前提。人物は約1.6〜1.8 BU |
| 座標系 | Z-up、-Y が正面（Front ビュー=Numpad 1 で正面が見える） | Rigify メタリグ・ミラーの前提 |
| 原点 | 人物は足元中央 (0,0,0) | 配置・リグ・書き出しが楽 |
| スケール | 編集後は **Ctrl+A → All Transforms / Scale** で適用 | 未適用だとベベル・自動ウェイト・物理が狂う |
| 保存 | Ctrl+S、File > External Data > Pack Resources でテクスチャ同梱 | 受け渡し時のリンク切れ防止 |

## 2. 最重要ショートカット
### ビュー
- 中ボタンドラッグ: 回転 / Shift+中: パン / ホイール: ズーム
- Numpad 1/3/7: 正面/右/上（Ctrl 併用で反対側）、Numpad 5: 透視/平行投影、Numpad .: 選択物にフォーカス、`~`: 視点パイ
- Alt+Z: X線（透過）切替 / Z: シェーディングパイ / Numpad /: ローカルビュー（選択物のみ表示）
- Shift+Space / N: サイドバー（寸法・ビュー設定・アドオン）/ T: ツールバー

### 共通
- Tab: オブジェクト⇔編集モード / Ctrl+Tab: モードパイ
- G / R / S: 移動・回転・拡縮 → X/Y/Z で軸拘束、Shift+X で軸除外、数値入力可（例 `R Z 90`）
- Shift+A: 追加 / X または Delete: 削除 / Shift+D: 複製 / Alt+D: リンク複製
- H / Alt+H: 隠す / 再表示、M: コレクション移動、Ctrl+Z / Ctrl+Shift+Z
- F3: 機能検索（名前で何でも呼べる）、F9 / 左下パネル: 直前操作の調整
- Shift+S: スナップパイ（カーソル→選択、選択→カーソル）/ Shift+C: カーソル原点＆全体表示
- Ctrl+P / Alt+P: 親子付け/解除、Ctrl+L: リンク/マテリアル転送

### 編集モード（モデリング）
- 1/2/3: 頂点/辺/面選択、Alt+クリック: ループ選択、Ctrl+Alt+クリック: リング選択、L: 連結選択、Ctrl+I: 選択反転
- E: 押し出し、I: 差し込み(Inset)、Ctrl+R: ループカット、K: ナイフ、Ctrl+B: ベベル（Ctrl+Shift+B 頂点ベベル）
- F: 面/辺を張る、J: 頂点間を接続、M: マージ（By Distance で重複削除）、V: リップ、Y: 分離、P: 別オブジェクトに分離
- GG: 辺/頂点スライド、Shift+N: 法線再計算、Alt+N: 法線メニュー
- Ctrl+E: 辺メニュー（シーム付け等）、U: UV展開メニュー
- O: プロポーショナル編集（ホイールで範囲）、Shift+Tab: スナップ切替

## 3. よく使うモディファイア（推奨スタック順）
1. **Mirror**（X軸、Clipping ON で中央頂点が越境しない、Merge ON）
2. **Subdivision Surface**（ビューポート1〜2 / レンダー2〜3、Catmull-Clark）
3. **Solidify**（布・鎧板の厚み付け。Even Thickness, Rim Fill）
4. **Shrinkwrap**（リトポメッシュを高ポリへ吸着、Project 方式で ±方向）
5. **Armature**（リグ変形。通常は Subsurf より上 = 先に評価させると軽い）
6. **Cloth**（物理）→ その後に Subsurf / Smooth Corrective
- その他: Bevel（ハードサーフェス、Limit Method: Angle）、Weighted Normal（ローポリのシェーディング改善）、Boolean（穴あけ・鍔の透かし）、Array + Curve（柄巻き・紐など連続パターン）、Displace、Lattice（全体形状調整）、Corrective Smooth（関節の潰れ緩和）
- **順序が結果を変える**: Mirror→Subsurf は正、Subsurf→Mirror は中央に継ぎ目が出る。

## 4. モデリング手法
- **ポリゴンモデリング（ボックス/ポリ張り）**: 立方体・円柱から押し出し、またはプレーンから一枚ずつ。ローポリ〜ミドルの人物・衣装・刀の拵え向き。
- **カーブ**: 紐・下緒・髪束・刀身の輪郭ガイドに。Bevel Depth で太さ、Taper で先細り、後で Mesh 化可。
- **スカルプト**: 有機形状。Voxel Remesh（均一密度・閉じたメッシュ必須）→ Dyntopo（局所的に細分、UV/カラー属性は消える）→ Multires（クリーンな四角面ベースが前提）。
- **ハードサーフェス**: 刀身・鍔・鎧の小札。Bevel＋Weighted Normal、またはサポートループ＋Subsurf。
- **Geometry Nodes**: 小札の並び（威毛の綴じ）、柄巻きの菱形パターンなど反復構造をプロシージャルに。

## 5. 正しいトポロジーの原則
- 変形部は**四角面(Quad)のみ**。三角形/Nゴンは平らで動かない場所へ。
- **ポール**（5本以上/3本の辺が集まる頂点）は曲がらない場所に置く（頬骨、胸の平面など）。
- 密度は均一に。急激な密度変化はシェーディングの歪みを生む。
- 法線を外向きに統一（Overlays > Face Orientation で青＝表）。
- 非多様体（Select > Select All by Trait > Non Manifold）や重複頂点を残さない。

## 6. UV 展開
- Ctrl+E > Mark Seam で継ぎ目 → U > Unwrap。シームは見えにくい所（脇の内側、脚の内側、髪の生え際、後頭部）。
- テクセル密度を揃える（顔は少し高く）。チェッカーテクスチャで伸びを確認。
- Smart UV Project はハードサーフェス（鍔・鎧板）なら十分。

## 7. マテリアル（Principled BSDF）
| 素材 | Base Color | Metallic | Roughness | 備考 |
|---|---|---|---|---|
| 刀身（研ぎ鋼） | 0.55〜0.6 灰 | 1.0 | 0.08〜0.2 | 刃文はマスクで Roughness/色を変える（刃側は白く曇る） |
| 鍔（鉄・錆仕上げ） | 暗褐〜黒 | 0.7〜1 | 0.5〜0.8 | ノイズで錆ムラ |
| 金具（銅・赤銅・金） | 素材色 | 1.0 | 0.3〜0.5 | 赤銅は黒紫、四分一は灰 |
| 漆（鞘・鎧） | 黒/朱 | 0 | 0.05〜0.2 | Coat Weight 1.0 で深い艶 |
| 鮫皮 | 白〜生成り | 0 | 0.6 | 粒状バンプ（Voronoi） |
| 絹・木綿の布 | 染色色 | 0 | 0.6〜0.9 | 絹は Sheen を上げる |
| 肌 | 肌色 | 0 | 0.4〜0.55 | Subsurface Weight 0.05〜0.2、Radius 赤>緑>青、Scale は実寸に合わせ ~0.01 m |
- テクスチャの色空間: Base Color = sRGB、Roughness/Normal/Metallic = Non-Color。

## 8. ライティング・レンダー
- EEVEE: 速いプレビュー。Cycles: 金属反射・SSS・布の陰影が正確（最終絵向け）。
- 刀は**環境（HDRI）＋細長いエリアライト**で刃の反射ラインを出すと映える。
- 3点照明（キー/フィル/リム）が人物の基本。Color Management は AgX（4.x 既定）。

## 9. リギング（概要）
- Rigify: Add > Armature > Human (Meta-Rig) → 骨を体に合わせる → Armature タブ下部 **Generate Rig**。
- メッシュ選択 → Shift でリグ選択 → **Ctrl+P > With Automatic Weights**。DEF ボーンが変形用。
- 自動ウェイトが失敗する原因: スケール未適用、重複頂点、非多様体、メッシュが極端に小さい/大きい。
- ウェイトペイントで脇・股関節・肩を修正。鎧の硬い板は **1本のボーンに100%**（または Child Of / 剛体パーツとして親子付け）にして曲がらないようにする。

## 10. 物理（クロス）
- 衣服は単純な初期形状で作る → Body に Collision、衣服に Cloth。
- 帯・腰の固定部は頂点グループで **Pin** する。
- 布が体にめり込んだ状態で開始しない。Self Collision を有効に。
- シミュ後に Apply して形状を固定、その上で Subsurf / Solidify。

## 11. 書き出し
- ゲームエンジン: FBX（Apply Transform、Forward -Z / Up Y 等エンジンに合わせる）または glTF 2.0（.glb）。
- 書き出し前: 全トランスフォーム適用、モディファイア適用確認、命名規則統一（例 `CH_Samurai_Body`, `PR_Katana_Blade`）。

## 12. Python（自動化）
- Scripting ワークスペース、`import bpy`。
- 例: 刀身の断面を作ってカーブに沿わせる、柄巻き菱形を配列生成、などは `tools/` 以下にスクリプト化可能。
