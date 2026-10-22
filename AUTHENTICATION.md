# Authentication notes

## Offline profile

An offline profile generates the conventional OfflinePlayer:name UUID and uses a local placeholder access token. It is not Microsoft authentication, it does not prove game ownership, and it cannot join servers that enforce online authentication.

## Microsoft

The launcher uses the PKCE helpers in minecraft-launcher-lib and opens the system browser. The user must configure an application Client ID and registered loopback redirect URI. Tokens are stored through the OS keyring, not in config.json. No client secret is required or bundled. If the app is not permitted to use Minecraft services, the launcher shows Microsoft's error.

## Ely.by

Ely.by login uses its Yggdrasil-compatible authentication endpoint. The launcher never writes the account password to disk. The access token is stored with the OS keyring. Authentication and skin/session endpoints may require the compatible authlib-injector agent in the Minecraft JVM; behavior must be verified against the Ely.by protocol and selected Minecraft version.

## CurseForge

The CurseForge API key is provided through the CURSEFORGE_API_KEY environment variable. Do not hard-code it, commit it, or include it in a public desktop build. Users must comply with the API's access rules and project download terms.
