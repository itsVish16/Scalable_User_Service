import pytest

from tests.conftest import login_user, signup_user


@pytest.mark.asyncio
async def test_health_live_endpoint(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_health_ready_endpoint(client):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dependencies"]["redis"] == "up"


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


@pytest.mark.asyncio
async def test_signup_validation_error(client):
    response = await client.post(
        "/api/v1/users/signup",
        json={
            "username": "ab",
            "email": "invalid@example.com",
            "full_name": "Test User",
            "password": "weak",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    response = await client.post(
        "/api/v1/users/login",
        json={
            "email": "doesnotexist@example.com",
            "password": "Password123",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_unverified_user_blocked(client):
    payload, _ = await signup_user(client)
    response = await login_user(client, payload["email"], payload["password"])
    assert response.status_code == 403
    assert response.json()["detail"] == "Please verify your email before logging in"


@pytest.mark.asyncio
async def test_signup_verify_login_and_get_me_flow(client, fake_redis):
    payload, _ = await signup_user(client, username_prefix="flowuser", verified=True, fake_redis=fake_redis)

    login_resp = await login_user(client, payload["email"], payload["password"])
    assert login_resp.status_code == 200

    token_data = login_resp.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"

    me_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert me_response.status_code == 200

    me_data = me_response.json()
    assert me_data["email"] == payload["email"]
    assert me_data["username"] == payload["username"]
    assert me_data["full_name"] == payload["full_name"]
    assert me_data["is_verified"] is True
    assert me_data["last_login_at"] is not None


@pytest.mark.asyncio
async def test_update_me_flow(client, fake_redis):
    payload, _ = await signup_user(client, username_prefix="updateuser", verified=True, fake_redis=fake_redis)

    login_resp = await login_user(client, payload["email"], payload["password"])
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    update_response = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"full_name": "After Update"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["full_name"] == "After Update"

    me_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["full_name"] == "After Update"


@pytest.mark.asyncio
async def test_forgot_and_reset_password_flow(client, fake_redis):
    payload, _ = await signup_user(client, username_prefix="resetuser", verified=True, fake_redis=fake_redis)

    forgot_response = await client.post(
        "/api/v1/users/forgot-password",
        json={"email": payload["email"]},
    )
    assert forgot_response.status_code == 200
    forgot_message = forgot_response.json()["message"]
    assert "Password reset OTP generated:" in forgot_message
    reset_otp = forgot_message.split("Password reset OTP generated: ", 1)[1]

    reset_response = await client.post(
        "/api/v1/users/reset-password",
        json={
            "email": payload["email"],
            "otp": reset_otp,
            "new_password": "NewPassword456",
        },
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["message"] == "Password reset successful"

    login_old = await login_user(client, payload["email"], payload["password"])
    assert login_old.status_code == 401

    login_new = await login_user(client, payload["email"], "NewPassword456")
    assert login_new.status_code == 200


@pytest.mark.asyncio
async def test_email_verification_flow(client):
    payload, signup_resp = await signup_user(client, username_prefix="verifyuser")

    signup_message = signup_resp.json()["message"]
    assert "Verification OTP:" in signup_message
    verification_token = signup_message.split("Verification OTP: ", 1)[1]

    verify_response = await client.post(
        "/api/v1/users/verify-email",
        json={"email": payload["email"], "token": verification_token},
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["message"] == "Email verified successfully"

    login_resp = await login_user(client, payload["email"], payload["password"])
    assert login_resp.status_code == 200

    token_data = login_resp.json()
    me_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["is_verified"] is True


@pytest.mark.asyncio
async def test_resend_verification_for_unverified_user(client):
    payload, _ = await signup_user(client, username_prefix="resenduser")

    resend_response = await client.post(
        "/api/v1/users/resend-verification",
        json={"email": payload["email"]},
    )
    assert resend_response.status_code == 200
    resend_message = resend_response.json()["message"]
    assert "Verification OTP generated:" in resend_message


@pytest.mark.asyncio
async def test_resend_verification_for_nonexistent_email(client):
    response = await client.post(
        "/api/v1/users/resend-verification",
        json={"email": "nobody@example.com"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_signup_email(client):
    payload, _ = await signup_user(client, username_prefix="dupuser")

    response = await client.post(
        "/api/v1/users/signup",
        json=payload,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_refresh_token_flow(client, fake_redis):
    payload, _ = await signup_user(client, username_prefix="refreshuser", verified=True, fake_redis=fake_redis)

    login_resp = await login_user(client, payload["email"], payload["password"])
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await client.post(
        "/api/v1/users/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()
    assert "refresh_token" in refresh_resp.json()

    reuse_resp = await client.post(
        "/api/v1/users/refresh",
        json={"refresh_token": refresh_token},
    )
    assert reuse_resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_refresh_token(client):
    response = await client.post(
        "/api/v1/users/refresh",
        json={"refresh_token": "invalid.token.here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_blacklists_token(client, fake_redis):
    payload, _ = await signup_user(client, username_prefix="logoutuser", verified=True, fake_redis=fake_redis)

    login_resp = await login_user(client, payload["email"], payload["password"])
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = await client.post(
        "/api/v1/users/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 200

    refresh_resp = await client.post(
        "/api/v1/users/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_account_lockout_after_failed_attempts(client, fake_redis):
    payload, _ = await signup_user(client, username_prefix="lockuser", verified=True, fake_redis=fake_redis)

    for _ in range(5):
        resp = await client.post(
            "/api/v1/users/login",
            json={"email": payload["email"], "password": "WrongPassword1"},
        )
        assert resp.status_code == 401

    locked_resp = await client.post(
        "/api/v1/users/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert locked_resp.status_code == 429
    assert "Too many failed login attempts" in locked_resp.json()["detail"]


@pytest.mark.asyncio
async def test_me_without_auth(client):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
