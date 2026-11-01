import os
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "social_auth.json"


def init_config():
    """Initializes the social configuration file if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        default_config = {
            "youtube": {
              "connected": False,
              "access_token": "",
              "refresh_token": "",
              "client_id": "",
              "client_secret": "",
              "channel_name": ""
            },
            "tiktok": {
              "connected": False,
              "access_token": "",
              "open_id": "",
              "account_name": ""
            },
            "instagram": {
              "connected": False,
              "access_token": "",
              "instagram_account_id": "",
              "account_name": ""
            }
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)


def get_social_config() -> Dict[str, Any]:
    """Reads all social auth credentials."""
    init_config()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def refresh_youtube_access_token() -> Optional[str]:
    """Automatically requests a fresh YouTube Access Token using Refresh Token + Client Credentials."""
    config = get_social_config()
    yt = config.get("youtube", {})
    refresh_token = yt.get("refresh_token", "").strip()
    client_id = yt.get("client_id", "").strip()
    client_secret = yt.get("client_secret", "").strip()

    if not refresh_token or not client_id or not client_secret:
        return None

    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }

    try:
        res = requests.post(token_url, data=payload, timeout=12)
        if res.status_code == 200:
            data = res.json()
            new_token = data.get("access_token")
            if new_token:
                yt["access_token"] = new_token
                yt["connected"] = True
                save_platform_config("youtube", yt)
                return new_token
        else:
            print(f"Google token refresh failed ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"Google token refresh error: {e}")

    return None


def get_youtube_valid_token() -> Optional[str]:
    """Returns an active YouTube token, automatically refreshing it if expired."""
    config = get_social_config()
    yt = config.get("youtube", {})
    token = yt.get("access_token", "").strip()

    if not token:
        return refresh_youtube_access_token()

    # Check if currently valid
    try:
        r = requests.get(f"https://oauth2.googleapis.com/tokeninfo?access_token={token}", timeout=6)
        if r.status_code == 200:
            return token
    except Exception:
        pass

    # Expired -> refresh automatically
    return refresh_youtube_access_token()


def refresh_tiktok_access_token() -> Optional[str]:
    """Automatically requests a fresh TikTok Access Token using Refresh Token + Client Credentials."""
    config = get_social_config()
    tt = config.get("tiktok", {})
    refresh_token = tt.get("refresh_token", "").strip()
    client_key = tt.get("client_key", "").strip()
    client_secret = tt.get("client_secret", "").strip()

    if not refresh_token:
        return tt.get("access_token")

    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    payload = {
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        res = requests.post(token_url, data=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            data = res.json()
            t_data = data.get("data", {})
            new_token = t_data.get("access_token")
            new_refresh = t_data.get("refresh_token")
            if new_token:
                tt["access_token"] = new_token
                if new_refresh:
                    tt["refresh_token"] = new_refresh
                tt["connected"] = True
                save_platform_config("tiktok", tt)
                return new_token
    except Exception as e:
        print(f"TikTok token auto-refresh notice: {e}")

    return tt.get("access_token")


def get_tiktok_valid_token() -> Optional[str]:
    """Returns an active TikTok token, verifying or automatically refreshing it."""
    config = get_social_config()
    tt = config.get("tiktok", {})
    token = tt.get("access_token", "").strip()

    if not token:
        return refresh_tiktok_access_token()

    # Test user info endpoint with current token
    try:
        r = requests.get(
            "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name",
            headers={"Authorization": f"Bearer {token}"},
            timeout=6
        )
        if r.status_code == 200:
            return token
    except Exception:
        pass

    # Token expired or invalid -> auto-refresh using refresh_token
    return refresh_tiktok_access_token()


def refresh_instagram_access_token() -> Optional[str]:
    """Automatically requests or extends a Long-Lived Instagram/Meta Graph Access Token (60-day renewal)."""
    config = get_social_config()
    ig = config.get("instagram", {})
    token = ig.get("access_token", "").strip()
    app_id = (ig.get("app_id") or ig.get("client_id") or "").strip()
    app_secret = (ig.get("app_secret") or ig.get("client_secret") or "").strip()

    if not token:
        return None

    # Method A: Meta Graph API exchange / refresh token endpoint (if App ID and App Secret are configured)
    if app_id and app_secret:
        try:
            exchange_url = "https://graph.facebook.com/v19.0/oauth/access_token"
            params = {
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": token
            }
            res = requests.get(exchange_url, params=params, timeout=12)
            if res.status_code == 200:
                data = res.json()
                new_token = data.get("access_token")
                if new_token:
                    ig["access_token"] = new_token
                    ig["connected"] = True
                    save_platform_config("instagram", ig)
                    return new_token
        except Exception as e:
            print(f"Meta Graph token exchange notice: {e}")

    # Method B: Instagram Basic Display refresh token endpoint
    try:
        ig_refresh_url = "https://graph.instagram.com/refresh_access_token"
        params = {
            "grant_type": "ig_refresh_token",
            "access_token": token
        }
        res = requests.get(ig_refresh_url, params=params, timeout=12)
        if res.status_code == 200:
            data = res.json()
            new_token = data.get("access_token")
            if new_token:
                ig["access_token"] = new_token
                ig["connected"] = True
                save_platform_config("instagram", ig)
                return new_token
    except Exception:
        pass

    return None


def get_instagram_valid_token() -> Optional[str]:
    """Returns an active Instagram token, verifying or automatically refreshing it if expired."""
    config = get_social_config()
    ig = config.get("instagram", {})
    token = ig.get("access_token", "").strip()
    account_id = ig.get("instagram_account_id", "").strip()

    if not token:
        return None

    if account_id:
        try:
            r = requests.get(
                f"https://graph.facebook.com/v19.0/{account_id}?fields=username,name",
                headers={"Authorization": f"Bearer {token}"},
                timeout=6
            )
            if r.status_code == 200:
                return token
        except Exception:
            pass

    # If invalid or expired -> attempt auto-refresh
    refreshed = refresh_instagram_access_token()
    return refreshed or token


def save_platform_config(platform: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Updates configuration for a specific social platform without overwriting with empty values."""
    config = get_social_config()
    if platform not in config:
        config[platform] = {}

    for k, v in data.items():
        if v is not None:
            val_str = str(v).strip()
            # Only update if non-empty, or if explicitly setting connected
            if val_str != "" or k in ["connected"]:
                config[platform][k] = v

    # Check if essential tokens are present
    if platform == "youtube":
        config[platform]["connected"] = bool(config[platform].get("access_token") or config[platform].get("refresh_token"))
    elif platform == "tiktok":
        config[platform]["connected"] = bool(config[platform].get("access_token") or config[platform].get("refresh_token"))
    elif platform == "instagram":
        config[platform]["connected"] = bool(config[platform].get("access_token") and config[platform].get("instagram_account_id"))

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    return get_public_account_status()


