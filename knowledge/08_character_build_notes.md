# 侍キャラクター（人体モデル）制作ノート — 第2フェーズ STEP 1〜3

## 1. ベースモデルとライセンス（制作前に確認済み）
| 素材 | 出典 | ライセンス | 確認方法 |
|---|---|---|---|
| 人体ベースメッシュ `base.obj`（hm08, 約19,000頂点, 四角面主体, UV付き） | MakeHuman（MPFB 2.0.18 拡張に同梱の data/3dobjs/base.obj） | **CC0 1.0** | ファイル先頭に「This asset was explicitly released as CC0 in september 2020」と明記 |
| 形状ターゲット `*.target.gz`（年齢・性別・筋肉・人種・顔の部位など） | 同上 data/targets | **CC0 1.0** | MakeHuman 公式FAQ「Targets are CC0 no matter how you got hold of them」 https://static.makehumancommunity.org/oldsite/faq/what_changed_regarding_the_license_in_2020.html |
| MPFB アドオンのプログラムコード | extensions.blender.org/add-ons/mpfb | GPL-3.0 | `blender_manifest.toml` |

**本プロジェクトでの扱い**
- MPFB の**プログラムコードは一切使用・同梱していない**。CC0 の `base.obj` と `.target.gz` を自作スクリプトで直接読み込んでいる。
- MPFB 同梱のテクスチャ（`mpfb_*.jpg`）・ノードツリー・リグ定義は**ライセンス表記が個別に確認できないため使用していない**。
- 肌・目・髪・服のマテリアル、髪・眉・睫毛・髭のストランド、目、褌、顔と骨格の追加造形はすべて本プロジェクトのスクリプトで生成。

**商用ゲームでの利用条件**
- CC0 のため、**商用利用・改変・再配布が無条件で可能、クレジット表記も不要**（任意で「Base mesh: MakeHuman (CC0)」と記載してよい）。
- 注意点：CC0 素材は他者も同じものを使える。独自性は本プロジェクトの造形・マテリアル・髪型で担保する（下記 §3）。
- MakeHuman の asset repository など**第三者アセットは別ライセンス**のため使用しない方針。
- 法的判断が必要な場合は、最終的に法務確認を推奨（本ノートは技術的な確認結果）。

## 2. 制作パイプライン（すべて再現可能）
```
blender -b --factory-startup --python blender/samurai/build_character.py -- \
  --data <MPFB data dir> --out <render dir> --blend <out.blend> --samples 96 --hair 45000
```
| ファイル | 役割 |
|---|---|
| `blender/samurai/build_body.py` | OBJ/ターゲット読込、マクロ（男性・約31歳・筋肉0.74・体重0.30・身長1.69m・アジア88%）と部位ターゲットの適用、**独自の解剖学的造形**（眉弓・頬骨・頬のこけ・下顎角・喉仏・僧帽筋・後頭部の扁平化）、関節中心の算出 |
| `blender/samurai/lookdev.py` | 肌シェーダー（SSS・毛穴・赤み・唇・髭剃り跡・頭皮・爪）、眼球＋角膜、頭髪（茶筅髷風の髷＋元結）、眉、睫毛、口髭・顎髭、褌 |
| `blender/samurai/render_views.py` | 確認用ライティング・カメラ（正面・側面・背面・斜め45°・顔） |
| `blender/samurai/build_character.py` | 全体の組み立てと .blend 保存 |

## 3. 汎用 MakeHuman に見せないための独自要素
- **顔**：96個のターゲットを独自配合＋スクリプトによる局所造形（眉弓の張り出し、頬骨の外側強調、頬下のこけ、下顎角、喉仏）、自然な左右非対称（7箇所）。
- **頭蓋**：日本人に多い短頭傾向に合わせて後頭部を扁平化。
- **身体**：剣術向け（広背筋・前腕・大腿・下腿を強化、ボディビルダー的な胸の誇張は避ける）、身長 1.69 m。
- **髪型**：鎌倉期（対馬の時代 1274年）の武士を想定した、月代を剃らない総髪の**髷（元結で結束）**、油で撫で付けた質感、もみあげ（鬢）、うなじの生え際。
- **髭**：口髭＋顎髭（鎌倉武士に一般的）。
- **肌**：日焼けした東アジア人の肌色、ランダムウォークSSS、毛穴と細かい皺のバンプ、部位ごとの赤み。

