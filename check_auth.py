"""Sanity check: refresh token and fetch athlete profile."""

from auth import get_client


def main():
    client = get_client()
    athlete = client.get_athlete()
    print(f"Authenticated as: {athlete.firstname} {athlete.lastname}")
    print(f"  Athlete ID: {athlete.id}")
    print(f"  Username:   {athlete.username}")
    print(f"  City:       {athlete.city}")
    print("Auth working.")


if __name__ == "__main__":
    main()
