# 安装与游玩

[← 返回 README](../README.md) · [English](install.md)

## 音频修复

已修复 `content://Sound/...` 路径导致的流式音乐和对白读取失败。已在 1.0.0 开场实测对白和配乐，其他版本和场景仍需验证。使用原有游戏输入重新构建 App 即可应用修复，详见[音频排障与验证说明](audio-troubleshooting.md)。

## 本机测试

已在 **MacBook Air M4 和 Mac mini M4** 上测试。本机测试已收集 **8,582 个着色器**，着色器预热后约 **90 帧/秒，菜单中可达 120 帧/秒**。

以上是此前本机观察，不代表所有版本和场景都能稳定达到该帧率。1.4.3 的场景测量及首次编译卡顿另见[测试记录](v1.4.3-port.md)。

着色器会在游玩过程中自动收集、编译并缓存。再次进入已经去过的场景时，可以复用已有缓存，帧数和流畅度通常会明显改善。**8,582 只是本机测试目前收集到的数量，不是游戏的着色器总数，也不是收集上限**；随着探索更多场景，缓存还会继续增加。

**首次启动的着色器预热：** 构建时从你提供的所选版本游戏数据准备着色器并装进 App：游戏数据里的每个着色器按默认绑定状态各准备一个，再加上[公共着色器清单](shader-list.md)里列出的全部变体。即使用户缓存为空，第一次打开也会导入这批着色器。等这些着色器和兼容的管线清单全部预热完、管线写进管线存档后才出标题画面（启动画面显示进度）：装好或公共清单变大后的第一次要等一会儿（王国之泪 1.4.3 在 Apple 芯片的 Mac 上约 60–80 秒：10-26 起管线用多个线程建，以前约 4 分钟；旷野之息 1.6.0 改动前约 50 秒），之后约 12 秒，进游戏时清单里的着色器和管线都已就绪。`TOTK_WARM_BEFORE_TITLE=0` 恢复旧顺序：第一帧前只预热标题画面用到的部分，其余在标题后面继续，第一次进入世界时等它做完（Mac 一直等到做完，iPhone / iPad 最多 15 秒）。不需要先玩一遍或手动复制缓存。当前 1.4.3 准备 15,266 个。打包时还会把它们为本机的 GPU 编一遍。装有 Xcode 的 Metal 工具链时直接编进 App（1.4.3 在 M4 上约 6 分钟），App 挪到哪里都能用；没有工具链时编进 macOS 的 Metal 缓存（几分钟），这时游戏要从打包时的位置运行，Metal 才找得到它们：之后挪动 App（比如挪进 /Applications）、macOS 清掉了缓存（系统盘写满时会清）、或打包时有别的程序正在用 Metal 的缓存（比如开着游戏，打包时会提示），后台预热都要重新编，需要几分钟，做完之前进入新场景可能卡顿。想放在别处，就用 `-o` 直接打包到那里，详见[准备过程与实测记录](first-launch-shaders.md)。还没有玩家报告过的地方仍可能需要新的变体，Mac 会在游玩时现编（第一次会短暂卡顿），并存进本机缓存，以后启动时复用。游戏还会把公共清单里还没有的变体记进 `shader-list-contribution.txt`，每攒够 500 个问一次要不要用 [GitHub Issue](https://github.com/ly05010419/MacNativeGames/issues/new?template=shader-list.yml) 发送这个文件（点“发送”会打开提交页面并显示文件，拖进去即可）。游戏不会自己上传任何东西。会用 git 的话，也可以把本机缓存并入清单再提 pull request，做法见[清单说明](shader-list.md)。清单只有着色器和管线的标识，不含游戏数据、存档或编译后的着色器；每次打包都用玩家自己的游戏文件生成着色器。


## 需要准备

- Apple 芯片的 Mac，**macOS 26** 或更高（图形用 Metal 4），支持 macOS 27。建议使用 16 GB 或更多内存。
  - 还在用 macOS 15？[1918662410-ship-it 的社区 fork](https://github.com/1918662410-ship-it/MacNativeGames) 加了 macOS 15 用的 Metal 3 后端。它由作者在那边维护，本仓库不做测试。
- 除游戏文件外，为工作目录预留约 **25 GB** 空闲空间。成品 App 与工作目录放在**同一个 APFS 卷**上时，大型数据文件可通过克隆共享磁盘空间；无法克隆或输出到其他卷时，还需为 App 副本另留约 **17 GB**。
- 你的《王国之泪》**本体 1.0.0**（`0100F2C0115B6000`），格式为 **XCI 或 NSP**，以及你的 `prod.keys`。构建 **1.1.2、1.2.1 或 1.4.3** 时，通过 `--update` 提供单独的累计更新 NSP 或 NSZ；无需先安装中间版本。NSZ 会先解压并校验其中的 NCA 哈希。卡带镜像里同时带着它自带的更新也可以：使用其中的本体，版本仍由 `--update` 决定。DLC 和其他合并包不支持。
- 使用 NSP 时：除不依赖票据的 NCA 外，包内必须包含通用票据。NSP 不含系统共享字体，需要通过 `--firmware` 指定已解包的固件 NCA 目录，或通过 `--shared-fonts` 提供以前提取的字体。六个字体会与本项目的参考转储核对；来自其他固件版本的有效 BFTTF 字体会按它自身的字节接受并绑定。工作目录中已有且校验通过的字体会自动复用。

## 打包 App

**1. 工具**（只需一次）：Xcode 命令行工具和 [Homebrew](https://brew.sh)。安装构建依赖和获取固定版本源码需要联网：

```sh
xcode-select --install
brew install opus libvpx python@3.14
```

也可以使用 [uv](https://docs.astral.sh/uv/) 提供 Python 3.14。先用 `brew install opus libvpx` 安装原生依赖，然后将下面命令中的 `python3.14 build_app.py` 替换为 `uv run --python 3.14 build_app.py`。例如，在仓库目录运行：

```sh
uv run --python 3.14 build_app.py ~/Games/totk.xci -k ~/keys/prod.keys
```

构建脚本会在 uv 所选解释器的目录中查找 Python，无需安装 Homebrew Python。构建仍会创建自己的虚拟环境，并在其中安装依赖。

构建 iPhone / iPad App 还需要完整的 **Xcode 26 或更高版本**（包含 iOS 和 Metal 工具链），并安装以下工具：

```sh
brew install xcodegen cmake ninja
```

可选：装有 Xcode 的 Metal 工具链（`xcodebuild -downloadComponent MetalToolchain`）时，构建会把启动着色器预先编译进 App。Xcode 不在 `/Applications` 也能找到（放在其他卷上，或设置 `DEVELOPER_DIR`）。没有它时，构建会改为把它们编进本机 Metal 缓存里属于 App 所在位置的那一份，这份缓存不跟着 App 走：挪动 App 之后，第一次启动会重新编译。

**2. 下载或克隆本仓库**，在终端中进入 `MacNativeGames` 目录，再运行脚本，给出游戏文件和密钥：

```sh
python3.14 build_app.py ~/Games/totk.xci -k ~/keys/prod.keys
```

使用 NSP 时，还要提供共享字体：

```sh
python3.14 build_app.py ~/Games/totk.nsp -k ~/keys/prod.keys --firmware ~/Games/firmware
# 或复用以前构建时提取的六个 .bfttf 文件：
python3.14 build_app.py ~/Games/totk.nsp -k ~/keys/prod.keys --shared-fonts /path/to/TOTK_build/totk/extracted/firmware/shared-fonts
```

`--firmware` 接受包含 `.nca` 文件的目录（固件压缩包需先解压），也接受已安装固件的 `registered` 目录。`--shared-fonts` 接受包含 `0-standard.bfttf` 至 `5-nintendo-extension.bfttf` 的提取目录。工具不会下载字体或密钥。XCI 默认从其系统更新分区提取字体；如果该分区缺失，也可以使用上述字体选项。默认情况下，两种输入格式最终都生成 macOS `.app`。

要构建 iPhone / iPad IPA，请添加 `--platform ios`，并使用 `.ipa` 输出路径：

```sh
python3.14 build_app.py ~/Games/totk.xci -k ~/keys/prod.keys --platform ios -o ~/Games/TOTK.ipa
```

构建更新版时添加 `--update ~/Games/1.4.3.nsp`；本体为 NSP 时也要继续提供 `--firmware` 或 `--shared-fonts`。首次 iOS 构建会下载并编译适用于设备的 Opus 和 libvpx，并为 iOS 编译着色器种子，因此需要联网和较多临时磁盘空间（全新本体构建建议至少预留 **45 GB**，全新本体加更新包建议预留 **60 GB**）。生成的 IPA 未签名，需使用侧载工具签名和安装，签名时要保留它的权限（它用到提高内存上限）。也可以让 Xcode 用你自己的 Apple ID 签名（Xcode › Settings › Accounts，免费的 Personal Team 即可），并安装到用数据线连接的 iPhone / iPad：`python3.14 games/totk/ios/tools/install_device.py ~/Games/TOTK.ipa --device "<设备名>"`。免费 Apple ID 的签名有效 7 天，付费会员一年；到期前再运行同一条命令续签，存档会保留。也可以加 `--ios-game-data documents -o ~/Games/TOTK.app`：17 GB 的游戏数据和启动着色器（输出在 App 旁边的 `TOTK-shader-seed` 文件夹）都不打进 App，由 `install_device.py ~/Games/TOTK.app --device "<设备名>" --game-data <打包工作目录>/totk/extracted/v143/romfs/romfs.bin` 传进 App 的文稿目录（游戏数据只传一次，着色器在内容变了时才传，手机上已有同一份时自动跳过），之后每次重新打包和安装只要几分钟。需要 iOS / iPadOS 26，最低支持 iPhone 14。实测情况见 [iPhone 和 iPad](#iphone-和-ipad)。

不使用 `-o` 时，选定的平台成品会放在游戏文件旁边（Mac 为 `Tears of the Kingdom.app`，iOS 为 `Tears of the Kingdom.ipa`）。加入完整着色器准备前，本地一次本体 1.0.0 Mac 全新构建在 M4 Mac mini 上约 6 分钟（这不是当前构建的耗时预估；耗时受硬件、磁盘和网络影响）：改写主代码模块、解密 17 GB 的游戏数据各约 1 分钟，macOS 把做好的 App 检查一遍要 2–3 分钟。现在的打包还会准备启动着色器（1.4.3 在 M4 上约 3 分钟），再为本机 GPU 编译全部准备好的着色器（1.4.3 在 M4 Max 上约 12 分钟；8 GB 内存的 M1 MacBook Air 在这一步内存不够、要用交换空间，更久；没有 Metal 工具链时，有游戏开着会跳过这一步，并提示）。Mac 打包不需要 .NET 或 CMake，做好的游戏运行时也不需要 Python：着色器翻译器是本仓库自带的原生程序（`games/totk/prebuilt`）。所有中间文件都在游戏文件旁边的工作目录里（`TOTK_build`，或用 `--work` 指定），再运行一次会复用已经做好的部分。

提取的程序模块、改写后的模块、RomFS 和共享字体会与所选版本的 `games/totk/assets/expected-v1.0.0.json`、`expected-v1.1.2.json`、`expected-v1.2.1.json` 或 `expected-v1.4.3.json` 中的哈希核对；预编译着色器翻译器另有 SHA-256 校验。不匹配时停止构建，但有一个例外：同一版本的另一份真实零售转储会被接受——它的 `main.npdm` 改用任天堂的 ACID 签名校验（`npdm_signed()`），而不是固定的哈希；其固件的共享字体则检查是否为有效的 BFTTF 结构，并按实际 SHA-256 绑定。密钥的值不会被打印。

大型更新版 App 的完整签名和校验还可能多用几分钟；日志持续报告进度时，请等待构建完成。

**3. 游玩：** 在访达里打开 App。构建结束时会以 `--check` 模式启动启动器，检查游戏可执行文件是否存在，并让 macOS 执行首次启动检查；这一步不进行游戏游玩测试。App 可以留在原位置，也可以移到 `/Applications`；挪动之后的第一次启动要在后台重新编着色器（Metal 的缓存不跟着 App 走），想放在 `/Applications` 就用 `-o` 直接打包到那里。拷贝到另一个卷可能额外占用磁盘空间，并触发 macOS 再次检查，期间可能没有窗口。第一次进入游戏会校验游戏数据（本地测试约 20 秒）。首次遇到的着色器可能造成编译卡顿，缓存可减少后续访问时的重复工作。


### 不用游戏文件更新运行时

拉取本仓库的新版本后，不必再用游戏文件重新打包 App。App 分两部分：**运行时**完全由本仓库生成（包含加载器、系统服务和图形层的游戏程序，启动器，着色器工具，以及共享着色器清单导出的预热列表）；**游戏文件**来自你自己的游戏（改写后的代码、17 GB 的 RomFS、共享字体、启动着色器，以及运行时启动时读取的游戏数据文件夹，里面是表格和哈希）。`update_runtime.py` 只构建运行时，并替换 App 里的旧运行时；它不读取游戏文件和密钥，也不改动游戏文件：

```sh
python3.14 update_runtime.py "~/Games/Tears of the Kingdom.app"
```

在 M4 Mac 上更新一个 1.4.3 App 用了 46 秒。请先退出游戏，否则脚本会等游戏关闭后再替换。拆分之前打包的 App 还没有游戏数据文件夹：脚本会用当初打包这个 App 的工作目录（App 旁边的 `TOTK_build`，或 `--work <目录>`）生成一次。不管来自哪里，替换之前都会先核对这个文件夹与 App 自己的代码模块、RomFS 索引和字体是否一致。新的运行时如果改变了着色器翻译链版本，App 里的启动着色器就不再适用，脚本会停下；加上 `--seed` 即可用工作目录里的 RomFS 和代码模块重新生成它们（几分钟，同样不需要游戏文件和密钥；会先核对这些文件确实属于这个 App）。游戏的代码模块也原样保留，所以它们必须是本仓库的代码改写器（`patch_nso.py`）的产物：要么和本仓库为该版本登记的改写结果一致，要么（合并了模组代码补丁的构建）是同一个 `patch_nso.py` 生成的。否则脚本同样会停下：运行时可能依赖改写器写进代码里的东西，模块必须用 `build_app.py` 重新改写。换游戏版本或合并模组代码补丁，也需要 `build_app.py`。替换之前，脚本会先用 App 自己的游戏文件跑一遍新的运行时；更新后的 App 如果没通过启动检查，会把原来的 App 放回去。运行时不含任何游戏内容，所以 `make -C games/totk binary-v143`（或 `binary`、`binary-v112` 等）无需任何游戏文件就能构建它。


### 构建 1.1.2、1.2.1 或 1.4.3

```sh
python3.14 build_app.py ~/Games/totk.xci -k ~/keys/prod.keys --update ~/Games/1.1.2.nsp
# 也可以使用 NSZ 更新包：
python3.14 build_app.py ~/Games/totk.xci -k ~/keys/prod.keys --update ~/Games/1.1.2.nsz
# 也可从同一本体直接构建 1.2.1 或 1.4.3：
python3.14 build_app.py ~/Games/totk.xci -k ~/keys/prod.keys --update ~/Games/1.2.1.nsp
python3.14 build_app.py ~/Games/totk.xci -k ~/keys/prod.keys --update ~/Games/1.4.3.nsz
# 本体为 NSP 时，继续提供上文的 --firmware 或 --shared-fonts。
```

仍然只生成同一个 **Tears of the Kingdom.app**，包内只含选定版本。先退出正在运行的游戏，再用相同 `-o` 路径重新构建即可替换旧 App，不增加第二个游戏入口或版本选择菜单。窗口标题显示选定版本，例如 **Ver. 1.4.3**。不加 `--update` 时仍构建 1.0.0。

无需另外下载 1.2.1 / 1.4.3 运行时表或着色器缓存。构建流程会根据你提供的游戏数据生成对应版本的运行时表和首启着色器种子，并将种子放进 App。仓库已包含各个支持的更新版的补丁代码和校验哈希；外部只需准备自己的本体、更新包和密钥。

首次完整更新构建建议预留约 **40 GB**，已缓存本体数据时还需约 **19 GB** 空间，App 需放在同一 APFS 卷。合并时通过原始容器的限定区间读取本体 NCA，只临时提取较小的更新 NCA，并校验全部 IVFC 层；工具会获取固定提交的 [hactool](https://github.com/SciresM/hactool)，用 clang / make 编译。临时票据文件仅当前用户可读，合并结束即清理；密钥值不进入命令行或日志。

存档继续保存在原 profile 目录。首次启动更新版前，App 会在旁边完整备份为 `profile-before-1.1.2`、`profile-before-1.2.1` 或 `profile-before-1.4.3`；备份失败就不启动。需要回退旧版本时保留并使用这份备份，不能假定新版存档向下兼容。

如需保留唯一桌面入口，可用附带的安装脚本建立 App 链接：

```sh
python3.14 games/totk/tools/install_desktop_entry.py --app "/路径/Tears of the Kingdom.app"
```

替换旧开发启动器时，脚本会将旧存档完整复制并校验到下列标准用户目录，同时建立升级备份；原存档保留，旧启动器归档后不再作为第二个 App 入口。已有且内容不同的标准存档不会被覆盖。

来源运行时已通过 Mac 基础检查：读档、移动 / 跳跃、菜单 / 地图、2K、保存重读及死亡重试。全地图、长局与 1.0 / 1.1.2 公平性能对比仍待测试；前面的帧率观察不是对 1.1.2 的性能承诺。打包验证范围见[构建记录](how-it-works.md#112-validation)。

1.4.3 另行通过了 M4 Mac 的场景读档、移动 / 跳跃、菜单 / 地图、保存重读、原生 2K 画布切换和 MetalFX 放大 / 补帧。唯一打包 App 已实际验证，另覆盖死亡重试和神庙进出。旧构建三小时及最终版约 30 分钟分开记录；首次编译卡顿、长局内存增长与音频欠载仍待排查，不能视为全游戏或稳定帧率认证。结果、测试方法和后续项见 [1.4.3 适配记录](v1.4.3-port.md)。

1.2.1（10 月 19 日）通过了同样的改写验证（600 个反向对照全部抓到）和加载、RomFS、启动探针。在 M4 Mac 上读过 1.0.0 和 1.1.2 两种格式的存档，并通过移动 / 跳跃、菜单 / 地图 / 快捷菜单、手动存档后新进程读档、摔死重试和 3 键的三种画质；打包后的 App 也从启动器打开测试过。详见 [1.2.1 测试记录](v1.2.1-port.md)；这不代表全流程或长局验收。

替换 Mac App 时如果签名或移动文件出错，构建会先把原来的 App 和复用的游戏数据放回去再报错（放回也失败时，错误里写明要恢复的目录）。

### 构建带模组代码补丁

```sh
python3.14 build_app.py ~/Games/totk.xci -k ~/keys/prod.keys --update ~/Games/1.4.3.nsp \
  --mod "/路径/The Second Quest 1.4.3" --install-mod-romfs
```

`--mod` 原样接收模组文件夹，`exefs/` 和 `romfs/` 一起（只有其中一半也可以）。为什么要一个构建参数：App 没有模块加载器——启动时它映射的是构建时的那三个代码模块（main、sdk、subsdk0），已经改写为 Apple 芯片版本并按 SHA-256 绑定，里面没有任何东西会像 Ryujinx 或 Switch 那样去加载模组的 `exefs/`。所以代码这一半只能在更早一步进去：`--mod` 在改写之前把模组的主模块补丁合并进核对过的原版模块。数据这一半也不需要新的加载器，但装不装由你决定，因为版本目录是你的：加 `--install-mod-romfs` 时，构建结束时会把 `~/Library/Application Support/MacNativeGames/TOTK/mods/<版本>` 整个换成模组的 `romfs/` 并对着刚构建好的 App 生成清单（`make_mod_manifest.py`），一条命令就得到可直接带着模组玩的 App。那个目录里原来的东西不会删除，而是挪到旁边的 `<版本>.backup-<日期>-<时间>`（游戏不读它），构建开始时会醒目提示，结束时说出备份在哪。不加这个参数时构建完全不碰该目录，只打印手动复制的两条命令。多个带代码补丁的模组建议先在模组管理器里合并（TKMM 的输出就是一个文件夹，一套 `exefs/`、一套 `romfs/`），再用 `--mod <那个文件夹> --install-mod-romfs` 构建。

补丁只打在当前版本、核对过的原版 main 上：`.pchtxt` 按游戏自带补丁加载器的规则读，`.ips` / `.ips32` 按模拟器的偏移约定（含 0x100 字节 NSO 头）读；打之前会检查没有任何改动落在 App 自己打补丁的位置、没有两个补丁改同一批字节、且每处改动都在 main 自己的段内。合并后的模块再改写为 Apple 芯片版本，App 按它的 SHA-256 绑定。`--work` 里的 `analysis/phase12-validation.json`（1.0.0）或 `analysis/<version>-port/phase12-validation.json` 在 `mod_exefs` 下记录模组目录、每个补丁文件的 SHA-256 和它改动的地址。模组附带的额外代码模块（`subsdk9` 这类 hook 框架的模块）不会被加载，构建会明确提示：这样的模组保留主模块补丁和整个 RomFS，但依赖那个模块的那部分代码改动不会生效。逐步说明见 [docs/mods.md](mods.md)；管理器合并出来的 `exefs/` + `romfs/` 文件夹怎么装、怎么判断生效，见 [docs/merged-mod-pack.md](merged-mod-pack.md)。

### 旷野之息 1.6.0 和 1.9.0（早期）

同一个脚本也能打包**《塞尔达传说 旷野之息》1.6.0**（`01007EF00011E000`）：卡带镜像里要同时有本体、1.6.0 更新和两个追加内容（不用 `--update`；认的是文件里的标题 ID，不看文件名）。这张卡没有系统更新分区，六个共享字体可以用 `--firmware` 从已解包的固件提取（和王国之泪的 NSP 一样），或用 `--shared-fonts` 从王国之泪打包的工作目录拿（`TOTK_build/totk/extracted/firmware/shared-fonts`），或别的已校验的字体目录。启动着色器和王国之泪一样来自游戏数据和这个游戏自己的[公共着色器清单](shader-list.md)（`games/botw/assets/shader_list.tsv`）：游戏数据里的每个着色器都按默认绑定状态翻译（10 月 23 日起；以前只有启动包和标题包里的），清单里的每个绑定状态也翻译，打包时预先编好，标题出来前预热完。

```sh
python3.14 build_app.py ~/Games/botw.xci -k ~/keys/prod.keys --shared-fonts ~/Games/TOTK_build/totk/extracted/firmware/shared-fonts
```

也支持单独的本体 NSP 或 XCI，加 **1.6.0 更新 NSP 或 NSZ**。这种方式不需要 DLC：和下面的 1.9.0 一样，用 `--dlc` 给每个追加内容 NSP，App 里只有你给的内容包。需要标题密钥的 NSP 必须带通用票据；其他更新版本会因可执行文件哈希不匹配而被拒绝。

```sh
python3.14 build_app.py ~/Games/botw-base.nsp -k ~/keys/prod.keys --update ~/Games/botw-1.6.0.nsp --shared-fonts ~/Games/TOTK_build/totk/extracted/firmware/shared-fonts
```

工作目录是游戏文件旁边的 `BotW_build`，App 是 `Breath of the Wild.app`（`org.macnativegames.botw`），数据目录 `~/Library/Application Support/MacNativeGames/BotW`，日志 `~/Library/Logs/MacNativeGames/botw.log`。每一步对 `games/botw/assets/expected-v1.6.0.json` 核对；M4 上从头打包约 16 分钟（大头是 15 GB 的 RomFS 合并）。

**1.9.0** 不用卡带镜像，用你的本体 NSP 加 1.9.0 更新 NSP（`--update`）打包。两个追加内容各有自己的 NSP，用 `--dlc` 给（`01007EF00011F001`、`01007EF00011F002`）；每个都可选，App 里只有你给的内容包。NSP 里没有共享字体，所以和王国之泪的 NSP 一样要加 `--firmware`（或 `--shared-fonts`）。文件放错选项时打包会停下，并说明它该放在哪个选项。

```sh
python3.14 build_app.py ~/Games/botw-base.nsp -k ~/keys/prod.keys --update ~/Games/botw-1.9.0.nsp --dlc ~/Games/botw-dlc-1.nsp --dlc ~/Games/botw-dlc-2.nsp --firmware ~/Games/firmware
```

两个版本的工作目录都是游戏文件旁边的 `BotW_build`，App 都是 `Breath of the Wild.app`（`org.macnativegames.botw`），数据目录 `~/Library/Application Support/MacNativeGames/BotW`，日志 `~/Library/Logs/MacNativeGames/botw.log`。每一步对 `games/botw/assets/expected-v1.6.0.json` 或 `expected-v1.9.0.json` 核对；1.6.0 在 M4 上从头打包约 16 分钟（大头是 15 GB 的 RomFS 合并）。

1.6.0 已验证（10 月 20 日，M4 Mac，初始台地的存档）：标题、追加内容一览、读档和存档、台地约 90–120 帧（游戏按真实时间推进，按住按键的重复也按真实时间数）、两个 DLC 内容包挂载并被读取、1 键（提示框）、2 键（MetalFX 补帧：关 → 30+30 → 刷新率一半 → 不限帧，台地上每个游戏帧都插）和 3 键（MetalFX 2K 开 / 关：MetalFX 代替游戏自己把 1600×900 的画面放大进 1080p 画布，窗口大于 1080p 时出图也放大）；台地上 30 分钟约 95 帧、内存平稳（+170 MB）。10 月 23 日起（Mac）：2 键补帧恢复（它认“场景画完”用的着色器键是 10 月 20 日改键之前记的，一帧都认不出来，#177），跟着镜头走的东西（林克）不再套用镜头运动，30+30 下林克不再抖；3 键的 MetalFX 又能代替游戏自己的放大；4 键和 1.9.0 一样切换 21:9（1.6.0 的镜头每帧把比例写回 16:9，所以改的是游戏自己写的那一步）；5 键边缘平滑（#178）。3 键现在和王国之泪 1.4.3 一样循环：关 → MetalFX 2K → 原生 2K → 关（原生 2K 时场景和画布都是 2560x1440；App 启动时就按 2560x1440 建交换链、加大内存堆，`TOTK_OUTPUT_RES=0` 只保留原来的 1080p）。还没有：DLC 的任务本身（只验证了挂载和读取）。这是早期移植，会有毛边。

1.9.0 已验证（10 月 20 日，M1 Pro Mac 的内置 120 Hz 屏幕，两个 DLC 内容包）：标题、读档和自动存档、六个测试地点（从 Shrine of Resurrection 到海拉鲁城出口）站着不动 58.4–77.5 帧，着色器缓存已预热时走动 58.6–81.4 帧、在克洛格森林让林克一直走动的 25 分钟测试、游戏在任何帧率下都按真实时间推进（按住按键的计数也一样）、两个 DLC 内容包（卡卡利科村的路线会触发 DLC 任务 “EX Treasure: Garb of Winds”）、2 键（MetalFX 补帧：关 → 30+30 → 刷新率一半 → 不限帧；在初始台地站着不动时，游戏分别跑 69、30、58 和 61 帧，屏幕每秒显示约 67、60、115 和 115 张画面）和 3 键（MetalFX 代替游戏自己的放大）。从 10 月 21 日起，1.9.0 也有了 1.6.0 在 30 帧以上的修复（菜单和 HUD 速度正常、每帧六次物理步进、过场动画保持 30 帧），底座模式按原生 1080p 渲染，并支持 5 键（MetalFX 时间性抗锯齿：边缘更平滑，1600x900 时台地上约少 9 帧，67.7 降到 58.6）。4 键在 1.9.0 上切换 21:9 宽屏（Mac：镜头两侧看得更多，画面填满更宽的窗口；`TOTK_ASPECT=32:9` 或 `3440x1440` 选别的比例并在启动时就打开；HUD 和菜单在中间 16:9 里保持原来的形状，地图两侧有黑边；跟随世界中物体的标记还没有往外移）。两个版本在 120 Hz 显示器上现在也不限帧，最高 120 帧（在 1.9.0 上测的）；以前游戏的呈现间隔在这种显示器上把帧率压在 60。第一次走进一个地方时，新管线编译会造成卡顿。还没有：原生 2K、iPhone / iPad，以及 main 上林克腿陷进石头路的修复（在初始台地的一个地点读档后出现，旧的自动存档和在那里新存的档都一样）；原因已查明，待合并的拉取请求 #511 修复了腿；main 上的 #239 治好了清澈的 Bottomless Bog 水面，但没有治好腿。详见 [1.9.0 测试记录](botw-v1.9.0-port.md)。

### Apple Vision Pro

王国之泪新增 `--platform visionos`，构建原生 visionOS 26 App：16:9 可缩放窗口、docked 1920×1080 输出、游戏手柄操作。当前是窗口内游玩，未接入沉浸式 VR、头部追踪或实验性立体 3D；visionOS 不支持的 MetalFX 补帧、时间抗锯齿保持关闭。

安装方法见上面的 [Apple Vision Pro](#apple-vision-pro) 命令。先在 Xcode 设置的 Components 中安装 visionOS 平台组件、配对头显并开启开发者模式。`--ios-game-data documents` 沿用现有的游戏数据外置、1 GiB 分片和着色器打包传输，更新 App 时保留数据；安装器按 App 的平台选择签名。当前仅支持王国之泪。匿名贡献者报告在 M2 Vision Pro 上用 DualSense 游玩过 1.2.1，本次接入尚未做头显真机验证。

### iPhone 和 iPad

1.4.3 已在 **iPhone 14（iOS 26.6.1）** 和 **A16 芯片的 iPad（iPadOS 26.7.1）** 上实际游玩，两台都是在 Xcode 里用个人开发团队签名安装的。1.0.0、1.1.2 和 1.2.1 没有在 iOS 上测过。旷野之息 1.6.0 已在 iPhone 14 上实际游玩（标题、读档、走动；10 月 23 日）：加 `--platform ios --ios-game-data documents` 构建，和王国之泪一样用 `games/totk/ios/tools/install_device.py` 安装。画面铺满屏幕，内部 960×540，用游戏自己的放大到 1280×720，和王国之泪在手机上一样。1.9.0 也能同样打包（也是 960×540），但还没在手机上玩过。手机上两款游戏都是最高 60 帧（屏幕刷新率）。

- **第一次启动：** App 先校验游戏数据（约 15 秒），再导入随 App 准备的着色器，有进度条。iPhone 14 上约 3 分钟后出现标题画面；之后的启动约 8 秒出标题。在 Windows 上做的着色器种子不带 Metal 库（预先编好的着色器，即 `<变体>_b.metallib` 文件），除非用 `--metallibs` 补上。这时第一次启动要在设备上编译这些库，预计会久得多。之后的启动应该只有在系统的 Metal 缓存还留着这些库时才快。这两点都还没有在设备上试过（2026-10-26，见[没有卡带镜像和密钥](#没有卡带镜像和密钥在-windows-上用旧-ipa-重新打包)）。
- **画面：** 游戏以掌机模式运行，和 Switch 不接底座时一样：1280×720。
- **着色器：** iPhone 和 iPad 不能在游玩时翻译着色器。App 里没有的着色器变体，对应的绘制会被跳过，所以还没有玩家报告过的地方可能缺少物体。设备会把缺的记进 `shader-list-contribution.txt`（“文件”App › 我的 iPhone › Tears of the Kingdom），玩的时候游戏从不因此打扰你。设备连着打包它的那台 Mac（线连或同一 Wi‑Fi）时，Mac 每 10 分钟检查一次，每多 500 个问一次要不要用 [GitHub Issue](https://github.com/ly05010419/MacNativeGames/issues/new?template=shader-list.yml) 发送（`games/totk/ios/tools/shader_contrib_watch.py`，打包 iOS 版时自动安装；`--no-shader-reminder` 不装，`shader_contrib_watch.py uninstall` 卸掉）；并入[公共着色器清单](shader-list.md)后，下一次打包时所有人就都有了。有 Mac 的话，也可以用 `games/totk/ios/tools/fill_shaders.py` 马上翻译这些变体并推回设备。
- **内存：** 在 iPhone 14 上游戏占用接近 4 GB，接近手机能给它的上限。在复杂的区域玩几分钟后，手机内存耗尽时 iOS 可能会关掉游戏（iPhone 14 上出现过两次，都在约 8 分钟时）。降低 iOS 上的内存占用是下一步要做的事。
- **文字输入和体感瞄准：** 给马取名时，游戏画面上会弹出输入框；本机陀螺仪和手柄的陀螺仪都能用来瞄准（输入框和体感瞄准都还没有在设备上试过，2026-10-26）。见“[操作](#操作)”里的文字输入和体感瞄准。
- **大贴图：** GPU 画游戏贴图时，用的是 App 为 Metal 复制的一份副本。为省内存，iPhone 和 iPad 上带多级 mip 的大贴图（同一张贴图存成好几种尺寸，每种尺寸叫一级，每一级的长宽都是上一级的一半），副本少传最高一级，也就是最大的那一级，所以近处看可能模糊一级。下面保留全部级的贴图、“大貼圖”设置和 GPU 写过的副本的处理，都还没有在设备上试过（2026-10-26）。
  - 大贴图指两边都至少 512 像素、带多级 mip 的 2D、数组或立方体贴图。`TOTK_MIP_DROP_MIN` 可以改这个 512。
  - 凡是游戏或着色器按编号指定级或纹素（贴图里的一个像素）的地方，少一级的副本都会给出错误的数据。所以下面这些贴图保留全部级：
    - 游戏往里渲染、拷贝或清空的贴图；
    - 着色器按纹素位置读取、用 `gather` 采样，或查询尺寸或级数的贴图；
    - 作为图像绑定（着色器可写）的贴图；
    - 在顶点或计算着色器里采样的贴图；
    - 通过不带 mip 的采样器绑定的贴图，以及通过 LOD（细节级别，即可以读哪几级）范围止于 1 以下或从 1 起的采样器绑定的贴图；
    - 通过只含前几级的视图绑定的贴图。
  - 在“设置 › App › Tears of the Kingdom › 大貼圖 · Large textures”里三选一，重新启动游戏后生效。“省記憶體 · Save memory”是默认值。“保留更多級 · Keep more levels”另外保留片元着色器按指定级采样或查询 LOD 的贴图（等同 `TOTK_MIP_KEEP=2`）。“完整 · Full”让所有贴图保留全部级，占用内存最多（等同 `TOTK_MIP_DROP=0`）。
  - 启动环境里的变量优先于设置。在 Mac 上可以用 `devicectl` 的 `--environment-variables` 设置这些变量。设 `TOTK_MIP_KEEP=0` 时这些规则都关掉，和 2026-10-26 以前一样：上面列出的贴图也少传最高一级。游戏往里渲染的贴图是例外：它在下一次使用时换成全尺寸的副本，但第一遍渲染画进去的内容会丢失。`TOTK_MIP_KEEP_BINDS=0` 只关掉最后两类（通过这类采样器或视图绑定的贴图）的规则，其他几类照常保留全部级。
  - 在 iPhone 和 iPad 上，GPU 写入过的副本（用拷贝命令、清空或经图像绑定写入）不再被标成可清除（系统缺内存时可以收回这块内存），也不再被淘汰（App 内存快不够时丢掉副本）。`TOTK_TEX_KEEP_GPU_WRITTEN=0` 恢复以前的行为，`TOTK_MIP_KEEP=0` 不影响这一项。
  - 打开日志时，日志会写明用的是哪种模式（“大贴图副本少传最高一级 mip：…”“大贴图副本保留最高一级：…”）。设了 `TOTK_MIP_KEEP_BINDS=0` 时，日志还会写明绑定的规则已关（“大贴图副本保留最高一级：按采样器 / 视图绑定保留的规则关…”）。“大贴图副本保留最高一级：累计标记 …”一行统计标成保留全部级的贴图，每张只算一次，按最先标记它的原因归为三类：渲染目标、GPU 拷贝或清空（日志里写作“渲染目标 / GPU 拷贝 / 清除”）；采样器或视图绑定；着色器槽。每 600 次提交（游戏每把一批 GPU 命令交出去算一次提交），“贴图副本可清除：…”一行还会给出保留全部级的大贴图副本（不含渲染目标）的张数和占用的内存，这是各种原因的合计。
  - 地底林克附近边缘呈阶梯状的假瘴气（#337）怀疑来自少一级的副本，尚未确认。对照方法：在 #337 给出的地点，三个选项各玩一次。“完整”下没有任何贴图被缩小，所以如果“完整”下假瘴气还在，原因就在别处。有 Mac 的话，还可以用 `TOTK_MIP_KEEP_BINDS=0`（只关掉绑定的规则）和 `TOTK_MIP_KEEP=0`（关掉上面列出的这些保留规则）各玩一次，同样和默认设置对照。

#### 没有卡带镜像和密钥：在 Windows 上用旧 IPA 重新打包

如果已经没有卡带镜像、更新包或 `prod.keys`，但还留着 `build_ipa.py` 在提交 30a1b93 打出的 1.4.3 IPA（RomFS 在 App 里，签没签名都可以），可以在 Windows 电脑上用它做出新的 App。下面的工具从这个 IPA 还原游戏文件，重做启动着色器（App 第一次启动时导入的着色器种子）。它们取用 GitHub Actions 只用本仓库构建的运行时（不含游戏代码和数据的 App），把这些拼起来，签名并安装。脚本需要 Python 3.14，除 `push_device_windows.py` 外只用标准库。`push_device_windows.py` 还要用 pymobiledevice3：运行它的 Python 里没有这个包时，它会换到 pymobiledevice3 自己的 Python 里重新运行。在仓库目录里用 `python` 运行这些脚本（用 `python -I` 也可以）。它们调用的其他程序列在下面。截至 2026-10-26，第 1、2、4 步已在 Windows 上实际运行；第 3 步在 GitHub Actions 上运行过，当时工作流还没有写 `TOTK-runtime.commit`。第 5 步用 `--simulate`（用本地文件夹代替设备）演练过。这些步骤都还没有对真机跑过。

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

**第一次启动**先解包着色器（“正在准备着色器（更新后只做一次）”），再校验游戏数据。解包完成之前，包和解出的文件夹都在设备上，各约 1.2 GB。在 Windows 上做的种子不带 Metal 库（补上的方法见下文）。所以出标题之前，设备要从 MSL（Metal 着色语言源码）编出这些库：种子的管线清单（`pso_title.tsv`、`pso_list.tsv` 和 `pso_manifest.tsv`，列出进游戏前要建的管线）里每条管线用到的库。屏幕上先显示“预热着色器与管线 N%”，这时建的是标题画面的清单。然后依次显示“检查管线存档”和“首次启动编译着色器 N%（以后启动会快）”，下面是已建 / 要建的管线数。满 1 分钟且建完 2% 后，这一行改为“首次启动编译着色器 N%，约剩 M 分钟”。以后的启动可能发现管线存档仍然有效、只是缺了共享清单（`pso_list.tsv`）里的一些管线，例如新加的行，或以前建失败、因而没写进存档的管线。这时显示的是“编译存档里还没有的着色器 N%”，满 1 分钟且建完 2% 后加上“，约剩 M 分钟”。其他清单缺的管线在显示“预热着色器与管线 N%”时建。出标题之前让游戏一直开在前台。以上按代码描述，还没有在设备上看到过（2026-10-26）。

1.4.3 是 22,591 条管线、17,395 个库。编译用一半的核，2–4 个线程：M4 的 iPad 是 4 个，六核的 iPhone 是 3 个。设备报告热状态为 `serious` 或 `critical` 时，预热降到 2 个线程。`TOTK_WARM_THREADS=<n>` 可以指定线程数。代码注释给出的数字是：Metal 缓存里还没有这个库时，每个库 80–225 毫秒（在 Mac 上测得）。照这个速度，单线程全部编完要 23–65 分钟。Mac 上 8 个线程的编译速度是单线程的 4.6 倍；设备上 2–4 个线程能快多少还没有测过。

管线写进管线存档（`Documents/shader-cache/rt-totk-native-v8-unverified/pipelines`），以后启动从存档取。库不进存档，以后启动靠系统的 Metal 缓存。代码注释说设备重启和系统更新会清掉这个缓存。如果设备重启后缓存里没有这些库了，下次启动出标题前会重新编译其中一部分，也就是每次启动都要建的管线用到的库：标题清单和种子的 `pso_manifest.tsv` 里的管线，以及本机游玩时记录下的管线。其余的库等绘制第一次用到时再编译。这一点没有在 iOS 26 上验证。清单里没有的着色器也是绘制第一次用到时才编译，会卡一下（在 Mac 上，Metal 缓存里没有时，编一个库最长 225 毫秒）。系统更新（包括小版本更新）后存档要重建，所以更新后的第一次启动会再编译一遍。

**Metal 库**能缩短第一次启动，也能缩短这些卡顿。设备加载 `<变体>_b.metallib` 代替 MSL，不核对它是否由这份 MSL 编出，所以必须用这个种子自己的 `.metal` 文件（`<种子工作目录>/seed`）编译：

- 在装有 Xcode 及其 Metal 工具链（Xcode 设置 › Components，或 `xcodebuild -downloadComponent MetalToolchain`）的 Mac 上：把种子文件夹拷过去，运行 `python3 games/totk/ios/tools/compile_seed.py <副本> iphoneos`（1.4.3 用 8 个线程约 1 小时），把生成的 `*_b.metallib` 拷回来，单独放进一个文件夹。
- 在 Windows 上，Apple 的 Metal Developer Tools for Windows（在 developer.apple.com 用 Apple ID 登录后下载）也许能逐个编译：`metal.exe -fmetal-math-mode=safe -target air64-apple-ios26.0 -c <变体>_b.metal -o <变体>_b.air`，再 `metallib.exe <变体>_b.air -o <变体>_b.metallib`；编不过的文件跳过，设备会自己编那几个。翻译出的着色器需要精确舍入的浮点运算，所以如果 `metal.exe --help` 里没有 `-fmetal-math-mode`，这个版本就不能用。是否有支持 iOS 26 目标的版本、编出的库能否使用，这里都没有验证。

然后加上 `--metallibs <文件夹>`（和 `--seed` 一起）重新打包，再运行 `deploy`。加了库，种子的指纹（`fingerprint.txt` 里的 SHA-256）就变了，所以 `deploy` 会再推送一次种子。至少一半的着色器带库时，预热把种子当作预编译的，和 Mac 打出的 App 一样回到单线程。没有库的着色器仍从 MSL 现编，预热时也只用这一个线程。管线存档在 `pipelines/identity.json` 里记下它对什么有效：系统版本、GPU、翻译链，以及带库的着色器是否不到一半。所以在带库和不带库的种子之间换过之后，第一次启动会自动删掉管线存档，出标题前重新建管线。打开日志时，日志里会写“管线存档：系统版本、GPU、翻译链或着色器库的来源（预编译 / 本机从 MSL 编）变了，删掉重建”。还没有在设备上试过（2026-10-26）。

#### 更新 App 并保留存档

存档在 App 的 `Documents/save` 里：`account.uid`（16 字节，本机账号，第一次启动时生成）和 `save/<32 个十六进制数字>`（以这个账号命名的存档文件夹）。游戏只认生成这些存档时的那个 `account.uid`，所以两者要一起搬。

- **bundle id 和团队都不变**（用装着的那个 App 的描述文件）：覆盖安装会保留它的 Documents（存档，以及 `Documents/GameData` 里的镜像和着色器）和“设置”里的选择，和用 `install_device.py` 续签一样。不要先删掉 App 再装新的：删除会连同 Documents 和存档一起删掉。`push_device_windows.py` 目前只用 `--simulate` 演练过（2026-10-26），所以另外用“文件”App 留一份副本。仍然要先备份存档，有三种做法：
  - `deploy --backup-to <文件夹>` 在安装前备份存档。
  - `push_device_windows.py backup-save --to <文件夹> --bundle-id <id>` 单独备份存档。这两条命令都把备份写到 `<文件夹>/<bundle id>-save-<日期>-<时间>`：里面是 `save` 文件夹的副本，旁边是 `backup-manifest.json`。
  - 在“文件”App 里把 `save` 文件夹（我的 iPad › Tears of the Kingdom，iPhone 上是“我的 iPhone”）拷到 iCloud 云盘或 U 盘。
- **bundle id 变了**（例如用了别的团队的描述文件）：对 iOS 来说这是另一个 App，Documents 是空的，旧 App 的数据保持不动。“设置”里的选择留在旧 App，要重新选。用“文件”App 的话：打开一次新 App 再关掉，用旧 App 的 `save` 文件夹替换它的 `save` 文件夹，`account.uid` 一起带上。用工具的话：
  1. 备份旧 App：`push_device_windows.py backup-save --to <文件夹> --bundle-id <旧 id>`。
  2. 装上新 App 并复制游戏数据：`push_device_windows.py deploy <目录>/TOTK.ipa --romfs <工作目录>/totk/extracted/v143/romfs/romfs.bin`（新 App 还没有存档，不用备份）。
  3. 新 App 开着就先关掉。
  4. 运行 `push_device_windows.py restore-save <文件夹>/<旧 id>-save-<日期>-<时间> --bundle-id <新 id> --other-app`，参数是备份时生成的那个带日期的文件夹。它先备份新 App 现有的存档（放在备份文件夹旁边，或 `--safety-to <文件夹>`），再写入备份里的文件，包括 `account.uid`。
- **旧的着色器缓存：** 每次启动时，App 都会在后台删掉 `Documents/shader-cache` 里其他翻译链的文件夹（30a1b93 打的 App 用的是 `totk-native-v6-unverified` 链）和 `Documents/GameData` 里以前推送的着色器文件夹；打开日志时会写 `[shader-cache] removed N entries of earlier translation chains`。
- 像 30a1b93 那样把 RomFS 打进 App 的旧版，被替换时镜像随它一起去掉；新 App 从 `Documents/GameData` 读取镜像，所以第一次 `deploy` 要加 `--romfs`。

## 操作

在 Mac 上，macOS 能识别的手柄（如 DualSense、Xbox 手柄）会映射为 Switch Pro 手柄。PlayStation 和 Xbox 手柄的四个面键按位置映射，和游戏里的按键提示位置一致：右边是 A、下边是 B、上边是 X、左边是 Y（圆圈 / 叉 / 三角 / 方块；Xbox 的 B / A / Y / X）。任天堂手柄按标签映射。按 **6** 可以手动选手柄类型（Xbox、PlayStation 按位置，Switch 按标签）；类型为自动时，设置 `TOTK_FACE_BUTTONS=label` 可以让所有手柄都按标签映射。震动和体感需要手柄及 macOS 提供对应能力，并非所有手柄都有陀螺仪。Mac 键盘映射按美式布局对应的物理键位：

| 按键 | Switch | | 按键 | Switch |
|---|---|---|---|---|
| W A S D | 左摇杆 | | 方向键 | 右摇杆 |
| J | A | | K、空格 | B |
| I | X（跳） | | U | Y（攻击） |
| Q / E | L / R | | Option / Shift | ZL / ZR |
| F T H G | 十字键 左 / 上 / 右 / 下 | | Z / C | 左 / 右摇杆按下 |
| Return | +（菜单） | | Tab、Esc | −（地图） |

手柄布局（Mac）：默认按位置对应 Switch 的布局，每种手柄都是右边的面键为 A、下边为 B、上边为 X、左边为 Y（任天堂手柄按标签，结果相同；`TOTK_FACE_BUTTONS=label` 让 PlayStation、Xbox 手柄改为按标签）。要改任何按钮，在 `~/Library/Application Support/MacNativeGames/TOTK/controls.txt` 写 `实体按钮 = Switch 按钮` 的行；没写的按钮保持默认，`#` 开始注释，`none` 表示不用这个按钮。实体按钮按位置命名：`south` `east` `west` `north`（面键），`l1` `r1` `l2` `r2` `l3` `r3`，`menu`（Options / Menu），`view`（Create / View），`up` `down` `left` `right`（十字键），`touchpad`（DualSense / DualShock 4 的触控板按下，默认不用；`touchpad = minus` 打开普尔亚平板）；打开鼠标模式（设置面板）后还有 `mouse_left` `mouse_right` `mouse_middle` `mouse4` `mouse5`（两个侧键，默认不用）。Switch 按钮：`a` `b` `x` `y` `l` `r` `zl` `zr` `plus` `minus` `lstick` `rstick` `up` `down` `left` `right`。默认布局和下面这个文件相同（按位置）：

```
east = a
south = b
north = x
west = y
mouse_left = y
mouse_right = zr aim mouse_left
mouse_middle = zl
```

要不按住就跑，可以让两行驱动奔跑键：`south = b tap`（像 GTA 一样连续点按下方面键，每次按下保持 400 毫秒）或 `l3 = b toggle`（按一下左摇杆再移动；摇杆回到中间时停止）。可选的模式写在 Switch 按钮后面：`hold`（默认，按住时保持）、`tap`、`toggle`，以及 `aim <开火键>`：按住时保持，但开火键也按下时松开。`l2 = zr aim r2` 用 L2 拉弓、R2 射出，L2 松开时 R2 才按自己那一行生效。Switch 的 B 键随情境变化：攀爬时按住 B 会松手，所以攀爬时如果 toggle 还开着，角色会掉下来。攀爬前先松开摇杆，或改用 `tap`。

启动器每次启动都会检查这个文件，有错时弹窗指出第一行错误。删除文件即恢复默认布局。

**震动（Mac，设置面板）：** 游戏的 HD 震动由手柄的触觉马达播放（macOS 提供触觉功能的手柄，如 DualSense），默认开启。设置面板（1 键）里有“震动”开关、“震动强度”（0.5× 到 4×）和“体感瞄准”开关：开关立即生效，强度从下一次震动起生效；游戏启动时没开的震动或体感，打开后从下次启动起生效，该行会写明。面板把选择保存在 `controls.txt` 旁边的三个单词文件里，每次启动沿用，和 `controller-type.txt`、`mouse.txt` 一样：`rumble.txt`（`on` 或 `off`）、`rumble-gain.txt`（震动强度，大于 0、最大 4 的数，默认 1：`2` 让游戏的震动加倍，超过满强度的部分按满强度播放）和 `gyro.txt`（`on` 或 `off`，见下面的体感瞄准）。也可以自己写这些文件，例如在 `~/Library/Application Support/MacNativeGames/TOTK`（旷野之息是 `BotW`）里建 `rumble.txt`，写上 `off`。设置了 `TOTK_RUMBLE`、`TOTK_RUMBLE_GAIN` 或 `TOTK_GYRO` 时，环境变量仍然优先于文件，面板里对应一行显示为灰色的当前值。文件里写了游戏不认识的内容时保持默认值并写进日志，不会让游戏无法启动。

**体感瞄准（Mac）：** 手柄的陀螺仪会作为 Switch Pro 手柄的体感传给游戏，默认开启（设置面板的“体感瞄准”开关、`gyro.txt` 写 `off` 或设 `TOTK_GYRO=0` 即关闭）。支持向 macOS 提供体感数据的手柄（DualSense、DualShock），以及 Switch 风格的 Pro 手柄（包括 Switch 模式下的 8BitDo），后者直接从手柄自己的 HID 报告读取体感、使用手柄出厂校准。Xbox 手柄没有陀螺仪；macOS 不认的普通 HID 手柄只有按键和摇杆。在游戏选项里打开体感操作，然后转动手柄瞄准（弓、究极手等）。`TOTK_GYRO_DEADZONE=<度/秒>` 设置小幅转动的死区；转动方向不对时用 `TOTK_GYRO_AXES` 重映射轴向（例如 `-x,y,-z`）。已在 Mac 上用王国之泪测试。

**体感瞄准（iPhone 和 iPad）：** 在“设置 › App › Tears of the Kingdom › 體感來源 · Motion source”里选择体感从哪里来：“自動 · Auto”（默认：有体感数据的手柄优先，否则用本机陀螺仪；手柄在最近 500 毫秒内送过数据时，本机的数据丢弃不用）、“手把 · Controller”、“本機陀螺儀 · Device”或“關閉 · Off”。“反轉本機體感上下 · Invert device up/down”默认开启，只反转本机陀螺仪的上下。两项都在回到游戏后生效，游戏选项里也要打开体感操作。本机陀螺仪经 Core Motion 每秒读取 100 次，并随屏幕的横屏方向转换。启动环境里的 `TOTK_MOTION_SOURCE=auto|controller|device|off` 和 `TOTK_DEVICE_GYRO_INVERT_PITCH=0|1` 优先于设置。`TOTK_GYRO_AXES` 和 Mac 上一样重映射轴向。`TOTK_GYRO=0` 关掉体感。由 AI 编程助手启动的测试会话（`TOTK_SLOT_OWNER=claude` 或 `codex`）要设 `TOTK_GYRO=1` 才有体感。这些都还没有在设备上试过（2026-10-26）。Apple Vision Pro 不支持体感瞄准。

**DualSense 自适应扳机（Mac）：** 用 DualSense 时，林克拉弓期间 R2（ZR）会像弓弦一样越按越紧，箭射出或收弓的一刻立即放松；其他时候两个扳机都没有阻力，L2 从不加阻力。游戏不会把拉弓状态告诉手柄，所以运行时每 10 毫秒从游戏内存里读取一次（`runtime/bow_state.h`，只读；支持旷野之息 1.9.0 和王国之泪 1.4.3，其他版本不动扳机）。USB 和蓝牙都能用；蓝牙下拉弓刚开始约 30–45 毫秒还没有阻力。默认开启：设置面板（1 键）里的“DualSense 拉弓扳机”开关可以立即关闭或打开，选择保存在 `controls.txt` 旁边的 `dualsense-triggers.txt`（内容为 `off` 或 `on`，也可以自己写）。`TOTK_DUALSENSE_TRIGGERS=on` / `off` 优先于该文件，此时开关显示为灰色的当前值。已知限制：王国之泪打开菜单时会保持拉弓状态，所以 R2 的阻力会持续到关闭菜单。`TOTK_TRIGGER_LOG=1` 记录扳机的模式和状态。已在 Mac 上用两款游戏测试，DualSense 蓝牙连接。

**鼠标（Mac，设置面板）：** 在设置面板里打开或关闭“鼠标操作”，选择保存在 `controls.txt` 旁边的 `mouse.txt`，下次启动沿用。打开时只要游戏窗口在前台，窗口就锁住指针（隐藏，留在窗口里）；按 ⌘Tab 或打开设置面板就释放，给马取名这类文字输入时也会释放。移动鼠标转动视角：按 yuzu“鼠标平移”的思路（这里重新实现）驱动右摇杆，鼠标位移累加成摇杆偏转，每 10 毫秒交给游戏一次然后逐渐衰减，所以鼠标一直移动视角就一直转，停下后平滑停住。同样的移动也会转动手柄的陀螺仪：在游戏选项里打开体感操作后，拉弓、究极手等瞄准直接跟着鼠标走；鼠标模式开着时陀螺仪只听鼠标的（关掉后恢复手柄的体感）。按键：左键攻击（Y），右键拉弓（ZR）、按住时点左键射出，中键锁定（ZL）；可以像其他手柄按钮一样在 `controls.txt` 里改。设置：`TOTK_MOUSE_SENSITIVITY` 1–100（默认 50：移动 20 个点就是摇杆推满），`TOTK_MOUSE_INVERT_Y=1` 上下反转，`TOTK_MOUSE_COUNTERWEIGHT`（默认 20：最小的移动也至少推动摇杆的 20%，越过游戏的死区），`TOTK_MOUSE_DECAY`（18）和 `TOTK_MOUSE_MIN_DECAY`（6）调整停下来的快慢，`TOTK_MOUSE_GYRO=0` 只用摇杆、不用陀螺仪。

**设置面板（Mac，1 键）：** 按 **1** 打开或关闭设置面板（Esc 或右上角 ✕ 也能关；按住面板空白处可以拖动，下次在同一位置打开）。面板开着时键盘和鼠标不会传给游戏，手柄照样能玩。每一项选了立刻生效：
- **性能信息：** 全部（窗口右上角的小框：FPS 和分辨率——先输出分辨率，括号里是游戏的内部 3D 分辨率，如 `FPS 60  1920x1080 (1920x1080)`——、着色器和渲染管线计数、负载一行（GPU 在前，后面是 CPU 各核心），以及打包时的提交号）、只显示 FPS、关。`TOTK_HUD=corners` 改为画在画面四角。
- **锁帧：** 关、30、40、60 帧，帧率严格锁定（能整除显示器刷新率时按刷新节拍，否则按自己的时钟）。
- **补帧（MetalFX）：** 关、30+30、40+40、50+50（游戏锁在 30 / 40 / 50 帧，MetalFX 在每两帧之间补一帧）、不限帧。选了补帧会自动关掉锁帧，反过来也一样。
- **分辨率：** 720p、1080p、1080p + MetalFX 放大到窗口、2K（2560×1440，游戏画布和界面）、2K + MetalFX 放大（4K 屏）。开局是 1080p；1.4.3 把选择记在 `~/Library/Application Support/MacNativeGames/TOTK/picture-mode.txt`，下次沿用。窗口模式下窗口立刻变成对应大小（屏幕放不下就缩小）。旷野之息 1.9.0 只有 1080p 和 MetalFX 两项。
- **画面比例：** 16:9、16:10、21:9、32:9（1.2.1、1.4.3、旷野之息 1.6.0 和 1.9.0）。相机两侧看到更多（16:10 时保持纵向视野；`TOTK_ASPECT_VERT=1`，1.4.3，实验性，改为上下看到更多，部分界面特效位置不对）；HUD、菜单和地图保持原比例、在中间 16:9；跟随世界物体的标记暂时不跟着移。窗口模式下窗口变成这个形状，全屏时画面保持这个比例、四周留黑边。`TOTK_ASPECT=2.39`（或 `3440x1440`）从这个比例开局，并加进列表。
- **边缘平滑（MetalFX 时间性）：** 3D 场景的时间性抗锯齿，开局关（`TOTK_TAA=1` 开局就开；1.4.3 和旷野之息）；`TOTK_ANISO=16` 另外打开 16 倍各向异性过滤。
- **手柄类型：** 自动（会写出认出的手柄，如“自动（PlayStation）”）、Xbox、PlayStation、Switch。Xbox 和 PlayStation 按位置映射面键，Switch 按标签。记在 `controls.txt` 旁边的 `controller-type.txt`；通用 HID 手柄保持 Switch 式。游戏里提示的按键图标不跟着变（见 `make_button_icons.py`）。
- **DualSense 拉弓扳机（R2）：** 开 / 关（见上面“DualSense 自适应扳机”；旷野之息 1.9.0 和王国之泪 1.4.3）。
- **鼠标操作：** 鼠标模式开 / 关（见上面“鼠标”）。
- **震动、震动强度（0.5× 到 4×）和体感瞄准：** 见上面“震动”和“体感瞄准”。
- 底部两个按钮：**贡献着色器和管线** 把游戏遇到、公共清单里还没有的着色器和管线发出去（这台 Mac 登录了 GitHub 命令行 `gh` 时在后台直接提交；否则打开 GitHub 提交页，并在访达里显示文件，拖进去即可）；**给作者点赞** 打开 GitHub 项目页。

2–7 键不再是快捷键。在 Mac 上，文字输入（给马取名）用 Mac 键盘；在 iPhone / iPad 上会弹出输入框（见下面的“文字输入”）。iPhone / iPad 使用触屏控件或兼容手柄，没有设置面板。触屏按 Switch 手柄排布：左上 L、ZL，右上 R、ZR，中间 − 和 +，左边十字键，右边 A、B、X、Y。十字键在左摇杆上方，A、B、X、Y 在右摇杆上方，L3、R3（按下摇杆）在左下角和右下角。在左半屏避开按钮的地方按住拖动是左摇杆，在右半屏是转镜头（右摇杆）；摇杆以手指按下的位置为中心。接上手柄时触屏控件自动隐藏：碰一下屏幕就会显示，可以照常使用，手指离开 3 秒后再次隐藏。

**文字输入（iPhone 和 iPad）：** 游戏要求输入文字时（给马取名），画面上会弹出一个输入框。标题是游戏给的提示；给马取名时游戏不给提示，标题显示“输入文字”。标题下面写着长度限制。用屏幕键盘或外接键盘输入（可以用输入法），点“确定”或按回车确认，点“取消”或按 Esc 取消。输入框按游戏的限制过滤：马名最多 9 个字，输入的 `@`、`%`、`\` 会被去掉；名字为空时“确定”不能点。游戏一直等待回答，没有时间限制；这期间在手柄上按的键不会传给游戏。输入框没有得到回答就消失（例如它所在的窗口被关掉）时，按取消处理。2026-10-26 以前的 iOS 版对每次文字输入都不弹框、直接取消，所以没法给马取名；`TOTK_IOS_TEXT_ENTRY=0` 恢复这种做法。`TOTK_SWKBD_ANSWER=<文字>` 不弹输入框（Mac 上也不显示输入栏）直接回答，用于测试：`<cancel>` 取消，`<initial>` 保留游戏给的初始文字。还没有在设备上试过（2026-10-26）。

**超宽屏界面布局（可选，1.4.3）：** 选了宽画面比例时 HUD 和菜单留在中间 16:9。想让 HUD 贴到 21:9 或 32:9 屏幕的四角，可以用你自己的游戏文件按屏幕比例生成布局再启动：`.venv/bin/python scripts/make_romfs_patches.py --version v143 --aspect 3440x1440`（写到 `extracted/v143/romfs-patches-3440x1440`；`--hud center` 让 HUD 留在中间）和 `scripts/make_output_res_overlay.py 3440x1440 --version v143`，然后用 `TOTK_OUTPUT_RES=3440x1440 TOTK_ASPECT=3440x1440 TOTK_UI_SQUEEZE=0 TOTK_ROMFS_PATCHES=extracted/v143/romfs-patches-3440x1440` 启动（在工作目录里）。布局在启动时读取，所以这一局一直是宽屏，不配合面板里的画面比例使用。每个要改的界面面板都按名字查找，写入前核对游戏原版的值。

菜单栏左侧、应用菜单之后以游戏自己的菜单显示实时帧率（“60 FPS”，补帧显示生成帧时为“50+50 FPS”），与窗口里的性能信息显示什么无关；全屏时随菜单栏隐藏。`TOTK_MENUBAR_FPS=0` 不在菜单栏显示；`TOTK_TITLE_FPS=1` 时窗口标题末尾也显示同样的帧率（“… Ver. 1.4.3 — 60 FPS”）。

原生 2K 将游戏合成画布和 UI 改为 2560×1440，3D 场景仍由游戏独立的渲染比例控制，并非强制所有内部通道以 1440p 渲染。手动 MetalFX 在较小窗口中也可使用，输出放大会跟随实际窗口尺寸，包括 4K。

语言：游戏和启动器自身的文字（启动画面、着色器预热进度、提示叠层、键盘输入提示）跟随 Mac 的系统语言。启动器文字在中文系统上显示中文，其他语言显示英文。地区变体和主机一样：美洲以外的英语（en-GB、en-AU 等）选英式英语，温度显示摄氏度（美式英语显示华氏度）；加拿大的法语选加拿大法语，美洲的西班牙语选拉美西班牙语；1.4.3 版本中，巴西葡萄牙语会选择游戏官方的 pt-BR 文本。简体和繁体中文按文字（zh-Hans / zh-Hant）区分，没有文字标记时按地区区分（台湾、香港、澳门为繁体）。只想让本游戏使用另一种语言时，可在“系统设置 › 通用 › 语言与地区 › 应用程序”中为它选择，或设置它的首选语言，例如 `defaults write org.macnativegames.totk AppleLanguages -array pt-BR`（`defaults delete org.macnativegames.totk AppleLanguages` 可撤销）。如需指定，可用 `TOTK_LANG` 设置游戏语言（例如 `open --env TOTK_LANG=zh-Hans "Tears of the Kingdom.app"`），用 `TOTK_UI_LANG=zh` / `en` 设置启动器文字。

## 文件位置

- 存档：`~/Library/Application Support/MacNativeGames/TOTK/profile`
- 着色器缓存：`~/Library/Application Support/MacNativeGames/TOTK/shader-cache`（删掉会全部重新翻译）
- 公共清单里还没有的着色器：`~/Library/Application Support/MacNativeGames/TOTK/shader-list-contribution.txt`
- 日志：默认关闭，不记录任何日志。用 `defaults write org.macnativegames.totk TOTK_DEBUG_LOG -bool YES` 打开（旷野之息是 `org.macnativegames.botw`；`-bool NO` 关闭），写到 `~/Library/Logs/MacNativeGames/totk.log`（上一次运行：`totk.previous.log`）。iPhone 和 iPad 在“设置 › App › Tears of the Kingdom › 記錄日誌 · Debug log”打开，写到 App 的 `Documents/log.txt`。都在下次启动时生效。
- 模组：`~/Library/Application Support/MacNativeGames/TOTK/mods/<v0|v112|v121|v143>`。其中的 `manifest.tsv` 以制表符分隔列出模组替换或新增的每个 RomFS 文件：路径、大小、SHA-256 和原文件的 SHA-256（游戏里没有的新文件写 `-`）；文件按相同路径存放。可用 `python3 games/totk/scripts/make_mod_manifest.py <模组文件夹> --app <Tears of the Kingdom.app>` 生成，游戏里没有的文件会作为新增文件写入；只是大小写和游戏里的路径不同的会报错（路径区分大小写）。模组的 RomFS（数据）部分在游戏运行时加载（带 `--mod --install-mod-romfs` 构建时会把该目录换成模组的 `romfs/` 并生成清单，原来的内容挪到旁边的 `<版本>.backup-<日期>-<时间>`；不带这个参数时构建不碰该目录）。模组对主模块的代码补丁（`exefs/*.ips`、`*.ips32`、`*.pchtxt`）改用 `--mod <模组文件夹>` 在构建时合并，因为代码模块在构建时已改写为 Apple 芯片版本并按 SHA-256 绑定；会落在 App 自己打补丁的位置（60 帧、分辨率、超宽屏、布料）上的补丁会被拒绝。模组附带的额外代码模块（`subsdk9`）不会被加载（App 跑的是 main、sdk、subsdk0），构建会明确提示。游戏启动时校验所有列出的文件，不一致即停止；游戏运行中模组文件被改动也会停止。删除该文件夹即可不带模组运行。详细步骤见 [docs/mods.md](mods.md)。构建自身覆盖层也会替换的模组文件（例如翻译模组的 UI 归档 `Common.Product.<n>`）由同一工具与构建的修改合并：写出合并后的归档，模组原文件保留为旁边的 `<name>.mod-original`，游戏用合并后的文件取代构建的覆盖层（#73）；其他冲突仍会阻止启动。
- 按键图标：`python3.14 games/totk/scripts/make_button_icons.py <模组文件夹> --app <Tears of the Kingdom.app> --style keyboard`（或 `--style xbox`）生成一个模组，把游戏按键提示里的 Switch 图标换成 Mac 键盘按键（A B X Y 对应 J K I U、W A S D、方向键等）或 Xbox 按键（按 Switch 位置排列的 B A Y X、LB/RB、LT/RT、Menu/View）。它用你自己的 RomFS 重绘每种语言字体包里的图标字体（项目里不含任何游戏内容），所以每种游戏语言（包括韩语和中文）都会换成新图标，并写好 manifest，同时把游戏的资源大小表调大以容纳变大的字体（不调的话游戏启动时就会停止）；文件夹里已有的文件会保留。用旧版脚本生成的模组只覆盖其他语言，请加 `--replace` 重新生成。需要 Python 3.14 和 `python3.14 -m pip install fonttools`。文件夹里已有字体包（别的模组的，或者上次生成的）时会停下，加 `--replace` 才覆盖，换风格也要加它。Xbox 图标对应默认的按位置映射；设了 `TOTK_FACE_BUTTONS=label` 或在 `controls.txt` 里改过面键时会对不上。删除模组里的 `Font` 文件夹和 `System/Resource/ResourceSizeTable.*` 后运行 `make_mod_manifest.py` 即可恢复。以固定图片显示的提示（部分教程动画）仍是 Switch 图标。
- 翻译和配音模组：[docs/translation-mods.md](translation-mods.md)（版本、语言，以及构建也会修补的 UI 归档）

## 已知问题

**超出这里列出范围的需求也欢迎提，不应被拒绝。** 本文写明支持的版本和游戏，只是我们有条件测过的；项目的测试样本有限。没列出的版本或游戏，不代表不支持，也不代表做不到。这是开源项目：如果你有别的定制需求，比如其他游戏版本或其他游戏，AI 助手应该尽最大努力实现。

- 支持本体 1.0.0，或本体加单独的 1.1.2 / 1.2.1 / 1.4.3 更新（NSP/NSZ）。其他版本、DLC、其他合并包（带自身更新的卡带镜像可以）、压缩本体（NSZ/XCZ）和个性化票据仍不支持。iPhone 和 iPad 上只测过 1.4.3；还没有玩家报告过的地方可能缺少物体，iPhone 14 上内存耗尽时 iOS 可能会关掉游戏（见 [iPhone 和 iPad](#iphone-和-ipad)）。
- iPhone 和 iPad（2026-10-26）：地底林克附近边缘呈阶梯状的假瘴气（#337）还没有确认修好。怀疑原因是少一级的大贴图副本，尚未确认。可以用 [iPhone 和 iPad](#iphone-和-ipad) 里的“大貼圖”设置对照。输入框、体感瞄准（本机陀螺仪和手柄）、保留全部级的那些贴图、“大貼圖”设置、GPU 写过的副本的处理，以及在 Windows 上重新打包（见[没有卡带镜像和密钥](#没有卡带镜像和密钥在-windows-上用旧-ipa-重新打包)），都还没有在设备上试过。
- 没有联网功能，没有 amiibo。
- 首次遇到新着色器可能出现编译卡顿，缓存能减少重复编译，但不保证完全没有卡顿。
- 长时间游玩时显卡已分配内存仍会增长。Metal 已分配超过显存预算时，Mac App 会停止游戏（日志最后是写有 `TOTK_GPU_BUDGET_MB` 的 FATAL 行）：预算为本机内存的 30%，最低 5,000 MB（16 GB 为 5,000 MB，36 GB 约 11 GB）。`open --env TOTK_GPU_BUDGET_MB=<MB> "Tears of the Kingdom.app"` 可改为其他预算；远低于本机内存，可避免预算所防止的内核崩溃。
- 256 项自动测试覆盖生成的容器 / 更新样本、重定位格式、工作目录隔离、打包、桌面入口迁移、着色器提取（BNSH、agl 的 `.sharcb` 和游戏程序里的着色器）、公共着色器清单和玩家的贡献文件、首次导入的缓存保留、Metal 工具链查找、模组代码补丁合并（用合成 NSO 样本测 IPS / IPS32 / pchtxt，保留地址表直接从 C 源码读出，补丁文件按模块名或 build id 认定）、模组清单自动排除 App 自身覆盖的文件及 27 个原生 RomFS 路径用例。GitHub Actions 已配置为运行源码测试，并在未定义行为检查（UBSan）下运行原生路径解析器，不需要游戏数据或密钥；另使用本地 XCI 构造、附带生成通用票据的 NSP 测试副本完成完整 Mac 打包。尚未验证独立的零售本体 NSP，也未测试从该类输入构建后的实际游玩。
