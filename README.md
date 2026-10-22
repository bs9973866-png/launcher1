# NOVAURA Launcher

A customizable Windows desktop launcher for Minecraft: Java Edition, built with Python, PySide6 and minecraft-launcher-lib.

## Current implementation

- Dark NOVAURA UI with violet/pink/cyan themes, rounded cards, animated page transitions, resizable pages and Russian/English UI labels.
- Separate named game instances and per-instance directories.
- Live Mojang version manifest, vanilla installation and launch, plus version-aware loader installation through minecraft-launcher-lib (Fabric, Forge, NeoForge and Quilt when supported).
- JVM executable path, memory allocation, custom JVM arguments, game root, opacity, UI scale, card radius, optional background image and saved settings.
- Offline nickname profiles, Microsoft OAuth with PKCE through the system browser, and Ely.by Yggdrasil login. Account tokens are stored via the OS keyring instead of the JSON settings file.
- Modrinth search and version-compatible downloads for mods, resource packs and shader packs; Modrinth .mrpack installation validates manifest hashes and installs client files/overrides.
- CurseForge search/download endpoints when a user supplies their own API key as CURSEFORGE_API_KEY.
- Resource folder shortcuts, imports and a shareable instance ZIP format that includes selected game folders and a JSON manifest.
- A one-click performance bundle that searches Modrinth for Sodium, Lithium, FerriteCore and EntityCulling for the active loader/version.
- Download progress for file downloads, clear error dialogs, app log and per-instance launch logs.

## Requirements

- Windows 10/11 x64 recommended.
- Python 3.11 or newer for running from source.
- An internet connection for version manifests, game files, Microsoft/Ely.by authentication and mod catalogs.
- Microsoft Minecraft Java Edition ownership for Microsoft-authenticated play on licensed/online-mode servers. Offline profiles do not grant a license and work only where offline-mode is allowed.
- Java: the launcher can use the Java runtime supplied by Minecraft's metadata; set an explicit javaw.exe/java.exe path in settings to override it.

## Run from source

~~~powershell
git clone https://github.com/bs9973866-png/launcher1.git
cd launcher1
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m novaura
~~~

Alternatively, install the package with pip install -e . and start it with python -m novaura.

## Download a Windows build

Every push to main and each manual workflow run triggers **Build NOVAURA for Windows** in GitHub Actions. Open the repository's Actions tab, select a successful run, and download the NOVAURA-Windows artifact. The archive contains the packaged application directory; extract it before running NOVAURA.exe.

To make a build locally:

~~~powershell
pip install -r requirements.txt
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --onedir --name NOVAURA --paths src --add-data "src/novaura/assets;novaura/assets" --collect-all minecraft_launcher_lib --collect-all keyring src/novaura/__main__.py
~~~

The output is placed in dist/NOVAURA/. Distribute the whole folder or archive it; do not send only the EXE.

## Microsoft login configuration

Microsoft sign-in requires a Microsoft Entra application configured for the supported public-client/loopback OAuth flow. In the app, set the **Application (client) ID** and a redirect URI registered for the application, normally http://localhost:8765/callback. Microsoft can require additional permission/eligibility approval before an application may call Minecraft services. Do not add client secrets to the repository. The client ID is an application identifier, not a secret.

## CurseForge

CurseForge requires an API key. Create it according to CurseForge's current developer terms, then set it only in the environment of the computer running NOVAURA:

~~~powershell
$env:CURSEFORGE_API_KEY = "your-key"
python -m novaura
~~~

Do not commit that value to source control. Availability of direct download links depends on the project and CurseForge response; the launcher reports when it cannot download a file.

## Known limitations

- The first release is an MVP, not a parity replacement for all features of the official Minecraft Launcher. Test new instances before moving important worlds.
- Modrinth is the primary integrated catalog. CurseForge availability depends on a user-provided key and the direct download URL returned by its API; CurseForge modpack manifest installation is not yet implemented.
- Microsoft sign-in depends on the user's Entra app configuration and Microsoft's current app eligibility rules.
- Ely.by uses its Yggdrasil-compatible login flow and downloads an integrity-checked authlib-injector agent for the game session; behavior can still vary by Minecraft version and loader.
- The skin panel renders a small isometric head preview only when the account API supplies an accessible skin texture; it is not a full-body, rotatable 3D model editor.
- Catalog download streams and authlib-injector downloads can be cancelled; minecraft-launcher-lib does not expose hard cancellation for every in-progress Mojang asset operation.
- Export includes selected instance data folders (mods, config, resourcepacks, shaderpacks and saves); it does not include Minecraft libraries/assets or automatically bundle every external dependency.

## Tests

~~~powershell
pytest
~~~

The GitHub Actions workflow runs the tests and builds a packaged Windows artifact. A successful workflow is the build verification; it does not replace testing actual Microsoft/Ely.by credentials on the end user's system.
