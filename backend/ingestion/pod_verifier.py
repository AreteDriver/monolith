"""POD (Provable Object Datatype) verification client.

Verifies CCP-signed data objects via the World API /v2/pod/verify endpoint.
POD objects are cryptographically signed by CCP's pod signing key and can be
verified to ensure data integrity and authenticity.

See: frontier.scetrov.live/develop/ for POD format specification.
"""

import logging

import httpx

logger = logging.getLogger(__name__)


class PodVerifier:
    """Verifies CCP-signed POD objects against the World API."""

    def __init__(self, base_url: str = "", timeout: int = 10):
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.timeout = timeout

    async def verify(self, pod_data: dict, client: httpx.AsyncClient) -> dict:
        """Verify a POD object against CCP's signing key.

        Args:
            pod_data: The POD object to verify (as received from ?format=pod endpoints).
            client: httpx async client.

        Returns:
            dict with 'valid' (bool) and 'details' (dict) keys.
        """
        if not self.base_url:
            return {"valid": False, "error": "no base_url configured"}

        try:
            resp = await client.post(
                f"{self.base_url}/v2/pod/verify",
                json=pod_data,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                result = resp.json()
                return {"valid": True, "details": result}
            else:
                return {
                    "valid": False,
                    "status_code": resp.status_code,
                    "error": resp.text[:200],
                }
        except httpx.HTTPError as e:
            logger.warning("POD verification failed: %s", e)
            return {"valid": False, "error": str(e)}

    async def fetch_pod(
        self, endpoint: str, client: httpx.AsyncClient, params: dict | None = None
    ) -> dict | None:
        """Fetch data from a World API endpoint in POD format.

        Appends ?format=pod to request POD-signed response.
        Returns the POD envelope or None on failure.
        """
        if not self.base_url:
            return None

        try:
            request_params = {"format": "pod"}
            if params:
                request_params.update(params)

            resp = await client.get(
                f"{self.base_url}{endpoint}",
                params=request_params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.warning("POD fetch from %s failed: %s", endpoint, e)
            return None
