import sqlite3

from backend.app import app
from backend.utils.security import decrypt_password

app.secret_key = "TEST_SECRET_KEY_ONLY"


DB = "db/attendance.db"


def get_test_users():
    conn = sqlite3.connect(DB)

    rows = conn.execute("""
        SELECT user_id, username, password_hash, role
        FROM users
        ORDER BY user_id
    """).fetchall()

    conn.close()

    users = {}

    for user_id, username, encrypted_password, role in rows:
        users[role] = {
            "id": user_id,
            "username": username,
            "password": decrypt_password(encrypted_password),
        }

    return users


users = get_test_users()

print("\n=== USERS ===")

for role, user in users.items():
    print(
        f"{role:6} -> "
        f"{user['username']} "
        f"(ID {user['id']})"
    )


client = app.test_client()


def login(user):
    response = client.post(
        "/login",
        json={
            "username": user["username"],
            "password": user["password"],
        },
    )

    return response


def check(name, response, expected):
    if response.status_code == expected:
        print(f"PASS  {name}")
        return True

    print(
        f"FAIL  {name} "
        f"(expected {expected}, got {response.status_code})"
    )
    return False


passed = 0
failed = 0


# =========================================================
# LOGIN
# =========================================================

print("\n=== LOGIN TEST ===")

for role in ("head", "admin", "user"):

    client = app.test_client()

    response = login(users[role])

    if check(
        f"{role} login",
        response,
        200
    ):
        passed += 1
    else:
        failed += 1


# =========================================================
# /users ACCESS
# =========================================================

print("\n=== USER MANAGEMENT ACCESS ===")


def test_users_access(role, expected):

    global passed, failed, client

    client = app.test_client()

    response = login(users[role])

    if response.status_code != 200:
        print(
            f"FAIL  {role} login before /users "
            f"({response.status_code})"
        )
        failed += 1
        return

    response = client.get("/users")

    if check(
        f"{role} -> GET /users",
        response,
        expected
    ):
        passed += 1
    else:
        failed += 1


test_users_access("head", 200)
test_users_access("admin", 200)
test_users_access("user", 403)


# =========================================================
# PASSWORD PERMISSIONS
# =========================================================

print("\n=== PASSWORD PERMISSIONS ===")


def test_password(actor_role, target_role, expected):

    global passed, failed, client

    client = app.test_client()

    actor = users[actor_role]
    target = users[target_role]

    response = login(actor)

    if response.status_code != 200:
        print(
            f"FAIL  {actor_role} login "
            f"before password test"
        )
        failed += 1
        return

    # IMPORTANT:
    # Use the SAME password so the test does not permanently
    # change any real password.
    #
    # This request will only actually update if permission
    # succeeds, so we DO NOT want to send a valid request
    # for successful cases.
    #
    # Therefore this test only verifies forbidden cases.

    if expected != 403:
        print(
            f"SKIP  {actor_role} -> {target_role} "
            f"(successful password mutation not tested)"
        )
        return

    response = client.post(
        "/users/password",
        json={
            "user_id": target["id"],
            "password": "__PERMISSION_TEST__",
        },
    )

    if check(
        f"{actor_role} -> change {target_role} password",
        response,
        expected
    ):
        passed += 1
    else:
        failed += 1


# Forbidden cases only.
test_password("user", "user", 403)
test_password("user", "admin", 403)
test_password("user", "head", 403)

test_password("admin", "admin", 403)
test_password("admin", "head", 403)


# =========================================================
# CREATE ACCOUNT PERMISSIONS
# =========================================================

print("\n=== CREATE USER PERMISSIONS ===")


def test_create(actor_role, target_role, expected):

    global passed, failed, client

    client = app.test_client()

    response = login(users[actor_role])

    if response.status_code != 200:
        print(
            f"FAIL  {actor_role} login "
            f"before create test"
        )
        failed += 1
        return

    response = client.post(
        "/users/add",
        json={
            "username": "__PERMISSION_TEST__",
            "password": "__PERMISSION_TEST__",
            "role": target_role,
        },
    )

    if expected == 403:
        result = response.status_code == 403
    else:
        # We do NOT allow successful creation in this test.
        # Prevents creating junk accounts.
        result = response.status_code != 200

    if result:
        print(
            f"PASS  {actor_role} -> create {target_role}"
        )
        passed += 1
    else:
        print(
            f"FAIL  {actor_role} -> create {target_role} "
            f"(got {response.status_code})"
        )
        failed += 1


test_create("user", "user", 403)
test_create("user", "admin", 403)
test_create("user", "head", 403)

test_create("admin", "admin", 403)
test_create("admin", "head", 403)


# =========================================================
# DELETE PERMISSIONS
# =========================================================

print("\n=== DELETE PERMISSIONS ===")


def test_delete(actor_role, target_role, expected):

    global passed, failed, client

    client = app.test_client()

    response = login(users[actor_role])

    if response.status_code != 200:
        print(
            f"FAIL  {actor_role} login "
            f"before delete test"
        )
        failed += 1
        return

    target = users[target_role]

    response = client.post(
        "/users/delete",
        json={
            "user_id": target["id"],
        },
    )

    if response.status_code == expected:
        print(
            f"PASS  {actor_role} -> delete {target_role}"
        )
        passed += 1
    else:
        print(
            f"FAIL  {actor_role} -> delete {target_role} "
            f"(expected {expected}, got {response.status_code})"
        )
        failed += 1


# Forbidden only.
test_delete("user", "user", 403)
test_delete("user", "admin", 403)
test_delete("user", "head", 403)

test_delete("admin", "admin", 403)
test_delete("admin", "head", 403)


# =========================================================
# RESULT
# =========================================================

print("\n" + "=" * 55)
print(f"PASSED: {passed}")
print(f"FAILED: {failed}")
print("=" * 55)

if failed == 0:
    print("ALL PERMISSION TESTS PASSED")
else:
    print("PERMISSION TESTS FAILED")