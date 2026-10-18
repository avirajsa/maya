
import asyncio
import getpass
import os
import uuid

import httpx


async def main():
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

    email = input("Your Supabase email: ").strip()
    password = getpass.getpass("Your Supabase password: ")

    async with httpx.AsyncClient(timeout=20) as client:
        login = await client.post(
            f"{url}/auth/v1/token?grant_type=password",
            headers={"apikey": key},
            json={"email": email, "password": password},
        )

        if login.status_code != 200:
            print(f"Supabase sign-in failed: HTTP {login.status_code}")
            print(login.text[:500])
            return

        token = login.json().get("access_token")
        if not token:
            print("No access token returned.")
            return

        print("Supabase sign-in successful.")

        response = await client.post(
            "http://127.0.0.1:8000/api/v1/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "message": "Hello Maya",
                "session_id": str(uuid.uuid4()),
                "voice_mode": False,
            },
        )

        print(f"Maya API: HTTP {response.status_code}")
        print(response.text[:1500])


if __name__ == "__main__":
    asyncio.run(main())

