# 安装

[← 返回 README](../README.md) · [English](install.md)

本页只讲一件事：用**你自己的**游戏文件，在 Mac、iPhone 或 iPad 上打包出 App。一次打包 20–40 分钟，大部分时间是等待。操作与设置见 [controls.zh-CN.md](controls.zh-CN.md)，测过什么见 [test-records.zh-CN.md](test-records.zh-CN.md)。AI 助理：同样的步骤写成了清单，在[安装 skill](../.claude/skills/install-zelda/SKILL.md) 里。

目录：[需要准备](#需要准备) · [打包 App](#打包-app) · [旷野之息](#旷野之息) · [iPhone 和 iPad](#iphone-和-ipad) · [Apple Vision Pro](#apple-vision-pro) · [更新 App](#更新-app) · [打包报错](#打包报错) · [文件位置](#文件位置) · [已知问题](#已知问题)

基本规则：
- 只用你自己的 Switch 和你自己的游戏导出的文件。打包不会替你下载任何东西，本仓库里也没有游戏内容。
- 不要为了绕过检查去改 `games/totk/assets/expected-*.json` 或脚本：报错信息会说明哪里不对。
- 打包出的 App 里含有游戏，只供你自己使用。

## 需要准备

**Mac**：Apple 芯片，**macOS 26** 或更高（图形用 Metal 4），建议 16 GB 或更多内存。
还在用 macOS 15 的，用 [1918662410-ship-it 的社区 fork](https://github.com/1918662410-ship-it/MacNativeGames)，它加了 Metal 3 后端（本仓库不测）。

**游戏文件**：从你自己的 Switch 导出。标题 ID 一般写在文件名的方括号里；打包认的是文件内容，不看文件名。

| 标题 ID | 是什么 | 命令里放在 |
|---|---|---|
| `0100F2C0115B6000` | 王国之泪本体 **1.0.0**，XCI 或 NSP | 第一个参数 |
| `0100F2C0115B6800` | 王国之泪更新 **1.1.2、1.2.1 或 1.4.3**，NSP 或 NSZ（可选） | `--update` |
| `01007EF00011E000` | 旷野之息本体，或 **1.6.0** 卡带镜像（本体、更新、DLC 在同一个 XCI 里） | 第一个参数 |
| `01007EF00011E800` | 旷野之息更新 **1.6.0 或 1.9.0**，NSP 或 NSZ | `--update` |
| `01007EF00011F001`、`01007EF00011F002` | 旷野之息的两个 DLC 包，NSP（都可选） | `--dlc`，每个包一次 |

- 王国之泪推荐 **1.4.3**：测得最多，也是唯一在 iPhone / iPad 上测过的版本。不需要中间版本的更新。不加 `--update` 打出来的是 1.0.0。
- 本体不能是压缩格式。NSZ / XCZ 本体先解压（`nsz -D`）。
- 卡带镜像里自带了更新也可以，版本仍由 `--update` 决定。

**`prod.keys`**：从同一台 Switch 导出（Lockpick_RCM）。在旧固件上导出的密钥，可能解不开较新的更新。

**系统字体**：本体是 **NSP** 时需要，**旷野之息**一律需要。二选一：
- `--firmware <文件夹>`：你导出的固件，一个装着 `.nca` 文件的文件夹（压缩包先解开），或已安装固件的 `registered` 文件夹。
- `--shared-fonts <文件夹>`：以前打包王国之泪时提取出的六个 `.bfttf` 文件，在 `TOTK_build/totk/extracted/firmware/shared-fonts`。

王国之泪的 XCI 自带字体，不用另给。

**磁盘空间**（工作目录所在的卷）：

| | Mac | iPhone / iPad |
|---|---|---|
| 只有本体 | 25 GB | 45 GB |
| 加更新 | 40 GB | 60 GB |

工作目录默认建在游戏文件旁边（`TOTK_build`；旷野之息是 `BotW_build`）。工作目录和 App 放在**同一个 APFS 卷**上：17 GB 的游戏数据是克隆过去的，不额外占空间。游戏文件在 exFAT / FAT 盘或快满的盘上时，用 `--work <文件夹>` 和 `-o <App>` 放到有空间的 APFS 盘上。

## 用窗口打包

不想敲命令的话：装好下面第 1 步的工具（窗口还要 `brew install python-tk@3.14`），在这个文件夹里双击 **Build Game.command**（或运行 `python3.14 -m tools.builder`），会打开一个窗口（界面是英文的，下面按钮名照原样写）：

- **Build**（打包）：选游戏，再选游戏文件、更新、`prod.keys`，游戏需要时再选固件或系统字体文件夹（工作目录和输出的 App 在 **Advanced** 里）。**Check files** 会检查这台 Mac 和你的文件，有问题就列出来，能修的附上修复命令。**Build app** 用这些路径运行 `build_app.py`，显示四个阶段、用时和日志；打完一键 **Open app** 或 **Show in Finder**。**Cancel** 会中断打包，下次用同一个工作目录再打会接着做。窗口只记住你选的路径，不复制文件；日志在 `~/Library/Logs/MacNativeGames/builder-<游戏>-<日期>-<时间>.log`。打包时别关掉跟着打开的终端窗口。
- **Settings**（设置；王国之泪 1.4.3、旷野之息 1.9.0）：开局画面、补帧（这台 Mac 的显卡支持 Metal 4 MetalFX 补帧时才有）、边缘平滑、远处地面更清晰，1.4.3 还有画面比例。**▶ Play** 启动游戏。画面、补帧、边缘平滑、画面比例就是游戏里设置面板（1 键）存的那份设置，从访达打开也生效，在哪边改都一样；只有“远处地面更清晰”面板里没有，只在用 **▶ Play** 启动时生效。游戏开着时不改设置，先关掉游戏。
- **Mods**（模组；王国之泪 1.4.3、旷野之息 1.9.0）：**Add mod...** 选你自己的模组文件夹（带 `romfs/`；王国之泪的代码补丁放 `exefs/`），窗口不带任何模组。每个模组都会对照打好的 App 检查，路径对得上这个版本才能打开；**Apply mods** 按顺序（下面的优先）装进游戏的模组文件夹，原来的文件夹留作备份，下次启动游戏生效。TKMM、BCML 的包不收，请用它们自己的管理器装。
- **Controls**（按键）：在手柄图上改键位，存进 `controls.txt`；王国之泪还能顺带把游戏里的按键图标换成对应的样子。
- **更新**：用 `git clone` 下载的，窗口打开时会看 MacNativeGames 的 `main` 有没有新提交；在 `main` 上点 **Update** 只做快进，本地改过文件或有自己的提交时不动、告诉你。更新后关掉窗口重新打开，再打包一次。用 ZIP 下载的不能自己更新，请重新下载。

没有 Tk 时 **Build Game.command** 会提示。同样的检查和打包也能在终端里用文字模式跑：

```sh
python3.14 -m tools.builder --cli --game totk --game-file ~/Games/totk.xci --keys ~/keys/prod.keys --check-only
```

`--dry-run` 只打印要运行的 `build_app.py` 命令；`python3.14 -m tools.builder --help` 列出全部选项。

**下载 ZIP 后第一次双击**：macOS 会拦下没打开过的下载脚本。在**系统设置 › 隐私与安全性**里对 `Build Game.command` 点**仍要打开**，或在这个文件夹里运行一次 `xattr -d com.apple.quarantine "Build Game.command"`。用 `git clone` 下载的不受影响。

## 打包 App

**1. 装工具**（只需一次，要联网）：

```sh
xcode-select --install
# 没有 Homebrew 的话，按 https://brew.sh 安装（必须装在 /opt/homebrew）
brew install opus libvpx python@3.14
brew install python-tk@3.14   # 只有打包窗口需要（见上面“用窗口打包”）
```

也可以不用 Homebrew 的 Python，改用 [uv](https://docs.astral.sh/uv/)：把 `python3.14 build_app.py …` 换成 `uv run --python 3.14 build_app.py …`。

可选（装了完整 Xcode 时）：`xcodebuild -downloadComponent MetalToolchain`。
- 装了它，打包时会把启动着色器直接编进 App：App 之后可以随意挪动，重新打包也更快。
- 不装也能打包，着色器会编进 macOS 的 Metal 缓存，绑定 App 所在的位置。

**2. 取得本仓库**：`git clone https://github.com/ly05010419/MacNativeGames.git`（或下载 ZIP），然后在 `MacNativeGames` 文件夹里打开终端。已经有的，先 `git pull`：很多打包报错在 `main` 上早就修好了。

**3. 打包。** 每个路径都加引号。用 `-o` 一次定好 App 的最终位置：Mac App 之后再挪动，第一次启动会重新编译着色器（装了 Metal 工具链的除外）。不加 `-o` 时，App 放在游戏文件旁边。

```sh
# 王国之泪 1.4.3，本体是 XCI
python3.14 build_app.py "<本体 1.0.0.xci>" -k "<prod.keys>" --update "<1.4.3 更新.nsp>" -o "/Applications/Tears of the Kingdom.app"

# 王国之泪 1.4.3，本体是 NSP：还要给字体
python3.14 build_app.py "<本体 1.0.0.nsp>" -k "<prod.keys>" --update "<1.4.3 更新.nsp>" --firmware "<固件文件夹>" -o "/Applications/Tears of the Kingdom.app"
```

`/Applications` 和工作目录不在同一个卷上时，`-o` 改用工作目录所在卷上的文件夹。

**4. 让它跑完。** M 系列 Mac 上从头打包要 **20–40 分钟**，8 GB 内存的 Mac 更久：

| 步骤 | 时间 |
|---|---|
| `1/4 code`：把游戏代码改写成 Apple 芯片版 | 约 3 分钟 |
| `2/4 data`：提取并校验 17 GB 数据，合并更新 | 几分钟 |
| `3/4 shaders`：准备启动着色器 | 约 3 分钟 |
| 为本机 GPU 编译着色器 | 6–12 分钟 |
| `4/4 app`：macOS 检查一次新 App | 2–3 分钟 |

- 长时间没有新输出、或出现 `... still running (3 min)`，都是正常的，不要停。
- 万一被打断，原样再跑**同一条命令**：已完成的步骤保存在工作目录里，会直接复用。
- 打包前先退出游戏。同一个工作目录不要同时跑两次打包。
- 最后几行出现 `done in N min: <App 路径>` 就是成功了。

**5. 打开 App**（在访达里打开）：
- 启动画面先校验游戏数据（约 20 秒），再准备着色器和管线，有进度条。第一次启动要 1–2 分钟，之后约 12 秒。
- 打包后又把 App 挪到别的卷，macOS 会重新检查一遍：几分钟内不出窗口，等着就行。
- macOS 询问是否允许访问可移除宗卷上的文件时，点“允许”。
- 第一次到新地方可能短暂卡顿。
- **1** 键打开设置面板。操作说明见 [controls.zh-CN.md](controls.zh-CN.md)。

## 旷野之息

同一个脚本也能打包旷野之息，但一律要给字体（见[需要准备](#需要准备)）。工作目录是 `BotW_build`，App 是 `Breath of the Wild.app`。M4 上从头打包约 16 分钟。

```sh
# 1.6.0，卡带镜像（本体、更新、DLC 在同一个 XCI 里）
python3.14 build_app.py "<旷野之息 1.6.0.xci>" -k "<prod.keys>" --shared-fonts "<…/TOTK_build/totk/extracted/firmware/shared-fonts>" -o "/Applications/Breath of the Wild.app"

# 1.9.0（或 1.6.0），用 NSP：本体加更新，DLC 包都可选
python3.14 build_app.py "<旷野之息本体.nsp>" -k "<prod.keys>" --update "<1.9.0 更新.nsp>" --dlc "<DLC 1.nsp>" --dlc "<DLC 2.nsp>" --firmware "<固件文件夹>" -o "/Applications/Breath of the Wild.app"
```

用单独的更新包时，App 里只有你用 `--dlc` 给的 DLC 包。卡带镜像自带 DLC，这时不要加 `--dlc`。

## iPhone 和 iPad

**需要：**
- iOS / iPadOS 26，iPhone 14 或更新的机型。
- Mac 上装好完整的 **Xcode 26** 或更高版本（含 iOS 平台），再 `brew install xcodegen cmake ninja`。
- 在 Xcode › Settings › Accounts 里登录你的 Apple ID（免费账号也行）。
- 设备上打开开发者模式。

**1. 打包 IPA。** 在上面的 Mac 命令后加 `--platform ios --ios-game-data documents`，`-o` 写成 `.ipa` 文件：

```sh
python3.14 build_app.py "<本体 1.0.0.xci>" -k "<prod.keys>" --update "<1.4.3 更新.nsp>" --platform ios --ios-game-data documents -o "<文件夹>/Tears of the Kingdom.ipa"
```

- 第一次打 iOS 包时，还会下载并编译设备用的库。
- `--ios-game-data documents` 不把 17 GB 的游戏镜像放进 IPA，以后重装只要几分钟。
- 打包时用数据线连着 iPhone / iPad：打包会在 Mac 上为它的 GPU 编好游戏的管线（第一次多约 10 分钟），首次启动进标题前就不用长时间填充。设备没连着时加 `--device-gpu <架构>`（iPhone 14 是 `applegpu_g14p`）。

**2. 安装**，设备用线连着 Mac：

```sh
python3.14 games/totk/ios/tools/install_device.py "<文件夹>/Tears of the Kingdom.ipa" --device "<访达里显示的设备名>" --game-data "<工作目录>/totk/extracted/<版本>/romfs/romfs.bin"
```

- `<版本>` 填那里实际有的文件夹（1.4.3 是 `v143`；用 `ls "<工作目录>/totk/extracted"` 看）。第一次安装会把 17 GB 的镜像拷过去一次。
- iPhone / iPad 只连着 Wi‑Fi 时脚本会停下：插上数据线、解锁设备，再跑一次。加 `--wifi` 也能走 Wi‑Fi 装，但很慢，游戏数据可能传到一半断开。
- 免费 Apple ID 的签名 7 天有效，付费账号一年。到期后再跑同一条命令续签，存档会保留。
- 设备提示时，到“设置 › 通用 › VPN 与设备管理”里信任开发者。

**3. 第一次启动：** iPhone 14 上先校验游戏数据约 15 秒，再导入着色器约 3 分钟，然后出标题。之后约 8 秒出标题。

手机上内部按 960×540 渲染，放大到 1280×720，最高 60 帧。旷野之息 1.6.0 也按同样的方法打包安装。

两个限制：
- 手机不能边玩边翻译着色器。App 里没带的着色器变体会被跳过，所以还没有玩家报告过的地方可能少画一些东西。
- iPhone 14 上，在复杂区域内存耗尽时 iOS 可能会关掉游戏。

### 大贴图

GPU 画游戏贴图时，用的是 App 为 Metal 复制的一份副本。为省内存，iPhone 和 iPad 上带多级 mip 的大贴图（同一张贴图存成好几种尺寸，每种尺寸叫一级，每一级的长宽都是上一级的一半），副本少传最高一级，也就是最大的那一级，所以近处看可能模糊一级。下面保留全部级的贴图、“大贴图”设置和 GPU 写过的副本的处理，都还没有在设备上试过（2026-10-26）。

- 大贴图指两边都至少 512 像素、带多级 mip 的 2D、数组或立方体贴图。`TOTK_MIP_DROP_MIN` 可以改这个 512。
- 凡是游戏或着色器按编号指定级或纹素（贴图里的一个像素）的地方，少一级的副本都会给出错误的数据。所以下面这些贴图保留全部级：
  - 游戏往里渲染、拷贝或清空的贴图；
  - 着色器按纹素位置读取、用 `gather` 采样，或查询尺寸或级数的贴图；
  - 作为图像绑定（着色器可写）的贴图；
  - 在顶点或计算着色器里采样的贴图；
  - 通过不带 mip 的采样器绑定的贴图，以及通过 LOD（细节级别，即可以读哪几级）范围止于 1 以下或从 1 起的采样器绑定的贴图；
  - 通过只含前几级的视图绑定的贴图。
- 在系统“设置” App › App › Tears of the Kingdom › 大贴图里三选一，重新启动游戏后生效。“省内存”是默认值。“保留更多级”另外保留片元着色器按指定级采样或查询 LOD 的贴图（等同 `TOTK_MIP_KEEP=2`）。“完整”让所有贴图保留全部级，占用内存最多（等同 `TOTK_MIP_DROP=0`）。
- 启动环境里的变量优先于设置。在 Mac 上可以用 `devicectl` 的 `--environment-variables` 设置这些变量。设 `TOTK_MIP_KEEP=0` 时这些规则都关掉，和 2026-10-26 以前一样：上面列出的贴图也少传最高一级。游戏往里渲染的贴图是例外：它在下一次使用时换成全尺寸的副本，但第一遍渲染画进去的内容会丢失。`TOTK_MIP_KEEP_BINDS=0` 只关掉最后两类（通过这类采样器或视图绑定的贴图）的规则，其他几类照常保留全部级。
- 在 iPhone 和 iPad 上，GPU 写入过的副本（用拷贝命令、清空或经图像绑定写入）不会被标成可清除（系统缺内存时可以收回这块内存），也不会被淘汰（App 内存快不够时丢掉副本）。`TOTK_TEX_KEEP_GPU_WRITTEN=0` 恢复以前的行为，`TOTK_MIP_KEEP=0` 不影响这一项。
- 打开日志时，日志会写明用的是哪种模式（“大贴图副本少传最高一级 mip：…”“大贴图副本保留最高一级：…”）。设了 `TOTK_MIP_KEEP_BINDS=0` 时，日志还会写明绑定的规则已关（“大贴图副本保留最高一级：按采样器 / 视图绑定保留的规则关…”）。“大贴图副本保留最高一级：累计标记 …”一行统计标成保留全部级的贴图，每张只算一次，按最先标记它的原因归为三类：渲染目标、GPU 拷贝或清空（上面列表的第一类，日志里写作“渲染目标 / GPU 拷贝 / 清除”）；采样器或视图绑定（最后两类）；着色器槽（由着色器自己怎样用这张贴图决定：第二到第四类，以及“保留更多级”另外保留的贴图）。每 600 次提交（游戏每把一批 GPU 命令交出去算一次提交），“贴图副本可清除：…”一行还会给出保留全部级的大贴图副本（不含渲染目标）的张数和占用的内存，这是各种原因的合计。
- 地底林克附近边缘呈阶梯状的假瘴气（#337）怀疑来自少一级的副本，尚未确认。对照方法：在 #337 给出的地点，三个选项各玩一次。“完整”下没有任何贴图被缩小，所以如果“完整”下假瘴气还在，原因就在别处。有 Mac 的话，还可以用 `TOTK_MIP_KEEP_BINDS=0`（只关掉绑定的规则）和 `TOTK_MIP_KEEP=0`（关掉上面列出的这些保留规则）各玩一次，同样和默认设置对照。

### 没有卡带镜像和密钥：在 Windows 上用旧 IPA 重新打包

如果已经没有卡带镜像、更新包或 `prod.keys`，但还留着 `build_ipa.py` 在提交 30a1b93 打出的 1.4.3 IPA（RomFS 在 App 里，签没签名都可以），可以在 Windows 电脑上用它做出新的 App。下面的工具从这个 IPA 还原游戏文件，重做启动着色器（App 第一次启动时导入的着色器种子）。它们取用 GitHub Actions 只用本仓库构建的运行时（不含游戏代码和数据的 App），把这些拼起来，签名并安装。脚本需要 Python 3.14，除 `push_device_windows.py` 外只用标准库。`push_device_windows.py` 还要用 pymobiledevice3：运行它的 Python 里没有这个包时，它会换到 pymobiledevice3 自己的 Python 里重新运行。在仓库目录里用 `python` 运行这些脚本（用 `python -I` 也可以）。它们调用的其他程序列在下面。截至 2026-10-26，第 1、2、4 步已在 Windows 上实际运行，第 3 步已在 GitHub Actions 上运行。第 5 步用 `--simulate`（用本地文件夹代替设备）演练过。这些步骤都还没有对真机跑过。

本分支合并上游 `f1d0077`（2026-10-30）之后的运行时，暂时不能和 30a1b93 打的 App 的代码节一起启动。iPhone / iPad 的运行时现在要求 main 的代码节里已经写好 1.4.3 针对 60 帧以上渐隐计数的修正：四处跳转，以及代码末尾之后新增的 80 字节代码（`games/totk/runtime/game_patches_v143.c` 的 `patch_fade_increment`）。这些代码节里没有它，按代码，游戏会在启动时以“1.4.3 embedded fade patch mismatch”停下。启动环境里设 `TOTK_FADE_FIX=0` 或 `TOTK_HIGHFPS_FIX=0` 可以跳过这项检查，但玩家从主屏幕打开的 App 拿不到这样的变量。要先由打包把这项修正写进代码节，并让布局文件写明改过之后的代码节哈希，这条路线才能再用；这一步还没有做。

需要准备：

- Python 3.14。做着色器另外需要 Visual Studio（“使用 C++ 的桌面开发”和“适用于 Windows 的 C++ Clang 工具”）、.NET 10 SDK、Git for Windows（用它的 `patch`），第一次运行时还要联网。
- GitHub 账号和本仓库的 fork。
- 你的开发证书和私钥（`.p12`）、存放 p12 密码的文件，以及开发描述文件（`.mobileprovision`）：要包含 App 的 bundle id 和你的设备，并授予 `com.apple.developer.kernel.increased-memory-limit`。签名前工具会检查描述文件的平台、有效期、bundle id 和授权（`get-task-allow` 和提高内存上限）。它还检查描述文件里是否列有 `.p12` 里的证书。设备列表不检查。想保留存档，就用设备上那个 App 的 bundle id 和团队。
- zsign（`--zsign`、`TOTK_ZSIGN` 或 `PATH`）和 Git for Windows 自带的 `openssl`（`mingw64` 下的那个也能读“钥匙串访问”导出的 p12）。
- 用 uv 或 pipx 安装的 pymobiledevice3（`uv tool install pymobiledevice3`），以及提供 USB 连接服务的 iTunes 或 Apple Devices。设备用数据线连接并解锁；和所有开发签名的 App 一样，设备要打开开发者模式。

**1. 还原游戏文件**，放到仓库以外的工作目录：

```powershell
python games/totk/ios/tools/recover_ipa.py <旧的 TOTK.ipa> --out <工作目录>/totk
```

每个文件放到位之前都要核对：三个改写后的代码模块和 `expected-v1.4.3.json` 核对，App 嵌入的九个代码节（main、subsdk0、sdk 三个游戏模块各三节）和 `games/totk/ios/ci/embed-layout-v143.json` 核对，RomFS 核对固定的大小和 SHA-256，字体按从卡带镜像构建时的规则接受（与固定的 SHA-256 一致，或是有效的 Switch BFTTF 格式字体文件），覆盖文件和它们的 `manifest.tsv` 以及 RomFS 核对。任何一项核对失败就立即停下，不写 `recover-manifest.json`，所以别的构建打出的 IPA 会被拒绝。解压 17 GB 的 RomFS 在 SSD 上约 2 分钟；再次运行会复用它（约 10 秒），加 `--skip-romfs` 则留到以后再解压。IPA 自带的着色器属于旧的翻译链，不还原。

**2. 做着色器种子：**

```powershell
python games/totk/ios/tools/seed_windows.py tools --work <种子工作目录>
python games/totk/ios/tools/seed_windows.py seed --work <种子工作目录> --romfs <工作目录>/totk/extracted/v143/romfs --modules <工作目录>/totk/rewritten/v143 --version v143
```

`tools` 构建 `build_app.py` 固定提交的 SPIRV-Cross（源码先和 GitHub 给出的该提交的源码树核对）和 win-x64 版着色器翻译器，放在 `<种子工作目录>/tools/bin`。`seed` 写出 `<种子工作目录>/seed`：1.4.3 约 3.1 万个变体，第一次约 11 分钟，之后会复用已有的翻译。

**3. 在 GitHub Actions 上构建运行时。** 工作流 `.github/workflows/ios-runtime.yml` 在 `macos-26` 机器上只用本仓库构建 App 的可执行文件（`build_ipa.py --runtime-only --embed-layout games/totk/ios/ci/embed-layout-v143.json`），游戏的九个代码节留成全零。在你的 fork 的 Actions 页启用 Actions。推送到分支 `ios-windows-fixes` 的改动涉及 `games/totk/**` 或工作流文件时，工作流就会运行。工作流文件进了 fork 的默认分支后，也可以用“Run workflow”手动运行。下载这次运行的产物 `totk-ios-runtime`（保留 14 天）并解压一次，里面是 `TOTK-runtime.zip`。这个 zip 里有 `TOTK.app` 和 `TOTK-runtime.commit`，后者写着这次运行构建的提交，下一步从这里读取。这样不会有任何游戏内容传到 GitHub，也绝不能传：工作目录、种子、IPA 以及用它们编出的 Metal 库都不要提交，也不要上传。

**4. 打包并签名：**

```powershell
python games/totk/ios/tools/package_ipa_windows.py <目录>/TOTK-runtime.zip --tree <工作目录>/totk --seed <种子工作目录>/seed --out <目录>/TOTK.ipa --p12 <证书.p12> --p12-password-file <密码文件> --profile <描述文件.mobileprovision> --zsign <zsign.exe>
```

它把九个代码节写进运行时。每一节都要和布局文件里的大小、SHA-256 以及可执行文件自己的代码节哈希表核对。然后它加上游戏数据。bundle id 取自描述文件，显示名和图标取自旧 App。版本号和构建号沿用旧 App 的（试过的那个 App 是 1.4.3 和 2610.22.1）。最后用 zsign 签名并校验签名。`TOTK.ipa` 旁边还会写出 `TOTK-unsigned.ipa`（临时签名，给别的签名工具用）、`TOTK-shader-seed`（设备用的种子形式）和 `TOTK-package.json`。17 GB 的镜像和种子都不进 IPA（`--game-data documents`，默认）。Windows 上的 zsign 1.1.2 给 4 GiB 及以上的文件记下错误的哈希，所以在 Windows 上签名的 App 不能带镜像。`--game-data app` 把镜像和种子放进 App。它必须和 `--unsigned-only` 一起用，否则工具报错停下。两者一起用时，工具只写出未签名的 IPA，留给 Mac 签名。

工具从 `TOTK-runtime.commit` 读出构建运行时的提交，并在第 3/6 步打印（“source commit: …”）。这个提交写进 `TOTK-package.json`；旧 App 的 `Info.plist` 里有 `TOTKSourceCommit` 这一项时，也写进这一项。`--source-commit <提交>` 可以手动指定提交，优先于这个文件。工作流开始写这个文件之前的 `TOTK-runtime.zip` 里没有它，这时工具记下当前检出的 HEAD 并打印警告，所以这样的运行时要用 `--source-commit` 给出那次运行构建的提交。在测试用的 Windows 电脑上（2026-10-26），第一次带种子打包约 8 分钟，同时写出设备用的种子文件夹（91,304 个文件，几乎都是指向种子的硬链接）。同一种子再打包不到 1 分钟。

**5. 安装并复制游戏数据：**

```powershell
python games/totk/ios/tools/push_device_windows.py deploy <目录>/TOTK.ipa --romfs <工作目录>/totk/extracted/v143/romfs/romfs.bin --backup-to <备份目录>
```

`deploy` 先备份已安装 App 的存档（`--backup-to`，或用 `--no-backup` 不备份），再覆盖安装。然后它把镜像复制成 App 的 `Documents/GameData` 里每份 1 GiB 的 `romfs.bin.000`、`.001`……（只复制一次，之后的安装都保留；中断后再运行会接着已有的分片继续）。最后，设备上还没有 IPA 旁边的种子时，它把种子作为一个包复制过去。`install`、`romfs`、`seed`、`backup-save` 各做 `deploy` 的一步。`restore-save` 恢复备份，`status` 显示设备上已有的内容（App 版本、镜像分片、种子和存档）。`--udid` 指定设备，`--simulate <文件夹>` 不连设备演练，`check` 不连设备检查 pymobiledevice3。如果游戏提示没有游戏数据或没有着色器（提示里写的是 Mac 上的 `install_device.py`），加 `--romfs` 再运行一次 `deploy`。

在 Mac 上打包、打包时设备用线连着的 App 带着 Mac 为设备 GPU 编好的管线，第一次启动直接从中取用，不用填充管线存档（见上文 `--device-gpu`）。在 Windows 上打包的 App 不带。**第一次启动**先解包着色器（“正在准备着色器（更新后只做一次）”），再校验游戏数据。解包完成之前，包和解出的文件夹都在设备上，各约 1.2 GB。在 Windows 上做的种子不带 Metal 库（补上的方法见下文）。所以出标题之前，设备要从 MSL（Metal 着色语言源码）编出这些库：种子的管线清单（`pso_title.tsv`、`pso_list.tsv` 和 `pso_manifest.tsv`，列出进游戏前要建的管线）里每条管线用到的库。屏幕上先显示“预热着色器与管线 N%”，这时建的是标题画面的清单。然后依次显示“检查管线存档”和“首次启动编译着色器 N%（以后启动会快）”，下面是已建 / 要建的管线数。满 1 分钟且建完 2% 后，这一行改为“首次启动编译着色器 N%，约剩 M 分钟”。以后启动时，管线存档可能仍然有效，只是缺了共享清单（`pso_list.tsv`）里的一些管线，例如第一次启动在出标题前中断了、清单里有新加的行，或以前建失败、因而没写进存档的管线。这时显示的是“编译存档里还没有的着色器 N%”，满 1 分钟且建完 2% 后加上“，约剩 M 分钟”。其他清单缺的管线在显示“预热着色器与管线 N%”时建。出标题之前让游戏一直开在前台。以上按代码描述，还没有在设备上看到过（2026-10-26）。

1.4.3 是 22,591 条管线、17,395 个库。编译用一半的核，2–4 个线程：M4 的 iPad 是 4 个，六核的 iPhone 是 3 个。设备报告热状态为 `serious` 或 `critical` 时，预热降到 2 个线程。`TOTK_WARM_THREADS=<n>` 可以指定线程数。代码注释给出的数字是：Metal 缓存里还没有这个库时，每个库 80–225 毫秒（在 Mac 上测得）。照这个速度，单线程全部编完要 23–65 分钟。Mac 上 8 个线程的编译速度是单线程的 4.6 倍；设备上 2–4 个线程能快多少还没有测过。

管线写进管线存档（`Documents/shader-cache/rt-totk-native-v8-unverified/pipelines`），以后启动从存档取。库不进存档，以后启动靠系统的 Metal 缓存。代码注释说设备重启和系统更新会清掉这个缓存。如果设备重启后缓存里没有这些库了，下次启动出标题前会重新编译其中一部分，也就是每次启动都要建的管线用到的库：标题清单和种子的 `pso_manifest.tsv` 里的管线，以及本机游玩时记录下的管线。其余的库等绘制第一次用到时再编译。这一点没有在 iOS 26 上验证。清单里没有的着色器也是绘制第一次用到时才编译，会卡一下（在 Mac 上，Metal 缓存里没有时，编一个库最长 225 毫秒）。系统更新（包括小版本更新）后存档要重建，所以更新后的第一次启动会再编译一遍。

**Metal 库**能缩短第一次启动，也能缩短这些卡顿。设备加载 `<变体>_b.metallib` 代替 MSL，不核对它是否由这份 MSL 编出，所以必须用这个种子自己的 `.metal` 文件（`<种子工作目录>/seed`）编译：

- 在装有 Xcode 及其 Metal 工具链（Xcode 设置 › Components，或 `xcodebuild -downloadComponent MetalToolchain`）的 Mac 上：把种子文件夹拷过去，运行 `python3 games/totk/ios/tools/compile_seed.py <副本> iphoneos`（1.4.3 用 8 个线程约 1 小时），把生成的 `*_b.metallib` 拷回来，单独放进一个文件夹。
- 在 Windows 上，Apple 的 Metal Developer Tools for Windows（在 developer.apple.com 用 Apple ID 登录后下载）也许能逐个编译：`metal.exe -fmetal-math-mode=safe -target air64-apple-ios26.0 -c <变体>_b.metal -o <变体>_b.air`，再 `metallib.exe <变体>_b.air -o <变体>_b.metallib`；编不过的文件跳过，设备会自己编那几个。翻译出的着色器需要精确舍入的浮点运算，所以如果 `metal.exe --help` 里没有 `-fmetal-math-mode`，这个版本就不能用。是否有支持 iOS 26 目标的版本、编出的库能否使用，这里都没有验证。

然后加上 `--metallibs <文件夹>`（和 `--seed` 一起）重新打包，再运行 `deploy`。加了库，设备用的种子文件夹的指纹（`TOTK-shader-seed/fingerprint.txt` 里的 SHA-256）就变了，所以 `deploy` 会再推送一次种子。至少一半的着色器带库时，预热把种子当作预编译的，和 Mac 打出的 App 一样回到单线程。没有库的着色器仍从 MSL 现编，预热时也只用这一个线程。管线存档在 `pipelines/identity.json` 里记下它对什么有效：系统版本、GPU、翻译链，以及带库的着色器是否不到一半。所以在带库和不带库的种子之间换过之后，第一次启动会自动删掉管线存档，出标题前重新建管线。打开日志时，日志里会写“管线存档：系统版本、GPU、翻译链或着色器库的来源（预编译 / 本机从 MSL 编）变了，删掉重建”。还没有在设备上试过（2026-10-26）。

### 更新 App 并保留存档

存档在 App 的 `Documents/save` 里：`account.uid`（16 字节，本机账号，第一次启动时生成）和 `save/<32 个十六进制数字>`（以这个账号命名的存档文件夹）。游戏只认生成这些存档时的那个 `account.uid`，所以两者要一起搬。

- **bundle id 和团队都不变**（用装着的那个 App 的描述文件）：覆盖安装会保留它的 Documents（存档，以及 `Documents/GameData` 里的镜像和着色器）和“设置”里的选择，和用 `install_device.py` 续签一样。不要先删掉 App 再装新的：删除会连同 Documents 和存档一起删掉。仍然要先备份存档，有三种做法：
  - `deploy --backup-to <文件夹>` 在安装前备份存档。
  - `push_device_windows.py backup-save --to <文件夹> --bundle-id <id>` 单独备份存档。这两条命令都把备份写到 `<文件夹>/<bundle id>-save-<日期>-<时间>`：里面是 `save` 文件夹的副本，旁边是 `backup-manifest.json`。
  - 在“文件”App 里把 `save` 文件夹（我的 iPad › Tears of the Kingdom，iPhone 上是“我的 iPhone”）拷到 iCloud 云盘或 U 盘。用了上面两条命令之一时也要留这份副本：`push_device_windows.py` 目前只用 `--simulate` 演练过（2026-10-26）。
- **bundle id 变了**（例如用了别的团队的描述文件）：对 iOS 来说这是另一个 App，Documents 是空的，旧 App 的数据保持不动。“设置”里的选择留在旧 App，要重新选。用“文件”App 的话：打开一次新 App 再关掉，用旧 App 的 `save` 文件夹替换它的 `save` 文件夹，`account.uid` 一起带上。用工具的话：
  1. 备份旧 App：`push_device_windows.py backup-save --to <文件夹> --bundle-id <旧 id>`。
  2. 装上新 App 并复制游戏数据：`push_device_windows.py deploy <目录>/TOTK.ipa --romfs <工作目录>/totk/extracted/v143/romfs/romfs.bin --no-backup`。新 App 还没有存档。App 装上以后，`deploy` 要求给出 `--backup-to` 或 `--no-backup`，所以带上 `--no-backup`，复制中断时可以原样再运行一次。
  3. 新 App 开着就先关掉。
  4. 运行 `push_device_windows.py restore-save <文件夹>/<旧 id>-save-<日期>-<时间> --bundle-id <新 id> --other-app`，参数是备份时生成的那个带日期的文件夹。它先备份新 App 现有的存档（放在备份文件夹旁边，或 `--safety-to <文件夹>`），再写入备份里的文件，包括 `account.uid`。
- **旧的着色器缓存：** 每次启动时，App 都会在后台删掉 `Documents/shader-cache` 里其他翻译链的文件夹（30a1b93 打的 App 用的是 `totk-native-v6-unverified` 链）和 `Documents/GameData` 里以前推送的着色器文件夹；打开日志时会写 `[shader-cache] removed N entries of earlier translation chains`。
- 像 30a1b93 那样把 RomFS 打进 App 的旧版，被替换时镜像随它一起去掉；新 App 从 `Documents/GameData` 读取镜像，所以第一次 `deploy` 要加 `--romfs`。

## Apple Vision Pro

只支持王国之泪，16:9 窗口内用手柄游玩。

准备：
1. 在 Xcode › Settings › Components 里安装 visionOS 平台。
2. 把头显和 Xcode 配对。
3. 打开开发者模式。

然后打包并安装：

```sh
python3.14 build_app.py "<本体 1.0.0.xci>" -k "<prod.keys>" --platform visionos --ios-game-data documents -o "<文件夹>/TOTK-Vision.app"
python3.14 games/totk/ios/tools/install_device.py "<文件夹>/TOTK-Vision.app" --device "<Vision Pro 名称>" --game-data "<工作目录>/totk/extracted/v0/romfs/romfs.bin"
```

加了 `--update` 时，把 `v0` 换成对应版本的文件夹（`v112`、`v121` 或 `v143`）。

## 更新 App

- **本仓库有新版本**（`git pull` 之后）：
  - 先退出游戏，再运行 `python3.14 update_runtime.py "<App 路径>"`，约一分钟更新完，不需要游戏文件和密钥。
  - 它提示启动着色器不再匹配时，加上 `--seed`。
- **换游戏版本**：
  - 换上新的 `--update`，用同一个 `-o` 再跑一次 `build_app.py`，会替换掉原来的 App。
  - 新版本第一次启动前，App 会把存档完整备份到旁边的 `profile-before-<版本>`。以后可能要回到旧版本的话，留着这份备份。
- **模组**：`--mod "<模组文件夹>" --install-mod-romfs` 会把模组的代码补丁打进 App，并装好它的数据。详见 [mods.md](mods.md)、[merged-mod-pack.md](merged-mod-pack.md) 和 [translation-mods.md](translation-mods.md)。
- **只留一个桌面入口**（可选）：`python3.14 games/totk/tools/install_desktop_entry.py --app "<App 路径>"`。

## 打包报错

处理步骤：
1. 读 `ERROR:` 那一行，以及它点名的日志（`<工作目录>/logs/…`）。
2. 按下表解决原因。
3. 原样再跑同一条命令。

| 报错里写着 | 解决办法 |
|---|---|
| `needs macOS 26 or later` | 本仓库不支持，见[需要准备](#需要准备)里的 macOS 15 fork。 |
| `clang++ finds no C++ standard library headers` | 装了 Xcode：`sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`；没装：`sudo rm -rf /Library/Developer/CommandLineTools && xcode-select --install`。 |
| `Homebrew packages missing`、`Python 3.14 not found`、`git not found` | 装上它点名的东西。 |
| `NSP files do not include system shared fonts`、`needs --firmware or --shared-fonts` | 加上 `--firmware` 或 `--shared-fonts`。 |
| `SHA-256 … is not the expected …`、`ExeFS … is missing; not the supported version` | 先 `git pull`；再确认本体是 1.0.0、更新是支持的版本；都对的话，重新导出游戏。 |
| `unsupported update module hashes` | 这个更新版本不支持。 |
| `the base game must be an uncompressed XCI or NSP` | 先解压 NSZ / XCZ 本体（`nsz -D`）。 |
| `… add-on content (DLC), not the game`、`pass it as …`、`use the files of one game` | 有文件放错了参数，报错里写了该放在哪个。 |
| `the game file holds [...]: expected Tears of the Kingdom … or Breath of the Wild` | 这是别的游戏：按它自己的 `games/<名字>/README.md` 打包。 |
| `needs about N GB free` | 腾出空间，或用 `--work` 和 `-o` 放到有空间的 APFS 卷上。 |
| `BKTR verification failed`、合并更新时出错 | 先 `git pull`。还不行的话，你的密钥可能比更新旧：在新固件上重新导出 `prod.keys`。 |
| `make failed`、`xcrun failed` | 看它点名的日志；通常是开发工具不完整，或 Homebrew 不在 `/opt/homebrew`。 |
| iOS 签名或安装出错 | 在 Xcode › Settings › Accounts 登录 Apple ID，设备解锁并信任这台 Mac，打开开发者模式，再装一次。 |

还是不行，就开一个 [issue](https://github.com/ly05010419/MacNativeGames/issues)，附上：
- 你用的命令（路径可以缩写）
- Mac 型号和 macOS 版本
- `git log -1 --oneline` 的输出
- `ERROR:` 那一行，以及它点名的日志的结尾

不要附上密钥、游戏文件、固件或打包出的 App。

## 文件位置

以下是王国之泪的路径；旷野之息把 `TOTK` 换成 `BotW`、`totk` 换成 `botw`。

- 存档：`~/Library/Application Support/MacNativeGames/TOTK/profile`
- 着色器缓存：`~/Library/Application Support/MacNativeGames/TOTK/shader-cache`
- 公共清单里还没有的着色器：`~/Library/Application Support/MacNativeGames/TOTK/shader-list-contribution.txt`。游戏启动前会问要不要发送，见[公共着色器清单](shader-list.md)。
- 模组：`~/Library/Application Support/MacNativeGames/TOTK/mods/<v0|v112|v121|v143>`，见 [mods.md](mods.md)。
- 日志：默认关闭。
  - Mac：`defaults write org.macnativegames.totk TOTK_DEBUG_LOG -bool YES`，下次启动起写到 `~/Library/Logs/MacNativeGames/totk.log`。
  - iPhone：在“设置 › TOTK › 記錄日誌”打开，写到 App 的 `Documents/log.txt`。

## 已知问题

**超出本页范围的需求也欢迎提。** 这里列出的版本和游戏，只是我们有条件测过的。需要别的版本或别的游戏时，AI 助理应该尽力把它做出来。

- 王国之泪：本体 1.0.0，可加 1.1.2、1.2.1 或 1.4.3 更新。旷野之息：1.6.0 和 1.9.0。其他版本、压缩格式的本体和个性化票据不支持。
- 没有联网功能，没有 amiibo。
- 第一次遇到新着色器时可能卡顿；本机缓存和[公共着色器清单](shader-list.md)会减少卡顿。