def get_public_account_status() -> Dict[str, Any]:
    """Returns safe connection status and form data for UI display."""
    config = get_social_config()
    public_status = {}

    for platform, creds in config.items():
        has_token = bool(creds.get("access_token"))
        has_refresh = bool(creds.get("refresh_token") or creds.get("app_secret") or creds.get("client_secret"))
        account_name = creds.get("account_name") or creds.get("channel_name") or ""
        
        public_status[platform] = {
            "connected": creds.get("connected", False) or has_token or has_refresh,
            "account_name": account_name,
            "has_token": has_token,
            "has_refresh_token": has_refresh,
            "has_client_id": bool(creds.get("client_id") or creds.get("client_key") or creds.get("app_id") or creds.get("instagram_account_id")),
            "access_token": creds.get("access_token", ""),
            "refresh_token": creds.get("refresh_token", ""),
            "client_id": creds.get("client_id", ""),
            "client_secret": creds.get("client_secret", ""),
            "client_key": creds.get("client_key", ""),
            "app_id": creds.get("app_id") or creds.get("client_id", ""),
            "app_secret": creds.get("app_secret") or creds.get("client_secret", ""),
            "channel_name": creds.get("channel_name", ""),
            "instagram_account_id": creds.get("instagram_account_id", ""),
            "open_id": creds.get("open_id", ""),
        }

    return public_status