## 4. オブジェクト構成
| コレクション | オブジェクト | 内容 |
|---|---|---|
| `SAM_Body` | `SAM_Body` | 人体メッシュ（四角面, Subdivision: viewport 1 / render 2）。カラー属性 `SkinMask`（R赤み/G唇/B髭/A頭皮）、属性 `NailMask` |
| `SAM_Head_Parts` | `SAM_Eye_L/R`, `SAM_Cornea_L/R`, `SAM_Teeth_Upper/Lower`, `SAM_Tongue` | 眼球（虹彩・瞳孔はシェーダー）、角膜（透過, 影なし）、歯・舌 |
| `SAM_Hair` | `SAM_Hair_Scalp`, `_Hairline`, `_Topknot`, `_Motoyui`, `_Eyebrows`, `_Eyelashes`, `_Moustache`, `_Beard` | Blender Hair Curves（ストランド） |
| `SAM_Clothing` | `SAM_Fundoshi` | 仮の下着（STEP 4 で和装に置換） |
| `SAM_Reference_Joints` | `J_*`（非表示 Empty） | 解剖学的関節中心（リギング用の基準） |
| `REV_Review_Scene` | カメラ・ライト・背景 | 確認用（キャラクター本体とは分離） |

マテリアル：`M_Skin`, `M_Eye`, `M_Cornea`, `M_Teeth`, `M_Mouth`, `M_Hair_Black`, `M_Hair_Fine`, `M_Motoyui_Paper`, `M_Cotton_Sarashi`

## 4b. メッシュ統計（v01）
| オブジェクト | 頂点 | 面 | 構成 |
|---|---|---|---|
| SAM_Body | 13,380 | 13,378 | **全て四角面**（三角形0・Nゴン0）、Subdivision render 2 |
| SAM_Eye_L/R, SAM_Cornea_L/R | 各1,986 | 各2,048 | UV球（極のみ三角形） |
| SAM_Teeth_Upper/Lower, SAM_Tongue | 68/68/226 | 48/48/224 | 四角面 |
| SAM_Fundoshi | 218 | 164 | 四角面＋Solidify |
| 関節基準 Empty `J_*` | 125個 | | |

## 5. アニメーション（剣術）を前提とした確認事項
- ベースメッシュは MakeHuman の**変形用エッジループ**（肩・肘・手首・指・股・膝・足首の円周ループ）をそのまま保持（頂点順序を変えていない）→ 後でリグとウェイトを付けやすい。
- 作業ポーズは**Aポーズ**（腕約45°下げ）。肩の変形に有利。
- 関節中心を `J_*` Empty として保存：肩・肘・手首・指各関節・股・膝・足首・足指。リギング時にボーン位置の基準にする。
- 指は5本×各3関節が独立、爪はシェーダーで表現。

## 6. 現時点の限界（正直な評価）
- **AAAゲームの最終品質ではない**。スキャンデータや手作業のスカルプト（ZBrush等）を使っていないため、顔の微細な造形（皺の深さ・皮膚の厚みの差）と肌のテクスチャは手描き/スキャンのAAAキャラに及ばない。
- 肌はプロシージャルシェーダー（画像テクスチャなし）。ゲームエンジン用にはテクスチャへのベイクが必要。
- 髪はレンダリング用のストランド（頭髪 67,500本＋髷 9,000本＋生え際・眉・睫毛・髭 約12,000本）。リアルタイムゲーム用にはヘアカード（板ポリ）化が必要。
- 爪は形状ではなくシェーダー表現。
- 次工程で改善できる点：顔の手作業スカルプト、法線マップのベイク、ヘアカード化、LOD。
