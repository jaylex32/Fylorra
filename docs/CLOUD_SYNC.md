# Cloud Sync (OneDrive + Google Drive)

This is the initial Cloud Sync MVP: connect, test, list root, and upload/download files.

## “One‑click Connect” (recommended for your shipped EXE)

End‑users should not deal with “Client IDs” or JSON files.

Fylorra supports publisher-owned OAuth app credentials via:

- Env vars (best for packaging):
  - `FYLORRA_ONEDRIVE_CLIENT_ID`
  - `FYLORRA_ONEDRIVE_TENANT` (optional; default `common`)
  - `FYLORRA_GDRIVE_CLIENT_SECRETS_PATH`
- Or a local file:
  - `~/.fylorra/oauth_apps.json`
    ```json
    {
      "onedrive_client_id": "YOUR_AZURE_APP_CLIENT_ID",
      "onedrive_tenant": "common",
      "gdrive_client_secrets_path": "C:/path/to/google_client_secrets.json"
    }
    ```

When these are present, the app hides “Advanced” and users can just click `Connect`.

## OneDrive (Microsoft)

Fylorra uses Microsoft Graph via device-code OAuth.

If you see errors like **AADSTS70002 / invalid_client** when starting device login:
- Azure Portal → App registrations → your app → **Authentication**
  - Advanced settings: enable **Allow public client flows**
- Ensure the app is intended for **mobile/desktop/public client** flows (not a confidential “Web” app)
- Ensure “Supported account types” matches what you want (Personal Microsoft accounts and/or your tenant)

1. Create an Azure App registration (Microsoft Entra ID).
2. Copy the **Application (client) ID**.
3. In Fylorra → `Settings` → `Cloud Sync`:
   - Set `Client ID` to the Application (client) ID
   - Leave `Tenant` as `common` (recommended)
4. Click `Connect` and follow the on-screen device-login instructions.

Required scopes:
- `User.Read`
- `Files.ReadWrite.All`
- `offline_access`

## Google Drive

Fylorra uses Google OAuth for installed apps.

If you see **“Access blocked … has not completed the Google verification process”**:
- In Google Cloud Console → **OAuth consent screen**
  - If status is **Testing**, add your email under **Test users**
  - Or change to **In production** (may require verification depending on scopes/audience)

1. Create OAuth credentials in Google Cloud Console:
   - OAuth client type: **Desktop app**
2. Download the `client_secret_*.json` file.
3. In Fylorra → `Settings` → `Cloud Sync`:
   - Set `Client secrets` to that JSON file
4. Click `Connect` (a browser window opens to finish sign-in).

## Token Storage

Tokens are stored locally in:
- `~/.fylorra/cloud_tokens.json`

This is not encrypted (MVP). A future version can use OS keyrings (DPAPI / Keychain / SecretService).
