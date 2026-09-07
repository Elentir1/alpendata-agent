import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from alpendata_api.models import Membership, Onboarding, Organization


def test_created_organization_is_committed_before_success_response(service, account):
    app, client = service
    user_id, headers = account("founder@example.com")
    observed = []

    async def application(scope, receive, send):
        async def checked_send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                body = json.loads(message["body"])
                organization_id = body["id"]
                with app.state.session_factory() as db:
                    observed.append(
                        db.get(Organization, organization_id) is not None
                        and db.get(Membership, (organization_id, user_id)) is not None
                        and db.scalar(
                            select(Onboarding).where(
                                Onboarding.organization_id == organization_id,
                                Onboarding.owner_id == user_id,
                            )
                        )
                        is not None
                    )
            await send(message)

        await app(scope, receive, checked_send)

    with TestClient(application, base_url=str(client.base_url)) as observer:
        response = observer.post("/api/organizations", headers=headers, json={"name": "Coaches"})
    assert response.status_code == 201
    assert observed == [True], "A success response must only expose committed organization data"
