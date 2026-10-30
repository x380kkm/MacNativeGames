# Install

[← README](../README.md) · [中文](install.zh-CN.md)

This page only covers turning **your own** game files into an app on your Mac, iPhone or iPad. One build takes 20–40 minutes, most of it waiting. Controls and settings: [controls.md](controls.md). What has been tested: [test-records.md](test-records.md). AI assistants: the same steps as a checklist are in the [install skill](../.claude/skills/install-zelda/SKILL.md).

Contents: [What you need](#what-you-need) · [Build the app](#build-the-app) · [Breath of the Wild](#breath-of-the-wild) · [iPhone and iPad](#iphone-and-ipad) · [Apple Vision Pro](#apple-vision-pro) · [Update the app](#update-the-app) · [When the build stops](#when-the-build-stops) · [Where things are](#where-things-are) · [Known issues](#known-issues)

Ground rules: use only files from your own Switch and your own game. Nothing is downloaded for you, and nothing from the game is in this repository. Never edit `games/totk/assets/expected-*.json` or the scripts to get past a check: the error message says what is wrong. The app you build contains the game: it is for you only.

## What you need

**A Mac** with Apple silicon and **macOS 26** or later (the graphics use Metal 4). 16 GB of memory or more is recommended.
On macOS 15, use the community fork by [1918662410-ship-it](https://github.com/1918662410-ship-it/MacNativeGames), which adds a Metal 3 backend (not tested here).

**Your game files**, dumped from your own Switch. The title ID is usually in the file name in brackets; the build reads the file itself, never its name.

| Title ID | What | On the command line |
|---|---|---|
| `0100F2C0115B6000` | Tears of the Kingdom, base game **1.0.0**, XCI or NSP | first argument |
| `0100F2C0115B6800` | Tears of the Kingdom update **1.1.2, 1.2.1 or 1.4.3**, NSP or NSZ (optional) | `--update` |
| `01007EF00011E000` | Breath of the Wild base game, or the **1.6.0** card image (base + update + DLC in one XCI) | first argument |
| `01007EF00011E800` | Breath of the Wild update **1.6.0 or 1.9.0**, NSP or NSZ | `--update` |
| `01007EF00011F001`, `01007EF00011F002` | Breath of the Wild DLC packs, NSP (each optional) | `--dlc`, once per pack |

- For Tears of the Kingdom, **1.4.3** is recommended: it is the most tested and the only version tested on iPhone and iPad. No intermediate update is needed. Without `--update` you get 1.0.0.
- The base game must be uncompressed. Decompress an NSZ or XCZ base first (`nsz -D`).
- A card image that also holds its own update is fine; the version still comes from `--update`.

**`prod.keys`** from the same Switch (Lockpick_RCM). Keys dumped on an old firmware can be too old for a newer update.

**System fonts**, needed when the base game is an **NSP** and always for **Breath of the Wild**. Give one of:
- `--firmware <folder>`: your firmware dump as a folder of `.nca` files (unzip it first), or an installed firmware `registered` folder.
- `--shared-fonts <folder>`: the six `.bfttf` files an earlier Tears of the Kingdom build extracted, in `TOTK_build/totk/extracted/firmware/shared-fonts`.

A Tears of the Kingdom XCI carries the fonts itself.

**Free disk space** on the volume of the work folder:

| | Mac | iPhone / iPad |
|---|---|---|
| base game only | 25 GB | 45 GB |
| with an update | 40 GB | 60 GB |

The work folder is created next to the game file (`TOTK_build`, or `BotW_build` for Breath of the Wild). Keep it and the app on the **same APFS volume**: the 17 GB of game data is then cloned, not copied. If your game files are on an exFAT/FAT disk or a full one, pass `--work <folder>` and `-o <app>` on an APFS disk with room.

## Build with a window

Rather not type the command? With the tools of step 1 below installed, double-click **Build Game.command** in this folder (or run `python3.14 -m tools.builder`). A window opens: choose the game, then your game file, update, `prod.keys` and, when the game needs them, a firmware or shared-fonts folder (the work folder and the output app are under **Advanced**). **Check files** checks this Mac and your files and shows each problem, with the exact command that fixes it when there is one. **Build app** then runs `build_app.py` with those paths, and shows its four stages, the elapsed time and the log. When it is done, **Open app** and **Show in Finder** are one click away. Nothing is copied: the window saves the paths you chose, and the game, version, app and commit of the last successful build, in `~/Library/Application Support/MacNativeGames/Builder/settings.json`. Each run's output is also saved as `~/Library/Logs/MacNativeGames/builder-<game>-<date>-<time>.log`.

**Cancel** sends the build and everything it started an interrupt (SIGINT), then SIGKILL if it is still running 10 seconds later. The window then says how the build ended and whether that matches the signal it sent; it never claims more. Build again with the same work folder to go on: what was already done is reused. Closing the window or quitting it during a build asks first, cancels, and closes once the build has stopped; closing the Terminal window that opens with it cancels the build the same way, so keep it open while it builds.

**Your own picture:** the builder ships no image. Under **Details**, **Choose picture...** puts a picture of yours (PNG, JPEG, HEIC, GIF or TIFF) beside the form; **Left**, **Center** and **Right** pick the part it shows, and **Remove** takes it away. A copy is kept in `~/Library/Application Support/MacNativeGames/Builder/`, so the original can move.

**Settings tab:** for an app built from Tears of the Kingdom 1.4.3 or Breath of the Wild 1.9.0, the game starts with its automatic settings unless you choose otherwise here: picture at start (MetalFX 2K, native 2K where the version has it), frame interpolation (offered only when this Mac's GPU has Metal 4 MetalFX frame interpolation), edge smoothing, sharper ground at a distance and, on 1.4.3, the picture shape. **Play** starts the game. The picture, frame interpolation, edge smoothing and picture shape are the game's own settings, the ones its settings panel (key 1) keeps beside `controls.txt`: they hold for a start from Finder too, and changing them in either place changes both. Only the sharper ground at a distance, which the panel does not have, holds just when the game is started with **Play**. Settings are not changed while the game is running: close it first.

**Mods tab:** for Tears of the Kingdom 1.4.3 and Breath of the Wild 1.9.0, **Add mod...** takes a mod folder of yours (with `romfs/`, and for Tears of the Kingdom `exefs/` for code patches; Breath of the Wild's code patches are not used); the builder ships no mod. Mod manager packages (TKMM's `.tkcl`, BCML's `.bnp`) are refused: install them with their manager, or use a RomFS version. A mod made for Breath of the Wild 1.6.0 may install but still not work on 1.9.0: try it in the game. Each one is checked against your built app: its paths must fit this version and it must replace a file of the game; only then can it be switched on (that does not test it in play). Files another mod also replaces, files the app replaces itself and code patches (which need a build with `--mod`) are listed under the mod. **Apply mods** puts the mods that are on, in order (the lower one wins), into the game's mod folder through the repository's own installer, which writes the manifest and keeps the previous folder as a backup; the game loads them at its next start, from Finder or Play. Your own backups are never removed unless you ask.

**Updates:** in a `git clone`, the window checks when it opens whether MacNativeGames has new commits on its `main`, and lists them. It looks only at the remote whose URL is github.com/ly05010419/MacNativeGames (in a fork, usually `upstream`): other remotes, such as your fork, are never fetched. On `main`, **Update** then fetches and fast-forwards it: it never merges, rebases or discards anything, and when files were changed here or `main` has commits of its own it says so and leaves the update to you. On any other branch it only says how many commits are waiting, to merge by hand. After an update, close and reopen the builder and build again; your saved paths, and the saves of the game, stay where they are. A ZIP download cannot update itself: download the new version.

The window needs Tk (`brew install python-tk@3.14`); without it, **Build Game.command** says so. The same checks and build run in Terminal too:

```sh
python3.14 -m tools.builder --cli --game totk --game-file ~/Games/totk.xci --keys ~/keys/prod.keys --check-only
```

`--dry-run` prints the exact `build_app.py` command instead, and without either it asks before building (`--yes` does not ask). `python3.14 -m tools.builder --help` lists every option.

**The first double-click after downloading the ZIP:** macOS blocks a downloaded script it has not opened before. Open **System Settings › Privacy & Security** and click **Open Anyway** for `Build Game.command`, or run `xattr -d com.apple.quarantine "Build Game.command"` in this folder once. A `git clone` is not affected. The builder never removes the quarantine itself.

How the builder is made, for anyone changing it (people or AI assistants): [builder.md](builder.md).

## Build the app

**1. Tools** (once). An internet connection is needed:

```sh
xcode-select --install
# Homebrew, if missing: see https://brew.sh (it must live in /opt/homebrew)
brew install opus libvpx python@3.14
brew install python-tk@3.14   # only for the builder window (Build with a window, above)
```

Instead of Homebrew's Python you can use [uv](https://docs.astral.sh/uv/): `uv run --python 3.14 build_app.py …` in place of `python3.14 build_app.py …`.

Optional, if the full Xcode app is installed: `xcodebuild -downloadComponent MetalToolchain`. The build then compiles the startup shaders into the app, so the app can be moved and rebuilds are faster. Without it the build still works, and the shaders go into macOS's Metal cache for the app's location.

**2. This repository**: `git clone https://github.com/ly05010419/MacNativeGames.git` (or download the ZIP), then open Terminal in the `MacNativeGames` folder. If you already have it, run `git pull` first: many build errors are fixed on `main`.

**3. Build.** Put each path in quotes. Pick the app's final place now with `-o`: moving a Mac app later makes its first start compile the shaders again (unless the Metal toolchain was installed). Without `-o` the app is written next to the game file.

```sh
# Tears of the Kingdom 1.4.3 from an XCI
python3.14 build_app.py "<base 1.0.0.xci>" -k "<prod.keys>" --update "<1.4.3 update.nsp>" -o "/Applications/Tears of the Kingdom.app"

# Tears of the Kingdom 1.4.3 from an NSP: also give the fonts
python3.14 build_app.py "<base 1.0.0.nsp>" -k "<prod.keys>" --update "<1.4.3 update.nsp>" --firmware "<firmware folder>" -o "/Applications/Tears of the Kingdom.app"
```

If `/Applications` is on another volume than the work folder, choose a folder on the work folder's volume instead.

**4. Let it run to the end.** A fresh build takes **20–40 minutes** on an M-series Mac, longer on an 8 GB Mac:

| Step | Time |
|---|---|
| `1/4 code`: rewriting the game code for Apple silicon | about 3 min |
| `2/4 data`: extracting and verifying 17 GB, merging the update | several minutes |
| `3/4 shaders`: preparing the startup shaders | about 3 min |
| compiling them for your GPU | 6–12 min |
| `4/4 app`: macOS checks the new app once | 2–3 min |

- Long quiet stretches and lines like `... still running (3 min)` are normal. Do not stop it.
- If it was interrupted, run **exactly the same command** again. The work folder keeps every finished step.
- Quit the game before building, and never run two builds on the same work folder.
- It worked when the last lines say `done in N min: <path of the app>`.

**5. Open the app** from Finder.
- The start screen verifies the game data (about 20 s), then prepares the shaders and pipelines with a progress bar. The first start takes 1–2 minutes; later starts take about 12 s.
- An app moved to another volume afterwards is checked by macOS again: no window for a few minutes. Wait.
- If macOS asks for access to files on a removable volume, click Allow.
- New places can stutter briefly the first time.
- Key **1** opens the settings panel. Controls: [controls.md](controls.md).

## Breath of the Wild

The same script builds Breath of the Wild. It always needs fonts (see [What you need](#what-you-need)). The work folder is `BotW_build` and the app is `Breath of the Wild.app`. A fresh build takes about 16 minutes on an M4.

```sh
# 1.6.0 from the card image (base + update + DLC in one XCI)
python3.14 build_app.py "<botw 1.6.0.xci>" -k "<prod.keys>" --shared-fonts "<…/TOTK_build/totk/extracted/firmware/shared-fonts>" -o "/Applications/Breath of the Wild.app"

# 1.9.0 (or 1.6.0) from NSPs: base + update, each DLC pack optional
python3.14 build_app.py "<botw base.nsp>" -k "<prod.keys>" --update "<1.9.0 update.nsp>" --dlc "<dlc 1.nsp>" --dlc "<dlc 2.nsp>" --firmware "<firmware folder>" -o "/Applications/Breath of the Wild.app"
```

With a separate update the app holds only the DLC packs you give with `--dlc`. A card image brings its own DLC: leave out `--dlc` then.

## iPhone and iPad

**Needed:**
- iOS / iPadOS 26 and an iPhone 14 or newer.
- On the Mac: the full **Xcode 26** or later with the iOS platform, plus `brew install xcodegen cmake ninja`.
- Your Apple ID in Xcode › Settings › Accounts. A free one works.
- Developer Mode on the device.

**1. Build an IPA.** Use the Mac command above, add `--platform ios --ios-game-data documents`, and give `-o` an `.ipa` file:

```sh
python3.14 build_app.py "<base 1.0.0.xci>" -k "<prod.keys>" --update "<1.4.3 update.nsp>" --platform ios --ios-game-data documents -o "<folder>/Tears of the Kingdom.ipa"
```

The first iOS build also downloads and compiles device libraries. `--ios-game-data documents` leaves the 17 GB game image out of the IPA, so later installs take minutes.

Keep the iPhone or iPad connected by cable while building: the build then compiles the game's pipelines for its GPU on the Mac (about 10 more minutes the first time), and its first start needs no long fill before the title. For a device that is not connected, add `--device-gpu <arch>` (`applegpu_g14p` for an iPhone 14).

**2. Install it** with the device connected by cable:

```sh
python3.14 games/totk/ios/tools/install_device.py "<folder>/Tears of the Kingdom.ipa" --device "<device name as in Finder>" --game-data "<work folder>/totk/extracted/<version>/romfs/romfs.bin"
```

- `<version>` is the folder that is there (`v143` for 1.4.3; `ls "<work folder>/totk/extracted"`). The first install copies the 17 GB image once.
- The script stops when the iPhone or iPad is connected over Wi-Fi only: plug in the cable, unlock the device and run it again. `--wifi` installs over Wi-Fi anyway; it is slow, and the game data copy can drop.
- A free Apple ID signs for 7 days, a paid one for a year. Run the same command again to renew; your saves are kept.
- If the device asks, trust the developer in Settings › General › VPN & Device Management.

**3. First start:** about 15 s to check the game data, then about 3 minutes of shader import before the title (iPhone 14). Later starts take about 8 s.

On the phone the game renders at 960×540, upscaled to 1280×720, at up to 60 fps. Breath of the Wild 1.6.0 builds and installs the same way.

Two limits:
- A phone cannot translate shaders while you play: objects whose shader variant the app does not carry are skipped, so a few things can be missing in places no player has reported yet.
- On an iPhone 14, iOS can close the game when memory runs out in busy areas.

### Large textures

The GPU draws a game texture from a copy the app makes of it for Metal. To save memory, on iPhone and iPad the copy of a large mipmapped texture (one stored at several sizes, called levels, each half as wide and high as the one before) leaves out the top level, the largest one, so such a texture can look one level softer close up. On a device with enough memory the default keeps every level instead (Auto, below). The textures that keep every level, the Large textures setting with its Auto value and the rule for copies the GPU wrote (below) have not been tried on a device yet (2026-10-30). The iPad Pro M4 run cited below used an app built before the setting and the rules that keep levels, one that left out more top levels than Save memory does now.

- A large texture is a 2D, array or cube texture with mipmaps whose sides are both at least 512 pixels. `TOTK_MIP_DROP_MIN` changes the 512.
- A copy one level smaller returns wrong data wherever the game or a shader names a level or a texel (one pixel of a texture) by number. So these textures keep every level:
  - textures the game renders into, copies or clears;
  - textures a shader reads by texel position, gathers from, or asks the size or level count of;
  - textures bound as images (that shaders can write);
  - textures a vertex or compute shader samples;
  - textures bound through a sampler without mipmapping, or through a sampler whose LOD range (level of detail: the levels it may read) ends below 1 or starts at 1 or higher;
  - textures bound through a view of their first levels only.
- In the system Settings app › Apps › Tears of the Kingdom › Large textures, choose one of four; the choice takes effect at the next launch. Auto is the default: Full when the app's memory allowance at launch (`os_proc_available_memory`) is at least 6,500 MiB, Save memory otherwise. The figure comes from an iPad Pro M4 run with the top levels left out (2026-10-30): a peak footprint of 4,980 MiB, up to about 1,263 MiB more with every level kept (three times the peak of the texture copies, 421 MiB), and the 250 MiB the eviction wants free, which comes to 6,493 MiB. In Breath of the Wild, Auto is always Save memory, since that figure was measured on Tears of the Kingdom only. With the debug log on, the log says what Auto chose ("large textures auto: …"). A choice made in Settings stays as it is. Save memory is what the paragraph above describes. Keep more levels also keeps the textures a fragment shader samples at an explicit level or asks the LOD of (`TOTK_MIP_KEEP=2`). Full keeps every level of every texture and uses the most memory (`TOTK_MIP_DROP=0`).
- A variable in the launch environment wins over the setting. From a Mac, `devicectl` sets such variables with `--environment-variables`. `TOTK_MIP_KEEP` and `TOTK_MIP_KEEP_BINDS` act only while top levels are left out, so they need Save memory or Keep more levels, or `TOTK_MIP_DROP=1` in the launch environment: with Full, which Auto picks on a device with enough memory, every texture keeps every level and they change nothing. With `TOTK_MIP_KEEP=0` these rules are off, as before 2026-10-26: the textures listed above lose their top level too. A texture the game renders into is the exception: at its next use it gets a full-size copy, without what the first pass drew into it. `TOTK_MIP_KEEP_BINDS=0` turns off only the rule for the last two kinds, the textures bound through such a sampler or view; the other kinds still keep every level.
- On iPhone and iPad, copies the GPU has written into (with a copy command, a clear or an image store) are not marked purgeable (memory the system may take back when it runs short) or evicted (dropped when the app runs low on memory). `TOTK_TEX_KEEP_GPU_WRITTEN=0` brings back the old behaviour; `TOTK_MIP_KEEP=0` does not.
- With the debug log on, the log says which modes are in use ("大贴图副本少传最高一级 mip：…", "大贴图副本保留最高一级：…"). With `TOTK_MIP_KEEP_BINDS=0` it also says that the binding rule is off ("大贴图副本保留最高一级：按采样器 / 视图绑定保留的规则关…"). The line "大贴图副本保留最高一级：累计标记 …" counts the textures marked to keep every level, each once, under the reason that marked it first: render target, GPU copy or clear (the first kind in the list above); sampler or view binding (the last two kinds); or shader slot (how the shader itself uses the texture: the second to fourth kinds, and the textures Keep more levels adds). Every 600 submissions (each a batch of GPU commands the game hands over), the line "贴图副本可清除：…" also counts the large copies kept whole (render targets not included) and the memory they take, for all the reasons together.
- The false Gloom with stair-stepped edges around Link in the Depths (#337) is suspected to come from copies one level smaller; this is not confirmed. To compare, play at the place #337 names once each with Save memory, Keep more levels and Full. Full leaves no texture smaller, so a false Gloom that stays with Full has another cause. With a Mac, a run with `TOTK_MIP_KEEP_BINDS=0` (only the binding rule off) and one with `TOTK_MIP_KEEP=0` (every rule of the list above off), both with Large textures set to Save memory, can be compared with the Save memory run in the same way.

### Without the card image and keys: from an earlier IPA, on Windows

If you no longer have the card image, the update or `prod.keys` but still have a 1.4.3 IPA that `build_ipa.py` made at commit 30a1b93 with the RomFS inside the app (signed or not), a Windows PC can make a new app from it. The tools below recover the game's files from that IPA and make the startup shaders (the shader seed the app imports at its first start). They take the runtime (the app without the game's code and data) that GitHub Actions builds from this repository alone, put everything together, sign the app and install it. The scripts need Python 3.14 and, apart from `push_device_windows.py`, only its standard library. `push_device_windows.py` also uses pymobiledevice3: when the Python running it lacks that package, it starts itself again in pymobiledevice3's own Python. Run the scripts from the repository folder with `python` (`python -I` works too). The other programs they call are listed below. As of 2026-10-26, steps 1, 3 and 5 have been run on Windows, and step 4 on GitHub Actions; step 2 was run on Windows on 2026-10-30. Step 5 has not been run with the sections of step 2 yet: that needs a runtime built since then (step 4). Step 6 has been rehearsed with `--simulate` (a local folder standing for the device). None of them has been run against a device yet.

The device cannot write code, so an app for iPhone and iPad carries main's code with the game patches already written in, and at start the runtime only checks them (`games/totk/runtime/game_patches_v143.c`). Since upstream `f1d0077` (merged here on 2026-10-30) the build writes two more patches this way, and the code sections of an app built at 30a1b93 lack both:

- The 1.4.3 fix for fade counters above 60 fps (`patch_fade_increment`): four jumps and 80 bytes of added code after the end of the code.
- The render resolution patch (`patch_render_res`): the four instructions between main+0x585e48 and main+0x585e60. Without it the scene stays at the game's handheld 1280×720, not the 960×540 above, and the Scene resolution setting (Settings app › Apps › Tears of the Kingdom) has no effect.

So this route does not reuse the old app's sections: step 2 makes them again from the recovered modules with this repository's patches, and the runtime takes only those. Neither patch has been seen on a device yet.

You need:

- Python 3.14, and Visual Studio with "C++ Clang tools for Windows": step 2 builds the patch code with its clang. For the shaders also "Desktop development with C++" in Visual Studio, the .NET 10 SDK, Git for Windows (for its `patch`) and, the first time, an internet connection.
- A GitHub account with a fork of this repository.
- Your development certificate with its private key (`.p12`), a file holding its password, and a development provisioning profile (`.mobileprovision`) that names the app's bundle identifier and your device and grants `com.apple.developer.kernel.increased-memory-limit`. Before it signs, the tool checks the profile's platform, expiry date, bundle identifier and entitlements (`get-task-allow` and the increased memory limit). It also checks that the profile lists the certificate in the `.p12`. It does not check the device list. To keep the saves, use the bundle identifier and team of the app on the device.
- zsign (`--zsign`, `TOTK_ZSIGN` or `PATH`) and Git for Windows' `openssl` (the one under `mingw64` also reads a p12 exported by Keychain Access).
- pymobiledevice3, installed with uv or pipx (`uv tool install pymobiledevice3`), and iTunes or Apple Devices for the USB connection. The device is connected by cable and unlocked, with Developer Mode on, as for any development-signed app.

**1. Recover the game files** into a work folder outside the repository:

```powershell
python games/totk/ios/tools/recover_ipa.py <old TOTK.ipa> --out <work>/totk
```

Every file is checked before it goes into place: the three rewritten code modules against `expected-v1.4.3.json`, the nine code sections the app embeds (three of each game module: main, subsdk0 and sdk) against those of the app built at 30a1b93 (`APP_SECTIONS` in `games/totk/ios/tools/recover_modules.py`), the RomFS against its pinned size and SHA-256, the fonts as a build from the card image accepts them (the pinned SHA-256, or a valid font file in the Switch's BFTTF format), and the overlays against their `manifest.tsv` and the RomFS. The first failed check stops the run before `recover-manifest.json` is written, so an IPA of another build is refused. Extracting the 17 GB RomFS takes about 2 minutes on an SSD; a second run reuses it (about 10 seconds), and `--skip-romfs` leaves it for a later run. The IPA's own shaders are of an older translation chain and are not recovered.

**2. Export main's code with the game patches:**

```powershell
python games/totk/ios/tools/export_ios_windows.py --tree <work>/totk
```

It writes the nine code sections into `<work>/totk/build/export-ios`, where step 5 takes them from. On a Mac `build_ipa.py` has the loader's `export-ios` do this. This tool builds the patch code itself, `games/totk/runtime/game_patches_v143.c`, with Visual Studio's clang, found with `vswhere` (`--clang <clang.exe>` names another one; without either it takes `clang` from `PATH`). It checks the recovered modules against `expected-v1.4.3.json` and runs the patches on them with the two variables `build_ipa.py` sets for its export, `TOTK_EXPORT_IOS` and `TOTK_RENDER_RES=1280x720`. Unlike `build_ipa.py`, which passes the shell's environment on, it drops every other `TOTK_*` variable, so the sections are those a Mac build makes from a shell without `TOTK_*` variables. Then it runs the device's checks from the same file on the sections, and stops unless every patch is there. Beside the sections it writes `layout.json`, their sizes and SHA-256. `games/totk/ios/ci/embed-layout-v143.json` must be the same file; the tool says so when the two differ, because a runtime built from another layout refuses the sections. `--check <folder>` only runs the device's checks on the sections in a folder and names the patches they lack. On the PC this was run on (2026-10-30), the export took a few seconds. Its main code differed from the old app's in 32 words: the 4 instructions of the render resolution patch, the 8 jump and no-op words of the fade fix and its 20 words of added code. The other eight sections were byte for byte the old app's.

**3. Make the shader seed:**

```powershell
python games/totk/ios/tools/seed_windows.py tools --work <seed work>
python games/totk/ios/tools/seed_windows.py seed --work <seed work> --romfs <work>/totk/extracted/v143/romfs --modules <work>/totk/rewritten/v143 --version v143
```

`tools` builds SPIRV-Cross at the commit `build_app.py` pins (its source checked against the tree GitHub names for that commit) and the shader translator for win-x64, into `<seed work>/tools/bin`. `seed` writes `<seed work>/seed`: for 1.4.3 about 31,000 variants, 11 minutes the first time; later runs reuse the translations. `--extra-list <shader-list-contribution.txt>` (repeatable) adds the `V` rows of a file your device wrote to this seed only. A row that a variant already serves adds no variant, and the run prints how many rows the seed serves, how many variants the rows added, and why any other row is not served.

**4. Build the runtime on GitHub Actions.** The workflow `.github/workflows/ios-runtime.yml` builds the app's executable on a `macos-26` runner from the repository alone (`build_ipa.py --runtime-only --embed-layout games/totk/ios/ci/embed-layout-v143.json`), with the game's nine code sections zero-filled. The executable carries the layout's section hashes, so a runtime from a run before the layout changed on 2026-10-30 refuses the sections of step 2, and step 5 stops with "another embed layout" (as `--check-only` did with the runtime of 2026-10-26). On your fork, enable Actions on its Actions tab. A push to the branch `ios-windows-fixes` that changes `games/totk/**` or the workflow file starts the workflow. Once the workflow file is on the fork's default branch, "Run workflow" also starts it. Download the run's artifact `totk-ios-runtime` (kept 14 days) and unzip it once: it holds `TOTK-runtime.zip`. That zip holds `TOTK.app` and `TOTK-runtime.commit`, which names the commit the run built; the next step reads the commit from there. Nothing of the game goes to GitHub this way, and nothing may: never commit or upload the work folders, the seed, an IPA or Metal libraries made from them.

**5. Package and sign:**

```powershell
python games/totk/ios/tools/package_ipa_windows.py <dir>/TOTK-runtime.zip --tree <work>/totk --seed <seed work>/seed --out <dir>/TOTK.ipa --p12 <certificate.p12> --p12-password-file <password file> --profile <profile.mobileprovision> --zsign <zsign.exe>
```

It writes the nine code sections of step 2 into the runtime (`--sections <folder>` takes them from another folder). Each section is checked against the layout's size and SHA-256 and against the executable's own table of section hashes. With `--check-only` the tool stops after these checks: it writes nothing and needs neither the certificate nor zsign, so run it first on a newly downloaded `TOTK-runtime.zip`. The tool then adds the game data. It takes the bundle identifier from the profile, and the display name and icon from the old app. It keeps the old app's version and build number (1.4.3 and 2610.22.1 for the app this was tried with). Then it signs with zsign and checks the signature. Beside `TOTK.ipa` it writes `TOTK-unsigned.ipa` (ad-hoc signed, for other signing tools), `TOTK-shader-seed` (the seed in the form the device takes) and `TOTK-package.json`. The 17 GB image and the seed stay out of the IPA (`--game-data documents`, the default). zsign 1.1.2 on Windows seals a file of 4 GiB or more with a wrong hash, so an app signed on Windows cannot carry the image. `--game-data app` puts the image and the seed into the app. It needs `--unsigned-only`; without it the tool stops. With both, the tool writes only an unsigned IPA, for signing on a Mac.

The tool reads the commit the runtime was built from out of `TOTK-runtime.commit` and prints it in step 3/6 ("source commit: …"). It writes that commit into `TOTK-package.json`, and into `Info.plist` as `TOTKSourceCommit` when the old app has that key. `--source-commit <commit>` names the commit by hand and wins over the file. A `TOTK-runtime.zip` from before the workflow wrote that file names no commit: the tool then records this checkout's HEAD and prints a warning, so for such a runtime give `--source-commit` with the commit its run built. On the Windows PC this was measured on (2026-10-26), the first packaging with a seed took about 8 minutes and wrote the device's seed folder (91,304 files, nearly all of them hard links into the seed). A second packaging with the same seed took under a minute.

**6. Install and copy the game data:**

```powershell
python games/totk/ios/tools/push_device_windows.py deploy <dir>/TOTK.ipa --romfs <work>/totk/extracted/v143/romfs/romfs.bin --backup-to <backup folder>
```

`deploy` first backs up the saves of the installed app (`--backup-to`, or `--no-backup`) and installs over it. It then copies the image into the app's `Documents/GameData` as `romfs.bin.000`, `.001`, … of 1 GiB each (once: later installs keep it, and a copy that stopped goes on from the parts already there). Last, it copies the seed beside the IPA as one pack when the device does not have it yet. `install`, `romfs`, `seed` and `backup-save` each do one step of `deploy`. `restore-save` puts a backup back, and `status` shows what the device has (the app's version, the image parts, the seed and the saves). With more than one device attached, every command stops and lists them with their UDIDs: name one with `--udid` (`TOTK_PUSH_FIRST_DEVICE=1` leaves the pick to pymobiledevice3 instead, which takes the first device on USB, otherwise the last one listed); each command prints the device it uses before it writes. `--simulate <folder>` rehearses without a device, and `check` checks pymobiledevice3 without one. If the game says there is no game data or no shaders (its message names the Mac's `install_device.py`), run `deploy` again with `--romfs`.

An app built on a Mac with the device on the cable brings pipelines the Mac compiled for the device's GPU, and its first start takes them from there instead of filling the pipeline archive (`--device-gpu`, above). An app packaged on Windows brings none. **The first start** unpacks the shaders ("Preparing the shaders (once after an update)") and checks the game data. Until the unpacking is done, the pack and the folder it fills are both on the device, about 1.2 GB each. A seed made on Windows has no Metal libraries (adding them is described below). So before the title the device compiles these libraries from their MSL (the Metal Shading Language source): those of every pipeline in the seed's pipeline lists (`pso_title.tsv`, `pso_list.tsv` and `pso_manifest.tsv`, which name the pipelines to build before play). The screen first shows "Warming shaders and pipelines N%" while the title screen's list is built. Then it shows "Checking the pipeline archive", then "First start: compiling shaders N% (later starts are quicker)", and under it the pipelines built so far out of those to build. After a minute, once 2% of the pipelines are built, the line becomes "First start: compiling shaders N%, about M min left". At a later start the pipeline archive can still be valid but lack some pipelines of the shared list (`pso_list.tsv`), for example after a first start that stopped before the title, rows new in the list, or pipelines whose build failed and so were never written into the archive. The screen then shows "Compiling shaders the pipeline archive lacks N%", with ", about M min left" added after a minute and 2%. Pipelines the other lists lack are built while "Warming shaders and pipelines N%" shows. Keep the game open in front until the title appears. This sequence follows the code; it has not been seen on a device yet (2026-10-26).

For 1.4.3 that is 27,457 pipelines from 20,005 libraries (the lists and the Windows-made seed as of 2026-10-30). They are compiled on half the cores, 2–4 threads: 4 on an iPad with an M4, 3 on an iPhone with six cores. While the device reports a `serious` or `critical` thermal state, the warm-up drops to 2 threads. `TOTK_WARM_THREADS=<n>` sets the number. A comment in the code gives 80–225 ms per library when the Metal cache does not hold it yet, measured on a Mac. At that rate one thread takes 27–75 minutes for all of them. On the Mac 8 threads compiled 4.6 times as fast as one. How much 2–4 threads gain on a device has not been measured.

The pipelines go into the pipeline archive (`Documents/shader-cache/rt-totk-native-v8-unverified/pipelines`), so later starts take them from there. The libraries do not: later starts rely on the system's Metal cache for them. The code notes that device restarts and system updates clear that cache. If the cache no longer has the libraries after the device restarts, the next start compiles some of them again before the title. These are the libraries of the pipelines every start builds: those in the title screen's list, in the seed's `pso_manifest.tsv` and among the pipelines this device has recorded in play. The other libraries are compiled when a draw first needs them. This has not been checked on iOS 26. A shader the lists do not name is also compiled when a draw first needs it, which stutters (on a Mac one library took up to 225 ms when the Metal cache did not hold it). After a system update, a minor one too, the archive is built again, so the first start after it compiles once more.

**Metal libraries** make the first start shorter and shorten those stutters. The device loads `<variant>_b.metallib` in place of the MSL without checking that it was compiled from it, so compile them from this seed's own `.metal` files (`<seed work>/seed`):

- On a Mac with Xcode and its Metal toolchain (Xcode Settings › Components, or `xcodebuild -downloadComponent MetalToolchain`): copy the seed folder there, run `python3 games/totk/ios/tools/compile_seed.py <copy> iphoneos` (about an hour on 8 threads for 1.4.3) and bring the `*_b.metallib` files back into a folder of their own.
- On Windows, Apple's Metal Developer Tools for Windows (downloaded from developer.apple.com with an Apple ID) may do the same, file by file: `metal.exe -fmetal-math-mode=safe -target air64-apple-ios26.0 -c <variant>_b.metal -o <variant>_b.air`, then `metallib.exe <variant>_b.air -o <variant>_b.metallib`; leave out a file that does not compile, and the device compiles that one itself. The translated shaders need exactly rounded float arithmetic, so a version whose `metal.exe --help` does not list `-fmetal-math-mode` is of no use. Whether a version for the iOS 26 target exists and works has not been checked here.

Then package again with `--metallibs <folder>` together with `--seed`, and run `deploy`. The libraries change the fingerprint of the device's seed folder (the SHA-256 in `TOTK-shader-seed/fingerprint.txt`), so `deploy` copies the seed to the device again. With libraries for at least half of the shaders, the warm-up treats the seed as precompiled and runs on one thread again, as with an app built on a Mac. A shader without its library is still compiled from its MSL, during the warm-up on that one thread. The pipeline archive notes in `pipelines/identity.json` what it is valid for: the system version, the GPU, the translation chain and whether fewer than half of the shaders came with libraries. So the first start after a change between a seed with libraries and one without removes the archive by itself and builds the pipelines again before the title. With the debug log on, the log then says "管线存档：系统版本、GPU、翻译链或着色器库的来源（预编译 / 本机从 MSL 编）变了，删掉重建". This has not been tried on a device yet (2026-10-26).

### Updating the app and keeping the saves

The saves are in the app's `Documents/save`: `account.uid` (16 bytes, the local account, made at the first start) and `save/<32 hexadecimal digits>`, the folder named after that account. The game finds its saves only with the `account.uid` they were made with, so the two always move together.

- **Same bundle identifier and team** (the profile of the installed app): installing over the app keeps its Documents (the saves, and the image and shaders in `Documents/GameData`) and its choices in Settings, as renewing with `install_device.py` does. Do not delete the app before installing the new one: that deletes its Documents, saves included. Back up the saves first anyway, in one of three ways:
  - `deploy --backup-to <folder>` backs up the saves before it installs.
  - `push_device_windows.py backup-save --to <folder> --bundle-id <id>` backs them up on its own. Both commands write the backup into `<folder>/<bundle id>-save-<date>-<time>`: a copy of the `save` folder, with `backup-manifest.json` beside it.
  - In the Files app, copy the `save` folder (On My iPad › Tears of the Kingdom, or On My iPhone on a phone) to iCloud Drive or a USB drive. Make this copy even when you use one of the two commands above: `push_device_windows.py` has only been rehearsed with `--simulate` so far (2026-10-26).
- **Another bundle identifier** (a profile of another team, for example): to iOS this is another app with an empty Documents, and the old app keeps its data. Choices in Settings stay with the old app; set them again. With the Files app, open the new app once, close it, and replace its `save` folder with the old app's, `account.uid` included. With the tools:
  1. Back up the old app: `push_device_windows.py backup-save --to <folder> --bundle-id <old id>`.
  2. Install the new app and copy the game data to it: `push_device_windows.py deploy <dir>/TOTK.ipa --romfs <work>/totk/extracted/v143/romfs/romfs.bin --no-backup`. The new app has no saves yet. Once it is installed, `deploy` asks for `--backup-to` or `--no-backup`, so with `--no-backup` the same command can run again if the copy stops.
  3. Quit the new app if it is running.
  4. Run `push_device_windows.py restore-save <folder>/<old id>-save-<date>-<time> --bundle-id <new id> --other-app`, naming the dated folder the backup made. It first backs up what the new app has (beside the backup, or into `--safety-to <folder>`), then writes the backup's files, `account.uid` included.
- **Old shader caches:** at every start the app removes, in the background, the folders of other translation chains in `Documents/shader-cache` (an app built at 30a1b93 used the chain `totk-native-v6-unverified`) and the earlier pushed shader folders in `Documents/GameData`; with the debug log on it writes `[shader-cache] removed N entries of earlier translation chains`.
- An app built with the RomFS inside, as at 30a1b93, takes the image away when it is replaced; the new app reads it from `Documents/GameData`, which is why the first `deploy` needs `--romfs`.

### Controller button icons, on Windows

The game's prompts show the Switch's buttons. A controller other than Nintendo's is mapped by position: its right button plays Switch A, the bottom one B, the top one X and the left one Y. So on an Xbox controller the letter in a prompt is not the letter printed on the button to press. A RomFS mod can draw the controller's buttons in the prompts instead. It changes the pictures only: which button does what stays as it is.

The app reads such a mod from its `Documents/mods/v143` (`ios/Sources/main.m`; `v143` is the folder of 1.4.3). An app whose runtime was built from a commit without this (one where `push_device_windows.py` has no `push-mod` command) ignores the folder: build the runtime again and package it, steps 4 and 5 of [Without the card image and keys](#without-the-card-image-and-keys-from-an-earlier-ipa-on-windows). With the debug log on, an app that reads the folder writes `[totk] player mods: <folder> (…)` at start, or `[totk] player mods: none (…)`, with the reason in the brackets.

**1. A Python with fontTools,** once. `uv` installs it from its cache without a download when the cache has fontTools (`--offline`; leave that out to download it):

```powershell
uv venv --python 3.14 <work>/tools/icons-venv
uv pip install --offline --python <work>/tools/icons-venv/Scripts/python.exe fonttools
```

**2. Make the mod** from the RomFS that `recover_ipa.py` recovered (`<work>/totk/extracted/v143/romfs`, step 1 of [Without the card image and keys](#without-the-card-image-and-keys-from-an-earlier-ipa-on-windows)), into a folder outside the repository:

```powershell
<work>/tools/icons-venv/Scripts/python.exe games/totk/scripts/make_button_icons.py <work>/mods/v143-xbox --romfs <work>/totk/extracted/v143/romfs --style xbox
```

- `--style xbox` draws B A Y X in the Switch A, B, X and Y icons: the letters printed on the buttons that play them by position. It also draws LB/RB, LT/RT, Menu and View, the d-pad and LS, in the prompts and in the button guide of the HUD, in every game language.
- `--faces` names other buttons for the Switch A, B, X and Y icons, in that order, by the letters an Xbox controller prints on them. Use it when something before the game swaps buttons: the controller's own profile (an Elite controller's, for example) or a customization in iPadOS Settings › General › Game Controller. To find the letters, press each button at a prompt and note which prompt it answers: `--faces` lists the printed letters of the buttons that answer A, B, X and Y. For example, when the button printed B answers A, the one printed A answers B, and X and Y answer the prompts of their own letters, use `--style xbox --faces BAXY`. Without `--faces` the style's own order is drawn (BAYX for `xbox`). The PlayStation styles take `--faces` too and draw the symbol of the same button (A Cross, B Circle, X Square, Y Triangle).
- `--romfs` names the folder of `romfs.bin`, or `romfs.bin` itself. The build's own overlay, `extracted/v143/romfs-patches` beside it, also replaces the HUD's layout archive: the script merges the mod's archive with that overlay's edit, as the app carries the same files in `GameData/romfs-patches`. Without that merge the game stops at start, because two overlays would replace one file.
- The script writes `manifest.tsv` (each file's size and SHA-256 and the original's SHA-256, which the game checks at start). Beside the layout archive it keeps `<archive>.mod-original`, the mod's archive before the merge; the device does not need it. With `--replace` it writes over the files of an earlier run, which is how to change the style or the order.
- Prompts drawn as fixed images (some tutorial animations) keep the Switch icons.
- The folder holds files made from the game's own (fonts and layouts): keep it on your PC, and never commit or upload it.

On the PC this was tried on (2026-10-30), `--style xbox --faces BAXY` took 33 s and wrote six files, 44 MiB. The runtime's overlay code (`games/totk/runtime/romfs.c`), compiled on Windows with Visual Studio's clang, accepted the mod on top of the build's overlay with the recovered RomFS. It has not been tried on a device yet.

**3. Copy it to the device:**

```powershell
python games/totk/ios/tools/push_device_windows.py push-mod <work>/mods/v143-xbox --bundle-id <id>
```

`push-mod` first checks each file `manifest.tsv` lists, by size and SHA-256, as the game does at start. It then copies those files into `Documents/mods/v143`, `manifest.tsv` last, so the game never loads a half-copied mod. A copy that stopped goes on from the files already there. `deploy … --mod <folder>` does the same after the install. `status` lists the folders in `Documents/mods`. The game loads the mod at its next start, unless the chosen row's slot folder from [Durability and battery presets](#durability-and-battery-presets-on-windows) is on the device: the app then loads that folder, so a new icon mod goes through `make_gameplay_tuning.py --slots` and `push-slots`. `--version` names another version's folder (`v143` by default).

**To remove it:** `push_device_windows.py remove-mod --bundle-id <id>` removes `Documents/mods/v143`, `manifest.tsv` first; the next start plays with the Switch icons. Slot folders on the device hold the icons too, so remove those as well. In the Files app, deleting the `mods` folder (On My iPad › Tears of the Kingdom) removes them all.

`push-mod` and `remove-mod` have been rehearsed with `--simulate` only (2026-10-30).

### Durability and battery presets, on Windows

A RomFS mod made from your own game files can make weapons, shields and bows last longer and the Zonai battery drain slower and recharge faster. You make four folders on the PC, copy them to the device and choose one in the Settings app; the game loads it at its next start. [mods.md](mods.md#gameplay-tuning) says which values change.

| Settings › Apps › Tears of the Kingdom › Mods › Durability and battery | Folder in `Documents/mods` | Maximum durability | Battery drain | Recharge |
| --- | --- | --- | --- | --- |
| Off | `v143-off` | unchanged | unchanged | unchanged |
| Moderate | `v143-moderate` | ×3 | ÷2 | ×2 |
| Strong (the row's default) | `v143-strong` | ×5 | ÷3 | ×3 |
| Max | `v143-max` | ×10 | ÷5 | ×5 |

The game loads one mod folder, so every folder also holds the button icon files, and Off is the icons alone. This is a gameplay change. It reaches the game only through these folders, which you make from your own game files: upstream's app has no such row, and in this fork the row's default is Strong, so with the folders on the device the game plays Strong until the row says otherwise. Without a folder for the chosen row the app uses `Documents/mods/v143`, and without that one it loads no mod.

The row and the choice of folder are in the app itself. An app whose runtime was built from a commit without them (one where `push_device_windows.py` has no `push-slots` command) has no row and ignores these folders: build the runtime again and package it, steps 4 and 5 of [Without the card image and keys](#without-the-card-image-and-keys-from-an-earlier-ipa-on-windows).

**1. Make the button icon mod:** steps 1 and 2 of [Controller button icons, on Windows](#controller-button-icons-on-windows).

**2. Make the four folders** from the RomFS that `recover_ipa.py` recovered, with the icon mod as the base:

```powershell
python games/totk/scripts/make_gameplay_tuning.py --romfs <work>/totk/extracted/v143/romfs --slots <work>/mods --base <work>/mods/v143-xbox
```

It writes `v143-off`, `v143-moderate`, `v143-strong` and `v143-max` into `<work>/mods`. Each one is a copy of the base folder with its slot's values and its own `manifest.tsv`. Run it again after a new icon mod: each folder is built beside the old one and then takes its place. A folder of that name the script did not make stops the run. The values come from the table `SLOTS` in the script. The folders hold files made from the game's own: keep them on your PC, and never commit or upload them.

**3. Copy them to the device:**

```powershell
python games/totk/ios/tools/push_device_windows.py push-slots <work>/mods --bundle-id <id>
```

`push-slots` checks every folder as `push-mod` does, then copies them one after the other (46 MiB each, 44 MiB for `v143-off`). A copy that stopped goes on where it stopped. To put your own mod in a slot, `push-mod <folder> --slot strong` copies one folder into `Documents/mods/v143-strong`; `deploy … --mod <folder> --slot strong` does the same after the install.

**4. Choose a slot** in Settings › Apps › Tears of the Kingdom › Mods › Durability and battery, and restart the game. With the debug log on, the log says which folder it loaded and why: `[totk] player mods: <folder> (mod slot strong)`.

**To remove them:** `push_device_windows.py remove-mod --bundle-id <id> --slot strong` removes `Documents/mods/v143-strong`, and the other slots likewise. In the Files app, deleting the `mods` folder removes them all.

What they do not change:

- A higher maximum durability reaches only items obtained after the mod is in, because a save keeps each item's durability. Items picked up with a slot in use are expected to keep their durability after the slot changes, so back up the saves first (`backup-save`).
- The number of battery cells is saved and stays. Only the drain and the recharge rate change.
- The pause before the battery recharges is a constant in the game's code and stays.
- Items you already own wear as before. A melee hit costs a fixed 1 in the game's code that no data file scales. The data only holds an on/off switch per kind of target, and no slot touches it. [mods.md](mods.md#gameplay-tuning) has the details.

On the PC this was tried on (2026-10-30), `--slots` took 53 s. `v143-off` holds the 6 icon files, and the other folders 214 files, 45.8 MiB. A comparison with the RomFS found only the intended values changed, 418 fields of 4 bytes in 208 files, with the SARC member tables, the unpacked sizes and the zstd dictionaries as they were. The runtime's overlay code, compiled on Windows with Visual Studio's clang, accepted each folder on top of the build's overlay. `push-slots` has been rehearsed with `--simulate` only, and the change to `main.m` has only been syntax-checked. None of this has run on a device yet, so no effect has been seen in the game.

## Apple Vision Pro

Tears of the Kingdom only, windowed 16:9 play with a controller. Install the visionOS platform in Xcode › Settings › Components, pair the headset with Xcode and turn on Developer Mode, then:

```sh
python3.14 build_app.py "<base 1.0.0.xci>" -k "<prod.keys>" --platform visionos --ios-game-data documents -o "<folder>/TOTK-Vision.app"
python3.14 games/totk/ios/tools/install_device.py "<folder>/TOTK-Vision.app" --device "<Vision Pro name>" --game-data "<work folder>/totk/extracted/v0/romfs/romfs.bin"
```

With `--update`, use that version's folder (`v112`, `v121` or `v143`) instead of `v0`.

## Update the app

- **New version of this repository** (after `git pull`): `python3.14 update_runtime.py "<the app>"` updates it in about a minute, without the game files or keys. Quit the game first. If it says the startup shaders no longer fit, add `--seed`.
- **Another game version:** run `build_app.py` again with the new `--update` and the same `-o`. It replaces the app. Before the first start on the new version, the app backs up your saves next to them as `profile-before-<version>`; keep that backup if you may go back.
- **Mods:** `--mod "<mod folder>" --install-mod-romfs` builds the app with a mod's code patches and installs its data. See [mods.md](mods.md), [merged-mod-pack.md](merged-mod-pack.md) and [translation-mods.md](translation-mods.md).
- **One desktop entry** (optional): `python3.14 games/totk/tools/install_desktop_entry.py --app "<the app>"`.

## When the build stops

Read the `ERROR:` line and the log file it names (`<work folder>/logs/…`), fix the cause, and run the same command again.

| The error says | Fix |
|---|---|
| `needs macOS 26 or later` | Not supported here; see the macOS 15 fork under [What you need](#what-you-need). |
| `clang++ finds no C++ standard library headers` | With Xcode: `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`. Without: `sudo rm -rf /Library/Developer/CommandLineTools && xcode-select --install`. |
| `Homebrew packages missing`, `Python 3.14 not found`, `git not found` | Install what it names. |
| `NSP files do not include system shared fonts`, `needs --firmware or --shared-fonts` | Add `--firmware` or `--shared-fonts`. |
| `SHA-256 … is not the expected …`, `ExeFS … is missing; not the supported version` | `git pull` first. Then check that the base is 1.0.0 and the update a supported version; otherwise dump the game again. |
| `unsupported update module hashes` | That update version is not supported. |
| `the base game must be an uncompressed XCI or NSP` | Decompress the NSZ / XCZ base (`nsz -D`). |
| `… add-on content (DLC), not the game`, `pass it as …`, `use the files of one game` | A file is on the wrong option; the message names the right one. |
| `the game file holds [...]: expected Tears of the Kingdom … or Breath of the Wild` | Another game: build it with its own `games/<name>/README.md`. |
| `needs about N GB free` | Free space, or `--work` and `-o` on an APFS volume with room. |
| `BKTR verification failed`, an error merging the update | `git pull` first. If it stays, your keys may be older than the update: dump `prod.keys` again on current firmware. |
| `make failed`, `xcrun failed` | Read the named log; usually incomplete developer tools or Homebrew outside `/opt/homebrew`. |
| iOS signing or install errors | Apple ID in Xcode › Settings › Accounts, device unlocked and trusted, Developer Mode on; run the install again. |

Still stuck? Open an [issue](https://github.com/ly05010419/MacNativeGames/issues) with the command (paths shortened), Mac model, macOS version, `git log -1 --oneline`, the `ERROR:` line and the end of the log it names. Never attach keys, game files, firmware or the app.

## Where things are

Tears of the Kingdom; for Breath of the Wild replace `TOTK` with `BotW` and `totk` with `botw`.

- Saves: `~/Library/Application Support/MacNativeGames/TOTK/profile`
- Game data (only for an app built with `--mac-game-data library` or `--mac-game-data-folder`): `~/Library/Application Support/MacNativeGames/TOTK/GameData/<version>` (`BotW` for Breath of the Wild) holds the 16 GB RomFS image `romfs.bin`, and `romfs.sha256`, which the build writes once the copy is complete. By default the image is inside the app. With `--mac-game-data library` the build puts it in this folder once (an APFS clone when the work folder is on the same volume, otherwise a copy), and later builds leave it alone while it matches the version's pin. The app is then a few hundred MB, so a new build installs or copies to another Mac quickly. To keep it somewhere else, for example on another disk, add `--mac-game-data-folder <folder>` to the build instead (that alone is enough; the image goes in `<folder>/<version>`, so one folder can hold both games). The app remembers the folder, and when it holds no complete image (another Mac, or the disk is not connected) the launcher looks in `GameData` instead. When neither has it, the app asks where the game data is: connect the disk and choose Try Again, or choose the folder that holds `romfs.bin` (or its `<version>` folder). It reads the image where it is, without moving or copying it, and remembers the folder for the next starts (`defaults delete org.macnativegames.botw MNGGameDataFolder.botw190` forgets it). The game still checks the image against the pin at its first start. `make_mod_manifest.py --app` and `make_button_icons.py --app` find the image the same way (`--romfs-data <folder>` names it).
- Shader cache: `~/Library/Application Support/MacNativeGames/TOTK/shader-cache`
- Shaders the shared list lacks: `~/Library/Application Support/MacNativeGames/TOTK/shader-list-contribution.txt` (the game asks before it starts whether to send them; see the [shared shader list](shader-list.md))
- Mods: `~/Library/Application Support/MacNativeGames/TOTK/mods/<v0|v112|v121|v143>`; see [mods.md](mods.md). On an iPhone or iPad: the app's `Documents/mods/<version>` (`v143` for 1.4.3), or `<version>-<slot>` beside it; see [Controller button icons, on Windows](#controller-button-icons-on-windows) and [Durability and battery presets, on Windows](#durability-and-battery-presets-on-windows)
- Log: off by default. `defaults write org.macnativegames.totk TOTK_DEBUG_LOG -bool YES` turns it on from the next start, written to `~/Library/Logs/MacNativeGames/totk.log`. On an iPhone: Settings › TOTK › Debug log, written to the app's `Documents/log.txt`.

## Known issues

**Requests beyond this page are welcome.** The versions and games listed are the ones we could test. If you need another version or another game, the AI assistant should do its best to make it work.

- Tears of the Kingdom: base 1.0.0, optionally with the 1.1.2, 1.2.1 or 1.4.3 update. Breath of the Wild: 1.6.0 and 1.9.0. Other versions, compressed base games and personalized tickets are not supported.
- No online features, no amiibo.
- New shaders can stutter the first time; the cache and the [shared shader list](shader-list.md) reduce it.