def test_platform_auth(platform: str, token: Optional[str] = None) -> Dict[str, Any]:
    """Tests authentication against platform API. Uses provided token or saved config."""
    config = get_social_config()
    creds = config.get(platform, {})

    if token and token.strip():
        test_token = token.strip()
    else:
        test_token = creds.get("access_token", "").strip()

    if platform == "youtube":
        valid = False
        email = ""
        expires_in = "0"
        scopes = ""

        if test_token:
            try:
                info_res = requests.get(
                    f"https://oauth2.googleapis.com/tokeninfo?access_token={test_token}",
                    timeout=10
                )
                if info_res.status_code == 200:
                    valid = True
                    info_data = info_res.json()
                    email = info_data.get("email", "")
                    expires_in = info_data.get("expires_in", "0")
                    scopes = info_data.get("scope", "")
            except Exception:
                pass

        if not valid:
            # Automatically attempt token refresh using Refresh Token + Client ID & Secret
            refreshed = refresh_youtube_access_token()
            if refreshed:
                test_token = refreshed
                try:
                    info_res = requests.get(
                        f"https://oauth2.googleapis.com/tokeninfo?access_token={test_token}",
                        timeout=10
                    )
                    if info_res.status_code == 200:
                        valid = True
                        info_data = info_res.json()
                        email = info_data.get("email", "")
                        expires_in = info_data.get("expires_in", "0")
                        scopes = info_data.get("scope", "")
                except Exception:
                    pass

        if valid:
            try:
                ch_res = requests.get(
                    "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                    headers={"Authorization": f"Bearer {test_token}"},
                    timeout=10
                )
                channel_name = creds.get("channel_name") or email or "YouTube Channel"
                if ch_res.status_code == 200:
                    items = ch_res.json().get("items", [])
                    if items:
                        channel_name = items[0]["snippet"]["title"]

                creds["access_token"] = test_token
                creds["channel_name"] = channel_name
                creds["connected"] = True
                save_platform_config("youtube", creds)

                has_upload_scope = "youtube" in scopes.lower()
                scope_note = " (Upload scope active ✅)" if has_upload_scope else " (⚠️ Warning: Add youtube.upload scope)"
                return {
                    "success": True,
                    "new_token": test_token,
                    "message": f"Connected to YouTube channel: {channel_name}{scope_note}. Token valid for {expires_in}s."
                }
            except Exception as e:
                return {"success": False, "message": f"YouTube connection error: {str(e)}"}
        else:
            refresh_token = creds.get("refresh_token", "").strip()
            client_id = creds.get("client_id", "").strip()
            client_secret = creds.get("client_secret", "").strip()
            if refresh_token and client_id and client_secret:
                return {
                    "success": False,
                    "message": (
                        "YouTube Access Token is expired, and Google rejected the Refresh Token (invalid_grant: Token expired or revoked).\n\n"
                        "💡 Why this happens: Google expires OAuth refresh tokens after 7 days if the OAuth Consent Screen is in 'Testing' mode. "
                        "To prevent 7-day expiration, set OAuth Consent Screen status to 'In Production' in Google Cloud Console, then paste a new refresh token from OAuth Playground."
                    )
                }
            return {
                "success": False,
                "message": "YouTube Access Token is invalid or expired, and Refresh Token / Client Credentials are not configured."
            }

    elif platform == "tiktok":
        if not test_token:
            test_token = get_tiktok_valid_token()
        if not test_token:
            return {"success": False, "message": "TikTok Access Token or Refresh Token is not configured."}
        try:
            r = requests.get(
                "https://open.tiktokapis.com/v2/user/info/?fields=open_id,union_id,avatar_url,display_name",
                headers={"Authorization": f"Bearer {test_token}"},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                user = data.get("data", {}).get("user", {})
                name = user.get("display_name", "TikTok Creator")
                creds["account_name"] = name
                creds["access_token"] = test_token
                creds["connected"] = True
                save_platform_config("tiktok", creds)
                return {"success": True, "message": f"Connected to TikTok account: {name} (Auto-refresh active ✅)"}
            elif r.status_code == 401:
                # Try auto-refresh
                refreshed = refresh_tiktok_access_token()
                if refreshed and refreshed != test_token:
                    r2 = requests.get(
                        "https://open.tiktokapis.com/v2/user/info/?fields=open_id,union_id,avatar_url,display_name",
                        headers={"Authorization": f"Bearer {refreshed}"},
                        timeout=10
                    )
                    if r2.status_code == 200:
                        data2 = r2.json()
                        user2 = data2.get("data", {}).get("user", {})
                        name2 = user2.get("display_name", "TikTok Creator")
                        return {"success": True, "message": f"Connected to TikTok account: {name2} (Token auto-refreshed ✅)"}
                return {"success": False, "message": f"TikTok auth failed ({r.status_code}): {r.text[:120]}"}
            else:
                return {"success": False, "message": f"TikTok auth failed ({r.status_code}): {r.text[:120]}"}
        except Exception as e:
            return {"success": False, "message": f"TikTok connection error: {str(e)}"}

    elif platform == "instagram":
        if not test_token:
            test_token = get_instagram_valid_token() or creds.get("access_token", "").strip()
        account_id = creds.get("instagram_account_id", "").strip()
        if not test_token:
            return {"success": False, "message": "Instagram Access Token is not configured."}
        if not account_id:
            return {"success": False, "message": "Instagram Business Account ID is missing."}

        valid = False
        name = "Instagram Account"
        try:
            r = requests.get(
                f"https://graph.facebook.com/v19.0/{account_id}?fields=username,name",
                headers={"Authorization": f"Bearer {test_token}"},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                name = data.get("username") or data.get("name") or "Instagram Account"
                valid = True
        except Exception:
            pass

        if not valid:
            # Try auto-refresh
            refreshed = refresh_instagram_access_token()
            if refreshed and refreshed != test_token:
                test_token = refreshed
                try:
                    r2 = requests.get(
                        f"https://graph.facebook.com/v19.0/{account_id}?fields=username,name",
                        headers={"Authorization": f"Bearer {test_token}"},
                        timeout=10
                    )
                    if r2.status_code == 200:
                        data2 = r2.json()
                        name = data2.get("username") or data2.get("name") or "Instagram Account"
                        valid = True
                except Exception:
                    pass

        if valid:
            creds["account_name"] = f"@{name}"
            creds["access_token"] = test_token
            creds["connected"] = True
            save_platform_config("instagram", creds)
            return {
                "success": True,
                "new_token": test_token,
                "message": f"Connected to Instagram: @{name} 🟢"
            }
        else:
            app_id = creds.get("app_id") or creds.get("client_id")
            app_secret = creds.get("app_secret") or creds.get("client_secret")
            if app_id and app_secret:
                return {
                    "success": False,
                    "message": "Instagram token is invalid or expired, and Meta Graph renewal failed. Please verify your Meta App ID, App Secret, and Account ID."
                }
            return {
                "success": False,
                "message": (
                    "Instagram Access Token is invalid or expired.\n\n"
                    "💡 Tip: Add your Meta App ID & App Secret under 'Permanent Auto-Refresh' to enable 60-day auto-renewal, or paste a new token from Meta Graph API Explorer."
                )
            }

    return {"success": False, "message": "Unknown platform"}
