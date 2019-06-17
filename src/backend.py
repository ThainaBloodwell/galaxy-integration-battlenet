import asyncio
import requests
import functools
import logging

logging.getLogger("urllib3").setLevel(logging.WARNING)

from http import HTTPStatus

from galaxy.api.errors import (
    AccessDenied, AuthenticationRequired,
    BackendTimeout, BackendNotAvailable, BackendError, NetworkError, UnknownError
)

from consts import FIREFOX_AGENT

class AccessTokenExpired(Exception):
    pass


class BackendClient(object):
    def __init__(self, plugin, authentication_client):
        self._plugin = plugin
        self._authentication_client = authentication_client

    async def _authenticated_request(self, method, url, data=None, json=True, headers=None, ignore_failure=False):
        try:
            return await self.do_request(method, url, data, json, headers, ignore_failure)
        except:
            try:
                await self.refresh_cookies()
                self._authentication_client.refresh_credentials()

            except Exception:
                self._plugin.lost_authentication()
                raise AccessDenied()
            return await self.do_request(method, url, data, json, headers, ignore_failure)

    async def do_request(self, method, url, data=None, json=True, headers=None, ignore_failure=False):
        loop = asyncio.get_event_loop()
        if not headers:
            headers = self._authentication_client.session.headers
        try:
            if data is None:
                data = {}
            params = {
                "method": method,
                "url": url,
                "data": data,
                "timeout": self._authentication_client.timeout,
                "headers": headers
            }
            try:
                response = await loop.run_in_executor(None, functools.partial(self._authentication_client.session.request, **params))
            except (requests.Timeout, requests.ConnectTimeout, requests.ReadTimeout):
                raise BackendTimeout()
            except requests.ConnectionError:
                raise NetworkError

            if not ignore_failure:
                if response.status_code == HTTPStatus.UNAUTHORIZED:
                    raise AuthenticationRequired()
                if response.status_code == HTTPStatus.FORBIDDEN:
                    raise AccessDenied()
                if response.status_code == HTTPStatus.SERVICE_UNAVAILABLE:
                    raise BackendNotAvailable()
                if response.status_code >= 500:
                    raise BackendError()
                if response.status_code >= 400:
                    raise UnknownError()

            if json:
                return response.json()
            else:
                return response

        except Exception as e:
            raise e

    async def refresh_cookies(self):
        headers = {
            'User-Agent': FIREFOX_AGENT
        }
        r = await self.do_request('GET', f"https://{self._authentication_client.region}.account.blizzard.com/games", json=False, headers=headers,
                                   ignore_failure=True)

        # verbose log responses in this function due to large probability of failure

        headers = {
            'User-Agent': FIREFOX_AGENT,
            "Referer": "https://account.blizzard.com/games",
        }
        r = await self.do_request("GET", f"https://{self._authentication_client.region}.account.blizzard.com/api/games-and-subs", json=False,
                                   headers=headers, ignore_failure=True)

        if r.status_code != 401:
            return

        headers = {
            'User-Agent': FIREFOX_AGENT,
            "Referer": f"https://{self._authentication_client.region}.account.blizzard.com/api/"
        }
        r = await self.do_request("GET", f"https://{self._authentication_client.region}.account.blizzard.com:443/oauth2/authorization/account-settings",
                                   json=False, headers=headers)

        headers = {
            'User-Agent': FIREFOX_AGENT
        }
        r = await self.do_request("GET", f"https://{self._authentication_client.region}.account.blizzard.com/api/games-and-subs", json=False,
                                   headers=headers)
        return

    async def get_user_info(self):
        url = f"https://{self._authentication_client.region}.battle.net/oauth/userinfo"
        return await self._authenticated_request("GET", url)

    async def get_account_details(self):
        details_url = f"https://{self._authentication_client.region}.account.blizzard.com/api/details"
        return await self.do_request("GET", details_url)

    async def get_owned_games(self):
        games_url = f"https://{self._authentication_client.region}.account.blizzard.com/api/games-and-subs"
        return await self._authenticated_request("GET", games_url)

    async def validate_access_token(self, access_token):
        # this is inconsistent with the documentation https://develop.battle.net/documentation/api-reference/oauth-api
        token_url = f"https://{self._authentication_client.region}.battle.net/oauth/check_token"
        # return await self.do_request()("POST", token_url, data={"token": access_token})
        return await self.do_request("POST", token_url, data={"token": access_token}, ignore_failure=True)

    async def get_sc2_player_data(self, account_id):
        url = f"https://{self._authentication_client.region}.api.blizzard.com/sc2/player/{account_id}"
        return await self._authenticated_request("GET", url)

    async def get_sc2_profile_data(self, region_id, realm_id, player_id):
        url = f"https://{self._authentication_client.region}.api.blizzard.com/sc2/profile/{region_id}/{realm_id}/{player_id}"
        return await self._authenticated_request("GET", url)

    async def get_wow_character_data(self):
        url = f"https://{self._authentication_client.region}.api.blizzard.com/wow/user/characters"
        return await self._authenticated_request("GET", url)

    async def get_wow_character_achievements(self,  realm, character_name):
        url = f"https://{self._authentication_client.region}.api.blizzard.com/wow/character/{realm.lower()}/{character_name}?fields=achievements"
        return await self.do_request("GET", url)
