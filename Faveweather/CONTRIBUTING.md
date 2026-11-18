# コントリビュートの仕方 / Contributing

FaveWeather への協力、ありがとうございます！ / Thanks for helping out!

## バグ報告・要望 / Issues
- バグは **Issues → Bug report** から。ブラウザ（Chrome / Safari など）と端末、できればスクリーンショットを添えてください。
- 要望は **Issues → Feature request** から。

## コードを変える / Pull requests
1. このリポジトリを Fork して、ブランチを作る（例：`fix/export-flicker`）
2. 変更して、ブラウザで `index.html` を開いて動作を確認
3. Pull Request を作る。何を・なぜ変えたかを一言で

### 構成 / Layout
| ファイル | 中身 |
| --- | --- |
| `index.html` | Web アプリ本体（HTML・CSS・JavaScript・WebGL2 シェーダーを 1 ファイルに） |
| `blender/faveweather_importer.py` | Blender アドオン（Blender 4.2 以降） |
| `docs/images/` | README 用の画像 |

### お願い / Notes
- **UI は画面の下にまとめる**（上には置かない）のがこのアプリのルールです。
- 文言を足すときは 6 言語（ja / en / zh / ko / es / fr）すべてに入れてください。分からない言語は英語のままで OK。
- Blender アドオンを変えたら、`index.html` の中に埋め込んであるアドオン（`BLENDER_ADDON_SRC`）も同じ内容に更新してください。設定画面の「Blender 用アドオンをダウンロード」はそこから配っています。

ライセンスは MIT です。送ってもらった変更も MIT で公開されます。
